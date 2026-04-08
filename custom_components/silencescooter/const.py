"""Constants for the Silence Scooter integration."""
from pathlib import Path
from homeassistant.const import Platform

DOMAIN = "silencescooter"
CONF_IMEI = "imei"
CONF_MULTI_DEVICE = "multi_device"

COMPONENT_PATH = Path(__file__).parent
SCRIPTS_PATH = COMPONENT_PATH / "scripts"

# Persistent data lives outside the integration folder so HACS updates
# don't wipe it. /config/silencescooter/ survives integration reinstalls.
PERSISTENT_DATA_PATH = Path("/config/silencescooter")

HISTORY_FILE = PERSISTENT_DATA_PATH / "history.json"
HISTORY_SCRIPT = SCRIPTS_PATH / "history.sh"
LOG_FILE = PERSISTENT_DATA_PATH / "silence_logs.log"

# Legacy paths (pre-1.3.3) — kept only for one-time migration on startup
LEGACY_DATA_PATH = COMPONENT_PATH / "data"
LEGACY_HISTORY_FILE = LEGACY_DATA_PATH / "history.json"
LEGACY_LOG_FILE = LEGACY_DATA_PATH / "silence_logs.log"

PLATFORMS = [
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.DATETIME,
    Platform.SWITCH,
]

CONF_NAME = "name"
CONF_ICON = "icon"
CONF_UNIT = "unit_of_measurement"
CONF_TARIFF_SENSOR = "tariff_sensor"
CONF_CONFIRMATION_DELAY = "confirmation_delay"
CONF_PAUSE_MAX_DURATION = "pause_max_duration"
CONF_WATCHDOG_DELAY = "watchdog_delay"
CONF_USE_TRACKED_DISTANCE = "use_tracked_distance"
CONF_OUTDOOR_TEMP_SOURCE = "outdoor_temp_source"
CONF_OUTDOOR_TEMP_ENTITY = "outdoor_temp_entity"

DEFAULT_ELECTRICITY_PRICE = 0.215
DEFAULT_BATTERY_CAPACITY = 5.6  # kWh - S01. S02/S03 = 2.0 kWh (configurable via config_flow)
MANUFACTURER = "Silence"
DEFAULT_TARIFF_SENSOR = ""
DEFAULT_CONFIRMATION_DELAY = 120
DEFAULT_PAUSE_MAX_DURATION = 5
DEFAULT_WATCHDOG_DELAY = 5
DEFAULT_USE_TRACKED_DISTANCE = False
DEFAULT_OUTDOOR_TEMP_SOURCE = "scooter"
DEFAULT_OUTDOOR_TEMP_ENTITY = ""
DEFAULT_MULTI_DEVICE = False

# Outdoor temperature sources
OUTDOOR_TEMP_SOURCE_SCOOTER = "scooter"
OUTDOOR_TEMP_SOURCE_EXTERNAL = "external"

# Scooter ambient temperature sensor
SENSOR_SCOOTER_AMBIENT_TEMP = "sensor.silence_scooter_ambient_temperature"

# Key MQTT sensors monitored for connectivity health checks
MQTT_MONITORED_SENSORS = [
    "sensor.silence_scooter_status",
    "sensor.silence_scooter_odo",
    "sensor.silence_scooter_battery_soc",
    "sensor.silence_scooter_speed",
    "sensor.silence_scooter_discharged_energy",
    "sensor.silence_scooter_regenerated_energy",
]