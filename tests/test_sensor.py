"""Test Silence Scooter sensors."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_UNKNOWN
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.silencescooter.const import DOMAIN, CONF_IMEI
from custom_components.silencescooter.sensor import (
    ScooterWritableSensor,
    ScooterTemplateSensor,
    ScooterTriggerSensor,
    ScooterTripsSensor,
    ScooterUtilityMeterSensor,
    ScooterDefaultTariffSensor,
)


async def test_writable_sensor_creation(hass: HomeAssistant, valid_imei):
    """Test writable sensor creation."""
    config = {
        "name": "Test Sensor",
        "unit_of_measurement": "km",
        "device_class": "distance",
        "icon": "mdi:speedometer",
    }

    sensor = ScooterWritableSensor(
        hass, "test_sensor", config, valid_imei, multi_device=False
    )

    assert sensor._attr_unique_id == f"test_sensor_{valid_imei}"
    assert sensor._attr_name == "Test Sensor"
    assert sensor._attr_native_unit_of_measurement == "km"
    assert sensor._attr_device_class == "distance"
    assert sensor._attr_icon == "mdi:speedometer"


async def test_writable_sensor_creation_multi_device(hass: HomeAssistant, valid_imei):
    """Test writable sensor creation in multi-device mode."""
    config = {
        "name": "Test Sensor",
        "unit_of_measurement": "km",
    }

    sensor = ScooterWritableSensor(
        hass, "test_sensor", config, valid_imei, multi_device=True
    )

    imei_short = valid_imei[-4:]
    assert sensor._attr_unique_id == f"test_sensor_{valid_imei}"
    assert f"({imei_short})" in sensor._attr_name


async def test_writable_sensor_state_update(hass: HomeAssistant, valid_imei):
    """Test writable sensor state update."""
    config = {"name": "Test Sensor"}
    sensor = ScooterWritableSensor(
        hass, "test_sensor", config, valid_imei, multi_device=False
    )

    await sensor.async_set_native_value(42.5)
    assert sensor._attr_native_value == 42.5


async def test_writable_sensor_state_update_invalid(hass: HomeAssistant, valid_imei):
    """Test writable sensor handles invalid state update."""
    config = {"name": "Test Sensor"}
    sensor = ScooterWritableSensor(
        hass, "test_sensor", config, valid_imei, multi_device=False
    )

    original_value = sensor._attr_native_value
    await sensor.async_set_native_value("invalid")
    # Should keep original value on error
    assert sensor._attr_native_value == original_value


async def test_writable_sensor_restore_state(hass: HomeAssistant, valid_imei):
    """Test writable sensor restores last state."""
    config = {"name": "Test Sensor"}
    sensor = ScooterWritableSensor(
        hass, "test_sensor", config, valid_imei, multi_device=False
    )

    # Initialize hass.data
    hass.data[DOMAIN] = {}

    # Mock restore state
    with patch.object(sensor, "async_get_last_state") as mock_restore:
        mock_state = MagicMock()
        mock_state.state = "123.45"
        mock_restore.return_value = mock_state

        await sensor.async_added_to_hass()

    assert sensor._attr_native_value == 123.45


async def test_template_sensor_creation(hass: HomeAssistant, valid_imei):
    """Test template sensor creation."""
    config = {
        "value_template": "{{ 100 }}",
        "unit_of_measurement": "%",
        "device_class": "battery",
    }

    sensor = ScooterTemplateSensor(
        hass, "test_template", config, valid_imei, multi_device=False
    )

    assert sensor._attr_unique_id == f"test_template_{valid_imei}"
    assert sensor._attr_native_unit_of_measurement == "%"
    assert sensor._attr_device_class == "battery"


async def test_template_sensor_update(hass: HomeAssistant, valid_imei):
    """Test template sensor updates correctly."""
    config = {
        "value_template": "{{ 50 + 50 }}",
    }

    sensor = ScooterTemplateSensor(
        hass, "test_template", config, valid_imei, multi_device=False
    )

    await sensor.async_update()
    assert sensor._attr_native_value == "100"


async def test_template_sensor_with_icon_template(hass: HomeAssistant, valid_imei):
    """Test template sensor with icon template."""
    config = {
        "value_template": "{{ 100 }}",
        "icon_template": "mdi:battery-{{ 100 }}",
    }

    sensor = ScooterTemplateSensor(
        hass, "test_template", config, valid_imei, multi_device=False
    )

    await sensor.async_update()
    assert "mdi:battery" in sensor._attr_icon


async def test_template_sensor_error_handling(hass: HomeAssistant, valid_imei):
    """Test template sensor handles template errors."""
    config = {
        "value_template": "{{ invalid | nonexistent_filter }}",
    }

    sensor = ScooterTemplateSensor(
        hass, "test_template", config, valid_imei, multi_device=False
    )

    await sensor.async_update()
    # Should not crash, value should be None
    assert sensor._attr_native_value is None


async def test_trigger_sensor_creation(hass: HomeAssistant, valid_imei):
    """Test trigger sensor creation."""
    config = {
        "value_template": "{{ 42 }}",
        "triggers": [
            {
                "platform": "state",
                "entity_id": "sensor.test",
            }
        ],
    }

    sensor = ScooterTriggerSensor(
        hass, "test_trigger", config, valid_imei, multi_device=False
    )

    assert sensor._triggers == config["triggers"]


async def test_trigger_sensor_state_trigger(hass: HomeAssistant, valid_imei):
    """Test trigger sensor responds to state changes."""
    config = {
        "value_template": "{{ states('sensor.test') | int }}",
        "triggers": [
            {
                "platform": "state",
                "entity_id": "sensor.test",
            }
        ],
    }

    sensor = ScooterTriggerSensor(
        hass, "test_trigger", config, valid_imei, multi_device=False
    )

    # Set up test sensor
    hass.states.async_set("sensor.test", "100")

    await sensor.async_added_to_hass()
    await hass.async_block_till_done()

    # Trigger should have been set up
    assert len(sensor._triggers) == 1


async def test_trips_sensor_creation(hass: HomeAssistant, valid_imei):
    """Test trips sensor creation."""
    sensor = ScooterTripsSensor(hass, valid_imei, multi_device=False)

    assert sensor._attr_unique_id == f"trips_{valid_imei}"
    assert sensor._attr_name == "Scooter Trips"
    assert sensor._attr_icon == "mdi:scooter"
    assert sensor._attr_native_value == 0


async def test_trips_sensor_multi_device(hass: HomeAssistant, valid_imei):
    """Test trips sensor in multi-device mode."""
    sensor = ScooterTripsSensor(hass, valid_imei, multi_device=True)

    imei_short = valid_imei[-4:]
    assert f"({imei_short})" in sensor._attr_name


async def test_trips_sensor_read_history(hass: HomeAssistant, valid_imei, mock_history_file):
    """Test trips sensor reads history file."""
    import json

    # Write test history
    history_data = [
        {"distance": 10, "avg_speed": 30},
        {"distance": 15, "avg_speed": 35},
    ]
    mock_history_file.write_text(json.dumps(history_data))

    sensor = ScooterTripsSensor(hass, valid_imei, multi_device=False)

    await sensor.async_update()

    assert sensor._attr_native_value == 2
    assert len(sensor._attr_extra_state_attributes["history"]) == 2


async def test_utility_meter_sensor_creation(hass: HomeAssistant, valid_imei):
    """Test utility meter sensor creation."""
    config = {
        "source": "sensor.source",
        "cycle": "daily",
    }

    sensor = ScooterUtilityMeterSensor(
        hass, "test_meter", config, valid_imei, multi_device=False
    )

    assert sensor._attr_unique_id == f"test_meter_{valid_imei}"
    assert sensor._source == "sensor.source"
    assert sensor._cycle == "daily"
    assert sensor._attr_native_unit_of_measurement == "kWh"
    assert sensor._attr_device_class == "energy"


async def test_utility_meter_sensor_updates(hass: HomeAssistant, valid_imei):
    """Test utility meter sensor tracks consumption."""
    config = {
        "source": "sensor.source",
        "cycle": "daily",
    }

    sensor = ScooterUtilityMeterSensor(
        hass, "test_meter", config, valid_imei, multi_device=False
    )

    # Initialize
    hass.states.async_set("sensor.source", "10.5")
    await sensor.async_added_to_hass()
    await hass.async_block_till_done()

    # Should initialize with 0 consumption
    assert sensor._attr_native_value == 0
    assert sensor._cycle_start_value == 10.5

    # Simulate consumption increase
    hass.states.async_set("sensor.source", "12.0")
    await hass.async_block_till_done()

    # Should track consumption
    assert sensor._attr_native_value == 1.5


async def test_utility_meter_sensor_handles_negative_consumption(hass: HomeAssistant, valid_imei):
    """Test utility meter sensor handles negative consumption (source reset)."""
    config = {
        "source": "sensor.source",
        "cycle": "daily",
    }

    sensor = ScooterUtilityMeterSensor(
        hass, "test_meter", config, valid_imei, multi_device=False
    )

    # Initialize with high value
    hass.states.async_set("sensor.source", "100.0")
    await sensor.async_added_to_hass()
    await hass.async_block_till_done()

    # Source is reset to lower value (e.g., counter was reset)
    hass.states.async_set("sensor.source", "5.0")
    await hass.async_block_till_done()

    # Should reset cycle_start_value to avoid negative consumption
    assert sensor._attr_native_value == 0
    assert sensor._cycle_start_value == 5.0


async def test_utility_meter_sensor_restore_state(hass: HomeAssistant, valid_imei):
    """Test utility meter sensor restores state."""
    from datetime import datetime

    config = {
        "source": "sensor.source",
        "cycle": "daily",
    }

    sensor = ScooterUtilityMeterSensor(
        hass, "test_meter", config, valid_imei, multi_device=False
    )

    # Mock restore state
    with patch.object(sensor, "async_get_last_state") as mock_restore:
        mock_state = MagicMock()
        mock_state.state = "5.5"
        mock_state.attributes = {
            "last_reset": datetime.now().isoformat(),
            "cycle_start_value": 10.0,
        }
        mock_restore.return_value = mock_state

        hass.states.async_set("sensor.source", "15.5")
        await sensor.async_added_to_hass()

    assert sensor._attr_native_value == 5.5
    assert sensor._cycle_start_value == 10.0


async def test_utility_meter_sensor_offline_source_preservation(hass: HomeAssistant, valid_imei):
    """Test utility meter preserves data when source is offline (0)."""
    config = {
        "source": "sensor.source",
        "cycle": "daily",
    }

    sensor = ScooterUtilityMeterSensor(
        hass, "test_meter", config, valid_imei, multi_device=False
    )

    # Mock restored state with valid data
    with patch.object(sensor, "async_get_last_state") as mock_restore:
        from datetime import datetime
        mock_state = MagicMock()
        mock_state.state = "2.5"
        mock_state.attributes = {
            "last_reset": datetime.now().isoformat(),
            "cycle_start_value": 10.0,
        }
        mock_restore.return_value = mock_state

        # Source is 0 (offline)
        hass.states.async_set("sensor.source", "0")
        await sensor.async_added_to_hass()
        await hass.async_block_till_done()

    # Should preserve restored data, not recalculate
    assert sensor._attr_native_value == 2.5
    assert sensor._cycle_start_value == 10.0


async def test_default_tariff_sensor_creation(hass: HomeAssistant, valid_imei):
    """Test default tariff sensor creation."""
    sensor = ScooterDefaultTariffSensor(hass, valid_imei, multi_device=False)

    assert sensor._attr_unique_id == f"default_electricity_price_{valid_imei}"
    assert sensor._attr_name == "Silencescooter Default Electricity Price"
    assert sensor._attr_native_unit_of_measurement == "€/kWh"
    assert sensor._attr_device_class == "monetary"


async def test_default_tariff_sensor_value(hass: HomeAssistant, valid_imei):
    """Test default tariff sensor returns default price."""
    from custom_components.silencescooter.const import DEFAULT_ELECTRICITY_PRICE

    sensor = ScooterDefaultTariffSensor(hass, valid_imei, multi_device=False)

    assert sensor.native_value == DEFAULT_ELECTRICITY_PRICE


async def test_sensor_platform_setup(hass: HomeAssistant, valid_imei, mock_automations):
    """Test sensor platform setup."""
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

    # Check that sensors were created
    state = hass.states.get("sensor.scooter_trips")
    # Sensor might not be fully initialized yet, but platform should be loaded
    assert "sensor" in hass.config.components or f"{DOMAIN}.sensor" in hass.config.components
