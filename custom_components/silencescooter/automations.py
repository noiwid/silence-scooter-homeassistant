"""Automations for the Silence Scooter integration."""
import logging

from datetime import timedelta
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.components.number import SERVICE_SET_VALUE
from .const import (
    DOMAIN,
    CONF_CONFIRMATION_DELAY,
    CONF_PAUSE_MAX_DURATION,
    CONF_WATCHDOG_DELAY,
    CONF_CONNECTIVITY_LOSS_TOLERANCE,
    CONF_OUTDOOR_TEMP_SOURCE,
    CONF_OUTDOOR_TEMP_ENTITY,
    DEFAULT_CONFIRMATION_DELAY,
    DEFAULT_PAUSE_MAX_DURATION,
    DEFAULT_WATCHDOG_DELAY,
    DEFAULT_CONNECTIVITY_LOSS_TOLERANCE,
    DEFAULT_OUTDOOR_TEMP_SOURCE,
    DEFAULT_BATTERY_CAPACITY,
    OUTDOOR_TEMP_SOURCE_SCOOTER,
    OUTDOOR_TEMP_SOURCE_EXTERNAL,
    SENSOR_SCOOTER_AMBIENT_TEMP,
)
from homeassistant.util import dt as dt_util
from .helpers import (
    log_event, update_history, is_date_valid, get_valid_datetime,
    insert_imei_in_entity_id, get_history_file,
)
from .errors import ErrorCategory, ErrorSeverity, get_error_detector
from .record_time import usable_record_time

STARTUP_TIME = dt_util.utcnow()

_LOGGER = logging.getLogger(__name__)


def _tracking_key(imei: str) -> str:
    """Clé hass.data de l'état de suivi : une par scooter en multi-device."""
    return f"trip_tracking_state:{imei}" if imei else "trip_tracking_state"


def get_config_value(hass: HomeAssistant, key: str, default: any, imei: str = "") -> any:
    """Get configuration value from config_entry with fallback to default.

    En multi-device (imei fourni), lit la config de CE scooter ; sinon la
    config globale (la dernière entrée chargée écrasait celle des autres).
    """
    try:
        domain_data = hass.data.get(DOMAIN, {})
        config = domain_data.get("config", {})
        if imei:
            for value in domain_data.values():
                if isinstance(value, dict) and value.get("imei") == imei and "config" in value:
                    config = value["config"]
                    break
        return config.get(key, default)
    except Exception as e:
        _LOGGER.warning("Error getting config value %s: %s, using default %s", key, e, default)
        return default


def get_outdoor_temperature_entity_id(hass: HomeAssistant, imei: str = "", multi_device: bool = False) -> str:
    """Get the outdoor temperature sensor entity ID based on configuration.

    Returns:
        Entity ID of the temperature sensor to use (scooter or external)
    """
    temp_source = get_config_value(hass, CONF_OUTDOOR_TEMP_SOURCE, DEFAULT_OUTDOOR_TEMP_SOURCE, imei)

    if temp_source == OUTDOOR_TEMP_SOURCE_EXTERNAL:
        # Use external weather sensor if configured
        external_entity = get_config_value(hass, CONF_OUTDOOR_TEMP_ENTITY, "", imei)
        if external_entity:
            return external_entity
        else:
            _LOGGER.warning("External temperature source selected but no entity configured, falling back to scooter sensor")
            return insert_imei_in_entity_id(SENSOR_SCOOTER_AMBIENT_TEMP, imei, multi_device)
    else:
        # Use scooter ambient temperature sensor (default)
        return insert_imei_in_entity_id(SENSOR_SCOOTER_AMBIENT_TEMP, imei, multi_device)


def get_energy_gap(hass: HomeAssistant, imei: str = "", multi_device: bool = False) -> float | None:
    """Écart (kWh) entre le compteur brut du scooter (déchargé − régénéré) et
    sensor.scooter_energy_consumption. None si une des valeurs est illisible."""
    values = []
    for base in (
        "sensor.silence_scooter_discharged_energy",
        "sensor.silence_scooter_regenerated_energy",
        "sensor.scooter_energy_consumption",
    ):
        state = hass.states.get(insert_imei_in_entity_id(base, imei, multi_device))
        try:
            values.append(float(state.state))
        except (AttributeError, ValueError, TypeError):
            return None
    return values[0] - values[1] - values[2]


def get_sensor_float_value(hass: HomeAssistant, entity_id: str, default: float = 0.0, fallback_entity: str | None = None) -> float:
    """Safely get float value from sensor state.

    Args:
        hass: HomeAssistant instance
        entity_id: Entity ID to read
        default: Default value if sensor unavailable or invalid
        fallback_entity: Optional entity to try if primary is unavailable

    Returns:
        Float value from sensor or default
    """
    state = hass.states.get(entity_id)
    if state and state.state not in ["unknown", "unavailable"]:
        try:
            return float(state.state)
        except (ValueError, TypeError):
            pass
    if fallback_entity:
        fb_state = hass.states.get(fallback_entity)
        if fb_state and fb_state.state not in ["unknown", "unavailable"]:
            try:
                return float(fb_state.state)
            except (ValueError, TypeError):
                pass
    return default


async def set_writable_sensor_value(hass: HomeAssistant, entity_id: str, value: float) -> None:
    """Set value for a writable sensor.

    Args:
        hass: HomeAssistant instance
        entity_id: Sensor entity ID
        value: Value to set
    """
    sensor = hass.data.get(DOMAIN, {}).get("sensors", {}).get(entity_id)
    if sensor and hasattr(sensor, "async_set_native_value"):
        await sensor.async_set_native_value(value)
    else:
        _LOGGER.error("Writable sensor %s not found or not writable!", entity_id)
        _LOGGER.error("Available sensors: %s", list(hass.data.get(DOMAIN, {}).get("sensors", {}).keys()))


def determine_trip_end_timestamp(hass: HomeAssistant, imei: str = "", multi_device: bool = False) -> str:
    """Determine the best available end timestamp for the trip.

    Args:
        hass: HomeAssistant instance
        imei: IMEI of the scooter (optional for single-device)
        multi_device: Whether multi-device mode is enabled

    Priority:
    1. datetime.scooter_end_time (if already set and valid)
    2. datetime.scooter_last_moving_time (last time scooter was moving)
    3. sensor.silence_scooter_last_update (if scooter unavailable)
    4. Current time (fallback)

    Returns:
        Timestamp string in format "YYYY-MM-DD HH:MM:SS"
    """
    def entity_id(base: str) -> str:
        from .helpers import insert_imei_in_entity_id
        return insert_imei_in_entity_id(base, imei, multi_device)

    end_time_current = hass.states.get(entity_id("datetime.scooter_end_time"))
    if end_time_current and end_time_current.state not in ["unknown", "unavailable"]:
        try:
            from .helpers import is_date_valid, get_valid_datetime
            if is_date_valid(end_time_current.state):
                end_dt = get_valid_datetime(end_time_current.state)
                if end_dt and end_dt > dt_util.now() - timedelta(hours=24):
                    _LOGGER.info("Using existing valid end_time: %s", end_time_current.state)
                    return end_time_current.state
        except Exception as e:
            _LOGGER.debug("Could not use end_time: %s", e)

    last_moving = hass.states.get(entity_id("datetime.scooter_last_moving_time"))
    if last_moving and last_moving.state not in ["unknown", "unavailable"]:
        try:
            from .helpers import is_date_valid
            # last_moving_time n'est écrit qu'à l'arrêt (is_moving on→off). Si
            # le scooter est encore en marche (arrêt manuel), la valeur date
            # d'un arrêt PRÉCÉDENT : durée nulle ou tronquée. On retombe alors
            # sur l'heure courante.
            moving_st = hass.states.get(entity_id("sensor.scooter_is_moving"))
            still_moving = moving_st is not None and moving_st.state == "on"
            if is_date_valid(last_moving.state) and not still_moving:
                _LOGGER.info("Using last_moving_time: %s", last_moving.state)
                return last_moving.state
        except Exception as e:
            _LOGGER.debug("Could not use last_moving_time: %s", e)

    # NOTE: c'était sensor.scooter_status, une entité qui n'existe nulle part —
    # la priorité 3 (last_update quand le scooter est injoignable) ne se
    # déclenchait jamais. Le bon capteur est le status MQTT brut.
    scooter_status = hass.states.get(entity_id("sensor.silence_scooter_status"))
    if scooter_status and scooter_status.state in ["unknown", "unavailable"]:
        last_up = hass.states.get(entity_id("sensor.silence_scooter_last_update"))
        if last_up and last_up.state not in ["unknown", "unavailable"]:
            try:
                from .helpers import is_date_valid
                if is_date_valid(last_up.state):
                    _LOGGER.info("Using last_update (scooter unavailable): %s", last_up.state)
                    return last_up.state
            except Exception as e:
                _LOGGER.warning("last_update non valide: %s", e)

    # Trajet daté à l'heure de mesure (voir get_record_time) : la fin aussi,
    # sinon un arrêt manuel scooter en marche rallonge le trajet du retard.
    if hass.data.get(DOMAIN, {}).get(_tracking_key(imei), {}).get("start_uses_record_time"):
        record_st = hass.states.get(entity_id("sensor.silence_scooter_record_time"))
        start_st = hass.states.get(entity_id("datetime.scooter_start_time"))
        record_dt = usable_record_time(
            record_st.state if record_st else None, dt_util.now(), timedelta(hours=24),
            get_valid_datetime(start_st.state) if start_st else None,
        )
        if record_dt is not None:
            _LOGGER.info("Using record time: %s", record_dt.isoformat())
            return record_dt.isoformat()

    current_time = dt_util.now().isoformat()
    _LOGGER.info("Using current time: %s", current_time)
    return current_time


async def calculate_trip_duration(
    hass: HomeAssistant,
    start_time_str: str,
    end_time_str: str,
    imei: str = "",
    multi_device: bool = False,
) -> float:
    """Calculate trip duration in minutes (net of pauses).

    Args:
        hass: HomeAssistant instance
        start_time_str: Start time string
        end_time_str: End time string
        imei: IMEI of the scooter (optional for single-device)
        multi_device: Whether multi-device mode is enabled

    Returns:
        Trip duration in minutes (0 if calculation fails)
    """
    try:
        from .helpers import is_date_valid, get_valid_datetime

        def entity_id(base: str) -> str:
            from .helpers import insert_imei_in_entity_id
            return insert_imei_in_entity_id(base, imei, multi_device)

        dt_start = None
        if is_date_valid(start_time_str):
            dt_start = get_valid_datetime(start_time_str)
        else:
            dt_start = dt_util.parse_datetime(start_time_str)
            if dt_start and dt_start.tzinfo is None:
                dt_start = dt_util.as_local(dt_start)

        dt_end = None
        if is_date_valid(end_time_str):
            dt_end = get_valid_datetime(end_time_str)
        else:
            dt_end = dt_util.parse_datetime(end_time_str)
            if dt_end and dt_end.tzinfo is None:
                dt_end = dt_util.as_local(dt_end)

        if not (dt_start and dt_end and
                dt_start.year > 2000 and dt_end.year > 2000 and
                dt_end >= dt_start):
            _LOGGER.warning("Invalid dates for duration calculation: start=%s, end=%s", dt_start, dt_end)
            return 0.0

        delta = dt_end - dt_start
        total_duration = delta.total_seconds() / 60
        pause_duration = get_sensor_float_value(hass, entity_id("number.scooter_pause_duration"), 0.0)
        # Au dixième : l'arrondi à la minute donnait « 3 km en 1 min = 180 km/h »
        # et faisait rejeter de vrais petits trajets.
        trip_duration = max(0, round(total_duration - pause_duration, 1))

        if trip_duration > 1440:
            _LOGGER.warning("Trip duration too long (%.1f min > 24h), capped at 24h", trip_duration)
            trip_duration = 1440
        elif trip_duration < 0:
            _LOGGER.error("Negative trip duration calculated, reset to 0")
            trip_duration = 0

        _LOGGER.info("Trip duration: total=%.1f min, pauses=%.1f min, net=%.1f min",
                    total_duration, pause_duration, trip_duration)

        return float(trip_duration)

    except Exception as e:
        _LOGGER.error("Error calculating trip duration: %s (start=%s, end=%s)", e, start_time_str, end_time_str)
        return 0.0


