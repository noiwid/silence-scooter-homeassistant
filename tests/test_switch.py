"""Test Silence Scooter switch entities."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.silencescooter.const import DOMAIN, CONF_IMEI
from custom_components.silencescooter.switch import ScooterSwitchEntity


async def test_switch_entity_creation(hass: HomeAssistant, valid_imei):
    """Test switch entity creation."""
    config = {
        "name": "Test Switch",
        "icon": "mdi:power",
    }

    entity = ScooterSwitchEntity("test_switch", config, valid_imei, multi_device=False)

    assert entity._attr_unique_id == f"{valid_imei}_test_switch"
    assert entity._attr_name == "Test Switch"
    assert entity._icon == "mdi:power"
    assert entity._is_on is False


async def test_switch_entity_multi_device(hass: HomeAssistant, valid_imei):
    """Test switch entity in multi-device mode."""
    config = {
        "name": "Test Switch",
    }

    entity = ScooterSwitchEntity("test_switch", config, valid_imei, multi_device=True)

    assert entity._attr_unique_id == f"{valid_imei}_test_switch"
    assert entity._attr_device_info is not None


async def test_switch_entity_default_icon(hass: HomeAssistant, valid_imei):
    """Test switch entity with default icon."""
    config = {
        "name": "Test Switch",
    }

    entity = ScooterSwitchEntity("test_switch", config, valid_imei, multi_device=False)

    assert entity._icon == "mdi:toggle-switch"


async def test_switch_entity_turn_on(hass: HomeAssistant, valid_imei):
    """Test turning on switch entity."""
    config = {
        "name": "Test Switch",
    }

    entity = ScooterSwitchEntity("test_switch", config, valid_imei, multi_device=False)

    await entity.async_turn_on()

    assert entity._is_on is True
    assert entity.is_on is True


async def test_switch_entity_turn_off(hass: HomeAssistant, valid_imei):
    """Test turning off switch entity."""
    config = {
        "name": "Test Switch",
    }

    entity = ScooterSwitchEntity("test_switch", config, valid_imei, multi_device=False)

    # First turn it on
    await entity.async_turn_on()
    assert entity._is_on is True

    # Now turn it off
    await entity.async_turn_off()

    assert entity._is_on is False
    assert entity.is_on is False


async def test_switch_entity_restore_state_on(hass: HomeAssistant, valid_imei):
    """Test switch entity restores 'on' state."""
    config = {
        "name": "Test Switch",
    }

    entity = ScooterSwitchEntity("test_switch", config, valid_imei, multi_device=False)

    # Mock restore state as 'on'
    with patch.object(entity, "async_get_last_state") as mock_restore:
        mock_state = MagicMock()
        mock_state.state = "on"
        mock_restore.return_value = mock_state

        await entity.async_added_to_hass()

    assert entity._is_on is True


async def test_switch_entity_restore_state_off(hass: HomeAssistant, valid_imei):
    """Test switch entity restores 'off' state."""
    config = {
        "name": "Test Switch",
    }

    entity = ScooterSwitchEntity("test_switch", config, valid_imei, multi_device=False)

    # Mock restore state as 'off'
    with patch.object(entity, "async_get_last_state") as mock_restore:
        mock_state = MagicMock()
        mock_state.state = "off"
        mock_restore.return_value = mock_state

        await entity.async_added_to_hass()

    assert entity._is_on is False


async def test_switch_entity_no_previous_state(hass: HomeAssistant, valid_imei):
    """Test switch entity with no previous state."""
    config = {
        "name": "Test Switch",
    }

    entity = ScooterSwitchEntity("test_switch", config, valid_imei, multi_device=False)

    # Mock no previous state
    with patch.object(entity, "async_get_last_state") as mock_restore:
        mock_restore.return_value = None

        await entity.async_added_to_hass()

    # Should default to off
    assert entity._is_on is False


async def test_switch_platform_setup(hass: HomeAssistant, valid_imei, mock_automations):
    """Test switch platform setup."""
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

    # Check that switch platform was loaded
    assert "switch" in hass.config.components or f"{DOMAIN}.switch" in hass.config.components
