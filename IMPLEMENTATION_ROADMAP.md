# Multi-Device Support Implementation Roadmap

## Quick Reference: Critical Changes for IMEI-Based Isolation

### Phase 1: Configuration & Constants (Low Risk)

#### 1.1 Update Constants
**File**: `/custom_components/silencescooter/const.py`
```python
# Add after line 31:
CONF_IMEI = "imei"
DEFAULT_IMEI = ""
```

#### 1.2 Config Flow
**File**: `/custom_components/silencescooter/config_flow.py`

**Changes needed**:
- Remove `single_instance_allowed` check (Line 122-123) for multi-device support
- Add IMEI field to user step (after line 138):
```python
vol.Required(CONF_IMEI): selector.TextSelector(
    selector.TextSelectorConfig(
        placeholder="YOUR_SCOOTER_IMEI"
    )
),
```
- Add IMEI validation in `validate_input()` (after line 110):
```python
imei = data.get(CONF_IMEI, "")
if not imei or imei.strip() == "":
    errors[CONF_IMEI] = "imei_required"
if not re.match(r'^\d{15}$', imei):  # IMEI format: 15 digits
    errors[CONF_IMEI] = "imei_invalid_format"
```

---

### Phase 2: Device Info & Entity Naming (Medium Risk)

#### 2.1 Update Device Info Function
**File**: `/custom_components/silencescooter/helpers.py`

**Lines 15-22 - Replace with**:
```python
def get_device_info(imei: str = None) -> DeviceInfo:
    """Return device info for Silence Scooter.
    
    Args:
        imei: IMEI of the scooter for multi-device support
    """
    if imei:
        name = f"Silence Scooter ({imei})"
        identifier = imei
    else:
        name = "Silence Scooter"
        identifier = "Silence Scooter"
    
    return DeviceInfo(
        identifiers={("silence_scooter", identifier)},
        name=name,
        manufacturer="Seat",
        model="Mo",
    )
```

#### 2.2 Create Entity ID Helper
**File**: `/custom_components/silencescooter/helpers.py`

**Add after get_device_info()**:
```python
def get_entity_id(base_id: str, imei: str = None) -> str:
    """Generate entity ID with optional IMEI suffix.
    
    Args:
        base_id: Base entity ID without prefix (e.g., "scooter_speed")
        imei: Optional IMEI for multi-device support
    
    Returns:
        Full entity ID (e.g., "sensor.scooter_speed_869123456789012")
    """
    if imei:
        return f"{base_id}_{imei}"
    return base_id
```

---

### Phase 3: Entity Classes (Medium-High Risk)

#### 3.1 Update All Sensor Classes
**File**: `/custom_components/silencescooter/sensor.py`

**Pattern to apply to all entity classes**:

Before:
```python
class ScooterTemplateSensor(SensorEntity, RestoreEntity):
    def __init__(self, hass: HomeAssistant, sensor_id: str, config: dict) -> None:
        self._attr_unique_id = f"{DOMAIN}_{sensor_id}"
        self.entity_id = f"sensor.{sensor_id}"
        self._attr_device_info = get_device_info()
```

After:
```python
class ScooterTemplateSensor(SensorEntity, RestoreEntity):
    def __init__(self, hass: HomeAssistant, sensor_id: str, config: dict, imei: str = None) -> None:
        self._imei = imei
        unique_suffix = f"_{imei}" if imei else ""
        self._attr_unique_id = f"{DOMAIN}_{sensor_id}{unique_suffix}"
        self.entity_id = f"sensor.{sensor_id}{unique_suffix}"
        self._attr_device_info = get_device_info(imei)
```

**Affected classes**:
- ScooterTemplateSensor (Line 164)
- ScooterWritableSensor (Line 207)
- ScooterTriggerSensor (Line 256)
- ScooterTripsSensor (Line 306)
- ScooterDefaultTariffSensor (Line 142)
- ScooterUtilityMeterSensor (Line 352)

#### 3.2 Update async_setup_entry() in sensor.py
**Lines 43-139 - Update all entity instantiations**:

Before:
```python
entities.append(ScooterWritableSensor(hass, sensor_id, config))
```

After:
```python
imei = config_entry.data.get(CONF_IMEI)
entities.append(ScooterWritableSensor(hass, sensor_id, config, imei))
```