async def update_trip_statistics(
    hass: HomeAssistant,
    distance: float,
    batt_consumption: float,
    imei: str = "",
    multi_device: bool = False,
) -> None:
    """Update cumulative trip statistics.

    Args:
        hass: HomeAssistant instance
        distance: Trip distance in km
        batt_consumption: Battery consumption in %
        imei: IMEI of the scooter (optional for single-device)
        multi_device: Whether multi-device mode is enabled
    """
    def entity_id(base: str) -> str:
        from .helpers import insert_imei_in_entity_id
        return insert_imei_in_entity_id(base, imei, multi_device)

    NUMBER_TRACKED_DISTANCE = entity_id("number.scooter_tracked_distance")
    NUMBER_TRACKED_BATT_USED = entity_id("number.scooter_tracked_battery_used")

    # Update tracked_distance
    tracked_dist = get_sensor_float_value(hass, NUMBER_TRACKED_DISTANCE, 0.0)
    tracked_dist += distance
    await hass.services.async_call(
        "number",
        SERVICE_SET_VALUE,
        {
            "entity_id": NUMBER_TRACKED_DISTANCE,
            "value": tracked_dist
        },
        blocking=True
    )

    # Update tracked_battery_used
    tracked_batt = get_sensor_float_value(hass, NUMBER_TRACKED_BATT_USED, 0.0)
    tracked_batt += batt_consumption
    await hass.services.async_call(
        "number",
        SERVICE_SET_VALUE,
        {
            "entity_id": NUMBER_TRACKED_BATT_USED,
            "value": tracked_batt
        },
        blocking=True
    )

    # Update energy_consumption_base
    energy_val = get_sensor_float_value(hass, entity_id("sensor.scooter_energy_consumption"), 0.0)

    # Capacité réelle de la batterie : énergie sortie pendant le trajet et %
    # consommés, cumulés avec un oubli exponentiel (0,9 par trajet, soit une
    # dizaine de trajets de mémoire). Le SoC est entier : un trajet seul est
    # imprécis, d'où le cumul et le seuil de 5 %. Une estimation hors de
    # 3-7 kWh (énergie d'un trajet non suivi comptée ici, SoC de départ
    # périmé) est écartée.
    start_energy = hass.data.get(DOMAIN, {}).get(_tracking_key(imei), {}).get("energy_at_start")
    trip_energy = energy_val - start_energy if start_energy else 0.0
    if batt_consumption >= 5 and trip_energy > 0 and 3.0 <= trip_energy / batt_consumption * 100 <= 7.0:
        for base, added in (
            ("number.scooter_capacity_energy_sum", trip_energy),
            ("number.scooter_capacity_soc_sum", batt_consumption),
        ):
            await hass.services.async_call(
                "number",
                SERVICE_SET_VALUE,
                {
                    "entity_id": entity_id(base),
                    "value": round(get_sensor_float_value(hass, entity_id(base), 0.0) * 0.9 + added, 3),
                },
                blocking=True
            )

    # Le template scooter_energy_consumption refuse toute hausse > 5.6 kWh
    # (pic du compteur brut). Un vrai retard plus grand (HA ou serveur coupés
    # plusieurs jours) resterait donc figé pour toujours. Si l'écart avec le
    # compteur brut était déjà là au départ ET l'est encore à l'arrivée, ce
    # n'est pas un pic d'une trame : on écrit la valeur brute dans la base,
    # que le template rattrape (base > capteur) au relevé suivant.
    gap_start = hass.data.get(DOMAIN, {}).get(_tracking_key(imei), {}).get("energy_gap_at_start")
    gap_end = get_energy_gap(hass, imei, multi_device)
    if (
        gap_start is not None and gap_end is not None
        and min(gap_start, gap_end) > DEFAULT_BATTERY_CAPACITY
    ):
        _LOGGER.warning(
            "Energy counter %.1f kWh behind the scooter for a whole trip: catching up (%.3f -> %.3f kWh)",
            gap_end, energy_val, energy_val + gap_end,
        )
        energy_val += gap_end
    await hass.services.async_call(
        "number",
        SERVICE_SET_VALUE,
        {
            "entity_id": entity_id("number.scooter_energy_consumption_base"),
            "value": energy_val
        },
        blocking=True
    )


# ============================================================================
# END OF HELPER FUNCTIONS
# ============================================================================

# is_date_valid and get_valid_datetime are imported from helpers.py


