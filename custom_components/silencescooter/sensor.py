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
from homeassistant.const import CONF_NAME, CONF_ICON, CONF_UNIT_OF_MEASUREMENT, Platform, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.util import dt as dt_util
from homeassistant.helpers.template import Template
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import TemplateError

from .const import (
    DOMAIN,
    CONF_IMEI,
    CONF_TARIFF_SENSOR,
    CONF_CHARGER_EFFICIENCY,
    DEFAULT_CHARGER_EFFICIENCY,
    CONF_USE_TRACKED_DISTANCE,
    CONF_MULTI_DEVICE,
    DEFAULT_TARIFF_SENSOR,
    DEFAULT_USE_TRACKED_DISTANCE,
    DEFAULT_MULTI_DEVICE,
)
from .helpers import get_device_info, insert_imei_in_entity_id, generate_entity_id_suffix, get_history_file
from .errors import ErrorCategory, ErrorSeverity, get_error_detector
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
    from homeassistant.exceptions import ConfigEntryNotReady

    # Get IMEI and multi_device from config entry
    imei = config_entry.data.get(CONF_IMEI, "")
    multi_device = config_entry.data.get(CONF_MULTI_DEVICE, DEFAULT_MULTI_DEVICE)

    # Multi-device mode requires IMEI
    if multi_device and not imei:
        raise ConfigEntryNotReady("Multi-device mode requires IMEI")

    def adapt_template_for_multi_device(template_str: str) -> str:
        """Replace hardcoded entity_ids in templates with IMEI-suffixed versions."""
        if not multi_device or not imei:
            return template_str
        imei_suffix = generate_entity_id_suffix(imei, multi_device)
        # Replace all known entity_id patterns: insert IMEI after "scooter_"
        # Handles: sensor.silence_scooter_*, sensor.scooter_*, number.scooter_*,
        #          datetime.scooter_*, binary_sensor.silence_scooter_*, switch.*_scooter_*
        import re
        return re.sub(
            r"((?:sensor|number|datetime|binary_sensor|switch)\.\w*scooter)_",
            rf"\1{imei_suffix}_",
            template_str,
        )

    entities = []

    # Capteurs retirés en 2026-11 (remplacés par la capacité réelle) : ôter
    # l'entité orpheline du registre, sinon elle reste « indisponible ».
    registry = er.async_get(hass)
    for removed in ("scooter_battery_soc_calculated", "scooter_battery_soc_deviation"):
        unique_id = f"{imei}_{removed}" if multi_device and imei else f"{DOMAIN}_{removed}"
        stale = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
        if stale:
            registry.async_remove(stale)

    for sensor_id, config in WRITABLE_SENSORS.items():
        entities.append(ScooterWritableSensor(hass, sensor_id, config, imei, multi_device))

    configured_tariff_sensor = config_entry.data.get(
        CONF_TARIFF_SENSOR, DEFAULT_TARIFF_SENSOR
    )

    # If no tariff sensor configured, create a default one
    if not configured_tariff_sensor or configured_tariff_sensor == "":
        entities.append(ScooterDefaultTariffSensor(hass, imei, multi_device))
        configured_tariff_sensor = "sensor.silencescooter_default_electricity_price"

    charger_efficiency = config_entry.data.get(
        CONF_CHARGER_EFFICIENCY, DEFAULT_CHARGER_EFFICIENCY
    ) / 100
    efficiency_default, efficiency_set = (
        "charger_efficiency = 0.90", f"charger_efficiency = {charger_efficiency}"
    )

    use_tracked_distance = config_entry.data.get(
        CONF_USE_TRACKED_DISTANCE, DEFAULT_USE_TRACKED_DISTANCE
    )

    for sensor_id, config in TEMPLATE_SENSORS.items():
        config_copy = config.copy()
        # Apply tracked distance mode if enabled for battery_per_km
        if use_tracked_distance and sensor_id == "scooter_battery_per_km" and "value_template" in config_copy:
            config_copy["value_template"] = """
                {% set tracked_dist = states('number.scooter_tracked_distance') | float(0) %}
                {% set tracked_batt = states('number.scooter_tracked_battery_used') | float(0) %}
                {% if tracked_dist > 0 %}
                    {{ (tracked_batt / tracked_dist) | round(2) }}
                {% else %}
                    0
                {% endif %}
            """
        if "value_template" in config_copy:
            config_copy["value_template"] = adapt_template_for_multi_device(config_copy["value_template"])
        if "icon_template" in config_copy:
            config_copy["icon_template"] = adapt_template_for_multi_device(config_copy["icon_template"])
        entities.append(ScooterTemplateSensor(hass, sensor_id, config_copy, imei, multi_device))

    for sensor_id, config in TRIGGER_SENSORS.items():
        config_copy = config.copy()
        if "value_template" in config_copy:
            config_copy["value_template"] = adapt_template_for_multi_device(config_copy["value_template"])
        if multi_device and imei:
            # Les déclencheurs écoutaient les identifiants sans IMEI
            config_copy["triggers"] = [
                {**t, "entity_id": [
                    insert_imei_in_entity_id(e, imei, multi_device)
                    for e in (t["entity_id"] if isinstance(t["entity_id"], list) else [t["entity_id"]])
                ]} if "entity_id" in t else t
                for t in config_copy.get("triggers", [])
            ]
        entities.append(ScooterTriggerSensor(hass, sensor_id, config_copy, imei, multi_device))

    for sensor_id, config in ENERGY_COST_SENSORS.items():
        config_copy = config.copy()
        if "value_template" in config_copy:
            config_copy["value_template"] = config_copy["value_template"].replace(
                "sensor.tarif_base_ttc", configured_tariff_sensor
            ).replace(efficiency_default, efficiency_set)
            config_copy["value_template"] = adapt_template_for_multi_device(config_copy["value_template"])
        entities.append(ScooterTemplateSensor(hass, sensor_id, config_copy, imei, multi_device))

    for sensor_id, config in BATTERY_HEALTH_SENSORS.items():
        config_copy = config.copy()
        if "value_template" in config_copy:
            config_copy["value_template"] = adapt_template_for_multi_device(config_copy["value_template"])
        entities.append(ScooterTemplateSensor(hass, sensor_id, config_copy, imei, multi_device))

    for sensor_id, config in USAGE_STATISTICS_SENSORS.items():
        config_copy = config.copy()
        if "value_template" in config_copy:
            config_copy["value_template"] = config_copy["value_template"].replace(
                "sensor.tarif_base_ttc", configured_tariff_sensor
            ).replace(efficiency_default, efficiency_set)
            config_copy["value_template"] = adapt_template_for_multi_device(config_copy["value_template"])
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
                    # Tracked mode: (battery% / 100 * capacity * price / charger) / distance
                    # (les pertes de la batterie elle-même ne sont pas comptées ici)
                    config_copy["value_template"] = f"""
                        {{% set tracked_dist = states('number.scooter_tracked_distance') | float(0) %}}
                        {{% set tracked_batt = states('number.scooter_tracked_battery_used') | float(0) %}}
                        {{% set price_per_kwh = states('{configured_tariff_sensor}') | float(0.215) %}}
                        {{% set battery_capacity = 5.6 %}}
                        {{% if tracked_dist > 0 %}}
                            {{{{ ((tracked_batt / 100 * battery_capacity * price_per_kwh / {charger_efficiency}) / tracked_dist) | round(3) }}}}
                        {{% else %}}
                            0
                        {{% endif %}}
                    """
            # Re-apply multi-device adaptation after tracked mode override
            config_copy["value_template"] = adapt_template_for_multi_device(config_copy["value_template"])
        entities.append(ScooterTemplateSensor(hass, sensor_id, config_copy, imei, multi_device))

    entities.append(ScooterTripsSensor(hass, imei, multi_device))

    for meter_id, config in UTILITY_METERS.items():
        config_copy = config.copy()
        if multi_device and imei:
            config_copy["source"] = insert_imei_in_entity_id(config_copy["source"], imei, multi_device)
        entities.append(ScooterUtilityMeterSensor(hass, meter_id, config_copy, imei, multi_device))

    entities.append(ScooterErrorDetectionSensor(hass, config_entry.entry_id, imei, multi_device))
    async_add_entities(entities)
    _LOGGER.info("Initialized %d sensors (%d writable, %d template, %d trigger, %d energy cost, %d utility meters)",
                 len(entities), len(WRITABLE_SENSORS), len(TEMPLATE_SENSORS), len(TRIGGER_SENSORS),
                 len(ENERGY_COST_SENSORS), len(UTILITY_METERS))


