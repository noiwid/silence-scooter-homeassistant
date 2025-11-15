"""Number platform for Silence Scooter integration."""

import logging
from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, CONF_IMEI, CONF_MULTI_DEVICE, DEFAULT_MULTI_DEVICE
from .definitions import INPUT_NUMBERS
from .helpers import get_device_info, insert_imei_in_entity_id

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the custom Number entities for Silence Scooter."""
    from homeassistant.exceptions import ConfigEntryNotReady

    # Get IMEI and multi_device from config entry
    imei = config_entry.data.get(CONF_IMEI)
    if not imei:
        raise ConfigEntryNotReady("IMEI not configured")

    multi_device = config_entry.data.get(CONF_MULTI_DEVICE, DEFAULT_MULTI_DEVICE)

    entities = []
    for number_id, config in INPUT_NUMBERS.items():
        entities.append(ScooterNumberEntity(hass, number_id, config, imei, multi_device))
    async_add_entities(entities)
    _LOGGER.info("✓ Initialized %d number entities", len(entities))


class ScooterNumberEntity(NumberEntity, RestoreEntity):
    """A NumberEntity to replace the old input_number usage."""

    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, number_id: str, config: dict, imei: str, multi_device: bool = False):
        """Initialize the number entity."""
        self.hass = hass
        self._number_id = number_id
        self._config = config
        self._imei = imei
        self._multi_device = multi_device

        # Simplified unique_id using IMEI + sensor type
        self._attr_unique_id = f"{imei}_{number_id}"

        # Entity name - just the data point name from config
        self._attr_name = config['name']

        # DO NOT set self.entity_id - let HA generate it

        self._attr_native_min_value = config["min"]
        self._attr_native_max_value = config["max"]
        self._attr_native_step = config["step"]
        self._attr_native_unit_of_measurement = config.get("unit_of_measurement")

        # Device info with IMEI
        self._attr_device_info = get_device_info(imei, multi_device)

        # Initial value
        self._value = float(config.get("initial", config["min"]))
        self._attr_native_value = self._value

    async def async_added_to_hass(self):
        """Handle entity which will be added."""
        await super().async_added_to_hass()

        # Restore from last known state
        if last_state := await self.async_get_last_state():
            try:
                restored_value = float(last_state.state)
                self._value = restored_value
                self._attr_native_value = restored_value
                self.async_write_ha_state()

                _LOGGER.debug("Restored %s: %s", self.entity_id, restored_value)
            except ValueError as e:
                _LOGGER.warning("Could not restore value for %s: %s", self.entity_id, e)
        else:
            _LOGGER.debug("No previous state for %s - starting at default", self.entity_id)

    @property
    def native_value(self) -> float:
        """Return the current value."""
        return self._value if self._value is not None else self._attr_native_value

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        self._value = value
        self._attr_native_value = value
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Prevent periodic update from resetting the value."""
        pass
