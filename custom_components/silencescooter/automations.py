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
from homeassistant.components.timer import EVENT_TIMER_FINISHED
from homeassistant.components.number import SERVICE_SET_VALUE
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.exceptions import HomeAssistantError
from .const import (
    DOMAIN,
    CONF_CONFIRMATION_DELAY,
    CONF_PAUSE_MAX_DURATION,
    CONF_WATCHDOG_DELAY,
    DEFAULT_CONFIRMATION_DELAY,
    DEFAULT_PAUSE_MAX_DURATION,
    DEFAULT_WATCHDOG_DELAY,
)
from homeassistant.util import dt as dt_util
from .helpers import log_event, update_history

STARTUP_TIME = datetime.utcnow()

_LOGGER = logging.getLogger(__name__)


def get_config_value(hass: HomeAssistant, key: str, default: any) -> any:
    """Get configuration value from config_entry with fallback to default."""
    try:
        config = hass.data.get(DOMAIN, {}).get("config", {})
        return config.get(key, default)
    except Exception as e:
        _LOGGER.warning(f"Error getting config value {key}: {e}, using default {default}")
        return default


def get_sensor_float_value(hass: HomeAssistant, entity_id: str, default: float = 0.0) -> float:
    """Safely get float value from sensor state.

    Args:
        hass: HomeAssistant instance
        entity_id: Entity ID to read
        default: Default value if sensor unavailable or invalid

    Returns:
        Float value from sensor or default
    """
    state = hass.states.get(entity_id)
    if state and state.state not in ["unknown", "unavailable"]:
        try:
            return float(state.state)
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


def determine_trip_end_timestamp(hass: HomeAssistant) -> str:
    """Determine the best available end timestamp for the trip.

    Priority:
    1. datetime.scooter_end_time (if already set and valid)
    2. datetime.scooter_last_moving_time (last time scooter was moving)
    3. sensor.silence_scooter_last_update (if scooter unavailable)
    4. Current time (fallback)

    Returns:
        Timestamp string in format "YYYY-MM-DD HH:MM:SS"
    """
    end_time_current = hass.states.get("datetime.scooter_end_time")
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

    last_moving = hass.states.get("datetime.scooter_last_moving_time")
    if last_moving and last_moving.state not in ["unknown", "unavailable"]:
        try:
            from .helpers import is_date_valid
            if is_date_valid(last_moving.state):
                _LOGGER.info("Using last_moving_time: %s", last_moving.state)
                return last_moving.state
        except Exception as e:
            _LOGGER.debug("Could not use last_moving_time: %s", e)

    scooter_status = hass.states.get("sensor.scooter_status")
    if scooter_status and scooter_status.state in ["unknown", "unavailable"]:
        last_up = hass.states.get("sensor.silence_scooter_last_update")
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
    end_time_str: str
) -> float:
    """Calculate trip duration in minutes (net of pauses).

    Args:
        hass: HomeAssistant instance
        start_time_str: Start time string
        end_time_str: End time string

    Returns:
        Trip duration in minutes (0 if calculation fails)
    """
    try:
        from .helpers import is_date_valid, get_valid_datetime

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
        pause_duration = get_sensor_float_value(hass, "number.scooter_pause_duration", 0.0)
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
    batt_consumption: float
) -> None:
    """Update cumulative trip statistics.

    Args:
        hass: HomeAssistant instance
        distance: Trip distance in km
        batt_consumption: Battery consumption in %
    """
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
    energy_val = get_sensor_float_value(hass, "sensor.scooter_energy_consumption", 0.0)
    await hass.services.async_call(
        "number",
        SERVICE_SET_VALUE,
        {
            "entity_id": "number.scooter_energy_consumption_base",
            "value": energy_val
        },
        blocking=True
    )


# ============================================================================
# END OF HELPER FUNCTIONS
# ============================================================================

# Entités et timers concernés
SENSOR_IS_MOVING = "sensor.scooter_is_moving"
SENSOR_TRIP_STATUS = "sensor.scooter_trip_status"
TIMER_STOP_TOLERANCE = "timer.scooter_stop_trip_tolerance"
INPUT_DT_LAST_MOVING = "datetime.scooter_last_moving_time"
SWITCH_STOP_NOW = "switch.stop_trip_now"

