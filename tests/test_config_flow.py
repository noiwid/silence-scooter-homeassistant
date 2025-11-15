"""Test the Silence Scooter config flow."""
from unittest.mock import patch, AsyncMock
import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.silencescooter.const import DOMAIN, CONF_IMEI, CONF_MULTI_DEVICE


async def test_form(hass: HomeAssistant):
    """Test we get the form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {}


async def test_form_invalid_imei_too_short(hass: HomeAssistant):
    """Test we handle invalid IMEI (too short)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_IMEI: "123", CONF_MULTI_DEVICE: False},
    )

    assert result2["type"] == FlowResultType.FORM
    assert CONF_IMEI in result2["errors"]


async def test_form_invalid_imei_too_long(hass: HomeAssistant):
    """Test we handle invalid IMEI (too long)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_IMEI: "12345678901234567", CONF_MULTI_DEVICE: False},
    )

    assert result2["type"] == FlowResultType.FORM
    assert CONF_IMEI in result2["errors"]


async def test_form_invalid_imei_non_numeric(hass: HomeAssistant):
    """Test we handle invalid IMEI (non-numeric)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_IMEI: "abcdefghijklmno", CONF_MULTI_DEVICE: False},
    )

    assert result2["type"] == FlowResultType.FORM
    assert CONF_IMEI in result2["errors"]


async def test_form_valid_imei_15_digits(hass: HomeAssistant):
    """Test successful config flow with valid 15-digit IMEI."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.silencescooter.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_IMEI: "869123456789012", CONF_MULTI_DEVICE: False},
        )
        await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert "9012" in result2["title"]
    assert result2["data"][CONF_IMEI] == "869123456789012"
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_valid_imei_14_digits(hass: HomeAssistant):
    """Test successful config flow with valid 14-digit IMEI."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.silencescooter.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_IMEI: "86912345678901", CONF_MULTI_DEVICE: False},
        )
        await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert "8901" in result2["title"]
    assert result2["data"][CONF_IMEI] == "86912345678901"
    assert len(mock_setup_entry.mock_calls) == 1


async def test_form_valid_imei_16_digits_truncated(hass: HomeAssistant):
    """Test that 16-digit IMEI/SV is truncated to 15 digits."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.silencescooter.async_setup_entry",
        return_value=True,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_IMEI: "8691234567890123", CONF_MULTI_DEVICE: False},
        )
        await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    # Should be truncated to 15 digits
    assert result2["data"][CONF_IMEI] == "869123456789012"


async def test_form_imei_with_spaces_and_dashes(hass: HomeAssistant):
    """Test that IMEI with spaces and dashes is cleaned."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.silencescooter.async_setup_entry",
        return_value=True,
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_IMEI: "869-123-456-789-012", CONF_MULTI_DEVICE: False},
        )
        await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_IMEI] == "869123456789012"


async def test_form_duplicate_imei(hass: HomeAssistant):
    """Test we handle duplicate IMEI."""
    # First entry
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with patch(
        "custom_components.silencescooter.async_setup_entry",
        return_value=True,
    ):
        await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_IMEI: "869123456789012", CONF_MULTI_DEVICE: False},
        )
        await hass.async_block_till_done()

    # Try to add same IMEI again
    result2 = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result3 = await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        {CONF_IMEI: "869123456789012", CONF_MULTI_DEVICE: False},
    )

    assert result3["type"] == FlowResultType.ABORT
    assert result3["reason"] == "already_configured"


async def test_form_validation_confirmation_delay_too_low(hass: HomeAssistant):
    """Test validation of confirmation_delay."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_IMEI: "869123456789012",
            CONF_MULTI_DEVICE: False,
            "confirmation_delay": 20,  # Too low
        },
    )

    assert result2["type"] == FlowResultType.FORM
    assert "confirmation_delay" in result2["errors"]


async def test_form_validation_confirmation_delay_too_high(hass: HomeAssistant):
    """Test validation of confirmation_delay."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_IMEI: "869123456789012",
            CONF_MULTI_DEVICE: False,
            "confirmation_delay": 700,  # Too high
        },
    )

    assert result2["type"] == FlowResultType.FORM
    assert "confirmation_delay" in result2["errors"]


