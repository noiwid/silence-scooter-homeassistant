"""Constants for the Silence Scooter integration."""
from pathlib import Path
from homeassistant.const import Platform

DOMAIN = "silencescooter"
CONF_IMEI = "imei"

COMPONENT_PATH = Path(__file__).parent
DATA_PATH = COMPONENT_PATH / "data"
SCRIPTS_PATH = COMPONENT_PATH / "scripts"

HISTORY_FILE = DATA_PATH / "history.json"
HISTORY_SCRIPT = SCRIPTS_PATH / "history.sh"
LOG_FILE = DATA_PATH / "silence_logs.log"

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
DEFAULT_TARIFF_SENSOR = ""
DEFAULT_CONFIRMATION_DELAY = 120
DEFAULT_PAUSE_MAX_DURATION = 5
DEFAULT_WATCHDOG_DELAY = 5
DEFAULT_USE_TRACKED_DISTANCE = False
DEFAULT_OUTDOOR_TEMP_SOURCE = "scooter"
DEFAULT_OUTDOOR_TEMP_ENTITY = ""

# Outdoor temperature sources
OUTDOOR_TEMP_SOURCE_SCOOTER = "scooter"
OUTDOOR_TEMP_SOURCE_EXTERNAL = "external"

# Scooter ambient temperature sensor
SENSOR_SCOOTER_AMBIENT_TEMP = "sensor.silence_scooter_ambient_temperature"