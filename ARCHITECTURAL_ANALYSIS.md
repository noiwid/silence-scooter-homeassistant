# Silence Scooter Home Assistant Integration - Architectural Analysis

## Executive Summary

The Silence Scooter integration is currently designed as a **single-device system** with hard-coded MQTT topic paths and entity IDs. There is **NO IMEI-based isolation** currently implemented. All data flows directly from MQTT to Home Assistant entities with a static device identifier.

**Current Architecture**: Monolithic, single-scooter design
**Challenge**: Multi-device support requires IMEI-based topic separation and entity namespacing

---

## 1. Integration Structure

### Main Entry Point
**File**: `/custom_components/silencescooter/__init__.py` (Lines 1-211)

**Key Components**:
- **async_setup_entry()** (Lines 15-171): Main setup function
  - Initializes storage: `hass.data[DOMAIN][entry.entry_id]`
  - Loads platforms: SENSOR, NUMBER, DATETIME, SWITCH
  - Registers services: `reset_tracked_counters`, `restore_energy_costs`
  - Sets up automations and persistent sensor updates

- **async_unload_entry()** (Lines 178-205): Cleanup on removal
- **async_reload_entry()** (Lines 208-211): Reload handler

### Data Storage
**Location**: Line 20-24 in `__init__.py`
```python
hass.data[DOMAIN] = {}
hass.data[DOMAIN][entry.entry_id] = {}
hass.data[DOMAIN]["sensors"] = {}
hass.data[DOMAIN]["config"] = entry.data
```

**Current Limitation**: Single `sensors` dict - no per-device separation

---

## 2. MQTT Topics Definition and Usage

### Topic Structure (From `/examples/silence.yaml`)
```
home/silence-server/{IMEI}/status/{sensor_name}
home/silence-server/{IMEI}/command/{command_name}
```

**Example Topics** (Lines 6-362 in silence.yaml):
- `home/silence-server/YOUR_SCOOTER_IMEI/status/speed`
- `home/silence-server/YOUR_SCOOTER_IMEI/status/SOCbatteria`
- `home/silence-server/YOUR_SCOOTER_IMEI/status/odo`
- `home/silence-server/YOUR_SCOOTER_IMEI/command/TURN_ON_SCOOTER`
- etc. (50+ sensors)

### MQTT Integration Method
**Location**: `/examples/silence.yaml` (Lines 1-384)

The integration uses **Home Assistant MQTT Discovery** via YAML configuration:
- Buttons, Binary Sensors, and Sensors are defined in `mqtt:` section
- Each topic has hardcoded `YOUR_SCOOTER_IMEI` placeholder
- All sensors share a single device identifier: `"Silence Scooter"`

**Critical Issue**: Entity IDs are auto-generated and IMEI is NOT encoded:
```
sensor.silence_scooter_speed
sensor.silence_scooter_odo
sensor.silence_scooter_battery_soc
```

These don't include IMEI, making multi-device support impossible.

---

## 3. Device/Scooter Identification

### Device Info Function
**File**: `/custom_components/silencescooter/helpers.py` (Lines 15-22)
```python
def get_device_info() -> DeviceInfo:
    """Return device info for Silence Scooter."""
    return DeviceInfo(
        identifiers={("silence_scooter", "Silence Scooter")},
        name="Silence Scooter",
        manufacturer="Seat",
        model="Mo",
    )
```

**Current Implementation**:
- **Hard-coded identifier**: `("silence_scooter", "Silence Scooter")`
- **No IMEI reference**: Device ID is static
- **No multi-device support**: All entities map to the same device

### Usage Locations
- **sensor.py** (Line 182, 317): Template and writable sensors
- **switch.py** (Line 36): Switch entity
- **datetime.py**: Not used (internal entities)
- **number.py**: Not used (internal entities)

### Device Tracker
**Location**: `automations.py` (Line 292)
```python
DEVICE_TRACKER_ID = "silence_scooter"
```

