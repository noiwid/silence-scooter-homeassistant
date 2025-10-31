"""Constants for the Silence Scooter integration."""
from pathlib import Path
from homeassistant.const import Platform

DOMAIN = "silencescooter"

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

DEFAULT_ELECTRICITY_PRICE = 0.215
DEFAULT_TARIFF_SENSOR = "sensor.tarif_base_ttc"
DEFAULT_CONFIRMATION_DELAY = 120
DEFAULT_PAUSE_MAX_DURATION = 5
DEFAULT_WATCHDOG_DELAY = 5
DEFAULT_USE_TRACKED_DISTANCE = False