SENSOR_SCOOTER_SPEED = "sensor.silence_scooter_speed"
SENSOR_LAT = "sensor.silence_scooter_silence_latitude"
SENSOR_LON = "sensor.silence_scooter_silence_longitude"
SENSOR_BATT_SOC = "sensor.silence_scooter_battery_soc"

# Pour la logique "Last start"
INPUT_DT_END_TIME = "datetime.scooter_end_time"
SENSOR_MAX_SPEED = "sensor.scooter_last_trip_max_speed"  # Writable sensor (nouveau)
NUMBER_ODO_DEBUT = "number.scooter_odo_debut"
INPUT_DT_START_TIME = "datetime.scooter_start_time"
NUMBER_BATT_SOC_DEBUT = "number.scooter_battery_soc_debut"

# Pour la mise à jour device_tracker
DEVICE_TRACKER_ID = "silence_scooter"

# Fichierentités gérés par la logique stop_trip
NUMBER_ODO_FIN = "number.scooter_odo_fin"
SENSOR_LAST_TRIP_DISTANCE = "sensor.scooter_last_trip_distance"  # Writable sensor (nouveau)
SENSOR_LAST_TRIP_DURATION = "sensor.scooter_last_trip_duration"  # Writable sensor (nouveau)
SENSOR_LAST_TRIP_AVG_SPEED = "sensor.scooter_last_trip_avg_speed"  # Writable sensor (nouveau)
SENSOR_LAST_TRIP_MAX_SPEED = "sensor.scooter_last_trip_max_speed"  # Writable sensor (nouveau)
SENSOR_LAST_TRIP_BATT_CONSUMPTION = "sensor.scooter_last_trip_battery_consumption"  # Writable sensor (nouveau)
NUMBER_BATT_SOC_FIN = "number.scooter_battery_soc_fin"
NUMBER_TRACKED_DISTANCE = "number.scooter_tracked_distance"
NUMBER_TRACKED_BATT_USED = "number.scooter_tracked_battery_used"
SENSOR_SCOOTER_ODO = "sensor.silence_scooter_odo"
SENSOR_SCOOTER_STATUS = "sensor.silence_scooter_status"
SENSOR_ENERGY_CONSUMPTION = "sensor.scooter_energy_consumption"
NUMBER_ENERGY_BASE = "number.scooter_energy_consumption_base"

# Nouvelles constantes ajoutées
SENSOR_SCOOTER_LAST_UPDATE = "sensor.silence_scooter_last_update"
BINARY_SENSOR_BATTERY_IN = "binary_sensor.silence_scooter_battery_in"

def is_date_valid(date_str: str) -> bool:
    """Vérifie si une date est valide (pas 1969/1970)."""
    if not date_str or date_str in ["unknown", "unavailable"]:
        return False
    return not (date_str.startswith("1969") or date_str.startswith("1970"))

def get_valid_datetime(dt_str: str, default=None):
    """Parse une date et retourne None si elle est invalide (1969/1970)."""
    if not is_date_valid(dt_str):
        return default
    try:
        dt = dt_util.parse_datetime(dt_str)
        if dt and dt.year > 2000:
            return dt_util.as_local(dt) if dt.tzinfo is None else dt
    except:
        pass
    return default
    
    