Used in `_do_update_tracker()` (Lines 959-994) to update GPS position via `device_tracker.see` service with hardcoded `dev_id`.

---

## 4. Configuration Handling

### Config Flow
**File**: `/custom_components/silencescooter/config_flow.py`

**Current Design** (Lines 113-196):
- Single instance only: `single_instance_allowed` check (Line 122-123)
- No IMEI input field
- Configuration options:
  - `CONF_TARIFF_SENSOR`
  - `CONF_CONFIRMATION_DELAY`
  - `CONF_PAUSE_MAX_DURATION`
  - `CONF_WATCHDOG_DELAY`
  - `CONF_USE_TRACKED_DISTANCE`
  - `CONF_OUTDOOR_TEMP_SOURCE`
  - `CONF_OUTDOOR_TEMP_ENTITY`

**Storage Location**: `config_entry.data` (Line 24 in `__init__.py`)

### Options Flow
**Location**: Lines 211-306 in `config_flow.py`

Allows reconfiguration of parameters but **NO device/IMEI selection**.

---

## 5. Entity Creation and Registration

### Entity Types and Counts

#### Writable Sensors
**File**: `sensor.py` (Lines 51-52)
- **Count**: 8 entities from `WRITABLE_SENSORS`
- **Examples**: Last trip distance, duration, battery consumption
- **Storage**: Registered in `hass.data[DOMAIN]["sensors"]` (Line 231)

#### Template Sensors
**File**: `sensor.py` (Lines 67-81)
- **Count**: 7 base + variations
- **Examples**: Status display, estimated range, battery per km
- **Dependency**: Listen to MQTT sensors (hard-coded entity IDs)

#### Trigger Sensors
**File**: `sensor.py` (Lines 83-84)
- **Count**: 4 entities
- **Examples**: Trip status, active trip duration
- **Triggers**: State changes and time patterns

#### Energy Cost Sensors
**File**: `sensor.py` (Lines 86-92)
- **Count**: 4 entities (daily, weekly, monthly, yearly)
- **Dependency**: Tariff sensor from config

#### Battery Health Sensors
**File**: `sensor.py` (Lines 94-95)
- **Count**: 4 entities
- **Examples**: Cell imbalance, SOC calculated, charge cycles

#### Usage Statistics Sensors
**File**: `sensor.py` (Lines 97-130)
- **Count**: 3 entities
- **Examples**: Distance per charge, cost per km

#### Number Entities
**File**: `number.py` (Lines 15-25)
- **Count**: 8 entities from `INPUT_NUMBERS`
- **Examples**: Pause duration, odometer readings, battery tracking

#### Datetime Entities
**File**: `datetime.py` (Lines 20-33)
- **Count**: 4 entities from `INPUT_DATETIMES`
- **Examples**: Start time, end time, last moving time

#### Switch Entities
**File**: `switch.py` (Lines 16-25)
- **Count**: 1 entity
- **Examples**: Stop trip now toggle

#### Utility Meter Sensors
**File**: `sensor.py` (Lines 134-135)
- **Count**: 4 entities (daily, weekly, monthly, yearly)
- **Dependency**: Source sensor: `sensor.scooter_energy_consumption`

### Total Entities Created
**~48 entities** (varies with config)

### Entity ID Generation Pattern
All entity IDs are **hard-coded** based on definitions:
```python
self.entity_id = f"sensor.{sensor_id}"  # sensor.py:172
self.entity_id = f"number.{number_id}"  # number.py:37
self.entity_id = f"datetime.{datetime_id}"  # datetime.py:45
```

**Critical Limitation**: No IMEI in entity_id, making multi-device impossible.

---

## 6. MQTT Data Flow

