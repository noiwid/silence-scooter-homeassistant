"""Helper functions for the Silence Scooter integration."""
import logging
import subprocess
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, HISTORY_SCRIPT, LOG_FILE

_LOGGER = logging.getLogger(__name__)


def get_device_info(imei: str, multi_device: bool = False) -> DeviceInfo:
    """Return device info for Silence Scooter with IMEI.

    Args:
        imei: The IMEI of the scooter
        multi_device: Whether to include IMEI in device name

    Returns:
        DeviceInfo with IMEI-based identifiers
    """
    if multi_device:
        # Use last 4 digits for display name
        imei_short = imei[-4:] if len(imei) >= 4 else imei
        name = f"Silence Scooter ({imei_short})"
    else:
        name = "Silence Scooter"

    return DeviceInfo(
        identifiers={(DOMAIN, imei)},  # Use full IMEI for unique identification
        name=name,
        manufacturer="Seat",
        model="Mo",
    )


def generate_entity_id_suffix(imei: str, multi_device: bool) -> str:
    """Generate entity ID suffix based on multi-device setting.

    Returns empty string if single-device mode.
    Returns _9012 (last 4 IMEI digits) if multi-device mode.

    Args:
        imei: Full IMEI (15 digits)
        multi_device: Whether to add IMEI suffix

    Returns:
        Empty string or _XXXX suffix
    """
    if not multi_device:
        return ""

    imei_short = imei[-4:] if len(imei) >= 4 else imei
    return f"_{imei_short}"


def insert_imei_in_entity_id(entity_id: str, imei: str, multi_device: bool) -> str:
    """Insert IMEI suffix BEFORE the last element of entity_id.

    Examples:
        silence_scooter_speed + 9012 → silence_scooter_9012_speed
        silence_scooter_battery_soc + 9012 → silence_scooter_9012_battery_soc
        scooter_tracked_distance + 9012 → scooter_9012_tracked_distance

    Args:
        entity_id: Base entity ID (e.g., "silence_scooter_speed")
        imei: Full IMEI (15 digits)
        multi_device: Whether to add IMEI suffix

    Returns:
        Modified entity ID with IMEI before last element (or unchanged if multi_device=False)
    """
    if not multi_device:
        return entity_id

    suffix = generate_entity_id_suffix(imei, multi_device)

    # Split on last underscore to insert IMEI before element name
    parts = entity_id.rsplit('_', 1)
    if len(parts) == 2:
        base, element = parts
        return f"{base}{suffix}_{element}"
    else:
        # No underscore found, append at end
        return f"{entity_id}{suffix}"



def is_date_valid(date_str: str) -> bool:
    """Vérifie si une date est valide (pas 1969/1970).

    Args:
        date_str: Date string to validate

    Returns:
        True if date is valid (not 1969/1970), False otherwise
    """
    if not date_str or date_str in ["unknown", "unavailable"]:
        return False
    return not (date_str.startswith("1969") or date_str.startswith("1970"))


def get_valid_datetime(dt_str: str, default=None):
    """Parse une date et retourne None si elle est invalide (1969/1970).

    Args:
        dt_str: Datetime string to parse
        default: Default value if parsing fails

    Returns:
        Parsed datetime or default value
    """
    if not is_date_valid(dt_str):
        return default
    try:
        dt = dt_util.parse_datetime(dt_str)
        if dt and dt.year > 2000:
            return dt_util.as_local(dt) if dt.tzinfo is None else dt
    except Exception:
        pass
    return default


async def log_event(hass: HomeAssistant, message: str):
    """Log a message to silence_logs.log."""
    try:
        if not message:
            _LOGGER.warning("log_event called with empty message")
            return

        _LOGGER.info("Log Event: %s", message)

        def write_log():
            try:
                from datetime import datetime
                log_file = Path(hass.config.path("silence_logs.log"))
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                log_entry = f"{timestamp} - {message}\n"

                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(log_entry)

            except Exception as e:
                _LOGGER.warning("Error writing to log file: %s", e)

        await hass.async_add_executor_job(write_log)

    except Exception as e:
        _LOGGER.error("Error in log_event helper: %s", e)


async def update_history(hass: HomeAssistant, **kwargs):
    """Update trip history."""
    try:
        avg_speed = kwargs.get("avg_speed", 0)
        distance = kwargs.get("distance", 0)
        duration = kwargs.get("duration", 0)
        start_time = kwargs.get("start_time", "")
        end_time = kwargs.get("end_time", "")
        max_speed = kwargs.get("max_speed", 0)
        battery = kwargs.get("battery", 0)
        outdoor_temp = kwargs.get("outdoor_temp", 0)

        _LOGGER.info("update_history called with: avg_speed=%s, distance=%s, duration=%s",
                     avg_speed, distance, duration)

        if not HISTORY_SCRIPT.exists():
            _LOGGER.error("History script not found at %s", HISTORY_SCRIPT)
            return False

        cmd = [
            "bash",
            str(HISTORY_SCRIPT),
            str(avg_speed),
            str(distance),
            str(duration),
            start_time,
            end_time,
            str(max_speed),
            str(battery),
            str(outdoor_temp)
        ]

        _LOGGER.debug("Executing command: %s", cmd)

        def run_script():
            return subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        process = await hass.async_add_executor_job(run_script)

        if process.returncode != 0:
            _LOGGER.error("Error updating history: %s", process.stderr)
            return False

        _LOGGER.info("History updated successfully")
        return True

    except Exception as e:
        _LOGGER.error("Failed to update history: %s", e)
        return False