#### 3.3 Update Number Class
**File**: `/custom_components/silencescooter/number.py`

Apply same pattern as sensors. Update:
- ScooterNumberEntity (Line 28)
- async_setup_entry() (Line 15-25)

#### 3.4 Update Datetime Class
**File**: `/custom_components/silencescooter/datetime.py`

Apply same pattern. Update:
- ScooterDateTimeEntity (Line 36)
- async_setup_entry() (Line 20-33)

#### 3.5 Update Switch Class
**File**: `/custom_components/silencescooter/switch.py`

Apply same pattern. Update:
- ScooterSwitchEntity (Line 28)
- async_setup_entry() (Line 16-25)

---

### Phase 4: Automations (HIGH RISK - Most Changes Here)

#### 4.1 Make async_setup_automations() IMEI-Aware
**File**: `/custom_components/silencescooter/automations.py`

**Line 332 - Update function signature**:
```python
async def async_setup_automations(hass: HomeAssistant, imei: str = None) -> bool:
    """Installe toutes les automatisations pour Silence Scooter
    
    Args:
        hass: Home Assistant instance
        imei: Optional IMEI for multi-device support
    """
```

#### 4.2 Create Entity ID Resolver
**File**: `/custom_components/silencescooter/automations.py`

**Add after function signature (Line 332)**:
```python
def _get_entity_id(sensor_name: str) -> str:
    """Get entity ID with IMEI suffix if applicable."""
    if imei:
        return f"sensor.{sensor_name}_{imei}"
    return f"sensor.{sensor_name}"

def _get_number_id(number_name: str) -> str:
    """Get number entity ID with IMEI suffix if applicable."""
    if imei:
        return f"number.{number_name}_{imei}"
    return f"number.{number_name}"

def _get_datetime_id(datetime_name: str) -> str:
    """Get datetime entity ID with IMEI suffix if applicable."""
    if imei:
        return f"datetime.{datetime_name}_{imei}"
    return f"datetime.{datetime_name}"

def _get_device_tracker_id() -> str:
    """Get device tracker ID with IMEI suffix if applicable."""
    if imei:
        return f"silence_scooter_{imei}"
    return "silence_scooter"
```

#### 4.3 Update Entity Constants
**Lines 273-311 - Replace hardcoded strings with resolver calls**:

Before:
```python
SENSOR_IS_MOVING = "sensor.scooter_is_moving"
SENSOR_TRIP_STATUS = "sensor.scooter_trip_status"
SENSOR_SCOOTER_SPEED = "sensor.silence_scooter_speed"
```

After:
```python
# These will be resolved dynamically in handlers using _get_entity_id()
# No longer hardcoded at module level
```

#### 4.4 Update All State Lookups
**Pattern for ALL hass.states.get() calls**:

Before:
```python
speed_state = hass.states.get("sensor.silence_scooter_speed")
odo_state = hass.states.get("sensor.silence_scooter_odo")
```

After:
```python
speed_state = hass.states.get(_get_entity_id("silence_scooter_speed"))
odo_state = hass.states.get(_get_entity_id("silence_scooter_odo"))
```

**Critical locations with high volume of changes**:
- Lines 370-437: Energy baseline init (3 state lookups)
- Lines 443-480: Track last movement (2 state lookups)
- Lines 500-600: Trip status trigger (6+ state lookups)
- Lines 850-950: Last start automation (15+ state lookups)
- Lines 959-994: Update tracker (5 state lookups)
- Lines 1004-1040: Watchdog (4 state lookups)
- Lines 1088-1180: Stop trip handler (20+ state lookups)
- Lines 1200-1320: Trip validation (15+ state lookups)
- Lines 1321-1394: Persistent sensors (8+ state lookups)

**Total state lookups to update**: ~80-100

#### 4.5 Update async_track_state_change_event() Calls
**Pattern for all listeners**:

Before:
```python
remove_energy = async_track_state_change_event(
    hass,
    ["sensor.silence_scooter_discharged_energy", "sensor.silence_scooter_regenerated_energy"],
    handle_energy
)
```