class ScooterDefaultTariffSensor(SensorEntity):
    """Default electricity tariff sensor when none is configured."""

    def __init__(self, hass: HomeAssistant, imei: str = "", multi_device: bool = False) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self._imei = imei
        self._multi_device = multi_device

        if multi_device and imei:
            self._attr_has_entity_name = True
            self._attr_unique_id = f"{imei}_default_electricity_price"
            self._attr_name = "Default Electricity Price"
            self.entity_id = insert_imei_in_entity_id(
                "sensor.silencescooter_default_electricity_price", imei, multi_device
            )
        else:
            # Legacy mode: same as v1.0.4
            self._attr_unique_id = f"{DOMAIN}_default_electricity_price"
            self._attr_name = "Silencescooter Default Electricity Price"
            self.entity_id = "sensor.silencescooter_default_electricity_price"

        self._attr_native_unit_of_measurement = "€/kWh"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_icon = "mdi:currency-eur"
        self._attr_device_info = get_device_info(imei, multi_device)

    @property
    def native_value(self) -> float:
        """Return the default electricity price."""
        from .const import DEFAULT_ELECTRICITY_PRICE
        return DEFAULT_ELECTRICITY_PRICE


class ScooterTemplateSensor(SensorEntity, RestoreEntity):
    """Representation of a Scooter Template sensor."""

    def __init__(self, hass: HomeAssistant, sensor_id: str, config: dict, imei: str = "", multi_device: bool = False) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self._sensor_id = sensor_id
        self._config = config
        self._imei = imei
        self._multi_device = multi_device

        if multi_device and imei:
            self._attr_has_entity_name = True
            self._attr_unique_id = f"{imei}_{sensor_id}"
            sensor_type = sensor_id.replace("scooter_", "").replace("_", " ").title()
            self._attr_name = sensor_type
            self.entity_id = insert_imei_in_entity_id(f"sensor.{sensor_id}", imei, multi_device)
        else:
            # Legacy mode: same as v1.0.4
            self._attr_unique_id = f"{DOMAIN}_{sensor_id}"
            self._attr_name = sensor_id.replace("_", " ").title().replace("Scooter ", "Scooter - ")
            self.entity_id = f"sensor.{sensor_id}"

        self._attr_native_unit_of_measurement = config.get("unit_of_measurement")
        self._attr_device_class = config.get("device_class")
        self._attr_state_class = config.get("state_class")
        self._template = Template(config["value_template"], hass)
        self._icon_template = Template(config["icon_template"], hass) if "icon_template" in config else None

        self._attr_device_info = get_device_info(imei, multi_device)
        internal_sensors = ["scooter_is_moving", "scooter_trip_status"]
        if sensor_id in internal_sensors:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    async def async_added_to_hass(self) -> None:
        """Handle entity added to Home Assistant."""
        await super().async_added_to_hass()

        # Un compteur (total_increasing) ne redescend jamais : après le premier
        # calcul, on garde la valeur d'avant le redémarrage si elle est plus
        # haute. Sans ça, les compteurs dont le template relit sa propre valeur
        # (scooter_energy_consumption, scooter_battery_charge_cycles)
        # retombaient à 0 à chaque redémarrage puis remontaient, ce que les
        # statistiques HA comptaient comme une nouvelle consommation.
        # NB : écrire l'état repris AVANT le calcul ne marche pas — un
        # async_write_ha_state() fait pendant l'ajout de l'entité n'est pas
        # visible du template (constaté le 2026-11-10).
        restored = None
        if self._attr_state_class == SensorStateClass.TOTAL_INCREASING:
            last_state = await self.async_get_last_state()
            try:
                restored = float(last_state.state)
            except (AttributeError, ValueError, TypeError):
                restored = None

        await self.async_update()

        if restored is not None:
            try:
                current = float(self._attr_native_value)
            except (ValueError, TypeError):
                current = None
            if current is None or current < restored:
                _LOGGER.info("Counter %s restored to %s (first render gave %s)",
                             self.entity_id, restored, self._attr_native_value)
                self._attr_native_value = restored

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
            detector = get_error_detector(self.hass)
            if detector:
                detector.record_error(
                    ErrorCategory.TEMPLATE_ERROR,
                    ErrorSeverity.WARNING,
                    f"Template render failed for {self._attr_name}: {err}",
                    source="ScooterTemplateSensor",
                    entity_id=getattr(self, "entity_id", self._attr_unique_id),
                )



