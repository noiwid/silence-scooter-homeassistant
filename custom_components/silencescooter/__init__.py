"""The Silence Scooter integration."""
import logging
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Silence Scooter from a config entry."""
    _LOGGER.info("Setting up Silence Scooter integration")

    try:
        # Initialize storage for this entry
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = {}
        hass.data[DOMAIN]["sensors"] = {}
        hass.data[DOMAIN]["config"] = entry.data
        _LOGGER.info("Storage initialized with config: %s", entry.data)

        # Load platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        _LOGGER.info("Platforms loaded")

        # Create timer helper for trip stop tolerance
        try:
            from .const import CONF_PAUSE_MAX_DURATION, DEFAULT_PAUSE_MAX_DURATION
            pause_duration = entry.data.get(CONF_PAUSE_MAX_DURATION, DEFAULT_PAUSE_MAX_DURATION)
            duration_str = f"00:{pause_duration:02d}:00"

            # Create timer via timer.configure service
            await hass.services.async_call(
                "timer",
                "configure",
                {
                    "id": "scooter_stop_trip_tolerance",
                    "name": "Scooter Stop Trip Tolerance",
                    "duration": duration_str,
                    "icon": "mdi:timer-pause-outline",
                    "restore": True,
                },
                blocking=False,
            )
            _LOGGER.info("Timer created: timer.scooter_stop_trip_tolerance (%s)", duration_str)
        except Exception as e:
            _LOGGER.warning("Could not create timer (may already exist): %s", e)

        # Create timer helper for trip stop tolerance
        try:
            from .const import CONF_PAUSE_MAX_DURATION, DEFAULT_PAUSE_MAX_DURATION
            pause_duration = entry.data.get(CONF_PAUSE_MAX_DURATION, DEFAULT_PAUSE_MAX_DURATION)
            duration_str = f"00:{pause_duration:02d}:00"

            # Create timer via timer.configure service
            await hass.services.async_call(
                "timer",
                "configure",
                {
                    "id": "scooter_stop_trip_tolerance",
                    "name": "Scooter Stop Trip Tolerance",
                    "duration": duration_str,
                    "icon": "mdi:timer-pause-outline",
                    "restore": True,
                },
                blocking=False,
            )
            _LOGGER.info("Timer created: timer.scooter_stop_trip_tolerance (%s)", duration_str)
        except Exception as e:
            _LOGGER.warning("Could not create timer (may already exist): %s", e)

        # Setup automations
        try:
            _LOGGER.info("Setting up automations...")
            from .automations import async_setup_automations, setup_persistent_sensors_update
            await async_setup_automations(hass)
            _LOGGER.info("Automations setup completed")

            await setup_persistent_sensors_update(hass)
            _LOGGER.info("Persistent sensors auto-update configured")
        except Exception as e:
            _LOGGER.error("Error setting up automations: %s", e, exc_info=True)
            _LOGGER.warning("Continuing setup without automations")

        # Register services
        async def reset_tracked_counters(call):
            """Reset tracked distance and battery counters."""
            await hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": "number.scooter_tracked_distance", "value": 0},
                blocking=True
            )
            await hass.services.async_call(
                "number",
                "set_value",
                {"entity_id": "number.scooter_tracked_battery_used", "value": 0},
                blocking=True
            )
            _LOGGER.info("Tracked counters reset to 0")

        hass.services.async_register(DOMAIN, "reset_tracked_counters", reset_tracked_counters)

        # Service to restore all energy cost utility meters
        async def restore_energy_costs(call: ServiceCall):
            """Restore energy cost utility meters by modifying sensors in memory."""
            daily_value = call.data.get("daily", 0.12)
            weekly_value = call.data.get("weekly", 0.12)
            monthly_value = call.data.get("monthly", 2.26)
            yearly_value = call.data.get("yearly", 2.26)
            source_value_param = call.data.get("source_value")
            electricity_price = 0.2062  # EUR/kWh

            # Get source value
            if source_value_param is not None:
                source_value = float(source_value_param)
                _LOGGER.info("Using manual source value: %.3f kWh", source_value)
            else:
                source_entity = hass.states.get("sensor.scooter_energy_consumption")
                if not source_entity or source_entity.state in ["unknown", "unavailable", "0", "0.0"]:
                    _LOGGER.error(
                        "Source sensor unavailable or 0 (scooter offline?). "
                        "Provide 'source_value' parameter manually (e.g., 724.692)"
                    )
                    return
                source_value = float(source_entity.state)
                _LOGGER.info("Using current source value: %.3f kWh", source_value)

            # Calculate target values
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

            # Find and update sensor OBJECTS (not just states)
            updated_count = 0

            # Get the sensor entity component
            entity_component = hass.data.get("entity_components", {}).get("sensor")
            if not entity_component:
                _LOGGER.error("Sensor component not found!")
                return

            for entity_id, values in targets.items():
                # Find the actual sensor object
                sensor_found = False

                # entity_component.entities returns all sensor entities
                for entity in entity_component.entities:
                    if entity.entity_id == entity_id:
                        # Found it! Update internal attributes
                        entity._attr_native_value = round(values["consumption"], 3)
                        entity._cycle_start_value = round(values["cycle_start"], 3)

                        # Force state update to save to HA
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
                _LOGGER.info("⚠️  The values are now active and will be saved on next HA restart.")
                _LOGGER.info("    Cost sensors will auto-calculate from these values.")
                _LOGGER.info("=" * 70)
            else:
                _LOGGER.error("No sensors were updated!")

        RESTORE_SCHEMA = vol.Schema({
            vol.Optional("daily", default=0.12): vol.Coerce(float),
            vol.Optional("weekly", default=0.12): vol.Coerce(float),
            vol.Optional("monthly", default=2.26): vol.Coerce(float),
            vol.Optional("yearly", default=2.26): vol.Coerce(float),
            vol.Optional("source_value"): vol.Coerce(float),
        })

        hass.services.async_register(
            DOMAIN,
            "restore_energy_costs",
            restore_energy_costs,
            schema=RESTORE_SCHEMA
        )

        _LOGGER.info("Services registered")

        # Support reload
        entry.async_on_unload(entry.add_update_listener(async_reload_entry))

        _LOGGER.info("Setup completed successfully")
        return True

    except Exception as err:
        _LOGGER.error("Error in setup: %s", err, exc_info=True)
        raise HomeAssistantError(f"Failed to set up Silence Scooter integration: {err}")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Silence Scooter integration")

    try:
        # Clean up automations
        if "silence_automations" in hass.data:
            _LOGGER.info("Cleaning up automations")
            for remove_listener in hass.data["silence_automations"]:
                try:
                    remove_listener()
                except Exception as e:
                    _LOGGER.warning("Error removing automation listener: %s", e)
            hass.data.pop("silence_automations", None)

        # Unload platforms
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        _LOGGER.info("Platforms unloaded: %s", unload_ok)

        if DOMAIN in hass.data:
            hass.data[DOMAIN].pop(entry.entry_id, None)
            _LOGGER.info("Storage cleaned")

        return unload_ok

    except Exception as e:
        _LOGGER.error("Error during unload: %s", e)
        return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)