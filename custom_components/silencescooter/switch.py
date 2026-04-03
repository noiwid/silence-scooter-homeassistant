"""Switch platform for Silence Scooter integration."""

import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, CONF_IMEI, CONF_MULTI_DEVICE, DEFAULT_MULTI_DEVICE
from .definitions import INPUT_BOOLEANS
from .helpers import get_device_info

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
):
    """Set up the custom Switch entities (ex-input_boolean) for Silence Scooter."""
    # Get IMEI and multi_device from config entry
    imei = entry.data.get(CONF_IMEI, "")
    multi_device = entry.data.get(CONF_MULTI_DEVICE, DEFAULT_MULTI_DEVICE)

    entities = []
    for bool_id, config in INPUT_BOOLEANS.items():
        entities.append(ScooterSwitchEntity(bool_id, config, imei, multi_device))
    async_add_entities(entities)


class ScooterSwitchEntity(SwitchEntity, RestoreEntity):
    """A SwitchEntity to replace the old input_boolean usage."""

    def __init__(self, bool_id: str, config: dict, imei: str = "", multi_device: bool = False):
        self._bool_id = bool_id
        self._config = config
        self._imei = imei
        self._multi_device = multi_device

        if multi_device and imei:
            self._attr_has_entity_name = True
            self._attr_unique_id = f"{imei}_{bool_id}"
            self._attr_name = config['name']
            self._attr_device_info = get_device_info(imei, multi_device)
        else:
            # Legacy mode: same as v1.0.4
            self._attr_unique_id = f"{DOMAIN}_{bool_id}"
            self._attr_name = config["name"]
            self._attr_device_info = get_device_info()

        self._icon = config.get("icon", "mdi:toggle-switch")

        # Etat interne initial
        self._is_on = False

    async def async_added_to_hass(self):
        """Récupère la dernière valeur enregistrée s’il y a."""
        await super().async_added_to_hass()
        if (old_state := await self.async_get_last_state()) is not None:
            self._is_on = (old_state.state == "on")

    @property
    def icon(self):
        return self._icon

    @property
    def is_on(self) -> bool:
        return self._is_on

    async def async_turn_on(self, **kwargs):
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        self._is_on = False
        self.async_write_ha_state()
