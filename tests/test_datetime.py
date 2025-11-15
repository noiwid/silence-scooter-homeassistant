"""Test Silence Scooter datetime entities."""
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.silencescooter.const import DOMAIN, CONF_IMEI
from custom_components.silencescooter.datetime import ScooterDateTimeEntity


async def test_datetime_entity_creation(hass: HomeAssistant, valid_imei):
    """Test datetime entity creation."""
    config = {
        "name": "Test DateTime",
        "has_date": True,
        "has_time": True,
    }

    entity = ScooterDateTimeEntity(hass, "test_datetime", config, valid_imei, multi_device=False)

    assert entity._attr_unique_id == f"{valid_imei}_test_datetime"
    assert entity._attr_name == "Test DateTime"
    assert entity._has_date is True
    assert entity._has_time is True
    assert entity._value is not None


async def test_datetime_entity_multi_device(hass: HomeAssistant, valid_imei):
    """Test datetime entity in multi-device mode."""
    config = {
        "name": "Test DateTime",
    }

    entity = ScooterDateTimeEntity(hass, "test_datetime", config, valid_imei, multi_device=True)

    assert entity._attr_unique_id == f"{valid_imei}_test_datetime"
    assert entity._attr_device_info is not None


async def test_datetime_entity_set_value(hass: HomeAssistant, valid_imei):
    """Test setting datetime entity value."""
    config = {
        "name": "Test DateTime",
    }

    entity = ScooterDateTimeEntity(hass, "test_datetime", config, valid_imei, multi_device=False)

    test_datetime = datetime(2024, 1, 15, 12, 30, 0)
    test_datetime_aware = dt_util.as_local(test_datetime)

    await entity.async_set_value(test_datetime_aware)

    assert entity._value == test_datetime_aware
    assert entity._attr_native_value == test_datetime_aware


async def test_datetime_entity_restore_from_input_datetime(hass: HomeAssistant, valid_imei):
    """Test datetime entity restores from old input_datetime."""
    config = {
        "name": "Test DateTime",
    }

    entity = ScooterDateTimeEntity(hass, "test_datetime", config, valid_imei, multi_device=False)

    # Create old input_datetime state
    old_datetime_str = "2024-01-15 12:30:00"
    hass.states.async_set("input_datetime.test_datetime", old_datetime_str)

    await entity.async_added_to_hass()

    # Should restore from old input_datetime
    assert entity._value.year == 2024
    assert entity._value.month == 1
    assert entity._value.day == 15
    assert entity._value.hour == 12
    assert entity._value.minute == 30


async def test_datetime_entity_restore_from_entity_state(hass: HomeAssistant, valid_imei):
    """Test datetime entity restores from its own state."""
    config = {
        "name": "Test DateTime",
    }

    entity = ScooterDateTimeEntity(hass, "test_datetime", config, valid_imei, multi_device=False)

    # Mock restore state
    test_datetime = datetime(2024, 2, 20, 14, 45, 0)
    test_datetime_aware = dt_util.as_local(test_datetime)

    with patch.object(entity, "async_get_last_state") as mock_restore:
        mock_state = MagicMock()
        mock_state.state = test_datetime_aware.isoformat()
        mock_state.attributes = {}
        mock_restore.return_value = mock_state

        # Mock no old input_datetime
        await entity.async_added_to_hass()

    # Should restore from entity state
    assert entity._value.year == 2024
    assert entity._value.month == 2
    assert entity._value.day == 20


async def test_datetime_entity_invalid_input_datetime(hass: HomeAssistant, valid_imei):
    """Test datetime entity handles invalid old input_datetime."""
    config = {
        "name": "Test DateTime",
    }

    entity = ScooterDateTimeEntity(hass, "test_datetime", config, valid_imei, multi_device=False)

    # Create old input_datetime state with invalid value
    hass.states.async_set("input_datetime.test_datetime", "unknown")

    await entity.async_added_to_hass()

    # Should not crash and use current time
    assert entity._value is not None


async def test_datetime_entity_no_previous_state(hass: HomeAssistant, valid_imei):
    """Test datetime entity with no previous state."""
    config = {
        "name": "Test DateTime",
    }

    entity = ScooterDateTimeEntity(hass, "test_datetime", config, valid_imei, multi_device=False)

    # Mock no previous state
    with patch.object(entity, "async_get_last_state") as mock_restore:
        mock_restore.return_value = None

        await entity.async_added_to_hass()

    # Should use current time (initialized in __init__)
    assert entity._value is not None
    assert isinstance(entity._value, datetime)


async def test_datetime_platform_setup(hass: HomeAssistant, valid_imei, mock_automations):
    """Test datetime platform setup."""
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

    # Check that datetime platform was loaded
    assert "datetime" in hass.config.components or f"{DOMAIN}.datetime" in hass.config.components
