"""Error detection system for the Silence Scooter integration.

Provides centralized error tracking, pattern detection, correlation analysis,
and diagnostic reporting for the integration's sensors, automations, and
MQTT connectivity.
"""
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Categories for classifying detected errors."""
    SENSOR_UNAVAILABLE = "sensor_unavailable"
    SENSOR_STALE = "sensor_stale"
    SENSOR_INVALID = "sensor_invalid"
    MQTT_DISCONNECT = "mqtt_disconnect"
    TRIP_ANOMALY = "trip_anomaly"
    STATE_RESTORATION = "state_restoration"
    TEMPLATE_ERROR = "template_error"
    SERVICE_CALL = "service_call"
    AUTOMATION_ERROR = "automation_error"
    DATA_INTEGRITY = "data_integrity"


class ErrorSeverity(Enum):
    """Severity levels for detected errors."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ErrorEvent:
    """A single error occurrence."""
    timestamp: float
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    source: str
    entity_id: Optional[str] = None
    details: Optional[dict] = None


@dataclass
class ErrorPattern:
    """A detected recurring error pattern."""
    category: ErrorCategory
    count: int
    first_seen: float
    last_seen: float
    source: str
    message: str
    severity: ErrorSeverity = ErrorSeverity.WARNING


# Maximum number of error events to keep in the rolling window
MAX_ERROR_HISTORY = 200

# Time window for pattern detection (seconds)
PATTERN_WINDOW = 3600  # 1 hour

# Threshold for recurring error pattern detection
PATTERN_THRESHOLD = 3

# Stale sensor timeout (seconds) — how long before a sensor is considered stale
STALE_SENSOR_TIMEOUT = 900  # 15 minutes