async def async_setup_automations(
    hass: HomeAssistant,
    config_entry=None,
    imei: str = "",
    multi_device: bool = False,
) -> list:
    """Installe toutes les automatisations (ex-YAML) pour Silence Scooter.

    Args:
        hass: HomeAssistant instance
        config_entry: ConfigEntry for this scooter (optional for single-device)
        imei: IMEI of the scooter (optional for single-device)
        multi_device: Whether to use multi-device entity naming

    Returns:
        List of cancel listeners for cleanup
    """

    # Helper to generate entity IDs with IMEI suffix
    def entity_id(base: str) -> str:
        """Generate entity ID for this scooter's IMEI."""
        from .helpers import insert_imei_in_entity_id
        # Use insert_imei_in_entity_id to place IMEI before last element if multi_device
        return insert_imei_in_entity_id(base, imei, multi_device)

    # Entités concernées - now generated with IMEI suffix
    SENSOR_IS_MOVING = entity_id("sensor.scooter_is_moving")
    SENSOR_TRIP_STATUS = entity_id("sensor.scooter_trip_status")
    INPUT_DT_LAST_MOVING = entity_id("datetime.scooter_last_moving_time")
    SWITCH_STOP_NOW = entity_id("switch.stop_trip_now")

    SENSOR_SCOOTER_SPEED = entity_id("sensor.silence_scooter_speed")
    SENSOR_BATT_SOC = entity_id("sensor.silence_scooter_battery_soc")

    # Pour la logique "Last start"
    INPUT_DT_END_TIME = entity_id("datetime.scooter_end_time")
    SENSOR_MAX_SPEED = entity_id("sensor.scooter_last_trip_max_speed")  # Writable sensor
    NUMBER_ODO_DEBUT = entity_id("number.scooter_odo_debut")
    INPUT_DT_START_TIME = entity_id("datetime.scooter_start_time")
    NUMBER_BATT_SOC_DEBUT = entity_id("number.scooter_battery_soc_debut")

    # Entités gérées par la logique stop_trip
    NUMBER_ODO_FIN = entity_id("number.scooter_odo_fin")
    SENSOR_LAST_TRIP_DISTANCE = entity_id("sensor.scooter_last_trip_distance")  # Writable sensor
    SENSOR_LAST_TRIP_DURATION = entity_id("sensor.scooter_last_trip_duration")  # Writable sensor
    SENSOR_LAST_TRIP_AVG_SPEED = entity_id("sensor.scooter_last_trip_avg_speed")  # Writable sensor
    SENSOR_LAST_TRIP_MAX_SPEED = entity_id("sensor.scooter_last_trip_max_speed")  # Writable sensor
    SENSOR_LAST_TRIP_BATT_CONSUMPTION = entity_id("sensor.scooter_last_trip_battery_consumption")  # Writable sensor
    NUMBER_BATT_SOC_FIN = entity_id("number.scooter_battery_soc_fin")
    NUMBER_TRACKED_DISTANCE = entity_id("number.scooter_tracked_distance")
    NUMBER_TRACKED_BATT_USED = entity_id("number.scooter_tracked_battery_used")
    SENSOR_SCOOTER_ODO = entity_id("sensor.silence_scooter_odo")
    SENSOR_SCOOTER_STATUS = entity_id("sensor.silence_scooter_status")
    SENSOR_ENERGY_CONSUMPTION = entity_id("sensor.scooter_energy_consumption")
    NUMBER_ENERGY_BASE = entity_id("number.scooter_energy_consumption_base")

    # Nouvelles constantes ajoutées
    SENSOR_SCOOTER_LAST_UPDATE = entity_id("sensor.silence_scooter_last_update")
    SENSOR_SCOOTER_RECORD_TIME = entity_id("sensor.silence_scooter_record_time")

    def get_record_time(max_age, not_before=None):
        """Heure de MESURE du dernier relevé du scooter, ou None.

        Publiée par le serveur (topic record-time, serveur >= 2026-11). Quand
        la liaison est mauvaise, le module livre ses relevés par paquets avec
        5 à 10 min de retard : dater le départ et l'arrivée à l'heure de
        réception a enregistré un trajet de 22 min comme 29,5 min
        (2026-11-10). Sans ce capteur (ancien serveur), on retombe sur
        l'heure de réception, comme avant.
        """
        state = hass.states.get(SENSOR_SCOOTER_RECORD_TIME)
        return usable_record_time(
            state.state if state is not None else None, dt_util.now(), max_age, not_before
        )

    BINARY_SENSOR_BATTERY_IN = entity_id("binary_sensor.silence_scooter_battery_in")

    #
    # Dictionnaire pour stocker les tâches planifiées
    # - nécessaire pour la gestion du "for: 00:02:00" (2 minutes)
    #
    scheduled_tasks = {}

    # Shared trip-tracking state, stored in hass.data so that functions
    # defined OUTSIDE setup_automations (like do_stop_trip) can access it.
    # The closure-based approach alone fails because do_stop_trip is a
    # module-level function; it cannot capture local variables here.
    #
    # Keys:
    #   last_trip_start_monotonic: monotonic time() of the last trip start
    #     (used by the ODO/battery tracking handlers to skip the stale-
    #     value repair during the first 5s to avoid a race with
    #     _do_last_start() writing odo_debut).
    #   odo_tracking_fired / battery_tracking_fired: set by the tracking
    #     handlers on their first firing during the current trip. Reset at
    #     trip start. do_stop_trip reads them to distinguish "tracked
    #     value" from "never tracked".
    #   last_telemetry_utc: horodatage UTC du dernier événement MQTT reçu
    #     par les handlers de tracking. Sert de référence de fraîcheur au
    #     watchdog quand sensor.silence_scooter_last_update est
    #     unknown/unavailable (garage, restart HA).
    hass.data.setdefault(DOMAIN, {}).setdefault(
        _tracking_key(imei),
        {
            "last_trip_start_monotonic": None,
            "odo_tracking_fired": False,
            "battery_tracking_fired": False,
            "last_telemetry_utc": None,
            "pause_is_connectivity_loss": False,
        },
    )
    _tracking_state = hass.data[DOMAIN][_tracking_key(imei)]

    # Backwards-compatible local dict wrappers so the existing closures
    # below keep working without change. They all write/read via the
    # shared hass.data dict.
    class _StateRef:
        def __init__(self, key):
            self._key = key

        def get(self, default=None):
            return _tracking_state.get(self._key, default)

        def __setitem__(self, k, v):
            assert k == "value"
            _tracking_state[self._key] = v

        def __getitem__(self, k):
            assert k == "value"
            return _tracking_state.get(self._key)

    last_trip_start_monotonic = _StateRef("last_trip_start_monotonic")
    odo_tracking_fired = _StateRef("odo_tracking_fired")
    battery_tracking_fired = _StateRef("battery_tracking_fired")

    #
    # Fonction helper pour vérifier si un trajet est en cours
    #
    def is_trip_active():
        """Vérifie si un trajet est actuellement actif."""
        end_time_st = hass.states.get(INPUT_DT_END_TIME)
        if not end_time_st or end_time_st.state in ["unknown", "unavailable"]:
            return False
        
        # Un trajet est actif si end_time est 1969/1970 OU si c'est dans le futur
        if not is_date_valid(end_time_st.state):
            # Vérifier que le trajet n'est pas trop vieux (>24h)
            start_time_st = hass.states.get(INPUT_DT_START_TIME)
            if start_time_st and is_date_valid(start_time_st.state):
                start_dt = get_valid_datetime(start_time_st.state)
                if start_dt:
                    # Si le trajet a commencé il y a plus de 24h, il n'est plus actif
                    if (dt_util.now() - start_dt).total_seconds() > 86400:
                        _LOGGER.warning("⚠️ Trajet bloqué détecté (>24h), nettoyage nécessaire")
                        return False
            return True
        
        try:
            end_dt = dt_util.parse_datetime(end_time_st.state)
            # Trajet actif si la date de fin est dans le futur
            return end_dt and dt_util.as_local(end_dt) > dt_util.now()
        except (ValueError, TypeError, AttributeError):
            return False

    #
    # 0. "Scooter - Auto-initialisation de la base d'énergie"
    #    La première fois qu'on reçoit des données valides du scooter,
    #    on capture la valeur actuelle comme baseline
    #
    #
    # 0bis. Marqueur de fraîcheur de la télémétrie
    #    Toute trame MQTT du scooter (quel que soit le capteur) rafraîchit
    #    last_telemetry_utc. C'est LE signal qui distingue une coupure réseau
    #    d'un arrêt réel : sans expire_after, les capteurs MQTT conservent
    #    indéfiniment leur dernière valeur et ne passent jamais unavailable.
    #
    @callback
    def handle_telemetry_seen(event):
        new_state = event.data.get("new_state")
        if not new_state or new_state.state in ("unknown", "unavailable"):
            return
        _tracking_state["last_telemetry_utc"] = dt_util.utcnow()

    remove_telemetry_seen = async_track_state_change_event(
        hass,
        [
            SENSOR_SCOOTER_STATUS,
            SENSOR_SCOOTER_SPEED,
            SENSOR_SCOOTER_ODO,
            SENSOR_BATT_SOC,
            SENSOR_SCOOTER_LAST_UPDATE,
        ],
        handle_telemetry_seen,
    )

    @callback
    def handle_energy_baseline_init(event):
        """Auto-initialize energy consumption baseline on first valid MQTT data."""
        new_state = event.data.get("new_state")
        if not new_state or new_state.state in ("unknown", "unavailable"):
            return

        # Vérifier si la base est déjà initialisée
        base_state = hass.states.get(NUMBER_ENERGY_BASE)
        if not base_state:
            return

        try:
            base_value = float(base_state.state)
        except (ValueError, TypeError):
            base_value = 0

        # Si la base n'est pas à 0, c'est qu'elle est déjà initialisée
        if base_value != 0:
            _LOGGER.debug("Energy baseline already initialized (%s kWh), skipping", base_value)
            return

        # Récupérer les valeurs discharged et regenerated
        discharged_state = hass.states.get(entity_id("sensor.silence_scooter_discharged_energy"))
        regenerated_state = hass.states.get(entity_id("sensor.silence_scooter_regenerated_energy"))

        if not discharged_state or not regenerated_state:
            return

        if discharged_state.state in ("unknown", "unavailable") or \
           regenerated_state.state in ("unknown", "unavailable"):
            return

        try:
            discharged = float(discharged_state.state)
            regenerated = float(regenerated_state.state)

            # Si les valeurs sont valides (au moins une > 0), initialiser la base
            if discharged > 0 or regenerated > 0:
                baseline = discharged - regenerated
                _LOGGER.info("🎯 Auto-initializing energy baseline: %.3f kWh (discharged: %.3f - regenerated: %.3f)",
                            baseline, discharged, regenerated)

                hass.async_create_task(
                    hass.services.async_call(
                        "number",
                        SERVICE_SET_VALUE,
                        {
                            "entity_id": NUMBER_ENERGY_BASE,
                            "value": baseline
                        },
                        blocking=True
                    )
                )
        except (ValueError, TypeError) as e:
            _LOGGER.debug("Could not initialize baseline: %s", e)

    # Écouter les changements sur les sensors d'énergie pour l'initialisation automatique
    remove_energy_baseline_init = async_track_state_change_event(
        hass,
        [entity_id("sensor.silence_scooter_discharged_energy"), entity_id("sensor.silence_scooter_regenerated_energy")],
        handle_energy_baseline_init
    )

    #
    # 1. "Scooter - Tracker dernier mouvement"
    #    Surveiller sensor.scooter_is_moving => ON -> OFF
    #
    @callback
    def handle_tracker_dernier_mouvement(event):
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if not old_state or not new_state:
            return

        _LOGGER.debug(
            "▶ handle_tracker_dernier_mouvement : %s → %s (changed %s/%s → %s/%s)",
            old_state.state, new_state.state,
            old_state.last_changed, old_state.last_updated,
            new_state.last_changed, new_state.last_updated
        )

         # Traiter on→off ET on→unavailable/unknown
        if old_state.state == "on" \
            and new_state.state in ("off", "unavailable", "unknown"):            
            # => datetime.scooter_last_moving_time = now()
            hass.async_create_task(_update_last_moving_time())

    async def _update_last_moving_time():
        # Heure de mesure du dernier relevé si le serveur la publie et qu'elle
        # appartient au trajet en cours (pas antérieure au départ).
        start_st = hass.states.get(INPUT_DT_START_TIME)
        start_dt = get_valid_datetime(start_st.state) if start_st else None
        # Une seule horloge par trajet : l'heure de mesure ne date l'arrivée
        # que si elle a daté le départ. Mélanger (départ à l'heure de
        # réception, arrivée à l'heure de mesure) raccourcirait le trajet du
        # retard du module.
        record_dt = None
        if _tracking_state.get("start_uses_record_time"):
            record_dt = get_record_time(timedelta(hours=24), not_before=start_dt)

        # Use the scooter's last MQTT update timestamp instead of now()
        # This avoids adding ~5min of artificial delay in the garage scenario
        # where the scooter goes unavailable without sending status=0
        last_update_state = hass.states.get(SENSOR_SCOOTER_LAST_UPDATE)
        if record_dt is not None:
            timestamp_str = record_dt.isoformat()
            _LOGGER.info("Last moving time = record time: %s", timestamp_str)
        elif last_update_state and last_update_state.state not in ["unknown", "unavailable"]:
            try:
                last_update_dt = dt_util.parse_datetime(last_update_state.state)
                if last_update_dt and last_update_dt.year > 2000:
                    timestamp_str = dt_util.as_local(last_update_dt).isoformat()
                    _LOGGER.info("Last moving time = last MQTT update: %s", timestamp_str)
                else:
                    timestamp_str = dt_util.now().isoformat()
                    _LOGGER.info("Last moving time = now() (invalid last_update): %s", timestamp_str)
            except (ValueError, TypeError):
                timestamp_str = dt_util.now().isoformat()
        else:
            timestamp_str = dt_util.now().isoformat()
            _LOGGER.debug("Last moving time = now() (no last_update available): %s", timestamp_str)

        await hass.services.async_call(
            "datetime",
            "set_value",
            {
                "entity_id": INPUT_DT_LAST_MOVING,
                "datetime": timestamp_str
            },
            blocking=True
        )

    remove_tracker_dernier_mouvement = async_track_state_change_event(
        hass, [SENSOR_IS_MOVING], handle_tracker_dernier_mouvement
    )

    #
    # 2. "Scooter - Démarrer le timer quand le scooter s'arrête" 
    #    => sensor.scooter_trip_status passe à off, PENDANT 2 minutes
    #
    @callback
    def handle_trip_status_off(event):
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if not old_state or not new_state:
            return

        from datetime import timedelta
        from homeassistant.util.dt import now as ha_now

        # ⚠️ On ignore uniquement les events de "off" déclenchés dans les 10s après démarrage HA
        if (dt_util.utcnow() - STARTUP_TIME) < timedelta(seconds=10):
            _LOGGER.debug("🔄 Ignoring trip_status_off due to HA recent startup")
            return

        # 🪵 Log complet pour debug
        _LOGGER.info("🪵 TRIP STATUS CHANGE: %s → %s (time=%s)", 
                     old_state.state, new_state.state, new_state.last_changed)

        # 🚦 Transition vers off/unavailable → on déclenche l'arrêt différé
        if old_state.state == "on" and new_state.state in ("off", "unavailable", "unknown"):

            # Vérifier si un trajet est en cours
            if not is_trip_active():
                _LOGGER.info("⚠️ Pas de trajet actif, ignoring trip_status→off")
                return

            # CORRECTION: Vérifier le statut réel du scooter
            raw_state = hass.states.get(SENSOR_SCOOTER_STATUS)
            _LOGGER.info("▶ Scooter raw status: %s", raw_state.state if raw_state else "MISSING")
            
            # Vérifier si la batterie est présente
            battery_in = hass.states.get(BINARY_SENSOR_BATTERY_IN)
            battery_present = battery_in and battery_in.state == "on"
            
            _LOGGER.info("▶ Battery present: %s", battery_present)

            # Always go through the delayed-stop path (2 min confirmation +
            # 5 min tolerance), matching the v1.0.4 behaviour that ran for
            # months without issue. Earlier releases shortcut the stop on
            # status=0 or "battery removed", but MQTT glitches can produce
            # those states transiently while still riding — and the delayed
            # path already cancels itself correctly if the scooter really
            # restarts. Cost of a false delayed stop: ~7 minutes of "trip
            # still active" after the real shutdown. Cost of a false
            # immediate stop: a legitimate 30-minute ride cut in half.

            # Perte de connectivité vs arrêt réel (status=0, batterie
            # retirée…). Les deux cas ne doivent PAS avoir la même échéance :
            # en perte de signal, le scooter roule peut-être encore (coupure
            # GSM, tunnel) et seule la tolérance (pause_max_duration) doit
            # décider. Sinon le délai de confirmation (2 min) clôture toujours
            # en premier et scinde les trajets réels
            # (2026-07-24 : commute de 12 km enregistré en 2×6 km).
            #
            # ⚠️ Ne PAS se fier au seul état unknown/unavailable du capteur :
            # sans `expire_after` côté MQTT, un capteur garde indéfiniment sa
            # dernière valeur, donc une coupure réseau ne le fait PAS passer
            # unavailable. Le 2026-07-27 le trajet retour a ainsi été scindé
            # en 3 (trous de 2min47 et 2min03, status resté à 4) : le seul
            # signal fiable est la FRAÎCHEUR de la télémétrie.
            stale_after = min(
                60.0,
                max(20.0, get_config_value(hass, CONF_CONFIRMATION_DELAY, DEFAULT_CONFIRMATION_DELAY, imei) / 4),
            )
            last_seen = _tracking_state.get("last_telemetry_utc")
            telemetry_age = (
                (dt_util.utcnow() - last_seen).total_seconds() if last_seen else None
            )
            telemetry_stale = telemetry_age is not None and telemetry_age > stale_after

            sensor_unavailable = not raw_state or raw_state.state in ["unknown", "unavailable"]
            connectivity_loss = sensor_unavailable or telemetry_stale

            if connectivity_loss:
                _LOGGER.info(
                    "Perte de connectivité -> delayed stop (tolérance seule) "
                    "[capteur=%s, dernière trame il y a %s s]",
                    "unavailable" if sensor_unavailable else raw_state.state,
                    f"{telemetry_age:.0f}" if telemetry_age is not None else "?",
                )
            elif raw_state.state in ["0", "0.0"]:
                _LOGGER.info("Scooter off (status=0) -> delayed stop (confirmation)")
            elif not battery_present:
                _LOGGER.info("Battery removed -> delayed stop (confirmation)")

            _LOGGER.info("DELAYED STOP triggered (2min + 5min timer)")

            # Définir les fonctions async AVANT de les utiliser
            def _start_tolerance_timer(connectivity=False):
                """Démarre le timer de tolérance (durée configurable).

                connectivity=True : coupure réseau (tunnel, zone blanche,
                module Astra qui se ré-enregistre) sans arrêt signalé. Le
                scooter roule très probablement encore : on applique la
                tolérance dédiée, plus longue que la pause maximale. Le
                2026-09-14 un commute a été scindé en deux par 8 min de
                silence à la Porte de la Muette (> 5 min de pause max).
                La fin du trajet reste calée sur la dernière trame, donc
                la durée enregistrée ne dépend pas de cette tolérance.
                """
                if connectivity:
                    pause_duration_min = get_config_value(hass, CONF_CONNECTIVITY_LOSS_TOLERANCE, DEFAULT_CONNECTIVITY_LOSS_TOLERANCE, imei)
                    stop_reason = "connectivity-timeout"
                else:
                    pause_duration_min = get_config_value(hass, CONF_PAUSE_MAX_DURATION, DEFAULT_PAUSE_MAX_DURATION, imei)
                    stop_reason = "tolerance-timeout"
                # Convert to seconds
                duration_seconds = pause_duration_min * 60

                # Cancel any existing tolerance timer
                if "tolerance_timer" in scheduled_tasks:
                    scheduled_tasks["tolerance_timer"].cancel()

                # Schedule the callback that will stop the trip when timer expires
                async def _on_tolerance_expired():
                    """Appelé quand le timer de tolérance arrive à expiration."""
                    scheduled_tasks.pop("tolerance_timer", None)
                    if not is_trip_active():
                        _LOGGER.info("⏱️ Timer de tolérance expiré mais trajet déjà clôturé, rien à faire")
                        return
                    _LOGGER.info("⏱️ Timer de tolérance terminé (%d min), arrêt définitif du trajet", pause_duration_min)
                    await do_log_event(hass, f"Trip auto-stopped: {stop_reason} ({pause_duration_min}min)")
                    await do_stop_trip(hass, imei=imei, multi_device=multi_device, reason=stop_reason)

                task = hass.loop.call_later(duration_seconds, lambda: hass.async_create_task(_on_tolerance_expired()))
                scheduled_tasks["tolerance_timer"] = task
                _LOGGER.info(f"✓ Tolerance timer started successfully ({pause_duration_min} min = {duration_seconds}s)")

            async def _confirm_off():
                """Confirme l'arrêt du trajet après le délai de confirmation."""
                confirmation_delay = get_config_value(hass, CONF_CONFIRMATION_DELAY, DEFAULT_CONFIRMATION_DELAY, imei)
                _LOGGER.info(f"⏰ CONFIRM OFF: vérification après {confirmation_delay}s d'attente")
                scheduled_tasks.pop("trip_off_delay", None)

                # Annulation du timer de tolérance s'il est encore actif
                tolerance_task = scheduled_tasks.pop("tolerance_timer", None)
                if tolerance_task:
                    tolerance_task.cancel()
                    _LOGGER.debug("Timer de tolérance annulé (arrêt confirmé)")

                if not is_trip_active():
                    _LOGGER.info("⏰ CONFIRM OFF: trajet déjà clôturé, rien à faire")
                    return

                # Re-vérifier la fraîcheur : si plus aucune trame n'est
                # arrivée depuis l'armement, l'arrêt supposé n'est en fait
                # qu'une coupure réseau. On repasse la main à la tolérance
                # au lieu de clôturer (sinon le trajet est scindé).
                last_seen_now = _tracking_state.get("last_telemetry_utc")
                if last_seen_now:
                    age_now = (dt_util.utcnow() - last_seen_now).total_seconds()
                    if age_now > stale_after:
                        _LOGGER.info(
                            "⏰ CONFIRM OFF annulé : aucune trame depuis %.0fs "
                            "(coupure réseau, pas un arrêt) -> tolérance seule",
                            age_now,
                        )
                        _tracking_state["pause_is_connectivity_loss"] = True
                        _start_tolerance_timer(connectivity=True)
                        return

                state = hass.states.get(SENSOR_TRIP_STATUS)
                # On considère unavailable/unknown comme un vrai arrêt aussi
                if state and state.state in ("off", "unavailable", "unknown"):
                    _LOGGER.info("✅ CONFIRM OFF: état toujours OFF après 2min -> arrêt du trajet")

                    # ✅ FIX: Ne PAS comptabiliser le délai de confirmation (2 min) comme une pause
                    # Ce délai est un anti-rebond technique, pas une pause réelle.
                    # Les vraies pauses sont déjà enregistrées par _record_pause_end()
                    # qui est appelé lors de la reprise du trajet (trip_status: off → on)
                    _LOGGER.debug("⏱️ Délai de confirmation (2 min) ignoré - pas une pause réelle")

                    await do_log_event(hass, "Auto stop trip (confirmed after 2min)")
                    await do_stop_trip(hass, imei=imei, multi_device=multi_device, reason="auto-confirmed")
                else:
                    _LOGGER.info("🔄 CONFIRM OFF: état changé -> annulation de l'arrêt")

            # Maintenant qu'on a défini les fonctions, on peut les utiliser
            # Enregistrer le début de la pause.
            # On mémorise AUSSI la nature de l'interruption : une perte de
            # connectivité (le scooter ne répond plus) n'est PAS une pause
            # — le scooter roule très probablement encore. La déduire de la
            # durée nette faussait tout : 4 coupures de ~1,5 min sur le
            # trajet du 2026-07-27 donnaient « 11 km en 11 min à 60 km/h »
            # pour un trajet réel de 18 min.
            _tracking_state["pause_is_connectivity_loss"] = connectivity_loss
            hass.async_create_task(
                hass.services.async_call(
                    "datetime",
                    "set_value",
                    {
                        "entity_id": entity_id("datetime.scooter_pause_start"),
                        "datetime": dt_util.now().isoformat()
                    },
                    blocking=True
                )
            )

            # Annuler toute tâche précédente (pop obligatoire : une tâche
            # annulée qui resterait dans le dict ferait croire au watchdog
            # qu'un arrêt est déjà en cours)
            previous_task = scheduled_tasks.pop("trip_off_delay", None)
            if previous_task:
                previous_task.cancel()

            if connectivity_loss:
                # Perte de signal : PAS de délai de confirmation. La
                # tolérance (pause_max_duration) est la seule échéance de
                # clôture — si les trames reviennent et que le trajet
                # repart, handle_stop_timer_if_restart annule le timer et
                # enregistre la pause ; si le scooter est réellement garé
                # (garage), la tolérance clôturera avec l'end_time basé sur
                # last_moving_time, pas sur l'heure d'expiration.
                _start_tolerance_timer(connectivity=True)
            else:
                # Arrêt réel signalé (status=0, batterie retirée…) :
                # 1) Planifie l'arrêt après le délai de confirmation configurable
                confirmation_delay = get_config_value(hass, CONF_CONFIRMATION_DELAY, DEFAULT_CONFIRMATION_DELAY, imei)
                task = hass.loop.call_later(confirmation_delay, lambda: hass.async_create_task(_confirm_off()))
                scheduled_tasks["trip_off_delay"] = task

                # 2) Démarre le timer de tolérance (filet de sécurité si la
                # confirmation est annulée sans reprise du trajet)
                _start_tolerance_timer()

            _LOGGER.info("📋 Tâches planifiées : %s", list(scheduled_tasks.keys()))
    #

    remove_trip_status_off = async_track_state_change_event(
        hass, [SENSOR_TRIP_STATUS], handle_trip_status_off
    )

    # 2bis. Statut « éteint » reçu pendant une tolérance « perte de signal »
    #    Le 2026-11-11 l'arrivée au marché a été livrée en retard : statut
    #    unavailable, puis 0 deux minutes après, et le trajet a quand même
    #    attendu les 15 min de la tolérance. Un statut 0 MESURÉ à l'instant
    #    prouve l'arrêt : on repasse au délai de confirmation. Un relevé
    #    ancien (arriéré rejoué par le module) ne prouve rien, d'où le
    #    contrôle de l'heure de mesure ; sans ce capteur, rien ne change.
    @callback
    def handle_off_status_after_signal_loss(event):
        # Écoute aussi l'heure de mesure : l'ordre d'arrivée des deux capteurs
        # n'est pas garanti, et un relevé parké suit toutes les ~15 s.
        raw_state = hass.states.get(SENSOR_SCOOTER_STATUS)
        if (
            not raw_state
            or raw_state.state not in ("0", "0.0")
            or not _tracking_state.get("pause_is_connectivity_loss")
            or "tolerance_timer" not in scheduled_tasks
            or "trip_off_delay" in scheduled_tasks
            or not is_trip_active()
            or get_record_time(timedelta(seconds=60)) is None
        ):
            return

        confirmation_delay = get_config_value(hass, CONF_CONFIRMATION_DELAY, DEFAULT_CONFIRMATION_DELAY, imei)
        _LOGGER.info(
            "Statut 0 reçu après une perte de signal -> arrêt réel, confirmation dans %ss",
            confirmation_delay,
        )

        async def _confirm_real_stop():
            scheduled_tasks.pop("trip_off_delay", None)
            trip_status = hass.states.get(SENSOR_TRIP_STATUS)
            if not is_trip_active() or (trip_status and trip_status.state == "on"):
                return
            # Plus aucune trame depuis : même doute que dans _confirm_off
            # (statut 0 transitoire puis coupure en roulant). La tolérance
            # reste armée ; un relevé frais réarmera cette confirmation.
            last_seen = _tracking_state.get("last_telemetry_utc")
            if not last_seen or (dt_util.utcnow() - last_seen).total_seconds() > 60:
                _LOGGER.info("Confirmation abandonnée : plus de trame, la tolérance décide")
                return
            tolerance_task = scheduled_tasks.pop("tolerance_timer", None)
            if tolerance_task:
                tolerance_task.cancel()
            await do_log_event(hass, "Auto stop trip (status 0 after signal loss)")
            await do_stop_trip(hass, imei=imei, multi_device=multi_device, reason="auto-confirmed")

        # Annulé par handle_stop_timer_if_restart si le scooter repart
        scheduled_tasks["trip_off_delay"] = hass.loop.call_later(
            confirmation_delay, lambda: hass.async_create_task(_confirm_real_stop())
        )

    remove_off_status_after_signal_loss = async_track_state_change_event(
        hass, [SENSOR_SCOOTER_STATUS, SENSOR_SCOOTER_RECORD_TIME], handle_off_status_after_signal_loss
    )

    # 3. "Scooter - Annuler les tâches d'arrêt si le scooter redémarre"
    #    => sensor.scooter_trip_status to 'on' : annule trip_off_delay + tolerance_timer
    #
    @callback
    def handle_stop_timer_if_restart(event):
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if not old_state or not new_state:
            return

        _LOGGER.debug(
            "▶ handle_stop_timer_if_restart : %s → %s", 
            old_state.state, new_state.state
        )

        # Si le scooter repart (trip_status passe de off à on), on annule la tâche
        if old_state.state != "on" and new_state.state == "on":
            trip_task = scheduled_tasks.pop("trip_off_delay", None)
            if trip_task:
                trip_task.cancel()
                _LOGGER.info("🔄 Trip status → ON : annulation du délai d'arrêt automatique (2 min).")

            # Si le timer de tolérance est actif, on le stoppe aussi
            tolerance_task = scheduled_tasks.pop("tolerance_timer", None)
            if tolerance_task:
                tolerance_task.cancel()
                _LOGGER.info("🔄 Timer de tolérance annulé (scooter redémarré)")

                # Enregistrer la fin de la pause (is_date_valid écarte la
                # sentinelle 1970 : sans ce filtre, une pause_start jamais
                # écrite produirait une "pause" de 56 ans qui annule toute la
                # durée nette du trajet)
                pause_start = hass.states.get(entity_id("datetime.scooter_pause_start"))
                if pause_start and is_date_valid(pause_start.state):
                    hass.async_create_task(_record_pause_end())

                hass.async_create_task(do_log_event(hass, "Pause stopped, trip restarted"))
    
    async def _reset_pause_start():
        """Remet la sentinelle sur pause_start (pause traitée ou ignorée)."""
        await hass.services.async_call(
            "datetime",
            "set_value",
            {
                "entity_id": entity_id("datetime.scooter_pause_start"),
                "datetime": "1970-01-01 00:00:00"
            },
            blocking=True
        )

    async def _record_pause_end():
        """Enregistre la durée de la pause qui vient de se terminer.

        Une interruption due à une PERTE DE CONNECTIVITÉ n'est pas une pause :
        le scooter roulait selon toute vraisemblance (tunnel, zone blanche,
        bus CAN qui décroche). La déduire de la durée nette produit des
        durées trop courtes et des vitesses moyennes absurdes.
        """
        try:
            if _tracking_state.get("pause_is_connectivity_loss"):
                _LOGGER.info(
                    "Interruption de connectivité (pas une pause) — durée non déduite"
                )
                _tracking_state["pause_is_connectivity_loss"] = False
                await _reset_pause_start()
                return

            pause_start = hass.states.get(entity_id("datetime.scooter_pause_start"))
            if pause_start and is_date_valid(pause_start.state):
                pause_start_dt = dt_util.parse_datetime(pause_start.state)
                if pause_start_dt:
                    pause_duration = (dt_util.now() - dt_util.as_local(pause_start_dt)).total_seconds() / 60

                    # Un arrêt plus court que le délai de confirmation n'est
                    # pas une pause : feu rouge, bouchon, statut 0 transitoire.
                    # Ils font partie intégrante du trajet (décision Benoit,
                    # 2026-09-14 : les déduire donnait « 4 km en 2 min à
                    # 120 km/h »). Seul un arrêt confirmé (>= délai de
                    # confirmation) est déduit de la durée nette.
                    confirmation_delay = get_config_value(hass, CONF_CONFIRMATION_DELAY, DEFAULT_CONFIRMATION_DELAY, imei)
                    if 0 <= pause_duration * 60 < confirmation_delay:
                        _LOGGER.info(
                            "Arrêt court (%.1f min < %ds de confirmation) : compté dans le trajet, non déduit",
                            pause_duration, confirmation_delay,
                        )
                        await _reset_pause_start()
                        return

                    # Clamp de sécurité : une pause ne peut pas dépasser la
                    # tolérance de beaucoup (le timer aurait clôturé). Une
                    # valeur énorme = pause_start périmée (restore, restart).
                    pause_max_min = get_config_value(hass, CONF_PAUSE_MAX_DURATION, DEFAULT_PAUSE_MAX_DURATION, imei)
                    pause_cap = max(60.0, pause_max_min * 3)
                    if pause_duration > pause_cap or pause_duration < 0:
                        _LOGGER.warning(
                            "Durée de pause aberrante (%.1f min), ignorée (pause_start périmé: %s)",
                            pause_duration, pause_start.state,
                        )
                        await _reset_pause_start()
                        return

                    # Ajouter à la durée totale des pauses
                    total_pause = hass.states.get(entity_id("number.scooter_pause_duration"))
                    if total_pause:
                        try:
                            current_pause = float(total_pause.state)
                        except (ValueError, TypeError):
                            current_pause = 0
                    else:
                        current_pause = 0

                    await hass.services.async_call(
                        "number",
                        "set_value",
                        {
                            "entity_id": entity_id("number.scooter_pause_duration"),
                            "value": current_pause + pause_duration
                        },
                        blocking=True
                    )
                    
                    _LOGGER.info("Pause terminée : durée %.1f min, total pauses: %.1f min",
                                pause_duration, current_pause + pause_duration)

                    # Réinitialiser pause_start (sentinelle) pour qu'un double
                    # événement de reprise ne recompte pas la même pause.
                    await _reset_pause_start()
        except Exception as e:
            _LOGGER.error("Erreur dans _record_pause_end: %s", e)

    remove_stop_timer_if_restart = async_track_state_change_event(
        hass, [SENSOR_TRIP_STATUS], handle_stop_timer_if_restart
    )

    #
    # 5. "Scooter - Gérer le bouton Arrêter maintenant"
    #    => input_boolean.stop_trip_now => on
    #
    @callback
    def handle_stop_trip_now(event):
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if not old_state or not new_state:
            return

        if old_state.state == "off" and new_state.state == "on":
            # => log_event("Manual stop button clicked")
            # => Annuler toutes les tâches d'arrêt en cours
            # => do_stop_trip
            # => input_boolean.stop_trip_now = off
            hass.async_create_task(_process_stop_trip_now())

    async def _process_stop_trip_now():
        await do_log_event(hass, "Manual stop button clicked")

        # Annuler toutes les tâches programmées si existantes
        if scheduled_tasks.get("trip_off_delay"):
            scheduled_tasks["trip_off_delay"].cancel()
            scheduled_tasks.pop("trip_off_delay", None)

        if scheduled_tasks.get("tolerance_timer"):
            scheduled_tasks["tolerance_timer"].cancel()
            scheduled_tasks.pop("tolerance_timer", None)

        # do_stop_trip — seulement si un trajet est ouvert : sinon il
        # réécrirait le dernier trajet une seconde fois dans l'historique.
        if is_trip_active():
            await do_stop_trip(hass, imei=imei, multi_device=multi_device, reason="Manual button")
        else:
            _LOGGER.info("Manual stop ignored: no active trip")

        # repasse le switch à off
        await hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": SWITCH_STOP_NOW},
            blocking=True
        )

    remove_stop_trip_now = async_track_state_change_event(
        hass, [SWITCH_STOP_NOW], handle_stop_trip_now
    )

    #
    # 6. "Scooter - Last start" 
    #    => sensor.scooter_is_moving => to on
    #

    @callback
    def handle_scooter_last_start(event):
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if not old_state or not new_state:
            return

        if old_state.state != "on" and new_state.state == "on":
            _LOGGER.info("🚀 START TRIGGER: is_moving %s → %s", old_state.state, new_state.state)
            
            # CORRECTION: Vérifier si un trajet est VRAIMENT en cours
            if is_trip_active():
                _LOGGER.info("⚠️ Trajet déjà actif, ignoring start trigger")
                return
            
            # Vérifier que le scooter est dans un état de trajet actif.
            # Status 3 = arrêté au feu / prêt à repartir (trajet en cours,
            # speed=0), status 4 = en mouvement. Les deux comptent comme un
            # trajet actif (cf. scooter_off = status in [0, 1, 5] côté
            # messageParser et template scooter_is_moving dans silence.yaml).
            # Un allumage à distance sans mouvement réel descend bien vers
            # 0 rapidement via la séquence 3 → 2 → 0, protégée par la
            # grace period de stop.
            scooter_status = hass.states.get(SENSOR_SCOOTER_STATUS)
            if scooter_status and scooter_status.state not in ["unknown", "unavailable"]:
                try:
                    status = float(scooter_status.state)
                    if status not in (3.0, 4.0):
                        _LOGGER.info(
                            "⚠️ Scooter status=%s, ignoring start trigger "
                            "(expected 3=idle or 4=moving)",
                            status,
                        )
                        return
                except (ValueError, TypeError):
                    _LOGGER.warning("Could not read scooter status, continuing anyway")
            
            _LOGGER.info("✅ START CONFIRMED: démarrage du trajet (scooter status OK)")
            hass.async_create_task(_do_last_start())

    async def _recover_untracked_km(km: float):
        """Ajoute au suivi les km que l'odomètre a pris hors de tout trajet.

        Trajet jamais vu (télémétrie absente), rejeté ou perdu : en novembre
        2026 l'odomètre avait pris 117 km et le suivi 81. La batterie est
        ajoutée au prorata de la moyenne suivie, pour ne pas fausser les
        indicateurs en km par % ; son vrai niveau entre deux trajets est
        inconnu (recharge, échange).
        """
        if not 0 < km <= 100:
            return
        tracked_dist = get_sensor_float_value(hass, NUMBER_TRACKED_DISTANCE, 0.0)
        tracked_batt = get_sensor_float_value(hass, NUMBER_TRACKED_BATT_USED, 0.0)
        updates = [(NUMBER_TRACKED_DISTANCE, tracked_dist + km)]
        if tracked_dist > 0:
            updates.append((NUMBER_TRACKED_BATT_USED, tracked_batt + km * tracked_batt / tracked_dist))
        for number, value in updates:
            await hass.services.async_call(
                "number", "set_value", {"entity_id": number, "value": round(value, 1)}, blocking=True
            )
        await do_log_event(hass, f"Untracked distance recovered: {km:.0f}km")

    async def _do_last_start():
        # Vérifier une dernière fois qu'un trajet n'est pas déjà en cours
        if is_trip_active():
            _LOGGER.info("⚠️ Trajet déjà actif dans _do_last_start, aborting")
            return
            
        # (1) Appelle 'silencescooter.log_event' avec message "Start trip triggered"
        await do_log_event(hass, "Start trip triggered")
        
        # Réinitialiser la durée totale des pauses
        await hass.services.async_call(
            "number",
            "set_value",
            {
                "entity_id": entity_id("number.scooter_pause_duration"),
                "value": 0
            },
            blocking=True
        )

        # Réinitialiser l'heure de début de pause
        await hass.services.async_call(
            "datetime",
            "set_value",
            {
                "entity_id": entity_id("datetime.scooter_pause_start"),
                "datetime": "1970-01-01 00:00:00"
            },
            blocking=True
        )

        # (2) datetime.scooter_end_time => "1970-01-01 00:00:00"
        await hass.services.async_call(
            "datetime",
            "set_value",
            {
                "entity_id": INPUT_DT_END_TIME,
                "datetime": "1970-01-01 00:00:00"
            },
            blocking=True
        )

        # (3) sensor.scooter_last_trip_max_speed => 0
        await set_writable_sensor_value(hass, SENSOR_MAX_SPEED, 0)

        # (4) input_number.scooter_odo_debut => sensor.silence_scooter_odo
        odo_val = get_sensor_float_value(hass, SENSOR_SCOOTER_ODO, 0.0, fallback_entity=entity_id("sensor.scooter_odo_display"))
        await hass.services.async_call(
            "number",
            "set_value",
            {
                "entity_id": NUMBER_ODO_DEBUT,
                "value": odo_val
            },
            blocking=True
        )
        # L'odomètre a avancé depuis la fin du trajet précédent : ces km ont
        # été roulés sans trajet enregistré, on les rend au suivi.
        previous_fin = get_sensor_float_value(hass, NUMBER_ODO_FIN, 0.0)
        if previous_fin > 0:
            await _recover_untracked_km(odo_val - previous_fin)

        # odo_fin repart du même point : handle_track_odo ne fait que le
        # monter, donc un seul relevé aberrant trop haut restait pour tous
        # les trajets suivants (distances de centaines de km).
        await hass.services.async_call(
            "number",
            "set_value",
            {
                "entity_id": NUMBER_ODO_FIN,
                "value": odo_val
            },
            blocking=True
        )

        # (5) datetime.scooter_start_time => heure de mesure du relevé qui a
        # déclenché le départ (publiée avant le status par le serveur), sinon now
        # Seulement si ce relevé est récent (tolérance réseau) : le module
        # livre parfois d'abord des relevés restés en attente depuis des
        # heures, qui feraient démarrer le trajet à l'heure du trajet précédent.
        record_start = get_record_time(timedelta(minutes=get_config_value(
            hass, CONF_CONNECTIVITY_LOSS_TOLERANCE, DEFAULT_CONNECTIVITY_LOSS_TOLERANCE, imei)))
        _tracking_state["start_uses_record_time"] = record_start is not None
        now_str = (record_start or dt_util.now()).isoformat()
        await hass.services.async_call(
            "datetime",
            "set_value",
            {
                "entity_id": INPUT_DT_START_TIME,
                "datetime": now_str
            },
            blocking=True
        )
        _LOGGER.info("✅ START TIME SET: %s", now_str)

        # (6) input_number.scooter_battery_soc_debut => sensor.silence_scooter_battery_soc
        batt_val = get_sensor_float_value(hass, SENSOR_BATT_SOC, 0.0, fallback_entity=entity_id("sensor.scooter_battery_display"))
        await hass.services.async_call(
            "number",
            "set_value",
            {
                "entity_id": NUMBER_BATT_SOC_DEBUT,
                "value": batt_val
            },
            blocking=True
        )
        
        _LOGGER.info("✅ TRIP STARTED: odo_start=%.1f, battery_start=%.1f%%", odo_val, batt_val)

        # Record the start timestamp for the ODO/battery tracking handlers
        # to use as a grace-period anchor (see handle_track_odo).
        import time as _time
        last_trip_start_monotonic["value"] = _time.monotonic()

        # Reset tracking-fired flags so do_stop_trip can tell whether the
        # live handlers actually ran during this trip.
        odo_tracking_fired["value"] = False
        battery_tracking_fired["value"] = False
        _tracking_state["pause_is_connectivity_loss"] = False
        _tracking_state["energy_gap_at_start"] = get_energy_gap(hass, imei, multi_device)
        # Lu en fin de démarrage : le compteur d'énergie de la même rafale MQTT
        # est alors arrivé (voir la capacité réelle dans update_trip_statistics).
        _tracking_state["energy_at_start"] = get_sensor_float_value(hass, SENSOR_ENERGY_CONSUMPTION, 0.0) or None

    remove_last_start = async_track_state_change_event(
        hass, [SENSOR_IS_MOVING], handle_scooter_last_start
    )

    #
    # 7. "Scooter - Update Max Speed"
    #    => sensor.silence_scooter_speed => state changed
    #
    @callback
    def handle_update_max_speed(event):
        new_state = event.data.get("new_state")
        if not new_state:
            return
        speed_str = new_state.state
        if speed_str in ["unknown", "unavailable"]:
            return

        try:
            current_speed = float(speed_str)
        except (ValueError, TypeError):
            return

        # Toute valeur de vitesse valide = télémétrie fraîche (réf. watchdog)
        _tracking_state["last_telemetry_utc"] = dt_util.utcnow()

        hass.async_create_task(_do_update_max_speed(current_speed))

    async def _do_update_max_speed(current_speed):
        old_max = get_sensor_float_value(hass, SENSOR_MAX_SPEED, 0.0)
        new_val = max(old_max, current_speed, 0)
        if new_val > old_max:
            _LOGGER.debug("New max speed: %.1f km/h (was %.1f)", new_val, old_max)
        await set_writable_sensor_value(hass, SENSOR_MAX_SPEED, new_val)

    remove_update_max_speed = async_track_state_change_event(
        hass, [SENSOR_SCOOTER_SPEED], handle_update_max_speed
    )

    #
    # 7b. "Scooter - Track ODO continuously during trip"
    #    Keeps number.scooter_odo_fin in sync with the live ODO sensor
    #    so that do_stop_trip() has a correct value even if the sensor
    #    becomes unavailable at the moment of the stop.
    #    Also repairs number.scooter_odo_debut if it was captured stale
    #    (ODO sensor was unavailable when the trip started).
    #
    @callback
    def handle_track_odo(event):
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if not new_state or new_state.state in ["unknown", "unavailable"]:
            return

        try:
            new_odo = float(new_state.state)
        except (ValueError, TypeError):
            return

        if new_odo <= 0 or new_odo > 1_000_000:
            return

        # Télémétrie fraîche reçue (réf. watchdog), trajet actif ou non
        _tracking_state["last_telemetry_utc"] = dt_util.utcnow()

        if not is_trip_active():
            return

        # Don't track stale (>24h) active trips — these are bugs (trip
        # never got stopped), and updating their counters pollutes stats.
        start_time_st = hass.states.get(INPUT_DT_START_TIME)
        if start_time_st and is_date_valid(start_time_st.state):
            start_dt = get_valid_datetime(start_time_st.state)
            if start_dt and (dt_util.now() - start_dt).total_seconds() > 86400:
                return

        hass.async_create_task(_do_track_odo(new_odo, old_state))

    async def _do_track_odo(new_odo: float, old_state):
        # Skip repair logic during the first 5 seconds after a trip start
        # to avoid racing with _do_last_start() writing odo_debut.
        import time as _time
        from datetime import timedelta
        start_mono = last_trip_start_monotonic.get("value")
        within_grace = start_mono is not None and (_time.monotonic() - start_mono) < 10.0

        # Also skip repair within 10s of HA startup: if HA restarted mid-trip,
        # MQTT sensors fire immediately on reconnect and may legitimately
        # "jump" from unknown/stale state, which should not trigger repair.
        within_startup = (dt_util.utcnow() - STARTUP_TIME) < timedelta(seconds=10)

        # Mark that tracking fired at least once for this trip.
        odo_tracking_fired["value"] = True

        # Update odo_fin continuously so that the stop path never reads a
        # stale or unavailable value.
        current_fin = get_sensor_float_value(hass, NUMBER_ODO_FIN, 0.0)
        if new_odo > current_fin:
            await hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": NUMBER_ODO_FIN, "value": new_odo},
                blocking=True,
            )

        # Repair is gated by the grace period — too early, odo_debut may
        # not even be written yet. Also gated by HA-startup grace to avoid
        # spurious repairs on reconnect after a restart.
        if within_grace or within_startup:
            return

        # Repair odo_debut if it was captured while the sensor was stale or
        # unavailable. We detect this by looking at the previous ODO state:
        # if it jumped significantly (> 5 km) between two consecutive
        # readings, the old value was cached/stale and the trip's odo_debut
        # is almost certainly wrong.
        current_debut = get_sensor_float_value(hass, NUMBER_ODO_DEBUT, 0.0)
        if current_debut <= 0 or old_state is None:
            return

        try:
            prev_odo = float(old_state.state) if old_state.state not in ["unknown", "unavailable"] else None
        except (ValueError, TypeError):
            prev_odo = None

        if prev_odo is None:
            return

        jump = new_odo - prev_odo
        # A jump > 5 km in a single update means the old value was stale.
        # If odo_debut was captured close to prev_odo (within 2 km), it is
        # almost certainly the stale value — repair it to new_odo.
        if jump > 5 and abs(current_debut - prev_odo) < 2 and new_odo > current_debut:
            # …sauf si le saut est compatible avec du roulage réel pendant une
            # coupure de connectivité : le scooter bufferise et l'ODO peut
            # légitimement avancer de plusieurs km entre deux trames. On ne
            # répare que si le kilométrage est IMPLAUSIBLE pour le temps écoulé
            # depuis la dernière valeur (>100 km/h soutenus), sinon on
            # écraserait des kilomètres réellement parcourus hors ligne.
            gap_s = 0.0
            prev_updated = getattr(old_state, "last_updated", None)
            if prev_updated:
                gap_s = max(0.0, (dt_util.utcnow() - prev_updated).total_seconds())
            plausible_km = gap_s / 3600.0 * 100.0 + 2.0
            if jump <= plausible_km:
                _LOGGER.info(
                    "🛣️ ODO jump +%.1f km en %.0fs plausible (segment hors ligne), "
                    "odo_debut %.1f conservé",
                    jump, gap_s, current_debut,
                )
                return
            _LOGGER.info(
                "🔧 ODO jump detected (%.1f -> %.1f = +%.1f km): repairing stale odo_debut "
                "from %.1f to %.1f",
                prev_odo, new_odo, jump, current_debut, new_odo,
            )
            await hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": NUMBER_ODO_DEBUT, "value": new_odo},
                blocking=True,
            )
            # Les km retirés du trajet ont bien été roulés (avant lui)
            await _recover_untracked_km(new_odo - current_debut)

    remove_track_odo = async_track_state_change_event(
        hass, [SENSOR_SCOOTER_ODO], handle_track_odo
    )

    #
    # 7c. "Scooter - Track battery SoC continuously during trip"
    #    Keeps number.scooter_battery_soc_fin in sync with the live SoC
    #    sensor so that do_stop_trip() has a correct value even if the
    #    sensor becomes unavailable at the moment of the stop.
    #    Also repairs number.scooter_battery_soc_debut if it was captured
    #    stale (SoC sensor was showing an old cached value at trip start).
    #
    @callback
    def handle_track_battery(event):
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if not new_state or new_state.state in ["unknown", "unavailable"]:
            return

        try:
            new_soc = float(new_state.state)
        except (ValueError, TypeError):
            return

        if new_soc < 0 or new_soc > 100:
            return

        # Télémétrie fraîche reçue (réf. watchdog), trajet actif ou non
        _tracking_state["last_telemetry_utc"] = dt_util.utcnow()

        if not is_trip_active():
            return

        # Don't track stale (>24h) active trips.
        start_time_st = hass.states.get(INPUT_DT_START_TIME)
        if start_time_st and is_date_valid(start_time_st.state):
            start_dt = get_valid_datetime(start_time_st.state)
            if start_dt and (dt_util.now() - start_dt).total_seconds() > 86400:
                return

        hass.async_create_task(_do_track_battery(new_soc, old_state))

    async def _do_track_battery(new_soc: float, old_state):
        # Mark that tracking fired at least once for this trip.
        battery_tracking_fired["value"] = True

        # Always keep odo_fin's battery counterpart in sync
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": NUMBER_BATT_SOC_FIN, "value": new_soc},
            blocking=True,
        )

        # Skip repair after HA restart only. PAS de délai de grâce après le
        # départ : le vrai SoC arrive souvent quelques millisecondes après le
        # status qui déclenche le trajet (même rafale MQTT). Le 2026-11-10 le
        # départ a capturé 25 % (valeur d'avant l'échange de batterie), 98 %
        # est arrivé 15 ms plus tard, la grâce de 10 s a bloqué la réparation
        # et le trajet a été enregistré à 0 % consommé. Les conditions
        # ci-dessous (saut > 10 %, debut ≈ ancienne lecture) suffisent.
        within_startup = (dt_util.utcnow() - STARTUP_TIME) < timedelta(seconds=10)
        if within_startup:
            return

        # Repair debut if we detect a "stale -> real" jump at reconnect.
        # A sudden jump > 10% in a single update is suspicious: during a
        # trip, SoC decreases gradually. A large positive jump means the
        # previous value was a stale cache from before a disconnection.
        current_debut = get_sensor_float_value(hass, NUMBER_BATT_SOC_DEBUT, 0.0)
        if current_debut <= 0 or old_state is None:
            return

        try:
            prev_soc = float(old_state.state) if old_state.state not in ["unknown", "unavailable"] else None
        except (ValueError, TypeError):
            prev_soc = None

        if prev_soc is None:
            return

        jump = new_soc - prev_soc
        # Positive jump > 10% -> stale cache was replaced by real value
        if jump > 10 and abs(current_debut - prev_soc) < 2:
            _LOGGER.info(
                "🔧 Battery jump detected (%.1f -> %.1f = +%.1f%%): repairing stale "
                "battery_soc_debut from %.1f to %.1f",
                prev_soc, new_soc, jump, current_debut, new_soc,
            )
            await hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": NUMBER_BATT_SOC_DEBUT, "value": new_soc},
                blocking=True,
            )

    remove_track_battery = async_track_state_change_event(
        hass, [SENSOR_BATT_SOC], handle_track_battery
    )

    #
    # 8. (supprimé) "Scooter - Update Device Tracker Position"
    #    La position GPS est désormais portée par l'entité native
    #    device_tracker.silence_scooter (plateforme device_tracker.py, filtrage
    #    distance/vitesse inclus). L'ancien appel au service device_tracker.see
    #    est obsolète et disparaît dans Home Assistant 2027.5.
    #

    #
    # 9. "Scooter - Watchdog pour fin de trajet"
    #    Vérifie toutes les 5 minutes si un trajet devrait être terminé
    #
    async def watchdog_check_trip_end(now):
        """Vérifie si un trajet en cours devrait être terminé."""
        try:
            # Vérifier s'il y a un trajet en cours
            if not is_trip_active():
                return  # Pas de trajet en cours

            # Trajet ouvert, scooter à l'arrêt, et plus aucun minuteur d'arrêt :
            # ils vivent en mémoire et sont perdus si HA redémarre (ou si
            # l'intégration est rechargée) pendant l'arrêt. Sans ce filet, le
            # trajet restait ouvert tant que le scooter émettait, et le trajet
            # suivant fusionnait avec lui. last_changed repart au redémarrage,
            # donc la pause maximale est comptée depuis celui-ci.
            status_st = hass.states.get(SENSOR_TRIP_STATUS)
            if not scheduled_tasks and status_st is not None and status_st.state != "on":
                pause_max_min = get_config_value(hass, CONF_PAUSE_MAX_DURATION, DEFAULT_PAUSE_MAX_DURATION, imei)
                if (dt_util.utcnow() - status_st.last_changed).total_seconds() > pause_max_min * 60:
                    _LOGGER.info("🔔 Watchdog: trajet ouvert sans minuteur d'arrêt depuis >%s min, clôture", pause_max_min)
                    await do_log_event(hass, "Watchdog: Auto stop trip (stop timers lost)")
                    await do_stop_trip(hass, imei=imei, multi_device=multi_device, reason="watchdog-timers-lost")
                    return
            
            # Référence de fraîcheur = la plus récente de :
            #  - sensor.silence_scooter_last_update (si exploitable),
            #  - le dernier événement télémétrie vu par les handlers
            #    (last_telemetry_utc),
            #  - le démarrage de HA (grâce post-restart).
            # L'ancien code faisait `return` quand le capteur était
            # unknown/unavailable — soit exactement les scénarios pour
            # lesquels le watchdog existe (garage, capteur expiré, restart
            # HA scooter hors ligne) : un trajet restauré restait alors
            # ouvert pour toujours.
            try:
                candidates = [STARTUP_TIME]

                last_update = hass.states.get(SENSOR_SCOOTER_LAST_UPDATE)
                if last_update and last_update.state not in ["unknown", "unavailable"]:
                    try:
                        last_update_dt = dt_util.parse_datetime(last_update.state)
                        if last_update_dt:
                            candidates.append(dt_util.as_utc(last_update_dt))
                    except (ValueError, TypeError):
                        pass

                last_seen = _tracking_state.get("last_telemetry_utc")
                if last_seen:
                    candidates.append(last_seen)

                ref_time = max(candidates)

                # Si pas de mise à jour depuis plus de X minutes (configurable)
                watchdog_delay_min = get_config_value(hass, CONF_WATCHDOG_DELAY, DEFAULT_WATCHDOG_DELAY, imei)
                # Le silence radio est d'abord une coupure réseau possible :
                # le watchdog ne doit pas clôturer avant la tolérance dédiée,
                # sinon il scinde un trajet que la tolérance aurait gardé.
                watchdog_delay_min = max(
                    watchdog_delay_min,
                    get_config_value(hass, CONF_CONNECTIVITY_LOSS_TOLERANCE, DEFAULT_CONNECTIVITY_LOSS_TOLERANCE, imei),
                )
                watchdog_delay_sec = watchdog_delay_min * 60
                if (dt_util.utcnow() - ref_time).total_seconds() > watchdog_delay_sec:
                    _LOGGER.info(f"🔔 Watchdog: Scooter non mis à jour depuis >{watchdog_delay_min}min, arrêt du trajet")

                    # Vérifier qu'on n'a pas déjà une tâche d'arrêt en cours
                    # (le chemin perte-de-signal n'arme que tolerance_timer)
                    if "trip_off_delay" not in scheduled_tasks and "tolerance_timer" not in scheduled_tasks:
                        detector = get_error_detector(hass)
                        if detector:
                            detector.record_error(
                                ErrorCategory.MQTT_DISCONNECT, ErrorSeverity.WARNING,
                                f"Watchdog: no scooter update for >{watchdog_delay_min}min",
                                source="watchdog",
                            )
                        await do_log_event(hass, "Watchdog: Auto stop trip (no update)")
                        await do_stop_trip(hass, imei=imei, multi_device=multi_device, reason="watchdog-no-update")
            except Exception as e:
                _LOGGER.error("Erreur dans watchdog_check_trip_end: %s", e)
                
        except Exception as e:
            _LOGGER.error("Erreur dans watchdog_check_trip_end: %s", e)

    # Enregistrer le watchdog
    watchdog_remove = async_track_time_interval(
        hass, watchdog_check_trip_end, timedelta(minutes=5)
    )


    def _cancel_scheduled_stop_tasks():
        """Annule les timers d'arrêt en attente (unload/reload).

        Sans cette annulation, un timer de confirmation/tolérance armé avant
        un reload survivait avec les anciennes closures et pouvait clôturer
        (voire double-enregistrer) un trajet géré par la nouvelle instance.
        """
        for name in list(scheduled_tasks):
            task = scheduled_tasks.pop(name)
            task.cancel()
            _LOGGER.debug("Scheduled stop task '%s' cancelled at unload", name)

    # Return all cancel listeners for cleanup
    cancel_listeners = [
        remove_telemetry_seen,
        remove_energy_baseline_init,
        remove_tracker_dernier_mouvement,
        remove_trip_status_off,
        remove_off_status_after_signal_loss,
        remove_stop_timer_if_restart,
        remove_stop_trip_now,
        remove_last_start,
        remove_update_max_speed,
        remove_track_odo,
        remove_track_battery,
        watchdog_remove,
        _cancel_scheduled_stop_tasks,
    ]

    _LOGGER.info("All custom automations for Silence Scooter (IMEI: %s) have been set up", imei)
    return cancel_listeners


