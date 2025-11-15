"""Test Silence Scooter helper functions."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from homeassistant.core import HomeAssistant

from custom_components.silencescooter.helpers import (
    get_device_info,
    generate_entity_id_suffix,
    insert_imei_in_entity_id,
    is_date_valid,
    get_valid_datetime,
    log_event,
    update_history,
)
from custom_components.silencescooter.const import DOMAIN


def test_get_device_info_single_device(valid_imei):
    """Test get_device_info for single device."""
    device_info = get_device_info(valid_imei, multi_device=False)

    assert device_info["name"] == "Silence Scooter"
    assert device_info["manufacturer"] == "Seat"
    assert device_info["model"] == "Mo"
    assert (DOMAIN, valid_imei) in device_info["identifiers"]


def test_get_device_info_multi_device(valid_imei):
    """Test get_device_info for multi-device mode."""
    device_info = get_device_info(valid_imei, multi_device=True)

    imei_short = valid_imei[-4:]
    assert f"({imei_short})" in device_info["name"]
    assert (DOMAIN, valid_imei) in device_info["identifiers"]


def test_generate_entity_id_suffix_single_device(valid_imei):
    """Test entity ID suffix generation for single device."""
    suffix = generate_entity_id_suffix(valid_imei, multi_device=False)
    assert suffix == ""


def test_generate_entity_id_suffix_multi_device(valid_imei):
    """Test entity ID suffix generation for multi-device mode."""
    suffix = generate_entity_id_suffix(valid_imei, multi_device=True)

    imei_short = valid_imei[-4:]
    assert suffix == f"_{imei_short}"


def test_insert_imei_in_entity_id_single_device(valid_imei):
    """Test IMEI insertion for single device (no change)."""
    entity_id = "silence_scooter_speed"
    result = insert_imei_in_entity_id(entity_id, valid_imei, multi_device=False)

    assert result == entity_id


def test_insert_imei_in_entity_id_multi_device(valid_imei):
    """Test IMEI insertion for multi-device mode."""
    entity_id = "silence_scooter_speed"
    result = insert_imei_in_entity_id(entity_id, valid_imei, multi_device=True)

    imei_short = valid_imei[-4:]
    assert result == f"silence_scooter_{imei_short}_speed"


def test_insert_imei_in_entity_id_complex(valid_imei):
    """Test IMEI insertion with complex entity ID."""
    entity_id = "scooter_battery_soc"
    result = insert_imei_in_entity_id(entity_id, valid_imei, multi_device=True)

    imei_short = valid_imei[-4:]
    assert result == f"scooter_battery_{imei_short}_soc"


def test_insert_imei_in_entity_id_no_underscore(valid_imei):
    """Test IMEI insertion with no underscore in entity ID."""
    entity_id = "test"
    result = insert_imei_in_entity_id(entity_id, valid_imei, multi_device=True)

    imei_short = valid_imei[-4:]
    assert result == f"test_{imei_short}"


def test_is_date_valid_good_date():
    """Test date validation with valid date."""
    assert is_date_valid("2024-01-15 12:00:00") is True


def test_is_date_valid_1970():
    """Test date validation rejects 1970."""
    assert is_date_valid("1970-01-01 00:00:00") is False


def test_is_date_valid_1969():
    """Test date validation rejects 1969."""
    assert is_date_valid("1969-12-31 23:59:59") is False


def test_is_date_valid_unknown():
    """Test date validation handles unknown."""
    assert is_date_valid("unknown") is False


def test_is_date_valid_unavailable():
    """Test date validation handles unavailable."""
    assert is_date_valid("unavailable") is False


def test_is_date_valid_empty():
    """Test date validation handles empty string."""
    assert is_date_valid("") is False


def test_is_date_valid_none():
    """Test date validation handles None."""
    assert is_date_valid(None) is False


def test_get_valid_datetime_good_date():
    """Test datetime parsing with valid date."""
    from homeassistant.util import dt as dt_util

    dt_str = "2024-01-15T12:00:00"
    result = get_valid_datetime(dt_str)

    assert result is not None
    assert result.year == 2024


def test_get_valid_datetime_invalid_date():
    """Test datetime parsing with invalid date (1970)."""
    dt_str = "1970-01-01T00:00:00"
    result = get_valid_datetime(dt_str, default="default")

    assert result == "default"


def test_get_valid_datetime_unknown():
    """Test datetime parsing with unknown."""
    result = get_valid_datetime("unknown", default=None)

    assert result is None


def test_get_valid_datetime_old_date():
    """Test datetime parsing rejects very old dates."""
    dt_str = "1999-01-01T00:00:00"
    result = get_valid_datetime(dt_str, default="default")

    assert result == "default"


async def test_log_event(hass: HomeAssistant):
    """Test log_event helper."""
    message = "Test log message"

    with patch("pathlib.Path.open", create=True) as mock_open:
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        await log_event(hass, message)
        await hass.async_block_till_done()

        # Verify file was written to
        mock_file.write.assert_called()
        written_text = mock_file.write.call_args[0][0]
        assert message in written_text


async def test_log_event_empty_message(hass: HomeAssistant):
    """Test log_event with empty message."""
    # Should not crash
    await log_event(hass, "")
    await hass.async_block_till_done()


async def test_update_history_success(hass: HomeAssistant):
    """Test update_history helper."""
    kwargs = {
        "avg_speed": 30,
        "distance": 10.5,
        "duration": 20,
        "start_time": "2024-01-15 12:00:00",
        "end_time": "2024-01-15 12:20:00",
        "max_speed": 45,
        "battery": 15.5,
        "outdoor_temp": 20,
    }

    with patch("custom_components.silencescooter.const.HISTORY_SCRIPT") as mock_script:
        mock_script.exists.return_value = True

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = await update_history(hass, **kwargs)

    assert result is True


async def test_update_history_script_not_found(hass: HomeAssistant):
    """Test update_history when script doesn't exist."""
    kwargs = {
        "avg_speed": 30,
        "distance": 10.5,
        "duration": 20,
    }

    with patch("custom_components.silencescooter.const.HISTORY_SCRIPT") as mock_script:
        mock_script.exists.return_value = False

        result = await update_history(hass, **kwargs)

    assert result is False


async def test_update_history_script_fails(hass: HomeAssistant):
    """Test update_history when script fails."""
    kwargs = {
        "avg_speed": 30,
        "distance": 10.5,
        "duration": 20,
    }

    with patch("custom_components.silencescooter.const.HISTORY_SCRIPT") as mock_script:
        mock_script.exists.return_value = True

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stderr="Script error"
            )

            result = await update_history(hass, **kwargs)

    assert result is False