class ErrorDetector:
    """Central error detection and tracking system.

    Tracks error events, detects recurring patterns, monitors sensor health,
    and provides diagnostic summaries for the integration.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._errors: deque[ErrorEvent] = deque(maxlen=MAX_ERROR_HISTORY)
        self._patterns: dict[str, ErrorPattern] = {}
        self._sensor_last_update: dict[str, float] = {}
        self._cascade_tracker: dict[str, list[str]] = {}
        self._listeners: list = []
        self._started = False

    def record_error(
        self,
        category: ErrorCategory,
        severity: ErrorSeverity,
        message: str,
        source: str,
        entity_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        """Record an error event and update pattern tracking."""
        event = ErrorEvent(
            timestamp=time.monotonic(),
            category=category,
            severity=severity,
            message=message,
            source=source,
            entity_id=entity_id,
            details=details,
        )
        self._errors.append(event)

        # Update pattern tracking
        pattern_key = f"{category.value}:{source}"
        now = time.monotonic()

        if pattern_key in self._patterns:
            pattern = self._patterns[pattern_key]
            pattern.count += 1
            pattern.last_seen = now
            pattern.message = message
            if severity.value > pattern.severity.value:
                pattern.severity = severity
        else:
            self._patterns[pattern_key] = ErrorPattern(
                category=category,
                count=1,
                first_seen=now,
                last_seen=now,
                source=source,
                message=message,
                severity=severity,
            )

        # Track cascade relationships
        if entity_id:
            self._cascade_tracker.setdefault(entity_id, []).append(pattern_key)

        # Log based on severity
        if severity == ErrorSeverity.CRITICAL:
            _LOGGER.error(
                "CRITICAL error detected [%s] %s: %s",
                category.value, source, message,
            )
        elif severity == ErrorSeverity.ERROR:
            _LOGGER.error(
                "Error detected [%s] %s: %s",
                category.value, source, message,
            )
        elif severity == ErrorSeverity.WARNING:
            _LOGGER.warning(
                "Warning detected [%s] %s: %s",
                category.value, source, message,
            )

    def record_sensor_update(self, entity_id: str) -> None:
        """Record that a sensor was successfully updated."""
        self._sensor_last_update[entity_id] = time.monotonic()

    def check_sensor_staleness(self, entity_id: str) -> bool:
        """Check if a sensor has gone stale (no updates within timeout).

        Returns True if the sensor is stale.
        """
        last_update = self._sensor_last_update.get(entity_id)
        if last_update is None:
            return False  # Never updated — don't flag during startup
        elapsed = time.monotonic() - last_update
        return elapsed > STALE_SENSOR_TIMEOUT

    def check_sensor_value(
        self,
        entity_id: str,
        value: object,
        min_val: Optional[float] = None,
        max_val: Optional[float] = None,
    ) -> bool:
        """Validate a sensor value is within expected bounds.

        Returns True if the value is valid.
        """
        if value is None or str(value) in ("unknown", "unavailable", ""):
            self.record_error(
                ErrorCategory.SENSOR_UNAVAILABLE,
                ErrorSeverity.WARNING,
                f"Sensor {entity_id} is unavailable or unknown",
                source="sensor_check",
                entity_id=entity_id,
            )
            return False

        try:
            float_val = float(value)
        except (ValueError, TypeError):
            self.record_error(
                ErrorCategory.SENSOR_INVALID,
                ErrorSeverity.WARNING,
                f"Sensor {entity_id} has non-numeric value: {value}",
                source="sensor_check",
                entity_id=entity_id,
            )
            return False

        if min_val is not None and float_val < min_val:
            self.record_error(
                ErrorCategory.SENSOR_INVALID,
                ErrorSeverity.WARNING,
                f"Sensor {entity_id} value {float_val} below minimum {min_val}",
                source="sensor_check",
                entity_id=entity_id,
            )
            return False

        if max_val is not None and float_val > max_val:
            self.record_error(
                ErrorCategory.SENSOR_INVALID,
                ErrorSeverity.WARNING,
                f"Sensor {entity_id} value {float_val} above maximum {max_val}",
                source="sensor_check",
                entity_id=entity_id,
            )
            return False

        return True

    def check_trip_anomaly(
        self,
        distance: float,
        duration: float,
        avg_speed: float,
        max_speed: float,
        battery_consumption: float,
    ) -> list[str]:
        """Detect anomalies in trip data. Returns list of anomaly descriptions."""
        anomalies = []

        # Physics checks
        if duration > 0 and distance > 0:
            calculated_speed = (distance / duration) * 60
            if avg_speed > 0 and abs(calculated_speed - avg_speed) / avg_speed > 0.3:
                anomalies.append(
                    f"Speed mismatch: calculated={calculated_speed:.1f} vs recorded={avg_speed:.1f} km/h"
                )

        if max_speed > 0 and avg_speed > max_speed:
            anomalies.append(
                f"Average speed ({avg_speed:.1f}) exceeds max speed ({max_speed:.1f})"
            )

        if avg_speed > 120:
            anomalies.append(f"Unrealistic average speed: {avg_speed:.1f} km/h")

        if distance > 500:
            anomalies.append(f"Unrealistic distance: {distance:.1f} km")

        if duration < 1.5 and distance > 2:
            anomalies.append(
                f"Impossible trip: {distance:.1f} km in {duration:.1f} min"
            )

        if battery_consumption > 100:
            anomalies.append(
                f"Battery consumption exceeds 100%: {battery_consumption:.1f}%"
            )

        if battery_consumption < 0:
            anomalies.append(
                f"Negative battery consumption: {battery_consumption:.1f}%"
            )

        # Efficiency check: > 10% per km is unusual for an electric scooter
        if distance > 0 and battery_consumption / distance > 10:
            anomalies.append(
                f"High battery drain: {battery_consumption/distance:.1f}%/km"
            )

        for anomaly in anomalies:
            self.record_error(
                ErrorCategory.TRIP_ANOMALY,
                ErrorSeverity.WARNING,
                anomaly,
                source="trip_validation",
            )

        return anomalies

    def detect_mqtt_disconnect(self, mqtt_sensors: list[str]) -> bool:
        """Check if MQTT sensors indicate a disconnect.

        Returns True if a disconnect is detected (all monitored sensors unavailable).
        """
        unavailable_count = 0
        for entity_id in mqtt_sensors:
            state = self._hass.states.get(entity_id)
            if not state or state.state in ("unknown", "unavailable"):
                unavailable_count += 1

        if unavailable_count == len(mqtt_sensors) and len(mqtt_sensors) > 0:
            self.record_error(
                ErrorCategory.MQTT_DISCONNECT,
                ErrorSeverity.ERROR,
                f"All {len(mqtt_sensors)} MQTT sensors are unavailable — possible disconnect",
                source="mqtt_monitor",
            )
            return True

        if unavailable_count > len(mqtt_sensors) * 0.5:
            self.record_error(
                ErrorCategory.MQTT_DISCONNECT,
                ErrorSeverity.WARNING,
                f"{unavailable_count}/{len(mqtt_sensors)} MQTT sensors unavailable",
                source="mqtt_monitor",
            )

        return False

    def detect_cascade_failure(self, entity_id: str) -> list[str]:
        """Check if errors on an entity correlate with errors on related entities.

        Returns list of related entity IDs that also have errors.
        """
        related_errors = self._cascade_tracker.get(entity_id, [])
        if len(related_errors) < 2:
            return []

        # Find other entities that share error patterns
        cascaded = []
        for other_entity, patterns in self._cascade_tracker.items():
            if other_entity == entity_id:
                continue
            shared = set(related_errors) & set(patterns)
            if shared:
                cascaded.append(other_entity)

        if cascaded:
            self.record_error(
                ErrorCategory.DATA_INTEGRITY,
                ErrorSeverity.WARNING,
                f"Cascade detected: {entity_id} errors correlate with {len(cascaded)} other entities",
                source="cascade_detector",
                entity_id=entity_id,
                details={"related_entities": cascaded[:5]},
            )

        return cascaded

    def get_recurring_patterns(self) -> list[ErrorPattern]:
        """Get error patterns that have recurred above the threshold."""
        now = time.monotonic()
        return [
            p for p in self._patterns.values()
            if p.count >= PATTERN_THRESHOLD
            and (now - p.first_seen) < PATTERN_WINDOW
        ]

    def get_error_summary(self) -> dict:
        """Get a diagnostic summary of all tracked errors."""
        now = time.monotonic()

        # Count by category
        category_counts: dict[str, int] = {}
        severity_counts: dict[str, int] = {}
        recent_errors = []

        for event in self._errors:
            cat = event.category.value
            sev = event.severity.value
            category_counts[cat] = category_counts.get(cat, 0) + 1
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        # Last 10 errors for quick review
        for event in list(self._errors)[-10:]:
            recent_errors.append({
                "category": event.category.value,
                "severity": event.severity.value,
                "message": event.message,
                "source": event.source,
                "entity_id": event.entity_id,
            })

        recurring = self.get_recurring_patterns()
        stale_sensors = [
            eid for eid in self._sensor_last_update
            if self.check_sensor_staleness(eid)
        ]

        return {
            "total_errors": len(self._errors),
            "errors_by_category": category_counts,
            "errors_by_severity": severity_counts,
            "recurring_patterns": len(recurring),
            "stale_sensors": stale_sensors,
            "recent_errors": recent_errors,
        }

    def get_error_count(self) -> int:
        """Get total number of tracked errors."""
        return len(self._errors)

    def get_active_issues_count(self) -> int:
        """Get count of currently active issues (errors + warnings in the last hour)."""
        now = time.monotonic()
        count = 0
        for event in self._errors:
            if (now - event.timestamp) < PATTERN_WINDOW:
                if event.severity in (ErrorSeverity.ERROR, ErrorSeverity.CRITICAL):
                    count += 1
        return count

    def clear_old_patterns(self) -> None:
        """Remove patterns older than the tracking window."""
        now = time.monotonic()
        expired = [
            key for key, pattern in self._patterns.items()
            if (now - pattern.last_seen) > PATTERN_WINDOW
        ]
        for key in expired:
            del self._patterns[key]

    async def async_setup(self) -> None:
        """Set up periodic health checks."""
        if self._started:
            return
        self._started = True

        from datetime import timedelta

        @callback
        def _periodic_health_check(_now):
            """Run periodic health checks."""
            self.clear_old_patterns()
            self._run_health_check()

        listener = async_track_time_interval(
            self._hass, _periodic_health_check, timedelta(minutes=5)
        )
        self._listeners.append(listener)
        _LOGGER.info("Error detection system initialized")

    def _run_health_check(self) -> None:
        """Run a health check on monitored sensors."""
        # Check key MQTT sensors for connectivity
        mqtt_sensors = [
            "sensor.silence_scooter_status",
            "sensor.silence_scooter_odo",
            "sensor.silence_scooter_battery_soc",
            "sensor.silence_scooter_speed",
        ]
        self.detect_mqtt_disconnect(mqtt_sensors)

        # Check for stale sensors
        for entity_id in list(self._sensor_last_update.keys()):
            if self.check_sensor_staleness(entity_id):
                self.record_error(
                    ErrorCategory.SENSOR_STALE,
                    ErrorSeverity.WARNING,
                    f"Sensor {entity_id} has not updated in >{STALE_SENSOR_TIMEOUT}s",
                    source="health_check",
                    entity_id=entity_id,
                )

        # Log summary if there are active issues
        active = self.get_active_issues_count()
        if active > 0:
            _LOGGER.warning(
                "Health check: %d active issues, %d total tracked errors",
                active, len(self._errors),
            )

    def cleanup(self) -> None:
        """Clean up listeners."""
        for listener in self._listeners:
            try:
                listener()
            except Exception:
                pass
        self._listeners.clear()
        self._started = False


def get_error_detector(hass: HomeAssistant) -> Optional[ErrorDetector]:
    """Get the ErrorDetector instance from hass.data, if available."""
    return hass.data.get(DOMAIN, {}).get("error_detector")
