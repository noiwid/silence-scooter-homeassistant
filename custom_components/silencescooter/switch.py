"""Switch platform for Silence Scooter integration."""

import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .definitions import INPUT_BOOLEANS
from .helpers import get_device_info

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
):
    """Set up the custom Switch entities (ex-input_boolean) for Silence Scooter."""
    entities = []
    for bool_id, config in INPUT_BOOLEANS.items():
        entities.append(ScooterSwitchEntity(bool_id, config))
    async_add_entities(entities)


class ScooterSwitchEntity(SwitchEntity, RestoreEntity):
    """A SwitchEntity to replace the old input_boolean usage."""

    def __init__(self, bool_id: str, config: dict):
        self._bool_id = bool_id
        self._attr_unique_id = f"{DOMAIN}_{bool_id}"
        self._attr_name = config["name"]
        self._icon = config.get("icon", "mdi:toggle-switch")
        self._attr_device_info = get_device_info()

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

    def turn_on(self, **kwargs):
        self._is_on = True
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs):
        self._is_on = False
        self.schedule_update_ha_state()