class ScooterWritableSensor(SensorEntity, RestoreEntity):
    """Writable sensor that can be updated programmatically.

    This replaces the old pattern of having a number.*_internal + sensor.* template.
    Instead, we have a single sensor that can be written to and read from.
    """

    def __init__(self, hass: HomeAssistant, sensor_id: str, config: dict, imei: str = "", multi_device: bool = False) -> None:
        """Initialize the writable sensor."""
        self.hass = hass
        self._sensor_id = sensor_id
        self._config = config
        self._imei = imei
        self._multi_device = multi_device

        if multi_device and imei:
            self._attr_has_entity_name = True
            self._attr_unique_id = f"{imei}_{sensor_id}"
            self._attr_name = config.get("name", sensor_id.replace("_", " ").title())
            self.entity_id = insert_imei_in_entity_id(f"sensor.{sensor_id}", imei, multi_device)
        else:
            # Legacy mode: same as v1.0.4
            self._attr_unique_id = f"{DOMAIN}_{sensor_id}"
            self._attr_name = config.get("name", sensor_id.replace("_", " ").title())
            self.entity_id = f"sensor.{sensor_id}"

        self._attr_native_unit_of_measurement = config.get("unit_of_measurement")
        self._attr_device_class = config.get("device_class")
        self._attr_state_class = config.get("state_class")
        self._attr_icon = config.get("icon", "mdi:information")
        self._attr_native_value = 0
        self._attr_device_info = get_device_info(imei, multi_device)

    async def async_added_to_hass(self) -> None:
        """Restore last state when added to hass."""
        await super().async_added_to_hass()

        # RestoreEntity : sans restauration effective (plus bas), chaque
        # redémarrage de HA remettait tous les capteurs writable à 0
        # (max_speed du trajet en cours, displays persistants…) — c'est
        # l'origine des max_speed=0 avec avg_speed>0 dans l'historique.
        if DOMAIN in self.hass.data:
            self.hass.data[DOMAIN].setdefault("sensors", {})[self.entity_id] = self
            _LOGGER.info("Writable sensor registered: %s", self.entity_id)

        if last_state := await self.async_get_last_state():
            try:
                restored = float(last_state.state)
                # Reject obviously-corrupt restored values (NaN, negative, absurd
                # magnitude). Downstream code treats these sensors as trip stats
                # or counters — clamping here prevents cascading poison.
                if restored != restored or restored < 0 or restored > 1e7:
                    raise ValueError(f"rejected restored value {restored!r}")
                self._attr_native_value = restored
                _LOGGER.debug("Restored %s: %.2f", self.entity_id, self._attr_native_value)
            except (ValueError, TypeError, AttributeError) as e:
                self._attr_native_value = 0
                _LOGGER.warning(
                    "Could not restore %s (state=%r), defaulting to 0: %s",
                    self.entity_id, last_state.state, e,
                )
                detector = get_error_detector(self.hass)
                if detector:
                    detector.record_error(
                        ErrorCategory.STATE_RESTORATION, ErrorSeverity.WARNING,
                        f"Could not restore {self.entity_id}: {e}",
                        source="ScooterWritableSensor", entity_id=self.entity_id,
                    )
        else:
            self._attr_native_value = 0
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
            detector = get_error_detector(self.hass)
            if detector:
                detector.record_error(
                    ErrorCategory.SENSOR_INVALID, ErrorSeverity.ERROR,
                    f"Failed to set value for {self.entity_id}: {e}",
                    source="ScooterWritableSensor", entity_id=self.entity_id,
                )


