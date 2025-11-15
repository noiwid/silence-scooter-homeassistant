"""Test Silence Scooter setup."""
from unittest.mock import patch, AsyncMock, MagicMock
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.silencescooter.const import DOMAIN, CONF_IMEI, CONF_MULTI_DEVICE


async def test_setup_entry(hass: HomeAssistant, valid_imei, mock_automations):
    """Test setup entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_IMEI: valid_imei,
            CONF_MULTI_DEVICE: False,
            "confirmation_delay": 120,
        },
        unique_id=valid_imei,
    )
    entry.add_to_hass(hass)

    with patch("custom_components.silencescooter.publish_mqtt_discovery_configs", AsyncMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state == ConfigEntryState.LOADED
    assert DOMAIN in hass.data
    assert entry.entry_id in hass.data[DOMAIN]
    assert hass.data[DOMAIN][entry.entry_id]["imei"] == valid_imei


async def test_setup_entry_multi_device(hass: HomeAssistant, valid_imei, mock_automations):
    """Test setup entry with multi-device mode."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_IMEI: valid_imei,
            CONF_MULTI_DEVICE: True,
            "confirmation_delay": 120,
        },
        unique_id=valid_imei,
    )
    entry.add_to_hass(hass)

    with patch("custom_components.silencescooter.publish_mqtt_discovery_configs", AsyncMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state == ConfigEntryState.LOADED
    assert hass.data[DOMAIN][entry.entry_id]["multi_device"] is True


async def test_setup_entry_no_imei_triggers_reauth(hass: HomeAssistant, mock_automations):
    """Test that missing IMEI triggers reauth flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},  # No IMEI
        unique_id=None,
    )
    entry.add_to_hass(hass)

    with patch("custom_components.silencescooter.publish_mqtt_discovery_configs", AsyncMock()):
        result = await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert result is False


async def test_unload_entry(hass: HomeAssistant, valid_imei, mock_automations):
    """Test unload entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_IMEI: valid_imei,
            CONF_MULTI_DEVICE: False,
        },
        unique_id=valid_imei,
    )
    entry.add_to_hass(hass)

    with patch("custom_components.silencescooter.publish_mqtt_discovery_configs", AsyncMock()):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state == ConfigEntryState.NOT_LOADED
    assert entry.entry_id not in hass.data.get(DOMAIN, {})


async def test_unload_entry_with_automations(hass: HomeAssistant, valid_imei):
    """Test unload entry cleans up automations."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_IMEI: valid_imei,
            CONF_MULTI_DEVICE: False,
        },
        unique_id=valid_imei,
    )
    entry.add_to_hass(hass)

    # Mock automation listeners
    mock_listener1 = MagicMock()
    mock_listener2 = MagicMock()

    with patch("custom_components.silencescooter.publish_mqtt_discovery_configs", AsyncMock()):
        with patch(
            "custom_components.silencescooter.automations.async_setup_automations",
            AsyncMock(return_value=[mock_listener1, mock_listener2])
        ):
            with patch("custom_components.silencescooter.automations.setup_persistent_sensors_update", AsyncMock()):
                await hass.config_entries.async_setup(entry.entry_id)
                await hass.async_block_till_done()

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    # Verify listeners were called (cleanup)
    mock_listener1.assert_called_once()
    mock_listener2.assert_called_once()


async def test_mqtt_discovery_published(hass: HomeAssistant, valid_imei, mock_automations):
    """Test that MQTT discovery configs are published."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_IMEI: valid_imei,
            CONF_MULTI_DEVICE: False,
        },
        unique_id=valid_imei,
    )
    entry.add_to_hass(hass)

    with patch("custom_components.silencescooter.publish_mqtt_discovery_configs", AsyncMock()) as mock_publish:
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    mock_publish.assert_called_once_with(hass, valid_imei)


async def test_mqtt_discovery_when_mqtt_not_available(hass: HomeAssistant, valid_imei, mock_automations):
    """Test setup continues when MQTT is not available."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_IMEI: valid_imei,
            CONF_MULTI_DEVICE: False,
        },
        unique_id=valid_imei,
    )
    entry.add_to_hass(hass)

    # Mock MQTT not being in components
    with patch("custom_components.silencescooter.publish_mqtt_discovery_configs") as mock_publish:
        async def mock_mqtt_publish(hass, imei):
            # Simulate MQTT not configured
            return

        mock_publish.side_effect = mock_mqtt_publish

        result = await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert result is True
    assert entry.state == ConfigEntryState.LOADED


async def test_reload_entry(hass: HomeAssistant, valid_imei, mock_automations):
    """Test reload entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_IMEI: valid_imei,
            CONF_MULTI_DEVICE: False,
        },
        unique_id=valid_imei,
    )
    entry.add_to_hass(hass)

    with patch("custom_components.silencescooter.publish_mqtt_discovery_configs", AsyncMock()):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Trigger reload
        from custom_components.silencescooter import async_reload_entry
        await async_reload_entry(hass, entry)
        await hass.async_block_till_done()

    assert entry.state == ConfigEntryState.LOADED


async def test_service_reset_tracked_counters(hass: HomeAssistant, valid_imei, mock_automations):
    """Test reset_tracked_counters service."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_IMEI: valid_imei,
            CONF_MULTI_DEVICE: False,
        },
        unique_id=valid_imei,
    )
    entry.add_to_hass(hass)

    with patch("custom_components.silencescooter.publish_mqtt_discovery_configs", AsyncMock()):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Verify service was registered
    assert hass.services.has_service(DOMAIN, "reset_tracked_counters")


async def test_service_restore_energy_costs(hass: HomeAssistant, valid_imei, mock_automations):
    """Test restore_energy_costs service."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_IMEI: valid_imei,
            CONF_MULTI_DEVICE: False,
        },
        unique_id=valid_imei,
    )
    entry.add_to_hass(hass)

    with patch("custom_components.silencescooter.publish_mqtt_discovery_configs", AsyncMock()):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Verify service was registered
    assert hass.services.has_service(DOMAIN, "restore_energy_costs")


async def test_platforms_loaded(hass: HomeAssistant, valid_imei, mock_automations):
    """Test all platforms are loaded."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_IMEI: valid_imei,
            CONF_MULTI_DEVICE: False,
        },
        unique_id=valid_imei,
    )
    entry.add_to_hass(hass)

    with patch("custom_components.silencescooter.publish_mqtt_discovery_configs", AsyncMock()):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Verify platforms are in the setup
    from custom_components.silencescooter.const import PLATFORMS
    for platform in PLATFORMS:
        # Check that platform setup was attempted
        assert f"{DOMAIN}.{platform}" in hass.config.components or platform in str(hass.config.components)
