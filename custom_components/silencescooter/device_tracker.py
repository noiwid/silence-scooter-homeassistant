"""Device tracker platform for the Silence Scooter integration.

Entité ``TrackerEntity`` native qui remplace l'ancien appel au service
``device_tracker.see`` (obsolète, supprimé dans Home Assistant 2027.5).

L'entité recopie les capteurs MQTT bruts latitude / longitude / SoC dans un
vrai tracker GPS et applique un filtre léger pour que la trace sur la carte
reste lisible :

- un point à (0, 0) ou hors plage est ignoré (on ne téléporte jamais le
  scooter sur l'île Null à la première trame batterie sans GPS) ;
- un point à moins de ``tracker_min_distance`` mètres du dernier point
  accepté est ignoré (jitter GPS à l'arrêt, au feu rouge, au garage) ;
- un point qui impliquerait une vitesse supérieure à
  ``TRACKER_MAX_SPEED_KMH`` depuis le dernier point accepté est rejeté comme
  aberrant ; après ``TRACKER_RESYNC_AFTER_REJECTS`` rejets consécutifs le
  point est accepté quand même, pour qu'un seul mauvais point « ancre » ne
  fige pas le tracker.

Latitude et longitude arrivent comme deux changements d'état MQTT distincts :
l'évaluation est différée de ``TRACKER_DEBOUNCE_SECONDS`` pour lire les deux
moitiés de la trame ensemble au lieu de produire un point « en diagonale ».
"""
from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
)
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance as gps_distance

from .const import (
    DOMAIN,
    CONF_IMEI,
    CONF_MULTI_DEVICE,
    DEFAULT_MULTI_DEVICE,
    CONF_DEVICE_TRACKER,
    DEFAULT_DEVICE_TRACKER,
    CONF_TRACKER_MIN_DISTANCE,
    DEFAULT_TRACKER_MIN_DISTANCE,
    TRACKER_MAX_SPEED_KMH,
    TRACKER_RESYNC_AFTER_REJECTS,
    TRACKER_DEBOUNCE_SECONDS,
)
from .helpers import get_device_info, insert_imei_in_entity_id

_LOGGER = logging.getLogger(__name__)

TRACKER_KEY = "silence_scooter"
ATTR_LAST_FIX = "last_fix"
ATTR_REJECTED = "rejected_fixes"


def _tracker_unique_id(imei: str, multi_device: bool) -> str:
    """Unique id of the tracker entity, per naming mode."""
    if multi_device and imei:
        return f"{imei}_device_tracker"
    return f"{DOMAIN}_{TRACKER_KEY}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the GPS device tracker for Silence Scooter."""
    imei = entry.data.get(CONF_IMEI, "")
    multi_device = entry.data.get(CONF_MULTI_DEVICE, DEFAULT_MULTI_DEVICE)
    enabled = entry.data.get(CONF_DEVICE_TRACKER, DEFAULT_DEVICE_TRACKER)
    min_distance = float(entry.data.get(CONF_TRACKER_MIN_DISTANCE, DEFAULT_TRACKER_MIN_DISTANCE))

    if not enabled:
        # Option décochée : on retire l'entité du registre si elle existait,
        # sinon elle resterait affichée « indisponible » pour toujours.
        registry = er.async_get(hass)
        existing = registry.async_get_entity_id(
            "device_tracker", DOMAIN, _tracker_unique_id(imei, multi_device)
        )
        if existing:
            registry.async_remove(existing)
            _LOGGER.info("Device tracker disabled in options, removed %s", existing)
        else:
            _LOGGER.debug("Device tracker disabled in options, nothing to create")
        return

    async_add_entities([ScooterDeviceTracker(imei, multi_device, min_distance)])


