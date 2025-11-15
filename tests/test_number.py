"""Test Silence Scooter number entities."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.silencescooter.const import DOMAIN, CONF_IMEI
from custom_components.silencescooter.number import ScooterNumberEntity


async def test_number_entity_creation(hass: HomeAssistant, valid_imei):
    """Test number entity creation."""
    config = {
        "name": "Test Number",
        "min": 0,
        "max": 100,
        "step": 1,
        "initial": 50,
        "unit_of_measurement": "km",
    }

    entity = ScooterNumberEntity(hass, "test_number", config, valid_imei, multi_device=False)

    assert entity._attr_unique_id == f"{valid_imei}_test_number"
    assert entity._attr_name == "Test Number"
    assert entity._attr_native_min_value == 0
    assert entity._attr_native_max_value == 100
    assert entity._attr_native_step == 1
    assert entity._attr_native_unit_of_measurement == "km"
    assert entity._value == 50


async def test_number_entity_multi_device(hass: HomeAssistant, valid_imei):
    """Test number entity in multi-device mode."""
    config = {
        "name": "Test Number",
        "min": 0,
        "max": 100,
        "step": 1,
    }

    entity = ScooterNumberEntity(hass, "test_number", config, valid_imei, multi_device=True)

    assert entity._attr_unique_id == f"{valid_imei}_test_number"
    assert entity._attr_device_info is not None


async def test_number_entity_set_value(hass: HomeAssistant, valid_imei):
    """Test setting number entity value."""
    config = {
        "name": "Test Number",
        "min": 0,
        "max": 100,
        "step": 1,
        "initial": 0,
    }

    entity = ScooterNumberEntity(hass, "test_number", config, valid_imei, multi_device=False)

    await entity.async_set_native_value(75.5)

    assert entity._value == 75.5
    assert entity._attr_native_value == 75.5
    assert entity.native_value == 75.5


async def test_number_entity_restore_state(hass: HomeAssistant, valid_imei):
    """Test number entity restores last state."""
    config = {
        "name": "Test Number",
        "min": 0,
        "max": 100,
        "step": 1,
        "initial": 0,
    }

    entity = ScooterNumberEntity(hass, "test_number", config, valid_imei, multi_device=False)

    # Mock restore state
    with patch.object(entity, "async_get_last_state") as mock_restore:
        mock_state = MagicMock()
        mock_state.state = "42.5"
        mock_restore.return_value = mock_state

        await entity.async_added_to_hass()

    assert entity._value == 42.5
    assert entity._attr_native_value == 42.5


async def test_number_entity_restore_invalid_state(hass: HomeAssistant, valid_imei):
    """Test number entity handles invalid restore state."""
    config = {
        "name": "Test Number",
        "min": 0,
        "max": 100,
        "step": 1,
        "initial": 10,
    }

    entity = ScooterNumberEntity(hass, "test_number", config, valid_imei, multi_device=False)

    # Mock restore state with invalid value
    with patch.object(entity, "async_get_last_state") as mock_restore:
        mock_state = MagicMock()
        mock_state.state = "invalid"
        mock_restore.return_value = mock_state

        await entity.async_added_to_hass()

    # Should keep initial value
    assert entity._value == 10


async def test_number_entity_no_previous_state(hass: HomeAssistant, valid_imei):
    """Test number entity with no previous state."""
    config = {
        "name": "Test Number",
        "min": 0,
        "max": 100,
        "step": 1,
        "initial": 25,
    }

    entity = ScooterNumberEntity(hass, "test_number", config, valid_imei, multi_device=False)

    # Mock no previous state
    with patch.object(entity, "async_get_last_state") as mock_restore:
        mock_restore.return_value = None

        await entity.async_added_to_hass()

    # Should use initial value
    assert entity._value == 25


async def test_number_platform_setup(hass: HomeAssistant, valid_imei, mock_automations):
    """Test number platform setup."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_IMEI: valid_imei,
            "multi_device": False,
        },
        unique_id=valid_imei,
    )
    entry.add_to_hass(hass)

    with patch("custom_components.silencescooter.publish_mqtt_discovery_configs", AsyncMock()):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Check that number platform was loaded
    assert "number" in hass.config.components or f"{DOMAIN}.number" in hass.config.components