async def do_log_event(hass: HomeAssistant, message: str):
    """Log an event via the helper function."""
    _LOGGER.info("LOG EVENT: %s", message)
    try:
        await log_event(hass, message)
    except Exception as exc:
        _LOGGER.error("Failed to call log_event helper: %s", exc)


async def do_stop_trip(hass: HomeAssistant, imei: str = "", multi_device: bool = False, reason: str = "Manual stop"):
    """Stop the current trip and update all trip-related entities.

    This function orchestrates the trip stop workflow by determining the end
    timestamp, updating odometer and time readings, calculating trip metrics
    (distance, duration, speed, battery consumption), updating cumulative
    statistics, and recording the trip in history.

    Args:
        hass: HomeAssistant instance
        imei: IMEI of the scooter (optional for single-device)
        multi_device: Whether multi-device mode is enabled
        reason: Reason for stopping the trip
    """
    _LOGGER.info("STOP TRIP TRIGGERED: reason=%s", reason)

    # Retrieve trip-tracking flags from hass.data (populated by
    # setup_automations). They are dicts with key "value" to keep the
    # read/write pattern uniform with the closure-based tracking in
    # setup_automations. Fallback to no-ops if the state isn't there
    # (e.g. very first run before setup_automations initialised it).
    _tracking_state = hass.data.get(DOMAIN, {}).get(
        _tracking_key(imei),
        {
            "last_trip_start_monotonic": None,
            "odo_tracking_fired": False,
            "battery_tracking_fired": False,
        },
    )
    odo_tracking_fired = {"value": _tracking_state.get("odo_tracking_fired", False)}
    battery_tracking_fired = {"value": _tracking_state.get("battery_tracking_fired", False)}

    def entity_id(base: str) -> str:
        from .helpers import insert_imei_in_entity_id
        return insert_imei_in_entity_id(base, imei, multi_device)

    # Entity IDs for this scooter
    INPUT_DT_END_TIME = entity_id("datetime.scooter_end_time")
    INPUT_DT_START_TIME = entity_id("datetime.scooter_start_time")
    NUMBER_ODO_DEBUT = entity_id("number.scooter_odo_debut")
    NUMBER_ODO_FIN = entity_id("number.scooter_odo_fin")
    NUMBER_BATT_SOC_DEBUT = entity_id("number.scooter_battery_soc_debut")
    NUMBER_BATT_SOC_FIN = entity_id("number.scooter_battery_soc_fin")
    SENSOR_SCOOTER_ODO = entity_id("sensor.silence_scooter_odo")
    SENSOR_BATT_SOC = entity_id("sensor.silence_scooter_battery_soc")
    SENSOR_TRIP_STATUS = entity_id("sensor.scooter_trip_status")
    SENSOR_LAST_TRIP_DISTANCE = entity_id("sensor.scooter_last_trip_distance")
    SENSOR_LAST_TRIP_DURATION = entity_id("sensor.scooter_last_trip_duration")
    SENSOR_LAST_TRIP_AVG_SPEED = entity_id("sensor.scooter_last_trip_avg_speed")
    SENSOR_LAST_TRIP_BATT_CONSUMPTION = entity_id("sensor.scooter_last_trip_battery_consumption")

    # Concurrency guard: if a previous do_stop_trip is still running, skip.
    # Two trip_status off events firing in quick succession (e.g. due to MQTT
    # flapping) would otherwise each record the trip and double-increment
    # scooter_trips, tracked_distance, and the history file.
    _domain_state = hass.data.setdefault(DOMAIN, {})
    _stop_lock_key = f"stop_trip_in_progress:{imei or 'single'}"
    if _domain_state.get(_stop_lock_key):
        _LOGGER.info(
            "do_stop_trip already in progress (reason=%s); skipping duplicate call",
            reason,
        )
        return
    _domain_state[_stop_lock_key] = True

    try:
        # 1) Determine end timestamp using helper
        end_timestamp = determine_trip_end_timestamp(hass, imei, multi_device)

        # 2) Update datetime.scooter_end_time
        await hass.services.async_call(
            "datetime",
            "set_value",
            {
                "entity_id": INPUT_DT_END_TIME,
                "datetime": end_timestamp
            },
            blocking=True
        )

        # 3) Prefer the NUMBER_ODO_FIN value kept in sync by handle_track_odo.
        # Fall back to live sensor only if tracking never fired during the
        # trip (flag odo_tracking_fired). We still take max() with the live
        # sensor as a safety net in case tracking missed the very last km.
        tracked_fin = get_sensor_float_value(hass, NUMBER_ODO_FIN, 0.0)
        live_odo = get_sensor_float_value(hass, SENSOR_SCOOTER_ODO, 0.0, fallback_entity=entity_id("sensor.scooter_odo_display"))

        if odo_tracking_fired.get("value") and tracked_fin > 0:
            # Tracking fired — trust it but take max with live sensor as
            # a safety net (live may have advanced since the last tracked
            # update, e.g. between the last ODO tick and the stop).
            odo_fin_val = max(tracked_fin, live_odo)
        else:
            # Tracking never fired — fall back entirely to live sensor.
            odo_fin_val = live_odo

        if odo_fin_val != tracked_fin:
            await hass.services.async_call(
                "number",
                SERVICE_SET_VALUE,
                {
                    "entity_id": NUMBER_ODO_FIN,
                    "value": odo_fin_val
                },
                blocking=True
            )

        # 4) Calculate trip distance
        odo_debut_val = get_sensor_float_value(hass, NUMBER_ODO_DEBUT, 0.0)
        distance_val = round(max(0, odo_fin_val - odo_debut_val), 1)

        if distance_val > 500:
            _LOGGER.warning("Distance too long (%.1f km), capped at 500 km", distance_val)
            distance_val = 500.0

        _LOGGER.info("Setting distance: %.1f km", distance_val)
        await set_writable_sensor_value(hass, SENSOR_LAST_TRIP_DISTANCE, distance_val)

        # 5) Calculate trip duration using helper
        start_time_state = hass.states.get(INPUT_DT_START_TIME)
        if start_time_state and start_time_state.state not in ["unknown", "unavailable"]:
            trip_duration_val = await calculate_trip_duration(
                hass,
                start_time_state.state,
                end_timestamp,
                imei=imei,
                multi_device=multi_device,
            )
        else:
            _LOGGER.debug("Pas de start_time disponible pour calculer la durée")
            trip_duration_val = 0.0

        await set_writable_sensor_value(hass, SENSOR_LAST_TRIP_DURATION, trip_duration_val)

        # 6) Calculate average speed
        if trip_duration_val > 0:
            avg_speed = round(distance_val / (trip_duration_val / 60.0), 1)
        else:
            avg_speed = 0.0

        await set_writable_sensor_value(hass, SENSOR_LAST_TRIP_AVG_SPEED, avg_speed)

        # 7) Prefer NUMBER_BATT_SOC_FIN kept in sync by handle_track_battery.
        # Unlike ODO, battery SoC decreases during a trip, so we keep the
        # most recently tracked value (latest reading during the trip)
        # rather than min/max. Fall back to live sensor only if tracking
        # explicitly never fired (battery_tracking_fired flag), not by
        # comparing values — the first tracked value may coincidentally
        # equal the debut (e.g. SoC didn't change in the first few secs).
        tracked_fin_val = None
        if battery_tracking_fired.get("value"):
            tracked_fin = hass.states.get(NUMBER_BATT_SOC_FIN)
            if tracked_fin and tracked_fin.state not in ["unknown", "unavailable"]:
                try:
                    tracked_fin_val = float(tracked_fin.state)
                except (ValueError, TypeError):
                    tracked_fin_val = None

        if tracked_fin_val is None:
            batt_soc_fin_val = get_sensor_float_value(hass, SENSOR_BATT_SOC, 0.0, fallback_entity=entity_id("sensor.scooter_battery_display"))
        else:
            batt_soc_fin_val = tracked_fin_val

        await hass.services.async_call(
            "number",
            SERVICE_SET_VALUE,
            {
                "entity_id": NUMBER_BATT_SOC_FIN,
                "value": batt_soc_fin_val
            },
            blocking=True
        )

        # 8) Calculate battery consumption
        # Clamp to [0, 100] — a trip cannot consume more than the full pack.
        # Upstream SoC glitches (e.g. >100% on reconnect) must not leak into
        # history.json and downstream sensors.
        battery_debut_val = get_sensor_float_value(hass, NUMBER_BATT_SOC_DEBUT, 0.0)
        raw_consumption = battery_debut_val - batt_soc_fin_val
        batt_consumption = round(max(0.0, min(100.0, raw_consumption)), 1)
        if raw_consumption < 0 or raw_consumption > 100:
            _LOGGER.warning(
                "Battery consumption out of range: debut=%.1f%%, fin=%.1f%%, "
                "raw=%.1f%% -> clamped to %.1f%%",
                battery_debut_val, batt_soc_fin_val, raw_consumption, batt_consumption,
            )
        await set_writable_sensor_value(hass, SENSOR_LAST_TRIP_BATT_CONSUMPTION, batt_consumption)

        # 9) Update trips history FIRST — la validation vit là-bas, et les
        # statistiques ne doivent compter que les trajets réellement
        # enregistrés (un trajet hard-rejeté sur données aberrantes ne doit
        # pas polluer tracked_distance, les compteurs batterie ni la base
        # énergie).
        recorded = await do_update_trips_history(hass, imei=imei, multi_device=multi_device)

        # 10) Update trip statistics using helper (trajets enregistrés
        # uniquement)
        if recorded:
            await update_trip_statistics(hass, distance_val, batt_consumption, imei=imei, multi_device=multi_device)
        else:
            _LOGGER.warning("Trip not recorded (rejected/ignored) — statistics left untouched")

        # 11) Update entities
        await hass.services.async_call(
            "homeassistant",
            "update_entity",
            {
                "entity_id": [
                    SENSOR_TRIP_STATUS,
                    SENSOR_LAST_TRIP_DURATION,
                    SENSOR_LAST_TRIP_AVG_SPEED,
                    SENSOR_LAST_TRIP_BATT_CONSUMPTION,
                    entity_id("sensor.scooter_energy_cost_daily"),
                    entity_id("sensor.scooter_energy_cost_weekly"),
                    entity_id("sensor.scooter_energy_cost_monthly"),
                    entity_id("sensor.scooter_energy_cost_yearly"),
                ]
            },
            blocking=True
        )

        _LOGGER.info(
            "TRIP STOPPED: distance=%.1f km, duration=%.0f min, avg_speed=%.1f km/h, battery=%.1f%% (reason=%s)",
            distance_val, trip_duration_val, avg_speed, batt_consumption, reason
        )

    except Exception as e:
        _LOGGER.error("Error in do_stop_trip: %s", e, exc_info=True)
        detector = get_error_detector(hass)
        if detector:
            detector.record_error(
                ErrorCategory.AUTOMATION_ERROR, ErrorSeverity.ERROR,
                f"do_stop_trip failed: {e}", source="do_stop_trip",
            )
    finally:
        _domain_state[_stop_lock_key] = False