### Source: MQTT Configuration
**How MQTT sensors are created**:
1. User manually adds MQTT sensors to `configuration.yaml` (see `examples/silence.yaml`)
2. Sensors have hardcoded IMEI in topic path: `home/silence-server/{IMEI}/status/{sensor}`
3. Home Assistant creates entities with auto-generated names (no IMEI)
4. Integration reads these sensors via state lookup

### Data Flow Path
```
MQTT Topic 
  ↓
Home Assistant MQTT Sensor Entity
  ↓
Integration reads via hass.states.get("sensor.silence_scooter_speed")
  ↓
Template Sensors (jinja2 rendering)
  ↓
Helper/Automation functions
  ↓
Writable Sensors / History / Device Tracker
```

### Key State Lookups (Hard-Coded Entity IDs)
**File**: `automations.py` (Lines 273-311)

**Persistent Sensors** (Lines 1321-1394):
- `sensor.silence_scooter_battery_soc` → reads from MQTT
- `sensor.silence_scooter_odo` → reads from MQTT
- `sensor.silence_scooter_discharged_energy` → reads from MQTT
- `sensor.silence_scooter_regenerated_energy` → reads from MQTT

**Automation Sensors** (Lines 279-311):
- Speed: `sensor.silence_scooter_speed`
- Location: `sensor.silence_scooter_silence_latitude`, `sensor.silence_scooter_silence_longitude`
- Battery: `sensor.silence_scooter_battery_soc`
- Odometer: `sensor.silence_scooter_odo`
- Status: `sensor.silence_scooter_status`
- Last Update: `sensor.silence_scooter_last_update`

### State Change Event Listeners
**File**: `automations.py` (async_setup_automations function)

**Tracked Entities**:
- Line 435: Energy baseline initialization
- Line 996-998: Device tracker position updates
- Line 1378-1390: Persistent sensor updates
- Lines 500-1050: Trip start/stop automation logic

All listeners are **hardcoded**, not device-aware.

---

## 7. IMEI-Based Isolation Analysis

### Current Status: **NONE**

**What's missing**:
1. No IMEI configuration field in config flow
2. No IMEI stored in config_entry.data
3. No IMEI-based entity ID namespacing
4. No IMEI-based device info
5. No per-device state storage in hass.data
6. No per-device automation listeners
7. No multi-instance support check

### If IMEI Were Added
**Storage Path**:
```python
config_entry.data["imei"]  # Would be stored but not used
```

**Unused**:
- Device creation: `get_device_info()` would ignore it
- Entity creation: Entity IDs wouldn't include it
- State access: All hass.states.get() calls are hard-coded
- Automations: All listeners are hard-coded

---

## 8. Where IMEI-Based Separation Would Be Needed

### A. Configuration Layer (config_flow.py)

**Lines 13-31**: Add IMEI field
```python
CONF_IMEI = "imei"
```

**Lines 138-190**: Add IMEI selector to user step
```python
vol.Required(CONF_IMEI): selector.TextSelector(...)
```

**Lines 74-110**: Validate IMEI format in validate_input()

### B. Constants Layer (const.py)

**Lines 1-47**: Add IMEI-related constants
```python
CONF_IMEI = "imei"
```

### C. Device Info Layer (helpers.py)

**Lines 15-22**: Make device info IMEI-aware
```python
def get_device_info(imei: str = None) -> DeviceInfo:
    if not imei:
        imei = "UNKNOWN"
    return DeviceInfo(
        identifiers={("silence_scooter", imei)},
        name=f"Silence Scooter ({imei})",
        ...
    )
```

**All callers need updating**:
- sensor.py (2 locations)
- switch.py (1 location)

### D. Entity ID Generation Layer

**sensor.py (Lines 172, 219, 313, 360)**:
```python
# Current:
self.entity_id = f"sensor.{sensor_id}"

# Needed:
def get_entity_id(sensor_id: str, imei: str) -> str:
    if imei:
        return f"sensor.{sensor_id}_{imei}"
    return f"sensor.{sensor_id}"
```

