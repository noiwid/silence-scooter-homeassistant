"""Datetime platform for Silence Scooter integration."""

import logging
from datetime import datetime
from typing import Optional
import zoneinfo

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .definitions import INPUT_DATETIMES

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Datetime entities for Silence Scooter."""
    if _LOGGER.isEnabledFor(logging.DEBUG):
        _LOGGER.debug("Setting up Silence Scooter datetime entities")
    entities = []
    for datetime_id, config in INPUT_DATETIMES.items():
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(f"Creating datetime entity for {datetime_id}")
        entities.append(ScooterDateTimeEntity(hass, datetime_id, config))
    async_add_entities(entities)


class ScooterDateTimeEntity(DateTimeEntity, RestoreEntity):
    """Representation of a Scooter DateTime entity."""

    def __init__(self, hass: HomeAssistant, datetime_id: str, config: dict):
        """Initialize the datetime entity."""
        self.hass = hass
        self._datetime_id = datetime_id
        self._attr_unique_id = f"{DOMAIN}_{datetime_id}"
        self._attr_name = config["name"]
        self.entity_id = f"datetime.{datetime_id}"

        # Configuration
        self._has_date = config.get("has_date", True)
        self._has_time = config.get("has_time", True)
        # Datetimes are internal entities, not shown on device page

        # Valeur initiale avec timezone
        self._value = dt_util.now()
        self._attr_native_value = self._value
        self._config = config

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("Initialized %s with config: %s", self.entity_id, config)

    async def async_added_to_hass(self):
        """Handle entity which will be added."""
        await super().async_added_to_hass()

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("Attempting to restore state for %s", self.entity_id)

        old_input_datetime = self.hass.states.get(f"input_datetime.{self._datetime_id}")
        if old_input_datetime and old_input_datetime.state not in ['unknown', 'unavailable']:
            try:
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug("Found old input_datetime state for %s: %s",
                                 self.entity_id, old_input_datetime.state)
                naive_dt = datetime.strptime(old_input_datetime.state, "%Y-%m-%d %H:%M:%S")
                restored_value = dt_util.as_local(naive_dt)
                self._value = restored_value
                self._attr_native_value = restored_value
                self.async_write_ha_state()
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug("Restored %s from input_datetime: %s", self.entity_id, self._value)
                return
            except (ValueError, TypeError) as e:
                _LOGGER.warning("Could not convert input_datetime state for %s: %s", self.entity_id, e)

        if last_state := await self.async_get_last_state():
            try:
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug("Found last state for %s: %s", self.entity_id, last_state.state)
                try:
                    naive_dt = datetime.strptime(last_state.state, "%Y-%m-%dT%H:%M:%S%z")
                except ValueError:
                    naive_dt = datetime.strptime(last_state.state, "%Y-%m-%d %H:%M:%S")
                restored_value = dt_util.as_local(naive_dt)
                self._value = restored_value
                self._attr_native_value = restored_value
                self.async_write_ha_state()
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug("Restored %s from last state: %s", self.entity_id, self._value)
            except (ValueError, TypeError) as e:
                _LOGGER.warning("Could not restore datetime from state %s for %s: %s",
                               last_state.state, self.entity_id, e)
                self._value = dt_util.now()
                self._attr_native_value = self._value
                self.async_write_ha_state()


    @property
    def native_value(self) -> Optional[datetime]:
        """Return the value reported by the datetime."""
        return self._value

    async def async_set_value(self, value: datetime) -> None:
        """Set new value."""
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("Setting %s to %s", self.entity_id, value)

        if value.tzinfo is None:
            value = dt_util.as_local(value)

        self._value = value
        self._attr_native_value = value
        self.async_write_ha_state()
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug("Successfully updated %s to %s", self.entity_id, value)