"""Automations for the Silence Scooter integration."""
import logging
import asyncio
import subprocess

from datetime import datetime, timedelta
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.components.number import SERVICE_SET_VALUE
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.exceptions import HomeAssistantError
from .const import (
    DOMAIN,
    CONF_CONFIRMATION_DELAY,
    CONF_PAUSE_MAX_DURATION,
    CONF_WATCHDOG_DELAY,
    CONF_OUTDOOR_TEMP_SOURCE,
    CONF_OUTDOOR_TEMP_ENTITY,
    DEFAULT_CONFIRMATION_DELAY,
    DEFAULT_PAUSE_MAX_DURATION,
    DEFAULT_WATCHDOG_DELAY,
    DEFAULT_OUTDOOR_TEMP_SOURCE,
    OUTDOOR_TEMP_SOURCE_SCOOTER,
    OUTDOOR_TEMP_SOURCE_EXTERNAL,
    SENSOR_SCOOTER_AMBIENT_TEMP,
)
from homeassistant.util import dt as dt_util
from .helpers import log_event, update_history, is_date_valid, get_valid_datetime
from .errors import ErrorCategory, ErrorSeverity, get_error_detector

STARTUP_TIME = dt_util.utcnow()

_LOGGER = logging.getLogger(__name__)


def get_config_value(hass: HomeAssistant, key: str, default: any) -> any:
    """Get configuration value from config_entry with fallback to default."""
    try:
        config = hass.data.get(DOMAIN, {}).get("config", {})
        return config.get(key, default)
    except Exception as e:
        _LOGGER.warning("Error getting config value %s: %s, using default %s", key, e, default)
        return default