All entity classes need IMEI parameter:
- ScooterTemplateSensor
- ScooterWritableSensor
- ScooterTriggerSensor
- ScooterTripsSensor
- ScooterDefaultTariffSensor
- ScooterUtilityMeterSensor

### E. Entity Platform Setup (sensor.py, number.py, etc.)

**Lines 43-139 in sensor.py**: Pass IMEI to entity constructors
```python
async def async_setup_entry(hass, config_entry, async_add_entities):
    imei = config_entry.data.get(CONF_IMEI)
    for sensor_id, config in WRITABLE_SENSORS.items():
        entities.append(ScooterWritableSensor(hass, sensor_id, config, imei))
```

### F. Data Storage Layer (__init__.py)

**Lines 20-24**: Organize by IMEI
```python
hass.data[DOMAIN] = {}
hass.data[DOMAIN][entry.entry_id] = {
    "imei": entry.data.get(CONF_IMEI),
    "sensors": {},
    "config": entry.data,
}
```

### G. State Access Layer (automations.py)

**All hass.states.get() calls** (hundreds in automations.py):
```python
# Current:
speed = hass.states.get("sensor.silence_scooter_speed")

# Needed:
speed = hass.states.get(self._get_entity_id("silence_scooter_speed"))

def _get_entity_id(self, sensor_id: str, imei: str) -> str:
    return f"sensor.{sensor_id}_{imei}" if imei else f"sensor.{sensor_id}"
```

**Affected locations**:
- Lines 279-311: Entity ID constants
- Lines 370-1058: All automation triggers and handlers
- Lines 1321-1394: Persistent sensor updates

### H. Automation Setup (automations.py)

**Lines 332-1058**: async_setup_automations()

Need to:
1. Accept IMEI parameter
2. Pass to all listener functions
3. Update all state lookups
4. Update device tracker ID
5. Create separate listener sets per IMEI

**Key functions affected**:
- handle_energy_baseline_init (Line 375)
- handle_tracker_dernier_mouvement (Line 443)
- handle_update_tracker (Line 955)
- watchdog_check_trip_end (Line 1004)
- All state change handlers

### I. Persistent Sensor Updates (automations.py)

**Lines 1321-1394**: setup_persistent_sensors_update()

**Current issue**:
```python
async_track_state_change_event(
    hass, ["sensor.silence_scooter_battery_soc"], update_battery_display
)
```

**Needed**:
```python
async_track_state_change_event(
    hass, 
    [f"sensor.silence_scooter_battery_soc_{imei}"],
    update_battery_display
)
```

### J. Definition Layer (definitions.py)

**Not directly affected**, but sensor references in templates would need updates:
- Lines 265-310: Energy consumption trigger sensor template
- Lines 313-438: Template sensors (especially those with sensor lookups)
- Lines 440-481: Energy cost sensors
- Lines 483-559: Battery health sensors
- Lines 561-610: Usage statistics sensors

### K. Services (__init__.py)

**Lines 45-61**: reset_tracked_counters service
```python
# Current:
entity_id: "number.scooter_tracked_distance"

# Needed:
entity_id: f"number.scooter_tracked_distance_{imei}"
```

**Lines 64-163**: restore_energy_costs service
```python
# Current:
for entity_id in ["sensor.scooter_energy_consumption_daily", ...]:

# Needed:
entity_ids = [f"sensor.scooter_energy_consumption_daily_{imei}", ...]
```

---

## 9. Summary of Changes Required for Multi-Device Support

### Total Files to Modify
1. **config_flow.py** - Add IMEI config field
2. **const.py** - Add IMEI constant
3. **helpers.py** - Make device info IMEI-aware
4. **__init__.py** - Pass IMEI to platforms, update services
5. **sensor.py** - Add IMEI to all entity classes (8 classes)
6. **number.py** - Add IMEI support (1 class)
7. **datetime.py** - Add IMEI support (1 class)
8. **switch.py** - Add IMEI support (1 class)
9. **automations.py** - Update all state lookups (~50+ changes)
10. **definitions.py** - Update templates with IMEI-aware lookups (minor)
11. **examples/silence.yaml** - Update topic examples
12. **manifest.json** - Possible version bump
13. **strings.json** - Add IMEI description to config flow

