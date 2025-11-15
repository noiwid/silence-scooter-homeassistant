"""Number platform for Silence Scooter integration."""

import logging
from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, CONF_IMEI
from .definitions import INPUT_NUMBERS
from .helpers import get_device_info

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the custom Number entities for Silence Scooter."""
    from homeassistant.exceptions import ConfigEntryNotReady

    # Get IMEI from config entry
    imei = config_entry.data.get(CONF_IMEI)
    if not imei:
        raise ConfigEntryNotReady("IMEI not configured")

    entities = []
    for number_id, config in INPUT_NUMBERS.items():
        entities.append(ScooterNumberEntity(hass, number_id, config, imei))
    async_add_entities(entities)
    _LOGGER.info("✓ Initialized %d number entities", len(entities))


class ScooterNumberEntity(NumberEntity, RestoreEntity):
    """A NumberEntity to replace the old input_number usage."""

    def __init__(self, hass: HomeAssistant, number_id: str, config: dict, imei: str):
        """Initialize the number entity."""
        self.hass = hass
        self._number_id = number_id
        self._config = config
        self._imei = imei

        # CRITICAL: Use full IMEI for unique_id
        self._attr_unique_id = f"{number_id}_{imei}"

        # Display name with last 4 digits
        imei_short = imei[-4:] if len(imei) >= 4 else imei
        self._attr_name = f"{config['name']} ({imei_short})"

        # DO NOT set self.entity_id - let HA generate it

        self._attr_native_min_value = config["min"]
        self._attr_native_max_value = config["max"]
        self._attr_native_step = config["step"]
        self._attr_native_unit_of_measurement = config.get("unit_of_measurement")

        # Device info with IMEI
        self._attr_device_info = get_device_info(imei)

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