After:
```python
remove_energy = async_track_state_change_event(
    hass,
    [_get_entity_id("silence_scooter_discharged_energy"), 
     _get_entity_id("silence_scooter_regenerated_energy")],
    handle_energy
)
```

**Locations**:
- Line 435: Energy baseline (2 topics)
- Line 481: Trip status (1 topic)
- Line 996: Tracker update (3 topics)
- Line 1378: Persistent battery (1 topic)
- Line 1382: Persistent odo (1 topic)
- Line 1386: Persistent regeneration (2 topics)

#### 4.6 Update Device Tracker ID
**Lines 959-994 - Update _do_update_tracker()**:

Before:
```python
DEVICE_TRACKER_ID = "silence_scooter"
...
await hass.services.async_call(
    "device_tracker", "see",
    {"dev_id": DEVICE_TRACKER_ID, ...}
)
```

After:
```python
device_tracker_id = _get_device_tracker_id()
await hass.services.async_call(
    "device_tracker", "see",
    {"dev_id": device_tracker_id, ...}
)
```

#### 4.7 Update Services Calls
**Lines 45-163 in __init__.py**:

Update all service calls to use IMEI-aware entity IDs:

Before:
```python
entity_id: "number.scooter_tracked_distance"
```

After:
```python
entity_id: f"number.scooter_tracked_distance{_get_entity_suffix()}"
```

---

### Phase 5: Integration Setup (__init__.py)

#### 5.1 Update async_setup_entry()
**Lines 15-171 - Pass IMEI to all platforms and automations**:

```python
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Silence Scooter from a config entry."""
    _LOGGER.info("Setting up Silence Scooter integration")
    
    imei = entry.data.get(CONF_IMEI)
    _LOGGER.info("Setting up scooter: %s", imei or "default")

    try:
        # Initialize storage for this entry (organized by IMEI if provided)
        hass.data.setdefault(DOMAIN, {})
        storage_key = imei if imei else entry.entry_id
        hass.data[DOMAIN][entry.entry_id] = {
            "imei": imei,
            "sensors": {},
            "config": entry.data
        }
        
        # Load platforms - pass config_entry which contains IMEI
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        
        # Setup automations with IMEI
        from .automations import async_setup_automations, setup_persistent_sensors_update
        await async_setup_automations(hass, imei)
        await setup_persistent_sensors_update(hass, imei)
        
        # Rest of setup...
```

---

### Phase 6: Testing Checklist

- [ ] Single IMEI setup works (backward compatible)
- [ ] Multiple IMEIs each create separate entities
- [ ] Entity IDs include IMEI suffix
- [ ] Device info correctly identifies each IMEI
- [ ] Trip detection works independently per IMEI
- [ ] Device tracker updates correct device per IMEI
- [ ] Automations don't interfere between IMEIs
- [ ] Services work with IMEI-suffixed entities
- [ ] Configuration validation requires valid IMEI
- [ ] MQTT topics must include IMEI in path
- [ ] History is tracked per IMEI
- [ ] Energy calculations separate per IMEI

---

## File-by-File Checklist

- [ ] const.py: Add CONF_IMEI
- [ ] config_flow.py: Add IMEI field, remove single_instance check, validate IMEI
- [ ] helpers.py: Update get_device_info(), add get_entity_id()
- [ ] __init__.py: Pass IMEI to platforms and automations
- [ ] sensor.py: Update all 6 entity classes, async_setup_entry()
- [ ] number.py: Update ScooterNumberEntity, async_setup_entry()
- [ ] datetime.py: Update ScooterDateTimeEntity, async_setup_entry()
- [ ] switch.py: Update ScooterSwitchEntity, async_setup_entry()
- [ ] automations.py: Add entity ID resolver, update 80+ state lookups, 6 listeners
- [ ] definitions.py: Update template references (minor)
- [ ] strings.json: Add IMEI config description
- [ ] examples/silence.yaml: Document IMEI placeholder usage
- [ ] manifest.json: Version bump

---

## Risk Summary

**Low Risk**: Constants, Config, Helpers, Device Info
**Medium Risk**: Entity Classes, Definitions
**High Risk**: Automations (pervasive changes, many state lookups)

**Estimated Development Time**: 40-60 hours
**Estimated Testing Time**: 20-30 hours
**Estimated Total**: 60-90 hours

