"""Config flow for Silence Scooter integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_IMEI,
    CONF_TARIFF_SENSOR,
    CONF_CONFIRMATION_DELAY,
    CONF_PAUSE_MAX_DURATION,
    CONF_WATCHDOG_DELAY,
    CONF_USE_TRACKED_DISTANCE,
    CONF_OUTDOOR_TEMP_SOURCE,
    CONF_OUTDOOR_TEMP_ENTITY,
    DEFAULT_TARIFF_SENSOR,
    DEFAULT_CONFIRMATION_DELAY,
    DEFAULT_PAUSE_MAX_DURATION,
    DEFAULT_WATCHDOG_DELAY,
    DEFAULT_USE_TRACKED_DISTANCE,
    DEFAULT_OUTDOOR_TEMP_SOURCE,
    DEFAULT_OUTDOOR_TEMP_ENTITY,
    OUTDOOR_TEMP_SOURCE_SCOOTER,
    OUTDOOR_TEMP_SOURCE_EXTERNAL,
)

_LOGGER = logging.getLogger(__name__)


def get_energy_sensors(hass: HomeAssistant) -> list[str]:
    """Get list of available energy/tariff sensors."""
    sensors = []

    for entity_id in hass.states.async_entity_ids("sensor"):
        state = hass.states.get(entity_id)
        if not state:
            continue

        entity_lower = entity_id.lower()
        name_lower = state.attributes.get("friendly_name", "").lower()

        if any(keyword in entity_lower or keyword in name_lower
               for keyword in ["tarif", "price", "prix", "cout", "cost", "kwh"]):
            sensors.append(entity_id)

    return sorted(sensors)


def get_temperature_sensors(hass: HomeAssistant) -> list[str]:
    """Get list of available temperature sensors."""
    sensors = []

    for entity_id in hass.states.async_entity_ids("sensor"):
        state = hass.states.get(entity_id)
        if not state:
            continue

        # Check device class or unit
        device_class = state.attributes.get("device_class")
        unit = state.attributes.get("unit_of_measurement", "")

        if device_class == "temperature" or unit in ["°C", "°F", "K"]:
            sensors.append(entity_id)

    return sorted(sensors)


def validate_imei(imei: str) -> str:
    """Validate IMEI format.

    Args:
        imei: The IMEI string to validate

    Returns:
        The cleaned IMEI string

    Raises:
        vol.Invalid: If the IMEI format is invalid
    """
    # Remove spaces and dashes
    imei_clean = imei.replace(" ", "").replace("-", "")

    # Check if it contains only digits
    if not imei_clean.isdigit():
        raise vol.Invalid("IMEI must contain only digits")

    # Support IMEI (15 digits) and IMEI/SV (16 digits)
    # Also support 14 digits for some older devices
    if len(imei_clean) == 16:
        imei_clean = imei_clean[:15]

    if len(imei_clean) not in [14, 15]:
        raise vol.Invalid("IMEI must be 14 or 15 digits")

    return imei_clean


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input."""
    errors = {}

    # Validate IMEI if present
    imei = None
    if CONF_IMEI in data:
        try:
            imei = validate_imei(data[CONF_IMEI])
        except vol.Invalid as e:
            errors[CONF_IMEI] = str(e)

    if data.get(CONF_CONFIRMATION_DELAY, 0) < 30:
        errors[CONF_CONFIRMATION_DELAY] = "confirmation_delay_too_low"
    elif data.get(CONF_CONFIRMATION_DELAY, 0) > 600:
        errors[CONF_CONFIRMATION_DELAY] = "confirmation_delay_too_high"

    if data.get(CONF_PAUSE_MAX_DURATION, 0) < 1:
        errors[CONF_PAUSE_MAX_DURATION] = "pause_duration_too_low"
    elif data.get(CONF_PAUSE_MAX_DURATION, 0) > 60:
        errors[CONF_PAUSE_MAX_DURATION] = "pause_duration_too_high"

    if data.get(CONF_WATCHDOG_DELAY, 0) < 1:
        errors[CONF_WATCHDOG_DELAY] = "watchdog_delay_too_low"
    elif data.get(CONF_WATCHDOG_DELAY, 0) > 60:
        errors[CONF_WATCHDOG_DELAY] = "watchdog_delay_too_high"

    tariff_sensor = data.get(CONF_TARIFF_SENSOR)
    if tariff_sensor and tariff_sensor != "":
        if not hass.states.get(tariff_sensor):
            errors[CONF_TARIFF_SENSOR] = "sensor_not_found"

    # Validate outdoor temperature configuration
    temp_source = data.get(CONF_OUTDOOR_TEMP_SOURCE, DEFAULT_OUTDOOR_TEMP_SOURCE)
    if temp_source == OUTDOOR_TEMP_SOURCE_EXTERNAL:
        temp_entity = data.get(CONF_OUTDOOR_TEMP_ENTITY)
        if not temp_entity or temp_entity == "":
            errors[CONF_OUTDOOR_TEMP_ENTITY] = "temp_entity_required"
        elif not hass.states.get(temp_entity):
            errors[CONF_OUTDOOR_TEMP_ENTITY] = "sensor_not_found"

    if errors:
        return {"errors": errors}

    # Create title with last 4 digits of IMEI if available
    if imei:
        imei_short = imei[-4:] if len(imei) >= 4 else imei
        title = f"Silence Scooter ({imei_short})"
    else:
        title = "Silence Scooter"

    return {"title": title, "imei": imei}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Silence Scooter."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            result = await validate_input(self.hass, user_input)

            if "errors" in result:
                errors = result["errors"]
            else:
                # Set unique_id to prevent duplicate IMEI entries
                if result.get("imei"):
                    await self.async_set_unique_id(result["imei"])
                    self._abort_if_unique_id_configured()

                # Store the cleaned IMEI in user_input
                cleaned_data = dict(user_input)
                if result.get("imei"):
                    cleaned_data[CONF_IMEI] = result["imei"]

                return self.async_create_entry(
                    title=result["title"],
                    data=cleaned_data,
                )

        data_schema = vol.Schema({
            vol.Required(CONF_IMEI): selector.TextSelector(
                selector.TextSelectorConfig(
                    type=selector.TextSelectorType.TEXT,
                )
            ),
            vol.Optional(
                CONF_TARIFF_SENSOR,
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor",
                    multiple=False,
                )
            ),
            vol.Optional(
                CONF_OUTDOOR_TEMP_SOURCE,
                default=DEFAULT_OUTDOOR_TEMP_SOURCE,
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=OUTDOOR_TEMP_SOURCE_SCOOTER,
                            label="Scooter ambient temperature sensor"
                        ),
                        selector.SelectOptionDict(
                            value=OUTDOOR_TEMP_SOURCE_EXTERNAL,
                            label="External weather sensor"
                        ),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_OUTDOOR_TEMP_ENTITY,
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor",
                    device_class="temperature",
                    multiple=False,
                )
            ),
            vol.Optional(
                CONF_USE_TRACKED_DISTANCE,
                default=DEFAULT_USE_TRACKED_DISTANCE,
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_CONFIRMATION_DELAY,
                default=DEFAULT_CONFIRMATION_DELAY,
            ): vol.All(vol.Coerce(int), vol.Range(min=30, max=600)),
            vol.Optional(
                CONF_PAUSE_MAX_DURATION,
                default=DEFAULT_PAUSE_MAX_DURATION,
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
            vol.Optional(
                CONF_WATCHDOG_DELAY,
                default=DEFAULT_WATCHDOG_DELAY,
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_import(self, import_info: dict[str, Any]) -> FlowResult:
        """Handle import from configuration.yaml."""
        return await self.async_step_user(import_info)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Handle reauth flow for migration from v1 to v2."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reauth confirmation step."""
        errors = {}

        if user_input is not None:
            try:
                imei = validate_imei(user_input[CONF_IMEI])

                # Set unique_id to prevent duplicate IMEI entries
                await self.async_set_unique_id(imei)
                self._abort_if_unique_id_configured()

                # Update the config entry with the IMEI
                entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
                if entry:
                    updated_data = dict(entry.data)
                    updated_data[CONF_IMEI] = imei

                    # Update title with IMEI
                    imei_short = imei[-4:] if len(imei) >= 4 else imei
                    self.hass.config_entries.async_update_entry(
                        entry,
                        data=updated_data,
                        title=f"Silence Scooter ({imei_short})",
                    )

                    return self.async_abort(reason="reauth_successful")

            except vol.Invalid as e:
                errors[CONF_IMEI] = str(e)

        data_schema = vol.Schema({
            vol.Required(CONF_IMEI): selector.TextSelector(
                selector.TextSelectorConfig(
                    type=selector.TextSelectorType.TEXT,
                )
            ),
        })

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "message": "Please enter your scooter's IMEI to complete the migration to multi-device support."
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlowHandler:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Silence Scooter."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors = {}

        if user_input is not None:
            result = await validate_input(self.hass, user_input)

            if "errors" in result:
                errors = result["errors"]
            else:
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=user_input,
                )
                return self.async_create_entry(title="", data={})

        current_data = self.config_entry.data

        # Only set default for tariff sensor if one is configured
        tariff_default = current_data.get(CONF_TARIFF_SENSOR)
        if tariff_default:
            tariff_optional = vol.Optional(CONF_TARIFF_SENSOR, default=tariff_default)
        else:
            tariff_optional = vol.Optional(CONF_TARIFF_SENSOR)

        # Only set default for outdoor temp entity if one is configured
        temp_entity_default = current_data.get(CONF_OUTDOOR_TEMP_ENTITY)
        if temp_entity_default:
            temp_entity_optional = vol.Optional(CONF_OUTDOOR_TEMP_ENTITY, default=temp_entity_default)
        else:
            temp_entity_optional = vol.Optional(CONF_OUTDOOR_TEMP_ENTITY)

        data_schema = vol.Schema({
            tariff_optional: selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor",
                    multiple=False,
                )
            ),
            vol.Optional(
                CONF_OUTDOOR_TEMP_SOURCE,
                default=current_data.get(CONF_OUTDOOR_TEMP_SOURCE, DEFAULT_OUTDOOR_TEMP_SOURCE),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=OUTDOOR_TEMP_SOURCE_SCOOTER,
                            label="Scooter ambient temperature sensor"
                        ),
                        selector.SelectOptionDict(
                            value=OUTDOOR_TEMP_SOURCE_EXTERNAL,
                            label="External weather sensor"
                        ),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            temp_entity_optional: selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor",
                    device_class="temperature",
                    multiple=False,
                )
            ),
            vol.Optional(
                CONF_USE_TRACKED_DISTANCE,
                default=current_data.get(CONF_USE_TRACKED_DISTANCE, DEFAULT_USE_TRACKED_DISTANCE),
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_CONFIRMATION_DELAY,
                default=current_data.get(CONF_CONFIRMATION_DELAY, DEFAULT_CONFIRMATION_DELAY),
            ): vol.All(vol.Coerce(int), vol.Range(min=30, max=600)),
            vol.Optional(
                CONF_PAUSE_MAX_DURATION,
                default=current_data.get(CONF_PAUSE_MAX_DURATION, DEFAULT_PAUSE_MAX_DURATION),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
            vol.Optional(
                CONF_WATCHDOG_DELAY,
                default=current_data.get(CONF_WATCHDOG_DELAY, DEFAULT_WATCHDOG_DELAY),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
        })

        return self.async_show_form(
            step_id="init",
            data_schema=data_schema,
            errors=errors,
        )
