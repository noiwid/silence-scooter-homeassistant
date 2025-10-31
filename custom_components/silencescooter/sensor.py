"""Sensor platform for Silence Scooter integration."""
import logging
import json
from datetime import timedelta
from typing import Any, Dict, Optional

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import CONF_NAME, CONF_ICON, CONF_UNIT_OF_MEASUREMENT, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.util import dt as dt_util
from homeassistant.helpers.template import Template
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import TemplateError

from .const import (
    DOMAIN,
    HISTORY_FILE,
    CONF_TARIFF_SENSOR,
    CONF_USE_TRACKED_DISTANCE,
    DEFAULT_TARIFF_SENSOR,
    DEFAULT_USE_TRACKED_DISTANCE,
)
from .helpers import get_device_info
from .definitions import (
    WRITABLE_SENSORS,
    TEMPLATE_SENSORS,
    TRIGGER_SENSORS,
    ENERGY_COST_SENSORS,
    BATTERY_HEALTH_SENSORS,
    USAGE_STATISTICS_SENSORS,
    UTILITY_METERS
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Silence Scooter sensor platform."""
    entities = []

    for sensor_id, config in WRITABLE_SENSORS.items():
        entities.append(ScooterWritableSensor(hass, sensor_id, config))

    configured_tariff_sensor = hass.data.get(DOMAIN, {}).get("config", {}).get(
        CONF_TARIFF_SENSOR, DEFAULT_TARIFF_SENSOR
    )
    use_tracked_distance = hass.data.get(DOMAIN, {}).get("config", {}).get(
        CONF_USE_TRACKED_DISTANCE, DEFAULT_USE_TRACKED_DISTANCE
    )

    for sensor_id, config in TEMPLATE_SENSORS.items():
        config_copy = config.copy()
        # Apply tracked distance mode if enabled for battery_per_km
        if use_tracked_distance and sensor_id == "scooter_battery_per_km" and "value_template" in config_copy:
            # Tracked mode: battery is already in %, just divide by distance
            config_copy["value_template"] = """
                {% set tracked_dist = states('number.scooter_tracked_distance') | float(0) %}
                {% set tracked_batt = states('number.scooter_tracked_battery_used') | float(0) %}
                {% if tracked_dist > 0 %}
                    {{ (tracked_batt / tracked_dist) | round(2) }}
                {% else %}
                    0
                {% endif %}
            """
        entities.append(ScooterTemplateSensor(hass, sensor_id, config_copy))

    for sensor_id, config in TRIGGER_SENSORS.items():
        entities.append(ScooterTriggerSensor(hass, sensor_id, config))

    for sensor_id, config in ENERGY_COST_SENSORS.items():
        config_copy = config.copy()
        if "value_template" in config_copy:
            config_copy["value_template"] = config_copy["value_template"].replace(
                "sensor.tarif_base_ttc", configured_tariff_sensor
            )
        entities.append(ScooterTemplateSensor(hass, sensor_id, config_copy))

    for sensor_id, config in BATTERY_HEALTH_SENSORS.items():
        entities.append(ScooterTemplateSensor(hass, sensor_id, config))

    for sensor_id, config in USAGE_STATISTICS_SENSORS.items():
        config_copy = config.copy()
        if "value_template" in config_copy:
            # Replace tariff sensor
            config_copy["value_template"] = config_copy["value_template"].replace(
                "sensor.tarif_base_ttc", configured_tariff_sensor
            )
            # Use completely different templates for tracked mode
            if use_tracked_distance:
                if sensor_id == "scooter_distance_per_charge":
                    # Tracked mode: distance / (battery% / 100) = km per full charge
                    config_copy["value_template"] = """
                        {% set tracked_dist = states('number.scooter_tracked_distance') | float(0) %}
                        {% set tracked_batt = states('number.scooter_tracked_battery_used') | float(0) %}
                        {% if tracked_batt > 0 and tracked_dist > 0 %}
                            {{ (tracked_dist / (tracked_batt / 100)) | round(1) }}
                        {% else %}
                            0
                        {% endif %}
                    """
                elif sensor_id == "scooter_cost_per_km":
                    # Tracked mode: (battery% / 100 * capacity * price) / distance
                    config_copy["value_template"] = f"""
                        {{% set tracked_dist = states('number.scooter_tracked_distance') | float(0) %}}
                        {{% set tracked_batt = states('number.scooter_tracked_battery_used') | float(0) %}}
                        {{% set price_per_kwh = states('{configured_tariff_sensor}') | float(0.215) %}}
                        {{% set battery_capacity = 5.6 %}}
                        {{% if tracked_dist > 0 %}}
                            {{{{ ((tracked_batt / 100 * battery_capacity * price_per_kwh) / tracked_dist) | round(3) }}}}
                        {{% else %}}
                            0
                        {{% endif %}}
                    """
        entities.append(ScooterTemplateSensor(hass, sensor_id, config_copy))

    entities.append(ScooterTripsSensor(hass))

    for meter_id, config in UTILITY_METERS.items():
        entities.append(ScooterUtilityMeterSensor(hass, meter_id, config))
    async_add_entities(entities)
    _LOGGER.info("Initialized %d sensors (%d writable, %d template, %d trigger, %d energy cost, %d utility meters)",
                 len(entities), len(WRITABLE_SENSORS), len(TEMPLATE_SENSORS), len(TRIGGER_SENSORS),
                 len(ENERGY_COST_SENSORS), len(UTILITY_METERS))


class ScooterTemplateSensor(SensorEntity, RestoreEntity):
    """Representation of a Scooter Template sensor."""

    def __init__(self, hass: HomeAssistant, sensor_id: str, config: dict) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self._attr_unique_id = f"{DOMAIN}_{sensor_id}"
        self._attr_name = sensor_id.replace("_", " ").title().replace("Scooter ", "Scooter - ")
        self.entity_id = f"sensor.{sensor_id}"
        self._attr_native_unit_of_measurement = config.get("unit_of_measurement")
        self._attr_device_class = config.get("device_class")
        self._attr_state_class = config.get("state_class")
        self._template = Template(config["value_template"], hass)
        self._icon_template = Template(config["icon_template"], hass) if "icon_template" in config else None

    async def async_added_to_hass(self) -> None:
        """Handle entity added to Home Assistant."""
        await super().async_added_to_hass()
        await self.async_update()

    async def async_update(self) -> None:
        """Update the state."""
        try:
            result = self._template.async_render()
            if isinstance(result, TemplateError):
                self._attr_native_value = None
                _LOGGER.error("Error rendering template for %s: %s", self._attr_name, result)
            else:
                self._attr_native_value = result

            if self._icon_template is not None:
                self._attr_icon = self._icon_template.async_render()
        except TemplateError as err:
            _LOGGER.error("Error rendering template for %s: %s", self._attr_name, err)
            self._attr_native_value = None



class ScooterWritableSensor(SensorEntity, RestoreEntity):
    """Writable sensor that can be updated programmatically.

    This replaces the old pattern of having a number.*_internal + sensor.* template.
    Instead, we have a single sensor that can be written to and read from.
    """

    def __init__(self, hass: HomeAssistant, sensor_id: str, config: dict) -> None:
        """Initialize the writable sensor."""
        self.hass = hass
        self._attr_unique_id = f"{DOMAIN}_{sensor_id}"
        self._attr_name = config.get("name", sensor_id.replace("_", " ").title())
        self.entity_id = f"sensor.{sensor_id}"
        self._attr_native_unit_of_measurement = config.get("unit_of_measurement")
        self._attr_device_class = config.get("device_class")
        self._attr_state_class = config.get("state_class")
        self._attr_icon = config.get("icon", "mdi:information")
        self._attr_native_value = 0

    async def async_added_to_hass(self) -> None:
        """Restore last state when added to hass."""
        await super().async_added_to_hass()

        if DOMAIN in self.hass.data:
            self.hass.data[DOMAIN].setdefault("sensors", {})[self.entity_id] = self
            _LOGGER.info("Writable sensor registered: %s", self.entity_id)

        if last_state := await self.async_get_last_state():
            try:
                self._attr_native_value = float(last_state.state)
                _LOGGER.debug("Restored %s: %.2f", self.entity_id, self._attr_native_value)
            except (ValueError, TypeError):
                self._attr_native_value = 0
                _LOGGER.warning("Could not restore %s, defaulting to 0", self.entity_id)
        else:
            _LOGGER.debug("New sensor %s initialized to 0", self.entity_id)
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set the sensor value."""
        try:
            old_value = self._attr_native_value
            self._attr_native_value = float(value)
            self.async_write_ha_state()
            _LOGGER.debug("Updated %s: %.2f → %.2f", self.entity_id, old_value, self._attr_native_value)
        except (ValueError, TypeError) as e:
            _LOGGER.error("Failed to set value for %s: %s", self.entity_id, e)


class ScooterTriggerSensor(ScooterTemplateSensor):
    """Representation of a Scooter sensor with triggers (state or time_pattern)."""

    def __init__(self, hass: HomeAssistant, sensor_id: str, config: dict) -> None:
        """Initialize the trigger-based sensor."""
        super().__init__(hass, sensor_id, config)
        self._triggers = config.get("triggers", [])
        self._time_listeners = []

    async def async_added_to_hass(self) -> None:
        """Handle entity added to Home Assistant."""
        await super().async_added_to_hass()

        await self.async_update()
        for trigger in self._triggers:
            platform = trigger.get("platform")
            if platform == "state":
                entity_ids = trigger.get("entity_id")
                if not isinstance(entity_ids, list):
                    entity_ids = [entity_ids]
                for entity_id in entity_ids:
                    async_track_state_change_event(
                        self.hass, [entity_id], self._handle_event_trigger
                    )

            elif platform == "time_pattern":
                minutes = trigger.get("minutes", "/5")
                interval = timedelta(minutes=1) if minutes == "/1" else timedelta(minutes=5)
                self._time_listeners.append(
                    async_track_time_interval(
                        self.hass, self._handle_time_trigger, interval
                    )
                )

    async def async_will_remove_from_hass(self) -> None:
        """Cleanup when the entity is removed."""
        for listener in self._time_listeners:
            listener()
        self._time_listeners = []

    async def _handle_event_trigger(self, event) -> None:
        """Handle a state change that should trigger an update."""
        await self.async_update()

    @callback
    def _handle_time_trigger(self, *_):
        """Handle a periodic time-based update."""
        self.async_schedule_update_ha_state(True)


class ScooterTripsSensor(SensorEntity, RestoreEntity):
    """Representation of a Scooter Trips sensor."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self._attr_unique_id = f"{DOMAIN}_trips"
        self._attr_name = "Scooter Trips"
        self._attr_icon = "mdi:scooter"
        self._attr_native_value = 0
        self._attr_extra_state_attributes = {"history": []}

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        if last_state := await self.async_get_last_state():
            self._attr_native_value = last_state.state
            if "history" in last_state.attributes:
                self._attr_extra_state_attributes["history"] = last_state.attributes["history"]
        
        self.async_schedule_update_ha_state(True)

    async def async_update(self) -> None:
        """Update the sensor."""
        try:
            content = await self.hass.async_add_executor_job(self._read_history_file)

            if content:
                self._attr_native_value = len(content)
                self._attr_extra_state_attributes = {"history": content[:10]}

        except Exception as e:
            _LOGGER.error("Error updating sensor: %s", e)

    def _read_history_file(self) -> Optional[list]:
        """Read and parse the history file."""
        try:
            if HISTORY_FILE.exists():
                with open(HISTORY_FILE, 'r') as file:
                    return json.load(file)
        except Exception as e:
            _LOGGER.error("Error reading history file: %s", e)
        return []


class ScooterUtilityMeterSensor(SensorEntity, RestoreEntity):
    """Simplified utility meter sensor that tracks consumption per cycle."""

    def __init__(self, hass: HomeAssistant, meter_id: str, config: dict) -> None:
        """Initialize the utility meter sensor."""
        self.hass = hass
        self._attr_unique_id = f"{DOMAIN}_{meter_id}"
        self._attr_name = meter_id.replace("_", " ").title().replace("Scooter ", "Scooter - ")
        self.entity_id = f"sensor.{meter_id}"
        self._attr_native_unit_of_measurement = "kWh"
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_icon = "mdi:counter"

        self._source = config["source"]
        self._cycle = config["cycle"]
        self._last_reset = None
        self._last_source_value = None
        self._cycle_start_value = None

        _LOGGER.debug(f"Initialized utility meter {meter_id}: source={self._source}, cycle={self._cycle}")

    async def async_added_to_hass(self) -> None:
        """Handle entity added to hass."""
        await super().async_added_to_hass()

        # Restore previous state
        if last_state := await self.async_get_last_state():
            try:
                self._attr_native_value = float(last_state.state)
                if "last_reset" in last_state.attributes:
                    self._last_reset = dt_util.parse_datetime(last_state.attributes["last_reset"])
                if "cycle_start_value" in last_state.attributes:
                    restored_start_value = float(last_state.attributes["cycle_start_value"])
                    if restored_start_value > 0:
                        self._cycle_start_value = restored_start_value
                # Log important pour les utility meters
                if self._cycle == "daily":
                    _LOGGER.info("Restored %s: value=%s, last_reset=%s, cycle_start=%s",
                                 self.entity_id, self._attr_native_value, self._last_reset, self._cycle_start_value)
                else:
                    _LOGGER.debug("Restored %s: value=%s, last_reset=%s, cycle_start=%s",
                                 self.entity_id, self._attr_native_value, self._last_reset, self._cycle_start_value)
            except (ValueError, TypeError) as e:
                _LOGGER.warning("Could not restore state for %s: %s", self.entity_id, e)
                self._attr_native_value = 0
        else:
            self._attr_native_value = 0

        if self._last_reset is None:
            self._last_reset = self._get_cycle_start(dt_util.now())

        @callback
        def source_changed(event):
            """Handle source sensor state change."""
            self.hass.async_create_task(self._handle_source_update(event))

        async_track_state_change_event(
            self.hass, [self._source], source_changed
        )

        # Add periodic check for cycle reset (every 5 minutes for all cycles)
        # This ensures we detect cycle changes even if source sensor doesn't update
        @callback
        def periodic_check(_):
            """Periodic check for cycle reset."""
            self.hass.async_create_task(self._handle_source_update(None))

        # Daily: check every 5 minutes (detects midnight rollover quickly)
        # Weekly/Monthly/Yearly: check every hour (sufficient for these longer cycles)
        interval = timedelta(minutes=5) if self._cycle == "daily" else timedelta(hours=1)

        async_track_time_interval(
            self.hass,
            periodic_check,
            interval
        )

        _LOGGER.info("Utility meter %s: periodic check every %s",
                     self.entity_id, interval)

        await self._handle_source_update(None)

    async def _handle_source_update(self, event):
        """Handle source sensor update."""
        try:
            source_state = self.hass.states.get(self._source)
            if not source_state or source_state.state in ["unknown", "unavailable"]:
                return

            source_value = float(source_state.state)

            # IMPORTANT: If source is 0 and we have a restored cycle_start_value > 0,
            # it means the scooter is offline but we have valid restored data.
            # Don't recalculate to avoid triggering negative consumption protection.
            if source_value == 0.0 and self._cycle_start_value and self._cycle_start_value > 0:
                _LOGGER.debug(
                    "%s: Source is 0 (scooter offline) but we have restored cycle_start_value=%.3f. "
                    "Keeping current state to preserve restored data.",
                    self.entity_id, self._cycle_start_value
                )
                return

            now = dt_util.now()
            should_reset = self._should_reset_cycle(now)

            if should_reset:
                _LOGGER.info("Resetting %s for new %s cycle", self.entity_id, self._cycle)
                self._cycle_start_value = source_value
                self._last_reset = self._get_cycle_start(now)
                self._attr_native_value = 0
            elif self._cycle_start_value is None or self._cycle_start_value == 0.0:
                _LOGGER.info("Initializing %s: cycle_start_value=%s", self.entity_id, source_value)
                self._cycle_start_value = source_value
                self._attr_native_value = 0
            else:
                consumption = source_value - self._cycle_start_value

                # Fix: if consumption is negative, cycle_start_value is probably wrong
                # This can happen after restoring state or if source sensor was reset
                if consumption < 0:
                    _LOGGER.warning(
                        "%s: Negative consumption detected (source=%.3f, start=%.3f), "
                        "resetting cycle_start_value",
                        self.entity_id, source_value, self._cycle_start_value
                    )
                    self._cycle_start_value = source_value
                    self._attr_native_value = 0
                else:
                    self._attr_native_value = round(consumption, 3)

            self._last_source_value = source_value
            self.async_write_ha_state()

        except (ValueError, TypeError) as e:
            _LOGGER.error("Error updating %s: %s", self.entity_id, e)

    def _get_cycle_start(self, now):
        """Get the start timestamp of the current cycle."""
        if self._cycle == "daily":
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif self._cycle == "weekly":
            # Start of week (Monday)
            days_since_monday = now.weekday()
            week_start = now - timedelta(days=days_since_monday)
            return week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        elif self._cycle == "monthly":
            return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif self._cycle == "yearly":
            return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return now

    def _should_reset_cycle(self, now) -> bool:
        """Check if cycle should be reset."""
        if self._last_reset is None:
            return False

        if self._cycle == "daily":
            return now.date() > self._last_reset.date()
        elif self._cycle == "weekly":
            last_week_tuple = self._last_reset.isocalendar()[:2]
            current_week_tuple = now.isocalendar()[:2]
            return current_week_tuple != last_week_tuple
        elif self._cycle == "monthly":
            return now.month != self._last_reset.month or now.year != self._last_reset.year
        elif self._cycle == "yearly":
            return now.year != self._last_reset.year

        return False

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        return {
            "source": self._source,
            "cycle": self._cycle,
            "last_reset": self._last_reset.isoformat() if self._last_reset else None,
            "cycle_start_value": self._cycle_start_value,
        }