async def do_update_trips_history(hass: HomeAssistant, imei: str = "", multi_device: bool = False) -> bool:
    """Update trip history with validation.

    Args:
        hass: HomeAssistant instance
        imei: IMEI of the scooter (optional for single-device)
        multi_device: Whether multi-device mode is enabled

    Returns:
        True si le trajet a été enregistré dans l'historique, False s'il a
        été rejeté/ignoré ou si l'écriture a échoué (l'appelant s'en sert
        pour ne pas mettre à jour les statistiques cumulées).
    """
    _LOGGER.info("UPDATING TRIP HISTORY")

    def entity_id(base: str) -> str:
        from .helpers import insert_imei_in_entity_id
        return insert_imei_in_entity_id(base, imei, multi_device)

    # Entity IDs for this scooter
    SENSOR_LAST_TRIP_DISTANCE = entity_id("sensor.scooter_last_trip_distance")
    SENSOR_LAST_TRIP_DURATION = entity_id("sensor.scooter_last_trip_duration")
    SENSOR_LAST_TRIP_AVG_SPEED = entity_id("sensor.scooter_last_trip_avg_speed")
    SENSOR_LAST_TRIP_MAX_SPEED = entity_id("sensor.scooter_last_trip_max_speed")
    SENSOR_LAST_TRIP_BATT_CONSUMPTION = entity_id("sensor.scooter_last_trip_battery_consumption")
    INPUT_DT_END_TIME = entity_id("datetime.scooter_end_time")
    INPUT_DT_START_TIME = entity_id("datetime.scooter_start_time")

    try:
        distance_val = get_sensor_float_value(hass, SENSOR_LAST_TRIP_DISTANCE, 0.0)
        duration_val = get_sensor_float_value(hass, SENSOR_LAST_TRIP_DURATION, 0.0)
        avg_val = get_sensor_float_value(hass, SENSOR_LAST_TRIP_AVG_SPEED, 0.0)
        max_val = get_sensor_float_value(hass, SENSOR_LAST_TRIP_MAX_SPEED, 0.0)
        battery_consumed = get_sensor_float_value(hass, SENSOR_LAST_TRIP_BATT_CONSUMPTION, 0.0)

        # === VALIDATION ===
        # Two tiers now:
        #  - HARD REJECT: only physically impossible data (avg speed > 120 km/h
        #    — the scooter is limited to ~100 km/h, so anything above that is
        #    definitely a sensor glitch or a computed value using a wrong
        #    duration/distance).
        #  - SOFT WARN: suspicious but possibly legitimate data is logged and
        #    still recorded. Earlier releases were strict enough to drop real
        #    trips whenever a sensor hiccup produced inconsistent metrics.
        hard_reject_errors = []
        soft_warnings = []

        # Hard reject: superhuman avg speed (physically impossible)
        # L'odomètre ne compte qu'en km entiers : on lui laisse 1 km de marge,
        # sinon « 1 km » (peut-être 100 m réels) en 20 s = 180 km/h et un vrai
        # petit trajet est rejeté.
        if duration_val > 0 and (distance_val - 1) / duration_val * 60 > 120:
            hard_reject_errors.append(f"Speed too high: {avg_val} km/h > 120 km/h")

        # Soft warn: very short trips with high distance
        if duration_val < 1.5 and distance_val > 2:
            soft_warnings.append(f"Trip looks short: {duration_val} min for {distance_val} km")

        # Soft warn: inconsistent speed calculation
        if duration_val > 0 and distance_val > 0:
            calculated_speed = (distance_val / duration_val) * 60
            if avg_val > 0 and abs(calculated_speed - avg_val) / avg_val > 0.3:
                soft_warnings.append(
                    f"Speed inconsistency: calculated={calculated_speed:.1f} vs recorded={avg_val}"
                )

        # Soft warn: max_speed=0 but avg>10 (max_speed sensor didn't update)
        if max_val == 0 and avg_val > 10:
            soft_warnings.append(f"Max speed is 0 but avg is {avg_val} km/h")

        # Run error detector trip anomaly checks
        detector = get_error_detector(hass)
        if detector:
            detector.check_trip_anomaly(
                distance=distance_val, duration=duration_val, avg_speed=avg_val,
                max_speed=max_val, battery_consumption=battery_consumed,
            )

        if hard_reject_errors:
            _LOGGER.error("⚠️ TRIP REJECTED - Data validation failed:")
            for error in hard_reject_errors:
                _LOGGER.error("  - %s", error)
            _LOGGER.error(
                "Trip data: distance=%.1f km, duration=%.1f min, avg_speed=%.1f km/h, battery=%.1f%%",
                distance_val, duration_val, avg_val, battery_consumed,
            )
            await log_event(hass, f"Trip rejected: {', '.join(hard_reject_errors)}")
            return False

        if soft_warnings:
            _LOGGER.warning(
                "Trip has suspicious data but will be recorded anyway: %s | "
                "distance=%.1f km, duration=%.1f min, avg_speed=%.1f km/h, max_speed=%.1f km/h",
                ", ".join(soft_warnings),
                distance_val, duration_val, avg_val, max_val,
            )

        # === Check for minimal trip data ===
        # Un "trajet" sans aucun déplacement ni durée (allumage du contact à
        # distance, séquence status 3→2→0) n'a rien à faire dans l'historique.
        # Les vrais petits trajets (<1 km, l'ODO est entier) gardent une durée
        # > 1 min et restent enregistrés.
        if distance_val <= 0 and duration_val <= 1:
            _LOGGER.info("Trajet vide ignoré (distance=%.1f km, durée=%.1f min)",
                         distance_val, duration_val)
            await log_event(hass, "Trip ignored (no movement)")
            return False
        if distance_val <= 0 or duration_val <= 0:
            _LOGGER.warning("Short trip detected (distance=%.1f, duration=%.1f), recording anyway",
                          distance_val, duration_val)
            await log_event(hass, "Trip recorded (short trip - may not count in stats)")
        
        end_time_st = hass.states.get(INPUT_DT_END_TIME)
        start_time_st = hass.states.get(INPUT_DT_START_TIME)

        def parse_and_validate(ts):
            try:
                dt = dt_util.parse_datetime(ts)
                if dt and dt.year >= 2000:
                    dt = dt_util.as_local(dt)
                    return dt.isoformat()
                if dt and dt.year < 2000:
                    _LOGGER.warning("Invalid date detected (year < 2000): %s", dt)
                return None
            except (ValueError, TypeError, AttributeError):
                return None

        end_time_str = None
        start_time_str = None

        if end_time_st and end_time_st.state not in ["unknown","unavailable"]:
            end_time_str = parse_and_validate(end_time_st.state)

        if start_time_st and start_time_st.state not in ["unknown","unavailable"]:
            start_time_str = parse_and_validate(start_time_st.state)

        if not end_time_str or not start_time_str:
            _LOGGER.warning("Invalid dates, using current time")
            current_time = dt_util.as_local(dt_util.now()).isoformat()
            if not end_time_str:
                end_time_str = current_time
            if not start_time_str:
                if duration_val > 0:
                    start_dt = dt_util.now() - timedelta(minutes=duration_val)
                    start_time_str = dt_util.as_local(start_dt).isoformat()
                else:
                    start_time_str = current_time

        # Garde de cohérence : end < start ne doit jamais partir en historique
        # (mélange horloge trames MQTT / horloge HA possible sur les fallbacks).
        try:
            _start_dt = dt_util.parse_datetime(start_time_str)
            _end_dt = dt_util.parse_datetime(end_time_str)
            if _start_dt and _end_dt and _end_dt < _start_dt:
                _LOGGER.warning("end_time (%s) antérieur à start_time (%s) — aligné sur start_time",
                                end_time_str, start_time_str)
                end_time_str = start_time_str
        except (ValueError, TypeError):
            pass

        # Get outdoor temperature from configured source (scooter or external)
        outdoor_temp_entity_id = get_outdoor_temperature_entity_id(hass, imei, multi_device)
        outdoor_temp = hass.states.get(outdoor_temp_entity_id)
        temp_val = float(outdoor_temp.state) if outdoor_temp and outdoor_temp.state not in ["unknown","unavailable"] else 0

        # battery_consumed vient du capteur writable rempli par do_stop_trip
        # (étape 8) : déjà clampé [0, 100] et basé sur le tracking continu.
        # L'ancien recalcul local (debut − fin, avec fallback 0 sur capteur
        # indisponible) réintroduisait les aberrations que l'étape 8 venait
        # d'éliminer : fin indisponible → « consommation » = tout le debut
        # (efficiences ×10 dans l'historique) ; debut ET fin indisponibles →
        # battery=0 (≈48 % des trajets historiques).

        # Énergie du trajet pour le Wh/km : MESURÉE par le compteur du
        # scooter entre le départ et l'arrivée. Le calcul d'origine
        # (% consommés × 5,6 kWh) surestime de 15-20 % sur une batterie usée
        # (60,6 Wh/km affichés pour 50 mesurés le 2026-11-10). Compteur
        # illisible ou immobile : % × capacité réelle estimée ; à défaut
        # history.sh garde % × 5,6 kWh.
        start_energy = hass.data.get(DOMAIN, {}).get(_tracking_key(imei), {}).get("energy_at_start")
        end_energy = get_sensor_float_value(hass, entity_id("sensor.scooter_energy_consumption"), 0.0)
        capacity = get_sensor_float_value(hass, entity_id("sensor.scooter_battery_capacity"), 0.0)
        energy_wh = 0.0
        if start_energy and 0 < end_energy - start_energy <= DEFAULT_BATTERY_CAPACITY:
            energy_wh = (end_energy - start_energy) * 1000
        elif 3.0 <= capacity <= 7.0:
            energy_wh = battery_consumed / 100 * capacity * 1000

        _LOGGER.info("Calling update_history: distance=%.1f, duration=%.0f, avg_speed=%.1f, energy=%.0f Wh",
                     distance_val, duration_val, avg_val, energy_wh)

        success = await update_history(
            hass,
            history_file=get_history_file(imei, multi_device),
            avg_speed=avg_val,
            distance=distance_val,
            duration=duration_val,
            start_time=start_time_str,
            end_time=end_time_str,
            max_speed=max_val,
            battery=battery_consumed,
            outdoor_temp=temp_val,
            energy_wh=energy_wh
        )

        if success:
            await log_event(hass, f"Trip recorded: {distance_val}km in {duration_val}min")
            _LOGGER.info("History updated successfully")
        else:
            await log_event(hass, "Failed to update trips history")
            _LOGGER.error("Failed to update history")

        return bool(success)

    except Exception as exc:
        _LOGGER.error("Error in do_update_trips_history: %s", exc)
        detector = get_error_detector(hass)
        if detector:
            detector.record_error(
                ErrorCategory.DATA_INTEGRITY, ErrorSeverity.ERROR,
                f"Trip history update failed: {exc}", source="do_update_trips_history",
            )
        return False


