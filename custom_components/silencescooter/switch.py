"""Switch platform for Silence Scooter integration."""

import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, CONF_IMEI
from .definitions import INPUT_BOOLEANS
from .helpers import get_device_info

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
):
    """Set up the custom Switch entities (ex-input_boolean) for Silence Scooter."""
    from homeassistant.exceptions import ConfigEntryNotReady

    # Get IMEI from config entry
    imei = entry.data.get(CONF_IMEI)
    if not imei:
        raise ConfigEntryNotReady("IMEI not configured")

    entities = []
    for bool_id, config in INPUT_BOOLEANS.items():
        entities.append(ScooterSwitchEntity(bool_id, config, imei))
    async_add_entities(entities)


class ScooterSwitchEntity(SwitchEntity, RestoreEntity):
    """A SwitchEntity to replace the old input_boolean usage."""

    def __init__(self, bool_id: str, config: dict, imei: str):
        self._bool_id = bool_id
        self._config = config
        self._imei = imei

        # CRITICAL: Use full IMEI for unique_id
        self._attr_unique_id = f"{bool_id}_{imei}"

        # Display name with last 4 digits
        imei_short = imei[-4:] if len(imei) >= 4 else imei
        self._attr_name = f"{config['name']} ({imei_short})"

        # DO NOT set self.entity_id - let HA generate it

        self._icon = config.get("icon", "mdi:toggle-switch")

        # Device info with IMEI
        self._attr_device_info = get_device_info(imei)

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
