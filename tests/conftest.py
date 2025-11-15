"""Common fixtures for Silence Scooter tests."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.silencescooter.const import DOMAIN


@pytest.fixture
def mock_setup_entry():
    """Mock async_setup_entry."""
    with patch(
        "custom_components.silencescooter.async_setup_entry",
        return_value=True,
    ) as mock_setup:
        yield mock_setup


@pytest.fixture
def valid_imei():
    """Return a valid IMEI."""
    return "869123456789012"


@pytest.fixture
def valid_imei_short():
    """Return a valid IMEI (14 digits)."""
    return "86912345678901"


@pytest.fixture
def mock_mqtt(hass):
    """Mock MQTT."""
    hass.data["mqtt"] = MagicMock()
    mqtt_mock = MagicMock()
    mqtt_mock.async_publish = AsyncMock()

    with patch.object(hass.components, "mqtt", mqtt_mock):
        with patch("custom_components.silencescooter.publish_mqtt_discovery_configs", AsyncMock()):
            yield mqtt_mock


@pytest.fixture
def config_entry(valid_imei):
    """Create a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            "imei": valid_imei,
            "multi_device": False,
            "confirmation_delay": 120,
            "pause_max_duration": 5,
            "watchdog_delay": 5,
            "use_tracked_distance": False,
            "outdoor_temp_source": "scooter",
            "outdoor_temp_entity": "",
        },
        unique_id=valid_imei,
        title=f"Silence Scooter ({valid_imei[-4:]})",
    )


@pytest.fixture
def config_entry_multi_device(valid_imei):
    """Create a mock config entry for multi-device mode."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            "imei": valid_imei,
            "multi_device": True,
            "confirmation_delay": 120,
            "pause_max_duration": 5,
            "watchdog_delay": 5,
            "use_tracked_distance": False,
            "outdoor_temp_source": "scooter",
            "outdoor_temp_entity": "",
        },
        unique_id=valid_imei,
        title=f"Silence Scooter ({valid_imei[-4:]})",
    )


@pytest.fixture
def mock_history_file(tmp_path):
    """Mock history file."""
    history_file = tmp_path / "history.json"
    history_file.write_text("[]")

    with patch("custom_components.silencescooter.const.HISTORY_FILE", history_file):
        yield history_file


@pytest.fixture
def mock_automations():
    """Mock automations setup."""
    with patch("custom_components.silencescooter.automations.async_setup_automations", AsyncMock(return_value=[])):
        with patch("custom_components.silencescooter.automations.setup_persistent_sensors_update", AsyncMock()):
            yield