async def test_form_validation_pause_duration(hass: HomeAssistant):
    """Test validation of pause_max_duration."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_IMEI: "869123456789012",
            CONF_MULTI_DEVICE: False,
            "pause_max_duration": 0,  # Too low
        },
    )

    assert result2["type"] == FlowResultType.FORM
    assert "pause_max_duration" in result2["errors"]


async def test_form_validation_watchdog_delay(hass: HomeAssistant):
    """Test validation of watchdog_delay."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_IMEI: "869123456789012",
            CONF_MULTI_DEVICE: False,
            "watchdog_delay": 100,  # Too high
        },
    )

    assert result2["type"] == FlowResultType.FORM
    assert "watchdog_delay" in result2["errors"]


async def test_form_validation_tariff_sensor_not_found(hass: HomeAssistant):
    """Test validation of non-existent tariff sensor."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_IMEI: "869123456789012",
            CONF_MULTI_DEVICE: False,
            "tariff_sensor": "sensor.nonexistent",
        },
    )

    assert result2["type"] == FlowResultType.FORM
    assert "tariff_sensor" in result2["errors"]


async def test_form_validation_external_temp_entity_required(hass: HomeAssistant):
    """Test that external temp entity is required when source is external."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_IMEI: "869123456789012",
            CONF_MULTI_DEVICE: False,
            "outdoor_temp_source": "external",
            "outdoor_temp_entity": "",  # Missing
        },
    )

    assert result2["type"] == FlowResultType.FORM
    assert "outdoor_temp_entity" in result2["errors"]


async def test_options_flow(hass: HomeAssistant, valid_imei):
    """Test options flow."""
    # Create config entry first
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_IMEI: valid_imei, CONF_MULTI_DEVICE: False},
        unique_id=valid_imei,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_options_flow_update(hass: HomeAssistant, valid_imei):
    """Test options flow can update settings."""
    # Create config entry
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

    result = await hass.config_entries.options.async_init(entry.entry_id)

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "confirmation_delay": 180,
            "pause_max_duration": 10,
        },
    )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data["confirmation_delay"] == 180
    assert entry.data["pause_max_duration"] == 10


async def test_reauth_flow(hass: HomeAssistant):
    """Test reauth flow for migration."""
    # Create entry without IMEI (simulating v1 migration)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},  # No IMEI
        unique_id=None,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"


async def test_reauth_confirm_success(hass: HomeAssistant, valid_imei):
    """Test reauth confirm step successfully adds IMEI."""
    # Create entry without IMEI
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        unique_id=None,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_IMEI: valid_imei},
    )

    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "reauth_successful"
    assert entry.data[CONF_IMEI] == valid_imei
    assert entry.unique_id == valid_imei


async def test_reauth_confirm_duplicate(hass: HomeAssistant, valid_imei):
    """Test reauth fails if IMEI already exists."""
    # Create first entry with IMEI
    entry1 = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_IMEI: valid_imei},
        unique_id=valid_imei,
    )
    entry1.add_to_hass(hass)

    # Create second entry without IMEI
    entry2 = MockConfigEntry(
        domain=DOMAIN,
        data={},
        unique_id=None,
    )
    entry2.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry2.entry_id,
        },
    )

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_IMEI: valid_imei},  # Same IMEI
    )

    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


async def test_import_flow(hass: HomeAssistant):
    """Test import from configuration.yaml."""
    with patch(
        "custom_components.silencescooter.async_setup_entry",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_IMPORT},
            data={CONF_IMEI: "869123456789012", CONF_MULTI_DEVICE: False},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_IMEI] == "869123456789012"
