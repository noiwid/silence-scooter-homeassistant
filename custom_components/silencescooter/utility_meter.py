"""
Utility Meter platform for Silence Scooter integration.
Génère les compteurs daily, weekly, monthly et yearly
à partir de sensor.scooter_energy_consumption.
"""

import logging

from homeassistant.components.utility_meter.const import (
    DAILY, WEEKLY, MONTHLY, YEARLY
)
from homeassistant.components.utility_meter.sensor import UtilityMeterSensor
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .definitions import UTILITY_METERS
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CYCLE_MAP = {
    "daily": DAILY,
    "weekly": WEEKLY,
    "monthly": MONTHLY,
    "yearly": YEARLY,
}

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Setup utility_meter sensors based on UTILITY_METERS definitions."""
    entities = []
    for meter_id, cfg in UTILITY_METERS.items():
        cycle = cfg.get("cycle")
        source = cfg.get("source")
        if cycle not in CYCLE_MAP or not source:
            _LOGGER.warning("Skipping utility_meter %s: bad cycle/source", meter_id)
            continue

        name = meter_id.replace("_", " ").title().replace("Scooter ", "Scooter - ")
        entities.append(
            UtilityMeterSensor(
                hass,
                name=name,
                meter=CYCLE_MAP[cycle],
                source_entity=source,
                round_digits=3,
                parent_meter=None,
                tariffs=None,
                net_consumption=False,
            )
        )

    async_add_entities(entities)
    _LOGGER.info("Created utility_meter sensors for Silence Scooter: %s", list(UTILITY_METERS.keys()))