class ScooterTriggerSensor(ScooterTemplateSensor):
    """Representation of a Scooter sensor with triggers (state or time_pattern)."""

    def __init__(self, hass: HomeAssistant, sensor_id: str, config: dict, imei: str = "", multi_device: bool = False) -> None:
        """Initialize the trigger-based sensor."""
        super().__init__(hass, sensor_id, config, imei, multi_device)
        self._triggers = config.get("triggers", [])
        self._time_listeners = []

    async def async_added_to_hass(self) -> None:
        """Handle entity added to Home Assistant."""
        # (le premier calcul et la reprise des compteurs sont faits par la
        # classe mère ; ne pas recalculer ici, la valeur reprise serait perdue)
        await super().async_added_to_hass()

        for trigger in self._triggers:
            platform = trigger.get("platform")
            if platform == "state":
                entity_ids = trigger.get("entity_id")
                if not isinstance(entity_ids, list):
                    entity_ids = [entity_ids]
                for entity_id in entity_ids:
                    # Conserver l'unsubscribe : sans ça, chaque reload
                    # ré-enregistrait un listener supplémentaire (fuite +
                    # double évaluation des templates).
                    self._time_listeners.append(
                        async_track_state_change_event(
                            self.hass, [entity_id], self._handle_event_trigger
                        )
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
        # async_update calcule la valeur mais ne la publie pas : sans cette
        # écriture, l'état visible ne changeait qu'au prochain poll de la
        # plateforme ou au tick time_pattern — le moteur de trajets réagissait
        # donc avec un décalage non déterministe aux transitions MQTT.
        self.async_write_ha_state()

    @callback
    def _handle_time_trigger(self, *_):
        """Handle a periodic time-based update."""
        self.async_schedule_update_ha_state(True)


class ScooterTripsSensor(SensorEntity, RestoreEntity):
    """Representation of a Scooter Trips sensor."""

    def __init__(self, hass: HomeAssistant, imei: str = "", multi_device: bool = False) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self._imei = imei
        self._multi_device = multi_device

        if multi_device and imei:
            self._attr_has_entity_name = True
            self._attr_unique_id = f"{imei}_trips"
            self._attr_name = "Trips"
            self.entity_id = insert_imei_in_entity_id("sensor.scooter_trips", imei, multi_device)
        else:
            # Legacy mode: same as v1.0.4
            self._attr_unique_id = f"{DOMAIN}_trips"
            self._attr_name = "Scooter Trips"

        self._attr_icon = "mdi:scooter"
        self._attr_native_value = 0
        self._attr_extra_state_attributes = {"history": []}
        self._attr_device_info = get_device_info(imei, multi_device)
        self._history_file = get_history_file(imei, multi_device)

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
                distances = []
                for trip in content:
                    try:
                        distances.append(float(trip.get("distance", 0)))
                    except (ValueError, TypeError, AttributeError):
                        pass
                self._attr_extra_state_attributes = {
                    "history": content[:10],
                    "average_distance": round(sum(distances) / len(distances), 1) if distances else 0,
                }

        except Exception as e:
            _LOGGER.error("Error updating sensor: %s", e)

    def _read_history_file(self) -> Optional[list]:
        """Read and parse the history file."""
        try:
            if self._history_file.exists():
                with open(self._history_file, 'r') as file:
                    return json.load(file)
        except Exception as e:
            _LOGGER.error("Error reading history file: %s", e)
        return []


class ScooterUtilityMeterSensor(SensorEntity, RestoreEntity):
    """Simplified utility meter sensor that tracks consumption per cycle."""

    def __init__(self, hass: HomeAssistant, meter_id: str, config: dict, imei: str = "", multi_device: bool = False) -> None:
        """Initialize the utility meter sensor."""
        self.hass = hass
        self._meter_id = meter_id
        self._config = config
        self._imei = imei
        self._multi_device = multi_device

        if multi_device and imei:
            self._attr_has_entity_name = True
            self._attr_unique_id = f"{imei}_{meter_id}"
            sensor_type = meter_id.replace("scooter_", "").replace("_", " ").title()
            self._attr_name = sensor_type
            self.entity_id = insert_imei_in_entity_id(f"sensor.{meter_id}", imei, multi_device)
        else:
            # Legacy mode: same as v1.0.4
            self._attr_unique_id = f"{DOMAIN}_{meter_id}"
            self._attr_name = meter_id.replace("_", " ").title().replace("Scooter ", "Scooter - ")
            self.entity_id = f"sensor.{meter_id}"

        self._attr_native_unit_of_measurement = "kWh"
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_icon = "mdi:counter"
        self._attr_device_info = get_device_info(imei, multi_device)

        self._source = config["source"]
        self._cycle = config["cycle"]
        self._max_step = config.get("max_step")
        self._last_reset = None
        self._last_source_value = None
        self._cycle_start_value = None

        _LOGGER.debug(f"Initialized utility meter {meter_id}: source={self._source}, cycle={self._cycle}")

    async def async_added_to_hass(self) -> None:
        """Handle entity added to hass."""
        await super().async_added_to_hass()

        # Register this sensor in hass.data so silencescooter.restore_energy_costs
        # can reach it. Without this, the restore service logs "Sensor object
        # not found" and silently fails.
        if DOMAIN in self.hass.data:
            self.hass.data[DOMAIN].setdefault("sensors", {})[self.entity_id] = self
            _LOGGER.debug("Utility meter registered: %s", self.entity_id)

        # Restore previous state
        if last_state := await self.async_get_last_state():
            try:
                restored_native = float(last_state.state)
                # Reject corrupt restored native_value (negative, NaN, absurd).
                if restored_native != restored_native or restored_native < 0 or restored_native > 1e6:
                    _LOGGER.warning(
                        "%s: rejecting corrupt restored value %r, resetting to 0",
                        self.entity_id, last_state.state,
                    )
                    self._attr_native_value = 0
                else:
                    self._attr_native_value = restored_native
                if "last_reset" in last_state.attributes:
                    self._last_reset = dt_util.parse_datetime(last_state.attributes["last_reset"])
                if "cycle_start_value" in last_state.attributes:
                    try:
                        restored_start_value = float(last_state.attributes["cycle_start_value"])
                        # Gate on finiteness + positivity + plausible magnitude.
                        # 2026-04-18 incident: a negative cycle_start_value (-866)
                        # was persisted and poisoned the meter for days after restarts.
                        if (
                            restored_start_value == restored_start_value  # not NaN
                            and 0 < restored_start_value < 1e6
                        ):
                            self._cycle_start_value = restored_start_value
                        else:
                            _LOGGER.warning(
                                "%s: rejecting corrupt cycle_start_value=%r",
                                self.entity_id, last_state.attributes.get("cycle_start_value"),
                            )
                    except (ValueError, TypeError):
                        _LOGGER.warning(
                            "%s: non-numeric cycle_start_value=%r, ignoring",
                            self.entity_id, last_state.attributes.get("cycle_start_value"),
                        )
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
                detector = get_error_detector(self.hass)
                if detector:
                    detector.record_error(
                        ErrorCategory.STATE_RESTORATION, ErrorSeverity.WARNING,
                        f"Could not restore state for {self.entity_id}: {e}",
                        source="ScooterUtilityMeterSensor", entity_id=self.entity_id,
                    )
        else:
            self._attr_native_value = 0

        if self._last_reset is None:
            self._last_reset = self._get_cycle_start(dt_util.now())

        @callback
        def source_changed(event):
            """Handle source sensor state change."""
            self.hass.async_create_task(self._handle_source_update(event))

        self.async_on_remove(async_track_state_change_event(
            self.hass, [self._source], source_changed
        ))

        # Add periodic check for cycle reset (every 5 minutes for all cycles)
        # This ensures we detect cycle changes even if source sensor doesn't update
        @callback
        def periodic_check(_):
            """Periodic check for cycle reset."""
            self.hass.async_create_task(self._handle_source_update(None))

        # Daily: check every 5 minutes (detects midnight rollover quickly)
        # Weekly/Monthly/Yearly: check every hour (sufficient for these longer cycles)
        interval = timedelta(minutes=5) if self._cycle == "daily" else timedelta(hours=1)

        self.async_on_remove(async_track_time_interval(
            self.hass,
            periodic_check,
            interval
        ))

        _LOGGER.info("Utility meter %s: periodic check every %s",
                     self.entity_id, interval)

        await self._handle_source_update(None)

    async def _handle_source_update(self, event):
        """Handle source sensor update."""
        try:
            # Changement de période AVANT toute garde sur la source. Sinon,
            # source illisible ou à 0 à minuit (scooter éteint), la remise à
            # zéro attendait la prochaine trame et repartait de sa valeur :
            # la tuile affichait la période précédente pendant des heures et
            # l'énergie du premier trajet était perdue (le 2026-11-02, mois
            # compté 6,45 kWh au lieu de 7,37). La nouvelle période repart de
            # la dernière valeur connue de la source (départ + consommation).
            now = dt_util.now()
            if self._should_reset_cycle(now):
                _LOGGER.info("Resetting %s for new %s cycle", self.entity_id, self._cycle)
                if self._cycle_start_value:
                    self._cycle_start_value = round(
                        self._cycle_start_value + float(self._attr_native_value or 0), 3
                    )
                self._last_reset = self._get_cycle_start(now)
                self._attr_native_value = 0
                self.async_write_ha_state()

            source_state = self.hass.states.get(self._source)
            if not source_state or source_state.state in ["unknown", "unavailable"]:
                return

            source_value = float(source_state.state)

            # Reject obviously-bad source values that would poison cycle_start_value
            # and corrupt the meter for the whole cycle:
            #  - Negative values (seen on 2026-04-18 shortly before a scooter shutdown
            #    when the upstream MQTT energy counter glitched to -866.918).
            #  - A huge regression vs the last seen value (source dropped by more than
            #    100 kWh in a single update while we had a plausible previous reading)
            #    which means the counter was transiently reset by the scooter/server.
            if source_value < 0:
                _LOGGER.warning(
                    "%s: Rejecting negative source_value=%.3f (keeping previous state)",
                    self.entity_id, source_value,
                )
                return
            if (
                self._last_source_value is not None
                and self._last_source_value > 0
                and source_value < self._last_source_value - 100
            ):
                _LOGGER.warning(
                    "%s: Rejecting large source drop (source=%.3f, last=%.3f, delta=%.3f). "
                    "Likely an upstream reset; keeping previous state.",
                    self.entity_id, source_value, self._last_source_value,
                    source_value - self._last_source_value,
                )
                return

            # shortcut: une hausse légitime au-delà de max_step gèle le compteur
            # jusqu'au redémarrage, à revoir si un scooter reste des semaines
            # sans se connecter.
            if (
                self._max_step
                and self._last_source_value
                and source_value > self._last_source_value + self._max_step
            ):
                _LOGGER.warning(
                    "%s: Rejecting source spike (source=%.3f, last=%.3f)",
                    self.entity_id, source_value, self._last_source_value,
                )
                return
            # Source brute : un ancien relevé rejoué (valeur plus basse) ne doit
            # pas passer par la branche « consommation négative », qui remet la
            # période à zéro.
            if (
                self._max_step
                and self._cycle_start_value
                and source_value < self._cycle_start_value + float(self._attr_native_value or 0) - 0.001
            ):
                return

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

            if self._cycle_start_value is None or self._cycle_start_value == 0.0:
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
                    detector = get_error_detector(self.hass)
                    if detector:
                        detector.record_error(
                            ErrorCategory.DATA_INTEGRITY, ErrorSeverity.WARNING,
                            f"Negative consumption on {self.entity_id}: source={source_value:.3f}, start={self._cycle_start_value:.3f}",
                            source="ScooterUtilityMeterSensor", entity_id=self.entity_id,
                        )
                    self._cycle_start_value = source_value
                    self._attr_native_value = 0
                else:
                    self._attr_native_value = round(consumption, 3)

            self._last_source_value = source_value
            self.async_write_ha_state()

        except (ValueError, TypeError) as e:
            _LOGGER.error("Error updating %s: %s", self.entity_id, e)
            detector = get_error_detector(self.hass)
            if detector:
                detector.record_error(
                    ErrorCategory.SENSOR_INVALID, ErrorSeverity.ERROR,
                    f"Utility meter update failed for {self.entity_id}: {e}",
                    source="ScooterUtilityMeterSensor", entity_id=self.entity_id,
                )

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


class ScooterErrorDetectionSensor(SensorEntity):
    """Diagnostic sensor exposing error detection summary to the HA dashboard.

    Native value = count of active issues (errors/critical in the last hour).
    Attributes include error breakdowns, recurring patterns, and stale sensors.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str, imei: str = "", multi_device: bool = False) -> None:
        """Initialize the error detection sensor."""
        self.hass = hass
        self._entry_id = entry_id
        self._imei = imei
        self._multi_device = multi_device

        if multi_device and imei:
            self._attr_has_entity_name = True
            self._attr_unique_id = f"{imei}_error_detection"
            self._attr_name = "Error Detection"
            self.entity_id = insert_imei_in_entity_id("sensor.scooter_error_detection", imei, multi_device)
        else:
            self._attr_unique_id = f"{DOMAIN}_error_detection"
            self._attr_name = "Scooter - Error Detection"
            self.entity_id = "sensor.scooter_error_detection"

        self._attr_icon = "mdi:alert-circle-outline"
        self._attr_native_value = 0
        self._attr_device_info = get_device_info(imei, multi_device)
        self._summary: dict = {}

    async def async_added_to_hass(self) -> None:
        """Set up periodic refresh."""
        await super().async_added_to_hass()

        @callback
        def _refresh(_now):
            self.async_schedule_update_ha_state(True)

        self.async_on_remove(async_track_time_interval(self.hass, _refresh, timedelta(minutes=5)))
        await self.async_update()

    async def async_update(self) -> None:
        """Update the error detection summary."""
        detector = get_error_detector(self.hass, self._entry_id)
        if not detector:
            self._attr_native_value = 0
            self._summary = {}
            return

        self._summary = detector.get_error_summary()
        self._attr_native_value = detector.get_active_issues_count()

        if self._attr_native_value > 0:
            self._attr_icon = "mdi:alert-circle"
        elif self._summary.get("total_errors", 0) > 0:
            self._attr_icon = "mdi:alert-outline"
        else:
            self._attr_icon = "mdi:check-circle-outline"

    @property
    def extra_state_attributes(self) -> dict:
        """Return error detection summary as attributes."""
        return {
            "total_errors": self._summary.get("total_errors", 0),
            "errors_by_category": self._summary.get("errors_by_category", {}),
            "errors_by_severity": self._summary.get("errors_by_severity", {}),
            "recurring_patterns": self._summary.get("recurring_patterns", 0),
            "recent_errors": self._summary.get("recent_errors", []),
        }