class ScooterDeviceTracker(TrackerEntity, RestoreEntity):
    """GPS tracker fed by the raw MQTT latitude / longitude sensors."""

    _attr_should_poll = False
    _attr_icon = "mdi:moped-electric"
    _attr_source_type = SourceType.GPS
    # Le firmware Astra ne publie pas de précision : 0 = "inconnue" pour HA
    _attr_location_accuracy = 0

    def __init__(self, imei: str, multi_device: bool, min_distance_m: float) -> None:
        self._imei = imei
        self._multi_device = multi_device
        self._min_distance_m = max(0.0, min_distance_m)

        self._attr_unique_id = _tracker_unique_id(imei, multi_device)
        if multi_device and imei:
            self._attr_has_entity_name = True
            self._attr_name = "Position"
            self._attr_device_info = get_device_info(imei, multi_device)
            self.entity_id = insert_imei_in_entity_id(
                f"device_tracker.{TRACKER_KEY}", imei, multi_device
            )
        else:
            # Legacy mode: same entity_id the old device_tracker.see call produced
            self._attr_name = "Silence Scooter"
            self._attr_device_info = get_device_info()
            self.entity_id = f"device_tracker.{TRACKER_KEY}"

        def eid(base: str) -> str:
            return insert_imei_in_entity_id(base, imei, multi_device)

        # Deux conventions de nommage cohabitent selon l'origine des capteurs
        # MQTT (ancien scooter_package.yaml → silence_scooter_silence_latitude,
        # Discovery / examples/silence.yaml → silence_scooter_latitude).
        self._lat_sensors = [
            eid("sensor.silence_scooter_silence_latitude"),
            eid("sensor.silence_scooter_latitude"),
        ]
        self._lon_sensors = [
            eid("sensor.silence_scooter_silence_longitude"),
            eid("sensor.silence_scooter_longitude"),
        ]
        self._batt_sensor = eid("sensor.silence_scooter_battery_soc")

        # Position / batterie via les _attr_ shorthand de TrackerEntity (HA
        # déprécie la surcharge des propriétés latitude/longitude/battery_level).
        self._attr_latitude = None
        self._attr_longitude = None
        self._attr_battery_level = None
        self._last_fix: datetime | None = None
        self._rejected = 0
        self._debounce_cancel = None
        self._unsub_sensors = None

    # ------------------------------------------------------------------ #
    # TrackerEntity surface
    # ------------------------------------------------------------------ #
    @property
    def extra_state_attributes(self) -> dict:
        return {
            ATTR_LAST_FIX: self._last_fix.isoformat() if self._last_fix else None,
            ATTR_REJECTED: self._rejected,
        }

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        # Les capteurs MQTT ne sont pas retained : après un redémarrage de HA
        # ils sont `unknown` jusqu'à la prochaine trame. On restaure donc la
        # dernière position connue pour ne pas perdre le scooter sur la carte.
        last = await self.async_get_last_state()
        if last is not None:
            self._attr_latitude = self._restore_float(last.attributes.get("latitude"))
            self._attr_longitude = self._restore_float(last.attributes.get("longitude"))
            batt = self._restore_float(last.attributes.get("battery_level"))
            self._attr_battery_level = int(batt) if batt is not None else None
            last_fix = last.attributes.get(ATTR_LAST_FIX)
            if isinstance(last_fix, str):
                parsed = dt_util.parse_datetime(last_fix)
                self._last_fix = dt_util.as_utc(parsed) if parsed else None
            if self._attr_latitude is None or self._attr_longitude is None:
                self._attr_latitude = self._attr_longitude = None

        self._unsub_sensors = async_track_state_change_event(
            self.hass,
            self._lat_sensors + self._lon_sensors + [self._batt_sensor],
            self._handle_sensor_event,
        )
        # Première évaluation sur l'état courant (cas d'un reload à chaud)
        self._evaluate()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub_sensors:
            self._unsub_sensors()
            self._unsub_sensors = None
        if self._debounce_cancel:
            self._debounce_cancel()
            self._debounce_cancel = None
        await super().async_will_remove_from_hass()

    # ------------------------------------------------------------------ #
    # Update path
    # ------------------------------------------------------------------ #
    @callback
    def _handle_sensor_event(self, event: Event) -> None:
        """Debounce: lat et lon arrivent en deux événements, on lit les deux."""
        if self._debounce_cancel:
            self._debounce_cancel()
        self._debounce_cancel = async_call_later(
            self.hass, TRACKER_DEBOUNCE_SECONDS, self._debounced_evaluate
        )

    @callback
    def _debounced_evaluate(self, _now) -> None:
        self._debounce_cancel = None
        self._evaluate()

    @callback
    def _evaluate(self) -> None:
        changed = False

        batt = self._read_float([self._batt_sensor])
        if batt is not None:
            batt_int = int(round(max(0.0, min(100.0, batt))))
            if batt_int != self._attr_battery_level:
                self._attr_battery_level = batt_int
                changed = True

        lat = self._read_float(self._lat_sensors)
        lon = self._read_float(self._lon_sensors)
        if lat is not None and lon is not None and self._is_plausible(lat, lon):
            if self._accept_fix(lat, lon):
                changed = True

        if changed:
            self.async_write_ha_state()

    def _read_float(self, entity_ids: list[str]) -> float | None:
        for entity_id in entity_ids:
            state = self.hass.states.get(entity_id)
            if state is None or state.state in ("unknown", "unavailable", ""):
                continue
            try:
                return float(state.state)
            except (ValueError, TypeError):
                continue
        return None

    @staticmethod
    def _restore_float(value) -> float | None:
        try:
            return float(value) if value is not None else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _is_plausible(lat: float, lon: float) -> bool:
        if abs(lat) < 1e-6 and abs(lon) < 1e-6:
            return False  # (0, 0) = pas de fix GPS
        return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0

    def _accept_fix(self, lat: float, lon: float) -> bool:
        """Apply the distance / speed filter. Returns True if position changed."""
        now = dt_util.utcnow()

        if self._attr_latitude is not None and self._attr_longitude is not None:
            dist_m = gps_distance(self._attr_latitude, self._attr_longitude, lat, lon) or 0.0

            if dist_m < self._min_distance_m:
                # Jitter à l'arrêt : on garde le point précédent
                return False

            if self._last_fix is not None:
                elapsed = (now - self._last_fix).total_seconds()
                if elapsed > 0:
                    speed_kmh = dist_m / elapsed * 3.6
                    if speed_kmh > TRACKER_MAX_SPEED_KMH:
                        self._rejected += 1
                        if self._rejected < TRACKER_RESYNC_AFTER_REJECTS:
                            _LOGGER.debug(
                                "%s: rejected GPS fix (%.0f m in %.0f s = %.0f km/h, %d/%d)",
                                self.entity_id, dist_m, elapsed, speed_kmh,
                                self._rejected, TRACKER_RESYNC_AFTER_REJECTS,
                            )
                            return False
                        _LOGGER.debug(
                            "%s: %d consecutive rejected fixes, resyncing on %.6f, %.6f",
                            self.entity_id, self._rejected, lat, lon,
                        )

        self._attr_latitude = lat
        self._attr_longitude = lon
        self._last_fix = now
        self._rejected = 0
        return True