async def setup_persistent_sensors_update(hass: HomeAssistant, imei: str = "", multi_device: bool = False):
    """Setup persistent sensors auto-update.

    Updates persistent sensors (battery, odo, regeneration) when MQTT data changes.
    These sensors retain their last value even when the scooter is offline.

    Args:
        hass: HomeAssistant instance
        imei: IMEI of the scooter
        multi_device: Whether to use multi-device entity naming
    """
    _LOGGER.info("Setting up persistent sensors auto-update for IMEI: %s", imei)

    def entity_id(base: str) -> str:
        from .helpers import insert_imei_in_entity_id
        return insert_imei_in_entity_id(base, imei, multi_device)

    # Entity IDs for this scooter
    SENSOR_BATT_SOC = entity_id("sensor.silence_scooter_battery_soc")
    SENSOR_SCOOTER_ODO = entity_id("sensor.silence_scooter_odo")

    async def update_battery_display(event):
        """Update scooter_battery_display from sensor.silence_scooter_battery_soc."""
        new_state = event.data.get("new_state")
        if not new_state or new_state.state in ["unknown", "unavailable", None]:
            return

        try:
            battery_value = float(new_state.state)
            await set_writable_sensor_value(hass, entity_id("sensor.scooter_battery_display"), battery_value)
            _LOGGER.debug("Battery display updated: %.1f%%", battery_value)
        except (ValueError, TypeError) as e:
            _LOGGER.warning("Failed to update battery display: %s", e)

    async def update_odo_display(event):
        """Update scooter_odo_display from sensor.silence_scooter_odo."""
        new_state = event.data.get("new_state")
        if not new_state or new_state.state in ["unknown", "unavailable", None]:
            return

        try:
            odo_value = float(new_state.state)
            await set_writable_sensor_value(hass, entity_id("sensor.scooter_odo_display"), odo_value)
            _LOGGER.debug("ODO display updated: %.1f km", odo_value)
        except (ValueError, TypeError) as e:
            _LOGGER.warning("Failed to update ODO display: %s", e)

    async def update_regeneration_percentage(event):
        """Update scooter_battery_percentage_regeneration from energy sensors."""
        discharged_st = hass.states.get(entity_id("sensor.silence_scooter_discharged_energy"))
        regenerated_st = hass.states.get(entity_id("sensor.silence_scooter_regenerated_energy"))

        if not discharged_st or not regenerated_st:
            return

        if discharged_st.state in ["unknown", "unavailable", None] or \
           regenerated_st.state in ["unknown", "unavailable", None]:
            return

        try:
            discharged = float(discharged_st.state)
            regenerated = float(regenerated_st.state)

            if discharged > 0:
                percentage = (regenerated / discharged) * 100
                await set_writable_sensor_value(hass, entity_id("sensor.scooter_battery_percentage_regeneration"), round(percentage, 2))
                _LOGGER.debug("Regeneration percentage updated: %.2f%%", percentage)
        except (ValueError, TypeError) as e:
            _LOGGER.warning("Failed to update regeneration percentage: %s", e)

    remove_battery = async_track_state_change_event(
        hass, [SENSOR_BATT_SOC], update_battery_display
    )

    remove_odo = async_track_state_change_event(
        hass, [SENSOR_SCOOTER_ODO], update_odo_display
    )

    remove_regeneration = async_track_state_change_event(
        hass,
        [entity_id("sensor.silence_scooter_discharged_energy"), entity_id("sensor.silence_scooter_regenerated_energy")],
        update_regeneration_percentage
    )

    _LOGGER.info("Persistent sensors auto-update configured")

    return [remove_battery, remove_odo, remove_regeneration]