async def async_setup_automations(hass: HomeAssistant) -> bool:
    """Installe toutes les automatisations (ex-YAML) pour Silence Scooter """

    #
    # Dictionnaire pour stocker les tâches planifiées
    # - nécessaire pour la gestion du "for: 00:02:00" (2 minutes)
    #
    scheduled_tasks = {}

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
        except:
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
        discharged_state = hass.states.get("sensor.silence_scooter_discharged_energy")
        regenerated_state = hass.states.get("sensor.silence_scooter_regenerated_energy")

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
        ["sensor.silence_scooter_discharged_energy", "sensor.silence_scooter_regenerated_energy"],
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
        now_str = dt_util.now().isoformat()
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("Dernier mouvement OFF => on enregistre %s", now_str)
        await hass.services.async_call(
            "datetime",
            "set_value",
            {
                "entity_id": INPUT_DT_LAST_MOVING,
                "datetime": now_str
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
        if (datetime.utcnow() - STARTUP_TIME) < timedelta(seconds=10):
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

            # NOUVELLE LOGIQUE: Arrêt immédiat si scooter vraiment éteint
            should_stop_immediately = False
            
            if not raw_state or raw_state.state in ["unknown", "unavailable"]:
                _LOGGER.info("🛈 Scooter unavailable -> arrêt différé (tolérance)")
            elif raw_state.state == "0":
                _LOGGER.info("🛈 Scooter éteint (status=0) -> arrêt différé (tolérance)") 
            elif not battery_present:
                _LOGGER.info("🛈 Batterie retirée -> arrêt différé (tolérance)")

            if should_stop_immediately:
                # Arrêt immédiat sans délai
                _LOGGER.info("🚨 IMMEDIATE STOP triggered")
                hass.loop.create_task(_immediate_stop())
            else:
                # Arrêt avec délai (logique normale)
                _LOGGER.info("⏰ DELAYED STOP triggered (2min + 5min timer)")
                
                # Définir les fonctions async AVANT de les utiliser
                async def _start_tolerance_timer():
                    """Démarre le timer de tolérance (durée configurable)."""
                    try:
                        # Get configured pause duration (in minutes)
                        pause_duration_min = get_config_value(hass, CONF_PAUSE_MAX_DURATION, DEFAULT_PAUSE_MAX_DURATION)
                        # Convert to HH:MM:SS format
                        duration_str = f"00:{pause_duration_min:02d}:00"

                        await hass.services.async_call(
                            "timer",
                            "start",
                            {
                                "entity_id": TIMER_STOP_TOLERANCE,
                                "duration": duration_str
                            },
                            blocking=True
                        )
                        _LOGGER.info(f"✓ Timer started successfully ({duration_str})")
                    except Exception as e:
                        _LOGGER.warning("Could not start timer: %s", e)

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
                    await do_stop_trip(hass, reason="immediate")

                async def _confirm_off():
                    """Confirme l'arrêt du trajet après le délai de confirmation."""
                    confirmation_delay = get_config_value(hass, CONF_CONFIRMATION_DELAY, DEFAULT_CONFIRMATION_DELAY)
                    _LOGGER.info(f"⏰ CONFIRM OFF: vérification après {confirmation_delay}s d'attente")
                    scheduled_tasks.pop("trip_off_delay", None)

                    # Annulation du timer de tolérance s'il est encore actif
                    timer_state = hass.states.get(TIMER_STOP_TOLERANCE)
                    if timer_state and timer_state.state == "active":
                        await hass.services.async_call(
                            "timer", "cancel",
                            {"entity_id": TIMER_STOP_TOLERANCE},
                            blocking=True
                        )

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
                        await do_stop_trip(hass, reason="auto-confirmed")
                    else:
                        _LOGGER.info("🔄 CONFIRM OFF: état changé -> annulation de l'arrêt")

                # Maintenant qu'on a défini les fonctions, on peut les utiliser
                # Enregistrer le début de la pause
                hass.loop.create_task(
                    hass.services.async_call(
                        "datetime",
                        "set_value",
                        {
                            "entity_id": "datetime.scooter_pause_start",
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
                hass.loop.create_task(_start_tolerance_timer())

                _LOGGER.info("📋 Tâches planifiées : %s", list(scheduled_tasks.keys()))
    #

    remove_trip_status_off = async_track_state_change_event(
        hass, [SENSOR_TRIP_STATUS], handle_trip_status_off
    )

    # 3. "Scooter - Arrêter le timer si le scooter redémarre"
    #    => sensor.scooter_trip_status to 'on' & timer actif
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
            timer_state = hass.states.get(TIMER_STOP_TOLERANCE)
            if timer_state and timer_state.state == "active":
                # Enregistrer la fin de la pause
                pause_start = hass.states.get("datetime.scooter_pause_start")
                if pause_start and pause_start.state not in ["unknown", "unavailable"]:
                    hass.loop.create_task(_record_pause_end())
                
                hass.loop.create_task(do_log_event(hass, "Pause stopped, trip restarted"))
                hass.loop.create_task(
                    hass.services.async_call(
                        "timer",
                        "cancel",
                        {"entity_id": TIMER_STOP_TOLERANCE},
                        blocking=True
                    )
                )
    
    async def _record_pause_end():
        """Enregistre la durée de la pause qui vient de se terminer."""
        try:
            pause_start = hass.states.get("datetime.scooter_pause_start")
            if pause_start and pause_start.state not in ["unknown", "unavailable"]:
                pause_start_dt = dt_util.parse_datetime(pause_start.state)
                if pause_start_dt:
                    pause_duration = (dt_util.now() - dt_util.as_local(pause_start_dt)).total_seconds() / 60
                    
                    # Ajouter à la durée totale des pauses
                    total_pause = hass.states.get("number.scooter_pause_duration")
                    if total_pause:
                        try:
                            current_pause = float(total_pause.state)
                        except:
                            current_pause = 0
                    else:
                        current_pause = 0
                        
                    await hass.services.async_call(
                        "number",
                        "set_value",
                        {
                            "entity_id": "number.scooter_pause_duration",
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
            # => timer.cancel
            # => datetime.scooter_end_time = datetime.scooter_last_moving_time
            # => do_stop_trip
            # => input_boolean.stop_trip_now = off
            hass.loop.create_task(_process_stop_trip_now())

    async def _process_stop_trip_now():
        await do_log_event(hass, "Manual stop button clicked")

        # Annuler la tâche programmée si existante
        if scheduled_tasks.get("trip_off_delay"):
            scheduled_tasks["trip_off_delay"].cancel()
            scheduled_tasks.pop("trip_off_delay", None)

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
        await do_stop_trip(hass, reason="Manual button")

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
            
            # NOUVELLE LOGIQUE : Vérifier le statut du scooter (3 ou 4) au lieu de la vitesse
            scooter_status = hass.states.get(SENSOR_SCOOTER_STATUS)
            if scooter_status and scooter_status.state not in ["unknown", "unavailable"]:
                try:
                    status = float(scooter_status.state)
                    if status not in [3.0, 4.0]:
                        _LOGGER.info("⚠️ Scooter status incorrect (%s), ignoring start trigger (attendu: 3 ou 4)", status)
                        return
                except:
                    _LOGGER.warning("⚠️ Impossible de lire le statut du scooter, continuing anyway")
            
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
                "entity_id": "number.scooter_pause_duration",
                "value": 0
            },
            blocking=True
        )
        
        # Réinitialiser l'heure de début de pause
        await hass.services.async_call(
            "datetime",
            "set_value",
            {
                "entity_id": "datetime.scooter_pause_start",
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
        odo_state = hass.states.get(SENSOR_SCOOTER_ODO)
        odo_val = 0
        if odo_state and odo_state.state not in ["unknown", "unavailable", None]:
            try:
                odo_val = float(odo_state.state)
            except:
                odo_val = 0
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
        batt_state = hass.states.get(SENSOR_BATT_SOC)
        batt_val = 0
        if batt_state and batt_state.state not in ["unknown", "unavailable", None]:
            try:
                batt_val = float(batt_state.state)
            except:
                batt_val = 0
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
        except:
            current_speed = -1
        hass.loop.create_task(_do_update_max_speed(current_speed))

    async def _do_update_max_speed(current_speed):
        # log_event => "Current speed: X km/h"
        await do_log_event(hass, f"Current speed: {current_speed} km/h")

        # old max
        old_max = get_sensor_float_value(hass, SENSOR_MAX_SPEED, 0.0)

        new_val = max(old_max, current_speed, 0)
        await set_writable_sensor_value(hass, SENSOR_MAX_SPEED, new_val)

    remove_update_max_speed = async_track_state_change_event(
        hass, [SENSOR_SCOOTER_SPEED], handle_update_max_speed
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
            except:
                lat = 0.0

        if lon_state and lon_state.state not in ["unknown", "unavailable"]:
            try:
                lon = float(lon_state.state)
            except:
                lon = 0.0

        if batt_state and batt_state.state not in ["unknown", "unavailable"]:
            try:
                batt = int(float(batt_state.state))
            except:
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
                        await do_log_event(hass, "Watchdog: Auto stop trip (no update)")
                        await do_stop_trip(hass, reason="watchdog-no-update")
            except Exception as e:
                _LOGGER.error("Erreur dans watchdog_check_trip_end: %s", e)
                
        except Exception as e:
            _LOGGER.error("Erreur dans watchdog_check_trip_end: %s", e)

    # Enregistrer le watchdog
    watchdog_remove = async_track_time_interval(
        hass, watchdog_check_trip_end, timedelta(minutes=5)
    )


    if "silence_automations" not in hass.data:
        hass.data["silence_automations"] = []
    hass.data["silence_automations"].extend([
        remove_energy_baseline_init,
        remove_tracker_dernier_mouvement,
        remove_trip_status_off,
        remove_stop_timer_if_restart,
        remove_stop_trip_now,
        remove_last_start,
        remove_update_max_speed,
        remove_update_tracker,
        watchdog_remove,
    ])

    @callback
    def handle_timer_finished(event):
        """Appelé quand timer.scooter_stop_trip_tolerance arrive à expiration."""
        _LOGGER.info("▶ handle_timer_finished appelé pour %s", event.data)
        entity = event.data.get("entity_id")
        if entity == TIMER_STOP_TOLERANCE:
            _LOGGER.info("⏱️ Timer de tolérance terminé, on confirme l'arrêt du trajet")
            hass.async_create_task(_confirm_off())

    # Écoute la fin du timer de tolérance
    remove_timer_listener = hass.bus.async_listen(
        EVENT_TIMER_FINISHED,
        handle_timer_finished
    )

    hass.data["silence_automations"].append(remove_timer_listener)

    _LOGGER.info("All custom automations for Silence Scooter have been set up")
    return True


async def do_log_event(hass: HomeAssistant, message: str):
    """Log an event via the helper function."""
    _LOGGER.info("LOG EVENT: %s", message)
    try:
        await log_event(hass, message)
    except Exception as exc:
        _LOGGER.error("Failed to call log_event helper: %s", exc)


async def do_stop_trip(hass: HomeAssistant, reason: str = "Manual stop"):
    """Stop the current trip and update all trip-related entities.

    This function orchestrates the trip stop workflow by determining the end
    timestamp, updating odometer and time readings, calculating trip metrics
    (distance, duration, speed, battery consumption), updating cumulative
    statistics, and recording the trip in history.

    Args:
        hass: HomeAssistant instance
        reason: Reason for stopping the trip
    """
    _LOGGER.info("STOP TRIP TRIGGERED: reason=%s", reason)

    try:
        # 1) Determine end timestamp using helper
        end_timestamp = determine_trip_end_timestamp(hass)

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

        # 3) Update scooter_odo_fin from current ODO
        odo_fin_val = get_sensor_float_value(hass, SENSOR_SCOOTER_ODO, 0.0)
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
                end_timestamp
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

        # 7) Update battery_soc_fin
        batt_soc_fin_val = get_sensor_float_value(hass, SENSOR_BATT_SOC, 0.0)
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
        await update_trip_statistics(hass, distance_val, batt_consumption)

        # 10) Update entities
        await hass.services.async_call(
            "homeassistant",
            "update_entity",
            {
                "entity_id": [
                    SENSOR_TRIP_STATUS,
                    "sensor.scooter_last_trip_duration",
                    "sensor.scooter_last_trip_avg_speed",
                    "sensor.scooter_last_trip_battery_consumption",
                    "sensor.scooter_energy_cost_daily",
                    "sensor.scooter_energy_cost_weekly",
                    "sensor.scooter_energy_cost_monthly",
                    "sensor.scooter_energy_cost_yearly",
                ]
            },
            blocking=True
        )

        # 11) Update trips history
        await do_update_trips_history(hass)

        _LOGGER.info(
            "TRIP STOPPED: distance=%.1f km, duration=%.0f min, avg_speed=%.1f km/h, battery=%.1f%% (reason=%s)",
            distance_val, trip_duration_val, avg_speed, batt_consumption, reason
        )

    except Exception as e:
        _LOGGER.error("Error in do_stop_trip: %s", e, exc_info=True)

async def do_update_trips_history(hass: HomeAssistant):
    """Update trip history with validation."""
    _LOGGER.info("UPDATING TRIP HISTORY")

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
        
        end_time_st = hass.states.get("datetime.scooter_end_time")
        start_time_st = hass.states.get("datetime.scooter_start_time")

        def parse_and_validate(ts):
            try:
                dt = dt_util.parse_datetime(ts)
                if dt and dt.year >= 2000:
                    # Always convert to local timezone, even if already has timezone info
                    dt = dt_util.as_local(dt)
                    return dt.isoformat()
                if dt and dt.year < 2000:
                    _LOGGER.warning("Invalid date detected (year < 2000): %s", dt)
                return None
            except:
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
        battery_debut = hass.states.get("number.scooter_battery_soc_debut")
        battery_fin = hass.states.get("number.scooter_battery_soc_fin")
        outdoor_temp = hass.states.get("sensor.silence_scooter_ambient_temperature")
        
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


async def setup_persistent_sensors_update(hass: HomeAssistant):
    """Setup persistent sensors auto-update.

    Updates persistent sensors (battery, odo, regeneration) when MQTT data changes.
    These sensors retain their last value even when the scooter is offline.
    """
    _LOGGER.info("Setting up persistent sensors auto-update...")

    async def update_battery_display(event):
        """Update scooter_battery_display from sensor.silence_scooter_battery_soc."""
        new_state = event.data.get("new_state")
        if not new_state or new_state.state in ["unknown", "unavailable", None]:
            return

        try:
            battery_value = float(new_state.state)
            await set_writable_sensor_value(hass, "sensor.scooter_battery_display", battery_value)
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
            await set_writable_sensor_value(hass, "sensor.scooter_odo_display", odo_value)
            _LOGGER.debug("ODO display updated: %.1f km", odo_value)
        except (ValueError, TypeError) as e:
            _LOGGER.warning("Failed to update ODO display: %s", e)

    async def update_regeneration_percentage(event):
        """Update scooter_battery_percentage_regeneration from energy sensors."""
        discharged_st = hass.states.get("sensor.silence_scooter_discharged_energy")
        regenerated_st = hass.states.get("sensor.silence_scooter_regenerated_energy")

        if not discharged_st or not regenerated_st:
            return

        if discharged_st.state in ["unknown", "unavailable", None] or \
           regenerated_st.state in ["unknown", "unavailable", None]:
            return

        try:
            discharged = float(discharged_st.state)
            regenerated = float(regenerated_st.state)

            if (discharged + regenerated) > 0:
                percentage = (regenerated / (discharged + regenerated)) * 100
                await set_writable_sensor_value(hass, "sensor.scooter_battery_percentage_regeneration", round(percentage, 2))
                _LOGGER.debug("Regeneration percentage updated: %.2f%%", percentage)
        except (ValueError, TypeError) as e:
            _LOGGER.warning("Failed to update regeneration percentage: %s", e)

    remove_battery = async_track_state_change_event(
        hass, ["sensor.silence_scooter_battery_soc"], update_battery_display
    )

    remove_odo = async_track_state_change_event(
        hass, ["sensor.silence_scooter_odo"], update_odo_display
    )

    remove_regeneration = async_track_state_change_event(
        hass,
        ["sensor.silence_scooter_discharged_energy", "sensor.silence_scooter_regenerated_energy"],
        update_regeneration_percentage
    )

    _LOGGER.info("Persistent sensors auto-update configured")

    return [remove_battery, remove_odo, remove_regeneration]