### Complexity Analysis
- **High Complexity**: automations.py (pervasive hard-coded entity IDs)
- **Medium Complexity**: Entity classes (sensor.py, number.py, datetime.py, switch.py)
- **Low Complexity**: Configuration and helpers

### Estimated Impact
- ~500+ lines of code changes
- ~100+ entity ID references to update
- Full regression testing required
- Backward compatibility consideration (single-device vs multi-device)

---

## 10. Key Code Locations Reference

### Configuration
- Config Flow: `/custom_components/silencescooter/config_flow.py:113-196`
- Constants: `/custom_components/silencescooter/const.py:1-47`

### Setup & Initialization
- Entry Setup: `/custom_components/silencescooter/__init__.py:15-171`
- Platform Setups: 
  - Sensor: `/custom_components/silencescooter/sensor.py:43-139`
  - Number: `/custom_components/silencescooter/number.py:15-25`
  - DateTime: `/custom_components/silencescooter/datetime.py:20-33`
  - Switch: `/custom_components/silencescooter/switch.py:16-25`

### Device Definition
- Device Info: `/custom_components/silencescooter/helpers.py:15-22`

### Data Flow & MQTT
- Persistent Sensor Updates: `/custom_components/silencescooter/automations.py:1321-1394`
- Energy Baseline Init: `/custom_components/silencescooter/automations.py:370-437`
- Device Tracker Update: `/custom_components/silencescooter/automations.py:950-998`

### Automation Logic
- Trip Detection: `/custom_components/silencescooter/automations.py:332-1058`
- Trip Stop Logic: `/custom_components/silencescooter/automations.py:1070-1320`

### Definitions
- Entities Definitions: `/custom_components/silencescooter/definitions.py:1-632`
- Writable Sensors: `/custom_components/silencescooter/definitions.py:2-52`
- Template Sensors: `/custom_components/silencescooter/definitions.py:313-438`

