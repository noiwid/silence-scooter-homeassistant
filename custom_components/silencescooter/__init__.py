"""The Silence Scooter integration."""
import logging
import json
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
import homeassistant.helpers.device_registry as dr
import homeassistant.helpers.entity_registry as er

from .const import DOMAIN, PLATFORMS, CONF_IMEI, CONF_MULTI_DEVICE, DEFAULT_MULTI_DEVICE

_LOGGER = logging.getLogger(__name__)


async def publish_mqtt_discovery_configs(hass: HomeAssistant, imei: str) -> None:
    """Publish MQTT Discovery configs for all sensors/buttons for this IMEI.

    This implements automatic MQTT Discovery (Solution B) to simplify user
    configuration. Instead of manually configuring 80+ MQTT entities per scooter,
    this function publishes discovery configs automatically.
    """
    # Check if MQTT is available
    if "mqtt" not in hass.config.components:
        _LOGGER.warning("MQTT not configured, skipping auto-discovery for IMEI %s", imei[-4:])
        return

    try:
        mqtt_publish = hass.components.mqtt.async_publish
        imei_short = imei[-4:] if len(imei) >= 4 else imei

        # Device info shared by all entities
        device_info = {
            "identifiers": [imei],
            "name": f"Silence Scooter ({imei_short})",
            "manufacturer": "Seat",
            "model": "Silence S01"
        }

        # Define all sensors to auto-discover (extracted from examples/silence.yaml)
        sensors_config = {
            # Basic sensors
            "speed": {
                "name": "Speed",
                "unit": "km/h",
                "device_class": "speed",
                "icon": "mdi:speedometer"
            },
            "odo": {
                "name": "ODO",
                "unit": "km",
                "icon": "mdi:counter"
            },
            "range": {
                "name": "Range",
                "unit": "km",
                "device_class": "distance",
                "icon": "mdi:gauge"
            },
            "status": {
                "name": "Status",
                "icon": "mdi:information-outline",
                "expire_after": 120
            },
            "VIN": {
                "name": "VIN",
                "icon": "mdi:identifier"
            },
            "last-update": {
                "name": "Last Update",
                "device_class": "timestamp",
                "value_template": "{{ (value | as_datetime | as_local).isoformat() }}"
            },

            # Battery sensors
            "SOCbatteria": {
                "name": "Battery SoC",
                "unit": "%",
                "device_class": "battery",
                "icon": "mdi:battery"
            },
            "VOLTbatteria": {
                "name": "Battery Volt",
                "unit": "V",
                "device_class": "voltage",
                "icon": "mdi:flash"
            },
            "batteryCurrent": {
                "name": "Battery Current",
                "unit": "A",
                "device_class": "current",
                "icon": "mdi:current-dc"
            },
            "astraBatterySOC": {
                "name": "Astra Battery SoC",
                "unit": "%",
                "device_class": "battery",
                "icon": "mdi:battery-bluetooth"
            },
            "BatteryTempMin": {
                "name": "Battery Temperature Min",
                "unit": "°C",
                "device_class": "temperature",
                "icon": "mdi:thermometer-chevron-down"
            },
            "BatteryTempMax": {
                "name": "Battery Temperature Max",
                "unit": "°C",
                "device_class": "temperature",
                "icon": "mdi:thermometer-chevron-up"
            },

            # Energy sensors
            "chargedEnergy": {
                "name": "Charged Energy",
                "unit": "kWh",
                "device_class": "energy",
                "icon": "mdi:battery-charging"
            },
            "DischargedEnergy": {
                "name": "Discharged Energy",
                "unit": "kWh",
                "device_class": "energy",
                "state_class": "total_increasing",
                "icon": "mdi:battery-minus"
            },
            "RegeneratedEnergy": {
                "name": "Regenerated Energy",
                "unit": "kWh",
                "device_class": "energy",
                "state_class": "total_increasing",
                "icon": "mdi:battery-plus"
            },

            # Temperature sensors
            "inverterTemp": {
                "name": "Inverter Temperature",
                "unit": "°C",
                "device_class": "temperature",
                "icon": "mdi:thermometer"
            },
            "motorTemp": {
                "name": "Motor Temperature",
                "unit": "°C",
                "device_class": "temperature",
                "icon": "mdi:thermometer"
            },
            "ambientTemp": {
                "name": "Ambient Temperature",
                "unit": "°C",
                "device_class": "temperature",
                "icon": "mdi:thermometer"
            },

            # GPS sensors
            "latitude": {
                "name": "Latitude",
                "unit": "°",
                "icon": "mdi:map-marker-radius"
            },
            "longitude": {
                "name": "Longitude",
                "unit": "°",
                "icon": "mdi:map-marker-radius"
            },

            # Battery cell voltages (14 cells)
            "Cell1Voltage": {
                "name": "Cell 1 Voltage",
                "unit": "V",
                "device_class": "voltage",
                "value_template": "{{ (value | float / 1000) | round(3) }}"
            },
            "Cell2Voltage": {
                "name": "Cell 2 Voltage",
                "unit": "V",
                "device_class": "voltage",
                "value_template": "{{ (value | float / 1000) | round(3) }}"
            },
            "Cell3Voltage": {
                "name": "Cell 3 Voltage",
                "unit": "V",
                "device_class": "voltage",
                "value_template": "{{ (value | float / 1000) | round(3) }}"
            },
            "Cell4Voltage": {
                "name": "Cell 4 Voltage",
                "unit": "V",
                "device_class": "voltage",
                "value_template": "{{ (value | float / 1000) | round(3) }}"
            },
            "Cell5Voltage": {
                "name": "Cell 5 Voltage",
                "unit": "V",
                "device_class": "voltage",
                "value_template": "{{ (value | float / 1000) | round(3) }}"
            },
            "Cell6Voltage": {
                "name": "Cell 6 Voltage",
                "unit": "V",
                "device_class": "voltage",
                "value_template": "{{ (value | float / 1000) | round(3) }}"
            },
            "Cell7Voltage": {
                "name": "Cell 7 Voltage",
                "unit": "V",
                "device_class": "voltage",
                "value_template": "{{ (value | float / 1000) | round(3) }}"
            },
            "Cell8Voltage": {
                "name": "Cell 8 Voltage",
                "unit": "V",
                "device_class": "voltage",
                "value_template": "{{ (value | float / 1000) | round(3) }}"
            },
            "Cell9Voltage": {
                "name": "Cell 9 Voltage",
                "unit": "V",
                "device_class": "voltage",
                "value_template": "{{ (value | float / 1000) | round(3) }}"
            },
            "Cell10Voltage": {
                "name": "Cell 10 Voltage",
                "unit": "V",
                "device_class": "voltage",
                "value_template": "{{ (value | float / 1000) | round(3) }}"
            },
            "Cell11Voltage": {
                "name": "Cell 11 Voltage",
                "unit": "V",
                "device_class": "voltage",
                "value_template": "{{ (value | float / 1000) | round(3) }}"
            },
            "Cell12Voltage": {
                "name": "Cell 12 Voltage",
                "unit": "V",
                "device_class": "voltage",
                "value_template": "{{ (value | float / 1000) | round(3) }}"
            },
            "Cell13Voltage": {
                "name": "Cell 13 Voltage",
                "unit": "V",
                "device_class": "voltage",
                "value_template": "{{ (value | float / 1000) | round(3) }}"
            },
            "Cell14Voltage": {
                "name": "Cell 14 Voltage",
                "unit": "V",
                "device_class": "voltage",
                "value_template": "{{ (value | float / 1000) | round(3) }}"
            },
        }

        # Binary sensors
        binary_sensors_config = {
            "movementAlarm": {
                "name": "Movement Alarm",
                "device_class": "motion",
                "payload_on": "1",
                "payload_off": "0"
            },
            "batteryIn": {
                "name": "Battery In",
                "device_class": "plug",
                "payload_on": "1",
                "payload_off": "0",
                "expire_after": 120
            },
            "sidestandOut": {
                "name": "Sidestand Out",
                "device_class": "opening",
                "payload_on": "1",
                "payload_off": "0"
            },
            "bikefall": {
                "name": "Bikefall",
                "device_class": "problem",
                "payload_on": "1",
                "payload_off": "0"
            },
            "overspeedAlarm": {
                "name": "Overspeed Alarm",
                "device_class": "problem",
                "payload_on": "1",
                "payload_off": "0"
            },
            "motionDetected": {
                "name": "Motion Detected",
                "device_class": "motion",
                "payload_on": "1",
                "payload_off": "0"
            },
        }

        # Button commands
        buttons_config = {
            "TURN_ON_SCOOTER": {
                "name": "Turn On",
                "icon": "mdi:power"
            },
            "TURN_OFF_SCOOTER": {
                "name": "Turn Off",
                "icon": "mdi:power-off"
            },
            "OPEN_SEAT": {
                "name": "Open Seat",
                "icon": "mdi:car-seat"
            },
            "FLASH": {
                "name": "Flash",
                "icon": "mdi:lightbulb-flash"
            },
            "BEEP_FLASH": {
                "name": "Beep & Flash",
                "icon": "mdi:alarm-light"
            },
        }

        # Publish sensor discoveries
        for sensor_key, sensor_config in sensors_config.items():
            discovery_topic = f"homeassistant/sensor/{DOMAIN}_{imei}/{sensor_key}/config"

            payload = {
                "name": f"{sensor_config['name']} ({imei_short})",
                "state_topic": f"home/silence-server/{imei}/status/{sensor_key}",
                "unique_id": f"{DOMAIN}_{imei}_{sensor_key}",
                "device": device_info,
                "object_id": f"{DOMAIN}_{sensor_key}_{imei_short}"
            }

            # Add optional fields
            if "unit" in sensor_config:
                payload["unit_of_measurement"] = sensor_config["unit"]
            if "device_class" in sensor_config:
                payload["device_class"] = sensor_config["device_class"]
            if "state_class" in sensor_config:
                payload["state_class"] = sensor_config["state_class"]
            if "icon" in sensor_config:
                payload["icon"] = sensor_config["icon"]
            if "expire_after" in sensor_config:
                payload["expire_after"] = sensor_config["expire_after"]
            if "value_template" in sensor_config:
                payload["value_template"] = sensor_config["value_template"]

            await mqtt_publish(discovery_topic, json.dumps(payload), retain=True)

        # Publish binary sensor discoveries
        for sensor_key, sensor_config in binary_sensors_config.items():
            discovery_topic = f"homeassistant/binary_sensor/{DOMAIN}_{imei}/{sensor_key}/config"

            payload = {
                "name": f"{sensor_config['name']} ({imei_short})",
                "state_topic": f"home/silence-server/{imei}/status/{sensor_key}",
                "unique_id": f"{DOMAIN}_{imei}_{sensor_key}",
                "device": device_info,
                "object_id": f"{DOMAIN}_{sensor_key}_{imei_short}"
            }

            # Add optional fields
            if "device_class" in sensor_config:
                payload["device_class"] = sensor_config["device_class"]
            if "payload_on" in sensor_config:
                payload["payload_on"] = sensor_config["payload_on"]
            if "payload_off" in sensor_config:
                payload["payload_off"] = sensor_config["payload_off"]
            if "expire_after" in sensor_config:
                payload["expire_after"] = sensor_config["expire_after"]

            await mqtt_publish(discovery_topic, json.dumps(payload), retain=True)

        # Publish button discoveries
        for button_key, button_config in buttons_config.items():
            discovery_topic = f"homeassistant/button/{DOMAIN}_{imei}/{button_key}/config"

            payload = {
                "name": f"{button_config['name']} ({imei_short})",
                "command_topic": f"home/silence-server/{imei}/command/{button_key}",
                "unique_id": f"{DOMAIN}_{imei}_{button_key}",
                "device": device_info,
                "object_id": f"{DOMAIN}_{button_key}_{imei_short}"
            }

            if "icon" in button_config:
                payload["icon"] = button_config["icon"]

            await mqtt_publish(discovery_topic, json.dumps(payload), retain=True)

        _LOGGER.info("Published MQTT Discovery configs for IMEI %s (%d sensors, %d binary sensors, %d buttons)",
                     imei_short, len(sensors_config), len(binary_sensors_config), len(buttons_config))

    except Exception as e:
        _LOGGER.error("Error publishing MQTT Discovery configs for IMEI %s: %s", imei[-4:], e, exc_info=True)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services with multi-device support."""

    async def reset_tracked_counters(call: ServiceCall) -> None:
        """Reset tracked distance and battery counters for selected device."""
        device_id = call.data.get("device_id")

        if device_id:
            # Reset counters for specific device
            device_registry = dr.async_get(hass)
            entity_registry = er.async_get(hass)

            # Find all entities for this device
            entities = er.async_entries_for_device(entity_registry, device_id)

            # Reset relevant entities
            for entity in entities:
                if "tracked_distance" in entity.entity_id:
                    await hass.services.async_call(
                        "number", "set_value",
                        {"entity_id": entity.entity_id, "value": 0},
                        blocking=True
                    )
                    _LOGGER.info("Reset %s to 0", entity.entity_id)
                elif "tracked_battery_used" in entity.entity_id:
                    await hass.services.async_call(
                        "number", "set_value",
                        {"entity_id": entity.entity_id, "value": 0},
                        blocking=True
                    )
                    _LOGGER.info("Reset %s to 0", entity.entity_id)
        else:
            # Reset all devices (backward compatibility)
            _LOGGER.info("No device_id specified, resetting all scooters")
            entity_registry = er.async_get(hass)

            for entity in entity_registry.entities.values():
                if entity.platform == DOMAIN:
                    if "tracked_distance" in entity.entity_id or "tracked_battery_used" in entity.entity_id:
                        await hass.services.async_call(
                            "number", "set_value",
                            {"entity_id": entity.entity_id, "value": 0},
                            blocking=True
                        )
                        _LOGGER.info("Reset %s to 0", entity.entity_id)

    async def restore_energy_costs(call: ServiceCall) -> None:
        """Restore energy cost utility meters by modifying sensors in memory."""
        device_id = call.data.get("device_id")
        daily_value = call.data.get("daily", 0.12)
        weekly_value = call.data.get("weekly", 0.12)
        monthly_value = call.data.get("monthly", 2.26)
        yearly_value = call.data.get("yearly", 2.26)
        source_value_param = call.data.get("source_value")
        electricity_price = 0.2062  # EUR/kWh

        # Determine which entities to update based on device_id
        if device_id:
            # Get IMEI suffix from device
            device_registry = dr.async_get(hass)
            entity_registry = er.async_get(hass)

            device = device_registry.async_get(device_id)
            if not device:
                _LOGGER.error("Device %s not found", device_id)
                return

            # Extract IMEI from device identifiers
            imei = None
            for identifier in device.identifiers:
                if identifier[0] == DOMAIN:
                    imei = identifier[1]
                    break

            if not imei:
                _LOGGER.error("No IMEI found for device %s", device_id)
                return

            imei_short = imei[-4:] if len(imei) >= 4 else imei

            # Find source entity for this device
            source_entity_id = None
            for entity in er.async_entries_for_device(entity_registry, device_id):
                if "energy_consumption" in entity.entity_id and "daily" not in entity.entity_id:
                    source_entity_id = entity.entity_id
                    break

            if not source_entity_id:
                _LOGGER.error("Source energy consumption sensor not found for device")
                return

        else:
            # Legacy mode - use default entity IDs
            imei_short = ""
            source_entity_id = "sensor.scooter_energy_consumption"

        # Get source value
        if source_value_param is not None:
            source_value = float(source_value_param)
            _LOGGER.info("Using manual source value: %.3f kWh", source_value)
        else:
            source_entity = hass.states.get(source_entity_id)
            if not source_entity or source_entity.state in ["unknown", "unavailable", "0", "0.0"]:
                _LOGGER.error(
                    "Source sensor %s unavailable or 0 (scooter offline?). "
                    "Provide 'source_value' parameter manually",
                    source_entity_id
                )
                return
            source_value = float(source_entity.state)
            _LOGGER.info("Using current source value: %.3f kWh", source_value)

        # Build target entity IDs
        if imei_short:
            targets = {
                f"sensor.scooter_energy_consumption_daily_{imei_short}": {
                    "consumption": daily_value / electricity_price,
                    "cycle_start": source_value - (daily_value / electricity_price)
                },
                f"sensor.scooter_energy_consumption_weekly_{imei_short}": {
                    "consumption": weekly_value / electricity_price,
                    "cycle_start": source_value - (weekly_value / electricity_price)
                },
                f"sensor.scooter_energy_consumption_monthly_{imei_short}": {
                    "consumption": monthly_value / electricity_price,
                    "cycle_start": source_value - (monthly_value / electricity_price)
                },
                f"sensor.scooter_energy_consumption_yearly_{imei_short}": {
                    "consumption": yearly_value / electricity_price,
                    "cycle_start": source_value - (yearly_value / electricity_price)
                },
            }
        else:
            # Legacy mode
            targets = {
                "sensor.scooter_energy_consumption_daily": {
                    "consumption": daily_value / electricity_price,
                    "cycle_start": source_value - (daily_value / electricity_price)
                },
                "sensor.scooter_energy_consumption_weekly": {
                    "consumption": weekly_value / electricity_price,
                    "cycle_start": source_value - (weekly_value / electricity_price)
                },
                "sensor.scooter_energy_consumption_monthly": {
                    "consumption": monthly_value / electricity_price,
                    "cycle_start": source_value - (monthly_value / electricity_price)
                },
                "sensor.scooter_energy_consumption_yearly": {
                    "consumption": yearly_value / electricity_price,
                    "cycle_start": source_value - (yearly_value / electricity_price)
                },
            }

        # Find and update sensor objects
        updated_count = 0
        entity_component = hass.data.get("entity_components", {}).get("sensor")
        if not entity_component:
            _LOGGER.error("Sensor component not found!")
            return

        for entity_id, values in targets.items():
            sensor_found = False
            for entity in entity_component.entities:
                if entity.entity_id == entity_id:
                    # Update internal attributes
                    entity._attr_native_value = round(values["consumption"], 3)
                    entity._cycle_start_value = round(values["cycle_start"], 3)
                    entity.async_write_ha_state()

                    _LOGGER.info("✓ %s: %.3f kWh (cycle_start: %.3f kWh)",
                                 entity_id, values["consumption"], values["cycle_start"])
                    updated_count += 1
                    sensor_found = True
                    break

            if not sensor_found:
                _LOGGER.warning("Sensor object not found for %s", entity_id)

        if updated_count > 0:
            _LOGGER.info("=" * 70)
            _LOGGER.info("✓ Restored %d sensors", updated_count)
            _LOGGER.info("=" * 70)
        else:
            _LOGGER.error("No sensors were updated!")

    # Register services
    if not hass.services.has_service(DOMAIN, "reset_tracked_counters"):
        hass.services.async_register(DOMAIN, "reset_tracked_counters", reset_tracked_counters)
        _LOGGER.info("Service reset_tracked_counters registered")

    RESTORE_SCHEMA = vol.Schema({
        vol.Optional("device_id"): cv.string,
        vol.Optional("daily", default=0.12): vol.Coerce(float),
        vol.Optional("weekly", default=0.12): vol.Coerce(float),
        vol.Optional("monthly", default=2.26): vol.Coerce(float),
        vol.Optional("yearly", default=2.26): vol.Coerce(float),
        vol.Optional("source_value"): vol.Coerce(float),
    })

    if not hass.services.has_service(DOMAIN, "restore_energy_costs"):
        hass.services.async_register(
            DOMAIN,
            "restore_energy_costs",
            restore_energy_costs,
            schema=RESTORE_SCHEMA
        )
        _LOGGER.info("Service restore_energy_costs registered")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Silence Scooter from a config entry."""
    _LOGGER.info("Setting up Silence Scooter integration")

    try:
        # Get and validate IMEI
        imei = entry.data.get(CONF_IMEI)
        if not imei:
            _LOGGER.error("No IMEI found in config entry, triggering reconfiguration")
            # Trigger reconfiguration for migration from v1
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": "reauth"},
                    data={"entry_id": entry.entry_id}
                )
            )
            return False

        # Get multi_device flag
        multi_device = entry.data.get(CONF_MULTI_DEVICE, DEFAULT_MULTI_DEVICE)

        # Initialize storage with IMEI (isolated per entry)
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = {
            "imei": imei,
            "multi_device": multi_device,
            "sensors": {},
            "config": entry.data,
        }
        _LOGGER.info("Storage initialized for IMEI %s with config: %s", imei[-4:], entry.data)

        # Load platforms (they will get IMEI from entry.data)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        _LOGGER.info("Platforms loaded: %s", ", ".join(PLATFORMS))

        # Setup automations with IMEI
        try:
            _LOGGER.info("Setting up automations for IMEI %s...", imei[-4:])
            from .automations import async_setup_automations, setup_persistent_sensors_update

            # Pass IMEI and multi_device to automations for isolation
            cancel_listeners = await async_setup_automations(hass, entry, imei, multi_device)

            # Store listeners per entry for proper cleanup
            hass.data[DOMAIN][entry.entry_id]["cancel_listeners"] = cancel_listeners

            _LOGGER.info("Automations setup completed for IMEI %s", imei[-4:])

            await setup_persistent_sensors_update(hass, imei, multi_device)
            _LOGGER.info("Persistent sensors auto-update configured")
        except Exception as e:
            _LOGGER.error("Error setting up automations for IMEI %s: %s", imei[-4:], e, exc_info=True)
            _LOGGER.warning("Continuing setup without automations")

        # Publish MQTT Discovery configs (Solution B)
        await publish_mqtt_discovery_configs(hass, imei)

        # Register services (only once for all instances)
        await async_setup_services(hass)

        # Support reload
        entry.async_on_unload(entry.add_update_listener(async_reload_entry))

        _LOGGER.info("Setup completed successfully for IMEI %s", imei[-4:])
        return True

    except Exception as err:
        _LOGGER.error("Error in setup: %s", err, exc_info=True)
        raise HomeAssistantError(f"Failed to set up Silence Scooter integration: {err}")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    imei = entry.data.get(CONF_IMEI, "unknown")
    _LOGGER.info("Unloading Silence Scooter integration for IMEI %s", imei[-4:] if imei != "unknown" else imei)

    try:
        # Clean up automations for this entry
        if entry.entry_id in hass.data.get(DOMAIN, {}):
            entry_data = hass.data[DOMAIN][entry.entry_id]
            cancel_listeners = entry_data.get("cancel_listeners", [])

            if cancel_listeners:
                _LOGGER.info("Cleaning up automations for IMEI %s", imei[-4:])
                for remove_listener in cancel_listeners:
                    try:
                        remove_listener()
                    except Exception as e:
                        _LOGGER.warning("Error removing automation listener: %s", e)

        # Unload platforms
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        _LOGGER.info("Platforms unloaded: %s", unload_ok)

        # Clean up storage for this entry
        if DOMAIN in hass.data:
            hass.data[DOMAIN].pop(entry.entry_id, None)
            _LOGGER.info("Storage cleaned for entry %s", entry.entry_id)

        return unload_ok

    except Exception as e:
        _LOGGER.error("Error during unload: %s", e)
        return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