def get_outdoor_temperature_entity_id(hass: HomeAssistant) -> str:
    """Get the outdoor temperature sensor entity ID based on configuration.

    Returns:
        Entity ID of the temperature sensor to use (scooter or external)
    """
    temp_source = get_config_value(hass, CONF_OUTDOOR_TEMP_SOURCE, DEFAULT_OUTDOOR_TEMP_SOURCE)

    if temp_source == OUTDOOR_TEMP_SOURCE_EXTERNAL:
        # Use external weather sensor if configured
        external_entity = get_config_value(hass, CONF_OUTDOOR_TEMP_ENTITY, "")
        if external_entity:
            return external_entity
        else:
            _LOGGER.warning("External temperature source selected but no entity configured, falling back to scooter sensor")
            return SENSOR_SCOOTER_AMBIENT_TEMP
    else:
        # Use scooter ambient temperature sensor (default)
        return SENSOR_SCOOTER_AMBIENT_TEMP


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
            if is_date_valid(last_moving.state):
                _LOGGER.info("Using last_moving_time: %s", last_moving.state)
                return last_moving.state
        except Exception as e:
            _LOGGER.debug("Could not use last_moving_time: %s", e)

    scooter_status = hass.states.get(entity_id("sensor.scooter_status"))
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
        trip_duration = max(0, round(total_duration - pause_duration))

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
    SENSOR_LAT = entity_id("sensor.silence_scooter_silence_latitude")
    SENSOR_LON = entity_id("sensor.silence_scooter_silence_longitude")
    SENSOR_BATT_SOC = entity_id("sensor.silence_scooter_battery_soc")

    # Pour la logique "Last start"
    INPUT_DT_END_TIME = entity_id("datetime.scooter_end_time")
    SENSOR_MAX_SPEED = entity_id("sensor.scooter_last_trip_max_speed")  # Writable sensor
    NUMBER_ODO_DEBUT = entity_id("number.scooter_odo_debut")
    INPUT_DT_START_TIME = entity_id("datetime.scooter_start_time")
    NUMBER_BATT_SOC_DEBUT = entity_id("number.scooter_battery_soc_debut")

    # Pour la mise à jour device_tracker
    DEVICE_TRACKER_ID = entity_id("silence_scooter")

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
    BINARY_SENSOR_BATTERY_IN = entity_id("binary_sensor.silence_scooter_battery_in")

    #
    # Dictionnaire pour stocker les tâches planifiées
    # - nécessaire pour la gestion du "for: 00:02:00" (2 minutes)
    #
    scheduled_tasks = {}

    # Timestamp of the last trip start. Used by the ODO/battery tracking
    # handlers to skip stale-value repair during the first few seconds of
    # a trip, avoiding a race with _do_last_start() writing odo_debut.
    last_trip_start_monotonic = {"value": None}

    # Flags indicating whether tracking handlers have fired at least once
    # during the current trip. Reset at trip start. Used by do_stop_trip
    # to distinguish "tracked value" from "never tracked" (the first
    # tracked value may coincidentally equal the debut value).
    odo_tracking_fired = {"value": False}
    battery_tracking_fired = {"value": False}

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

                hass.loop.create_task(
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
            hass.loop.create_task(_update_last_moving_time())

    async def _update_last_moving_time():
        # Use the scooter's last MQTT update timestamp instead of now()
        # This avoids adding ~5min of artificial delay in the garage scenario
        # where the scooter goes unavailable without sending status=0
        last_update_state = hass.states.get(SENSOR_SCOOTER_LAST_UPDATE)
        if last_update_state and last_update_state.state not in ["unknown", "unavailable"]:
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

            # Arrêt immédiat si scooter éteint (status=0) ou batterie retirée
            # Data analysis confirms status=0 always follows the real shutdown
            # sequence (4→3→2→0) and never appears as a false positive during riding.
            # Network drops during riding produce "unavailable", not "0".
            should_stop_immediately = False

            if not raw_state or raw_state.state in ["unknown", "unavailable"]:
                _LOGGER.info("Scooter unavailable -> arret differe (tolerance)")
            elif raw_state.state in ["0", "0.0"]:
                should_stop_immediately = True
                _LOGGER.info("Scooter eteint (status=0, sequence 3->2->0) -> arret immediat")
            elif not battery_present:
                should_stop_immediately = True
                _LOGGER.info("Batterie retiree -> arret immediat")

            # Définir _immediate_stop AVANT son utilisation (sinon UnboundLocalError)
            async def _immediate_stop():
                """Arrêt immédiat du trajet sans délai."""
                _LOGGER.info("🚨 IMMEDIATE STOP: arrêt immédiat du trajet")

                # Utiliser last_moving_time au lieu de l'heure actuelle
                last_moving = hass.states.get(INPUT_DT_LAST_MOVING)
                if last_moving and last_moving.state not in ["unknown", "unavailable"]:
                    end_time_str = last_moving.state
                else:
                    # Fallback sur l'heure actuelle si last_moving_time indisponible
                    end_time_str = dt_util.now().isoformat()

                await hass.services.async_call(
                    "datetime",
                    "set_value",
                    {
                        "entity_id": INPUT_DT_END_TIME,
                        "datetime": end_time_str
                    },
                    blocking=True
                )

                await do_log_event(hass, "Immediate stop - scooter off/unavailable")
                await do_stop_trip(hass, imei=imei, multi_device=multi_device, reason="immediate")

            if should_stop_immediately:
                _LOGGER.info("IMMEDIATE STOP triggered (scooter off or battery removed)")
                hass.loop.create_task(_immediate_stop())
                return
            else:
                _LOGGER.info("DELAYED STOP triggered (2min + 5min timer)")

                # Définir les fonctions async AVANT de les utiliser
                def _start_tolerance_timer():
                    """Démarre le timer de tolérance (durée configurable)."""
                    # Get configured pause duration (in minutes)
                    pause_duration_min = get_config_value(hass, CONF_PAUSE_MAX_DURATION, DEFAULT_PAUSE_MAX_DURATION)
                    # Convert to seconds
                    duration_seconds = pause_duration_min * 60

                    # Cancel any existing tolerance timer
                    if "tolerance_timer" in scheduled_tasks:
                        scheduled_tasks["tolerance_timer"].cancel()

                    # Schedule the callback that will stop the trip when timer expires
                    async def _on_tolerance_expired():
                        """Appelé quand le timer de tolérance arrive à expiration."""
                        scheduled_tasks.pop("tolerance_timer", None)
                        _LOGGER.info("⏱️ Timer de tolérance terminé (%d min), arrêt définitif du trajet", pause_duration_min)
                        await do_log_event(hass, f"Trip auto-stopped: tolerance timer expired ({pause_duration_min}min)")
                        await do_stop_trip(hass, imei=imei, multi_device=multi_device, reason="tolerance-timeout")

                    task = hass.loop.call_later(duration_seconds, lambda: hass.loop.create_task(_on_tolerance_expired()))
                    scheduled_tasks["tolerance_timer"] = task
                    _LOGGER.info(f"✓ Tolerance timer started successfully ({pause_duration_min} min = {duration_seconds}s)")

                async def _confirm_off():
                    """Confirme l'arrêt du trajet après le délai de confirmation."""
                    confirmation_delay = get_config_value(hass, CONF_CONFIRMATION_DELAY, DEFAULT_CONFIRMATION_DELAY)
                    _LOGGER.info(f"⏰ CONFIRM OFF: vérification après {confirmation_delay}s d'attente")
                    scheduled_tasks.pop("trip_off_delay", None)

                    # Annulation du timer de tolérance s'il est encore actif
                    tolerance_task = scheduled_tasks.pop("tolerance_timer", None)
                    if tolerance_task:
                        tolerance_task.cancel()
                        _LOGGER.debug("Timer de tolérance annulé (arrêt confirmé)")

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
                # Enregistrer le début de la pause
                hass.loop.create_task(
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

                # Annuler toute tâche précédente
                if "trip_off_delay" in scheduled_tasks:
                    scheduled_tasks["trip_off_delay"].cancel()

                # 1) Planifie l'arrêt après le délai de confirmation configurable
                confirmation_delay = get_config_value(hass, CONF_CONFIRMATION_DELAY, DEFAULT_CONFIRMATION_DELAY)
                task = hass.loop.call_later(confirmation_delay, lambda: hass.loop.create_task(_confirm_off()))
                scheduled_tasks["trip_off_delay"] = task

                # 2) Démarre le timer de tolérance (durée configurable)
                _start_tolerance_timer()

                _LOGGER.info("📋 Tâches planifiées : %s", list(scheduled_tasks.keys()))
    #

    remove_trip_status_off = async_track_state_change_event(
        hass, [SENSOR_TRIP_STATUS], handle_trip_status_off
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

                # Enregistrer la fin de la pause
                pause_start = hass.states.get(entity_id("datetime.scooter_pause_start"))
                if pause_start and pause_start.state not in ["unknown", "unavailable"]:
                    hass.loop.create_task(_record_pause_end())

                hass.loop.create_task(do_log_event(hass, "Pause stopped, trip restarted"))
    
    async def _record_pause_end():
        """Enregistre la durée de la pause qui vient de se terminer."""
        try:
            pause_start = hass.states.get(entity_id("datetime.scooter_pause_start"))
            if pause_start and pause_start.state not in ["unknown", "unavailable"]:
                pause_start_dt = dt_util.parse_datetime(pause_start.state)
                if pause_start_dt:
                    pause_duration = (dt_util.now() - dt_util.as_local(pause_start_dt)).total_seconds() / 60

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
            # => datetime.scooter_end_time = datetime.scooter_last_moving_time
            # => do_stop_trip
            # => input_boolean.stop_trip_now = off
            hass.loop.create_task(_process_stop_trip_now())

    async def _process_stop_trip_now():
        await do_log_event(hass, "Manual stop button clicked")

        # Annuler toutes les tâches programmées si existantes
        if scheduled_tasks.get("trip_off_delay"):
            scheduled_tasks["trip_off_delay"].cancel()
            scheduled_tasks.pop("trip_off_delay", None)

        if scheduled_tasks.get("tolerance_timer"):
            scheduled_tasks["tolerance_timer"].cancel()
            scheduled_tasks.pop("tolerance_timer", None)

        # datetime.scooter_end_time = scooter_last_moving_time
        last_moving = hass.states.get(INPUT_DT_LAST_MOVING)
        end_time_value = last_moving.state if last_moving else dt_util.now().isoformat()
        await hass.services.async_call(
            "datetime",
            "set_value",
            {
                "entity_id": INPUT_DT_END_TIME,
                "datetime": end_time_value
            },
            blocking=True
        )

        # do_stop_trip
        await do_stop_trip(hass, imei=imei, multi_device=multi_device, reason="Manual button")

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
            
            # Vérifier que le scooter est réellement en mouvement (status=4)
            # Status=3 (prêt à conduire) ne suffit pas — un allumage à distance donne aussi status=3
            scooter_status = hass.states.get(SENSOR_SCOOTER_STATUS)
            if scooter_status and scooter_status.state not in ["unknown", "unavailable"]:
                try:
                    status = float(scooter_status.state)
                    if status != 4.0:
                        _LOGGER.info("⚠️ Scooter status=%s, ignoring start trigger (attendu: 4=en mouvement)", status)
                        return
                except (ValueError, TypeError):
                    _LOGGER.warning("Could not read scooter status, continuing anyway")
            
            _LOGGER.info("✅ START CONFIRMED: démarrage du trajet (scooter status OK)")
            hass.loop.create_task(_do_last_start())

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

        # (5) datetime.scooter_start_time => now
        now_str = dt_util.now().isoformat()
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
        hass.loop.create_task(_do_update_max_speed(current_speed))

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

        if not is_trip_active():
            return

        # Don't track stale (>24h) active trips — these are bugs (trip
        # never got stopped), and updating their counters pollutes stats.
        start_time_st = hass.states.get(INPUT_DT_START_TIME)
        if start_time_st and is_date_valid(start_time_st.state):
            start_dt = get_valid_datetime(start_time_st.state)
            if start_dt and (dt_util.now() - start_dt).total_seconds() > 86400:
                return

        hass.loop.create_task(_do_track_odo(new_odo, old_state))

    async def _do_track_odo(new_odo: float, old_state):
        # Skip repair logic during the first 5 seconds after a trip start
        # to avoid racing with _do_last_start() writing odo_debut.
        import time as _time
        from datetime import timedelta
        start_mono = last_trip_start_monotonic.get("value")
        within_grace = start_mono is not None and (_time.monotonic() - start_mono) < 5.0

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

        if not is_trip_active():
            return

        # Don't track stale (>24h) active trips.
        start_time_st = hass.states.get(INPUT_DT_START_TIME)
        if start_time_st and is_date_valid(start_time_st.state):
            start_dt = get_valid_datetime(start_time_st.state)
            if start_dt and (dt_util.now() - start_dt).total_seconds() > 86400:
                return

        hass.loop.create_task(_do_track_battery(new_soc, old_state))

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

        # Skip repair during grace period after trip start or after HA restart.
        import time as _time
        from datetime import timedelta
        start_mono = last_trip_start_monotonic.get("value")
        within_grace = start_mono is not None and (_time.monotonic() - start_mono) < 5.0
        within_startup = (dt_util.utcnow() - STARTUP_TIME) < timedelta(seconds=10)
        if within_grace or within_startup:
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
    # 8. "Scooter - Update Device Tracker Position"
    #    => changes in sensor.silence_scooter_silence_latitude,
    #                   sensor.silence_scooter_silence_longitude,
    #                   sensor.silence_scooter_battery_soc
    #
    @callback
    def handle_update_tracker(event):
        hass.loop.create_task(_do_update_tracker())

    async def _do_update_tracker():
        lat = 0.0
        lon = 0.0
        batt = 0
        lat_state = hass.states.get(SENSOR_LAT)
        lon_state = hass.states.get(SENSOR_LON)
        batt_state = hass.states.get(SENSOR_BATT_SOC)

        if lat_state and lat_state.state not in ["unknown", "unavailable"]:
            try:
                lat = float(lat_state.state)
            except (ValueError, TypeError):
                lat = 0.0

        if lon_state and lon_state.state not in ["unknown", "unavailable"]:
            try:
                lon = float(lon_state.state)
            except (ValueError, TypeError):
                lon = 0.0

        if batt_state and batt_state.state not in ["unknown", "unavailable"]:
            try:
                batt = int(float(batt_state.state))
            except (ValueError, TypeError):
                batt = 0

        await hass.services.async_call(
            "device_tracker",
            "see",
            {
                "dev_id": DEVICE_TRACKER_ID,
                "gps": [lat, lon],
                "battery": batt
            },
            blocking=True
        )

    remove_update_tracker = async_track_state_change_event(
        hass, [SENSOR_LAT, SENSOR_LON, SENSOR_BATT_SOC], handle_update_tracker
    )

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
            
            # Vérifier la dernière mise à jour du scooter
            last_update = hass.states.get(SENSOR_SCOOTER_LAST_UPDATE)
            if not last_update or last_update.state in ["unknown", "unavailable"]:
                return
            
            try:
                last_update_dt = dt_util.parse_datetime(last_update.state)
                if not last_update_dt:
                    return

                # Si pas de mise à jour depuis plus de X minutes (configurable)
                watchdog_delay_min = get_config_value(hass, CONF_WATCHDOG_DELAY, DEFAULT_WATCHDOG_DELAY)
                watchdog_delay_sec = watchdog_delay_min * 60
                if (dt_util.utcnow() - dt_util.as_utc(last_update_dt)).total_seconds() > watchdog_delay_sec:
                    _LOGGER.info(f"🔔 Watchdog: Scooter non mis à jour depuis >{watchdog_delay_min}min, arrêt du trajet")
                    
                    # Vérifier qu'on n'a pas déjà une tâche d'arrêt en cours
                    if "trip_off_delay" not in scheduled_tasks:
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


    # Return all cancel listeners for cleanup
    cancel_listeners = [
        remove_energy_baseline_init,
        remove_tracker_dernier_mouvement,
        remove_trip_status_off,
        remove_stop_timer_if_restart,
        remove_stop_trip_now,
        remove_last_start,
        remove_update_max_speed,
        remove_track_odo,
        remove_track_battery,
        remove_update_tracker,
        watchdog_remove,
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
        battery_debut_val = get_sensor_float_value(hass, NUMBER_BATT_SOC_DEBUT, 0.0)
        batt_consumption = round(max(0, battery_debut_val - batt_soc_fin_val), 1)
        await set_writable_sensor_value(hass, SENSOR_LAST_TRIP_BATT_CONSUMPTION, batt_consumption)

        # 9) Update trip statistics using helper
        await update_trip_statistics(hass, distance_val, batt_consumption, imei=imei, multi_device=multi_device)

        # 10) Update entities
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

        # 11) Update trips history
        await do_update_trips_history(hass, imei=imei, multi_device=multi_device)

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

async def do_update_trips_history(hass: HomeAssistant, imei: str = "", multi_device: bool = False):
    """Update trip history with validation.

    Args:
        hass: HomeAssistant instance
        imei: IMEI of the scooter (optional for single-device)
        multi_device: Whether multi-device mode is enabled
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
    NUMBER_BATT_SOC_DEBUT = entity_id("number.scooter_battery_soc_debut")
    NUMBER_BATT_SOC_FIN = entity_id("number.scooter_battery_soc_fin")

    try:
        distance_val = get_sensor_float_value(hass, SENSOR_LAST_TRIP_DISTANCE, 0.0)
        duration_val = get_sensor_float_value(hass, SENSOR_LAST_TRIP_DURATION, 0.0)
        avg_val = get_sensor_float_value(hass, SENSOR_LAST_TRIP_AVG_SPEED, 0.0)
        max_val = get_sensor_float_value(hass, SENSOR_LAST_TRIP_MAX_SPEED, 0.0)
        battery_consumed = get_sensor_float_value(hass, SENSOR_LAST_TRIP_BATT_CONSUMPTION, 0.0)

        # === VALIDATION: Reject obviously invalid trips ===
        validation_errors = []

        # Reject very short trips with high distance (impossible physics)
        if duration_val < 1.5 and distance_val > 2:
            validation_errors.append(f"Trip too short: {duration_val} min for {distance_val} km")

        # Reject superhuman speeds (scooter limited to ~100 km/h)
        if avg_val > 120:
            validation_errors.append(f"Speed too high: {avg_val} km/h > 120 km/h")

        # Check speed consistency: compare recorded speed vs calculated speed
        # If they differ by more than 30%, data is inconsistent
        if duration_val > 0 and distance_val > 0:
            calculated_speed = (distance_val / duration_val) * 60
            # If stored avg_speed differs by more than 30% from calculated, reject
            if avg_val > 0 and abs(calculated_speed - avg_val) / avg_val > 0.3:
                validation_errors.append(f"Speed inconsistency: calculated={calculated_speed:.1f} vs recorded={avg_val}")

        # If max speed is 0 but average speed is high, sensors were not working
        if max_val == 0 and avg_val > 10:
            validation_errors.append(f"Max speed is 0 but avg is {avg_val} km/h")

        # Run error detector trip anomaly checks
        detector = get_error_detector(hass)
        if detector:
            detector.check_trip_anomaly(
                distance=distance_val, duration=duration_val, avg_speed=avg_val,
                max_speed=max_val, battery_consumption=battery_consumed,
            )

        if validation_errors:
            _LOGGER.error("⚠️ TRIP REJECTED - Data validation failed:")
            for error in validation_errors:
                _LOGGER.error("  - %s", error)
            _LOGGER.error("Trip data: distance=%.1f km, duration=%.1f min, avg_speed=%.1f km/h, battery=%.1f%%",
                         distance_val, duration_val, avg_val, battery_consumed)
            await log_event(hass, f"Trip rejected: {', '.join(validation_errors)}")
            return

        # === Check for minimal trip data ===
        is_valid_trip = distance_val > 0 or duration_val > 0
        if not is_valid_trip:
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
        
        # Autres valeurs
        battery_debut = hass.states.get(NUMBER_BATT_SOC_DEBUT)
        battery_fin = hass.states.get(NUMBER_BATT_SOC_FIN)

        # Get outdoor temperature from configured source (scooter or external)
        outdoor_temp_entity_id = get_outdoor_temperature_entity_id(hass)
        outdoor_temp = hass.states.get(outdoor_temp_entity_id)

        batt_debut_val = float(battery_debut.state) if battery_debut and battery_debut.state not in ["unknown","unavailable"] else 0
        batt_fin_val = float(battery_fin.state) if battery_fin and battery_fin.state not in ["unknown","unavailable"] else 0
        temp_val = float(outdoor_temp.state) if outdoor_temp and outdoor_temp.state not in ["unknown","unavailable"] else 0
        
        battery_consumed = abs(round(batt_debut_val - batt_fin_val, 1))

        _LOGGER.info("Calling update_history: distance=%.1f, duration=%.0f, avg_speed=%.1f",
                     distance_val, duration_val, avg_val)

        success = await update_history(
            hass,
            avg_speed=avg_val,
            distance=distance_val,
            duration=duration_val,
            start_time=start_time_str,
            end_time=end_time_str,
            max_speed=max_val,
            battery=battery_consumed,
            outdoor_temp=temp_val
        )

        if success:
            await log_event(hass, f"Trip recorded: {distance_val}km in {duration_val}min")
            _LOGGER.info("History updated successfully")
        else:
            await log_event(hass, "Failed to update trips history")
            _LOGGER.error("Failed to update history")

    except Exception as exc:
        _LOGGER.error("Error in do_update_trips_history: %s", exc)
        detector = get_error_detector(hass)
        if detector:
            detector.record_error(
                ErrorCategory.DATA_INTEGRITY, ErrorSeverity.ERROR,
                f"Trip history update failed: {exc}", source="do_update_trips_history",
            )


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