### MQTT Configuration Example
- Single Device Config: `/examples/silence.yaml:1-384`

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Home Assistant                           │
│                                                               │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ MQTT Sensors (configured in configuration.yaml)     │  │
│  │                                                        │  │
│  │ home/silence-server/IMEI/status/speed → sensor.silence_scooter_speed
│  │ home/silence-server/IMEI/status/odo → sensor.silence_scooter_odo
│  │ home/silence-server/IMEI/status/battery → sensor.silence_scooter_battery_soc
│  │ ... (50+ sensors)                                     │  │
│  └───────────────────────────────────────────────────────┘  │
│                            ↓                                  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │   Silence Scooter Integration                         │  │
│  │                                                        │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │ Config Entry: silencescooter                    │  │  │
│  │  │ - tariff_sensor                                │  │  │
│  │  │ - confirmation_delay                           │  │  │
│  │  │ - pause_max_duration                           │  │  │
│  │  │ - watchdog_delay                               │  │  │
│  │  │ - use_tracked_distance                         │  │  │
│  │  │ - outdoor_temp_source / entity               │  │  │
│  │  │ [MISSING: IMEI]                               │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  │                      ↓                                  │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │ Entry Setup (__init__.py)                      │  │  │
│  │  │ - Storage: hass.data[DOMAIN]                   │  │  │
│  │  │ - Load platforms                               │  │  │
│  │  │ - Register services                            │  │  │
│  │  │ - Setup automations                            │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  │                      ↓                                  │  │
│  │  ┌───────────────────────────────────────────────┐    │  │
│  │  │ Platform Entities                             │    │  │
│  │  ├───────────────────────────────────────────────┤    │  │
│  │  │ SENSORS (48 total)                            │    │  │
│  │  │ - Writable Sensors (8): trip data             │    │  │
│  │  │ - Template Sensors (7): calculated values     │    │  │
│  │  │ - Trigger Sensors (4): state-based           │    │  │
│  │  │ - Energy Cost Sensors (4): tariff-based      │    │  │
│  │  │ - Battery Health Sensors (4): analysis       │    │  │
│  │  │ - Usage Statistics (3): metrics              │    │  │
│  │  │ - Utility Meters (4): per-cycle tracking     │    │  │
│  │  │ - Trips Sensor (1): history                  │    │  │
│  │  │ - Default Tariff (1): fallback               │    │  │
│  │  │                                               │    │  │
│  │  │ NUMBERS (8 total)                             │    │  │
│  │  │ - Pause duration, odometer, battery tracking  │    │  │
│  │  │                                               │    │  │
│  │  │ DATETIMES (4 total)                           │    │  │
│  │  │ - Start time, end time, last moving time     │    │  │
│  │  │                                               │    │  │
│  │  │ SWITCHES (1 total)                            │    │  │
│  │  │ - Stop trip now                               │    │  │
│  │  └───────────────────────────────────────────────┘    │  │
│  │                      ↓                                  │  │
│  │  ┌───────────────────────────────────────────────┐    │  │
│  │  │ Automations (automations.py)                  │    │  │
│  │  │                                               │    │  │
│  │  │ 0. Energy baseline initialization             │    │  │
│  │  │ 1. Track last movement (on→off)              │    │  │
│  │  │ 2. Trip status trigger                        │    │  │
│  │  │ 3. Stop timer if scooter restarts            │    │  │
│  │  │ 4. Stop trip via switch                       │    │  │
│  │  │ 5. Last trip start (auto-trip detection)     │    │  │
│  │  │ 6. Update max speed tracking                  │    │  │
│  │  │ 7. Update device tracker position            │    │  │
│  │  │ 8. Watchdog for offline detection            │    │  │
│  │  │                                               │    │  │
│  │  │ State Change Listeners (hard-coded entity IDs)│   │  │
│  │  │ - Watches specific sensors for triggers      │    │  │
│  │  │ - Updates helper entities                    │    │  │
│  │  │ - Calls trip detection logic                 │    │  │
│  │  └───────────────────────────────────────────────┘    │  │
│  │                      ↓                                  │  │
│  │  ┌───────────────────────────────────────────────┐    │  │
│  │  │ Helper Functions (helpers.py, automations.py)│    │  │
│  │  │                                               │    │  │
│  │  │ - Trip detection and logging                 │    │  │
│  │  │ - Distance/speed/battery calculation         │    │  │
│  │  │ - History recording                          │    │  │
│  │  │ - Device info generation                     │    │  │
│  │  │ - State value extraction                     │    │  │
│  │  │ - Services: reset counters, restore costs    │    │  │
│  │  └───────────────────────────────────────────────┘    │  │
│  │                                                        │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Conclusion

The Silence Scooter integration is a well-structured single-device implementation with clean separation of concerns. However, **adding multi-device support requires significant architectural changes**, primarily in:

1. **Configuration**: Add IMEI field to config flow
2. **Entity Naming**: Include IMEI in entity IDs
3. **Device Info**: Make device identifier IMEI-aware
4. **State Access**: Update 100+ hard-coded entity ID references in automations
5. **Data Storage**: Organize per-IMEI in hass.data

The most challenging aspect is the **automations.py file**, which contains pervasive hard-coded entity ID references that would all need to become dynamic and IMEI-aware.

A gradual migration strategy could:
1. Keep current single-device behavior if no IMEI provided
2. Add optional IMEI support
3. Create separate entity namespaces per IMEI
4. Maintain backward compatibility
