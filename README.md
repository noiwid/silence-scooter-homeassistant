# Silence Scooter - Home Assistant Integration

[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)
[![hacs][hacsbadge]][hacs]

<p align="center">
  <img src="https://raw.githubusercontent.com/noiwid/silence-scooter-homeassistant/main/images/scooter.png" alt="Silence Scooter" width="400">
</p>

_Advanced Home Assistant integration for Silence/Seat electric scooters with comprehensive trip tracking, energy monitoring, and intelligent automation._

## 🛵 About

This custom integration transforms your Silence electric scooter into a fully integrated smart device within Home Assistant. Built on top of the [Silence Private Server](https://github.com/lorenzo-deluca/silence-private-server/) by Lorenzo Deluca, this integration provides:

**Compatible models:**
- 🛵 **Silence S01** (50cc and 125cc equivalent)
- 🛵 **SEAT MÓ eScooter 50** (rebadged Silence S01)
- 🛵 **SEAT MÓ eScooter 125** (rebadged Silence S01)

All models use the same Astra telemetry module and are fully compatible with this integration.

**Features:**

- **Automatic trip detection** with intelligent pause management
- **Detailed trip metrics** (distance, duration, speed, battery consumption)
- **Energy cost tracking** with utility meters (daily/weekly/monthly/yearly)
- **Trip history** with persistent storage
- **Battery health monitoring** and efficiency statistics
- **Advanced automations** for trip start/stop detection
- **Device tracker** with GPS location updates

## ✨ Key Features

### 📊 Trip Tracking
- Automatic trip start/stop detection
- Pause detection with configurable tolerance (default: 5 minutes)
- Real-time metrics: distance, duration, average/max speed
- Battery consumption tracking per trip
- Outdoor temperature logging

### ⚡ Energy Monitoring
- Total energy consumption tracking
- Utility meters for different periods
- Cost calculation with configurable electricity tariff
- Efficiency metrics (Wh/km)
- Battery health indicators

### 📍 Location & Tracking
- GPS device tracker integration
- Real-time position updates
- Trip history with start/end locations

### 🔧 Customization
- Configurable via UI (Config Flow)
- Adjustable detection delays
- Custom tariff sensor support
- Optional tracked distance mode

## 📸 Dashboard Preview

Get a complete overview of your scooter status, trip statistics, and battery health:

<p align="center">
  <img src="https://raw.githubusercontent.com/noiwid/silence-scooter-homeassistant/main/images/dashboard-overview.png" alt="Dashboard Overview" width="800">
</p>

**Expanded battery health diagnostics:**

<p align="center">
  <img src="https://raw.githubusercontent.com/noiwid/silence-scooter-homeassistant/main/images/dashboard-details.png" alt="Dashboard Details" width="800">
</p>

The example dashboard includes:
- 🎛️ Scooter controls (ON/OFF, Flash, Open Seat)
- 🔋 Real-time battery level and autonomy
- 📊 Current trip metrics and statistics
- 🗺️ GPS tracking with route history
- 💶 Energy consumption and cost tracking
- 🔧 Battery health diagnostics with cell voltages
- 📜 Trip history table with detailed metrics

## 📋 Prerequisites

Before installing this integration, you need:

1. **Compatible Scooter** - Silence S01 or SEAT MÓ (50/125) with Astra telemetry module
2. **Silence Private Server** - Follow the setup guide at [lorenzo-deluca/silence-private-server](https://github.com/lorenzo-deluca/silence-private-server/)
3. **MQTT Broker** - Already configured and running in Home Assistant
4. **Home Assistant 2024.11.0+** - Required for timer management features

## 🚀 Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Go to "Integrations"
3. Click the three dots menu (top right) and select "Custom repositories"
4. Add this repository URL: `https://github.com/noiwid/silence-scooter-homeassistant`
5. Select category: "Integration"
6. Click "Install"
7. Restart Home Assistant

### Manual Installation

1. Download the latest release from the [Releases page](https://github.com/noiwid/silence-scooter-homeassistant/releases)
2. Copy the `custom_components/silencescooter` folder to your Home Assistant's `custom_components` directory
3. Restart Home Assistant

## ⚙️ Configuration

### Step 1: MQTT Base Configuration

First, configure the basic MQTT sensors from the Silence Private Server. Use the example file `examples/silence.yaml`:

```yaml
# Replace YOUR_SCOOTER_IMEI with your actual IMEI
mqtt:
  button:
    - name: "Command ON"
      unique_id: silence_scooter_command_on
      command_topic: "home/silence-server/YOUR_SCOOTER_IMEI/command/TURN_ON_SCOOTER"
      device:
        identifiers: "Silence Scooter"
        manufacturer: "Seat"
        model: "Mo"
    # ... (see examples/silence.yaml for full configuration)
```

### Step 2: Add the Integration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Silence Scooter"
3. Configure the integration parameters:

#### Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| **Tariff Sensor** | `sensor.tarif_base_ttc` | (Optional) Electricity tariff sensor for cost calculation. Can be any sensor providing EUR/kWh rate. |
| **Outdoor Temperature Source** | Scooter sensor | Choose between scooter's built-in ambient temperature sensor or an external weather sensor for trip history. |
| **External Temperature Sensor** | - | (Required if external source selected) Select a temperature sensor entity from your Home Assistant installation. |
| **Confirmation Delay** | 120 seconds | Anti-bounce delay before confirming trip stop. Prevents false stops from brief signal loss or sensor oscillations. |
| **Pause Max Duration** | 5 minutes | Maximum pause duration before ending trip. Pauses shorter than this (e.g., quick errands) keep the trip active. |
| **Watchdog Delay** | 5 minutes | Offline detection timeout. Automatically ends trip if scooter doesn't communicate for this duration (e.g., parked in underground garage without signal). |
| **Use Tracked Distance** | `false` | When enabled, uses internal tracked distance instead of ODO delta. Useful if ODO sensor has issues. |

**💡 Tip:** The Watchdog Delay ensures trips are automatically closed even when the scooter loses connectivity (garage, tunnel, etc.), preventing "stuck" trips that never end.

### Step 3: Optional Dashboard

Import the example Lovelace dashboard for a ready-to-use interface:
- **French version**: `examples/lovelace_silence.yaml`
- **English version**: `examples/lovelace_silence_en.yaml`

**Dashboard Image Setup (condensed)**
1. Create the folder: `\`/config/www/silence/``
2. Copy the images:
   * `images/scooter.png` → `\`/config/www/silence/scooter.png``
   * `images/Last_ride.png` → `\`/config/www/silence/Last_ride.png``
3. Reference them in the dashboard:
   * `\`/local/silence/scooter.png``
   * `\`/local/silence/Last_ride.png``
> Reminder: `\`/local``maps to``/config/www``.

**Note:** The `scooter.png` file is included in this repository (`images/` folder) for display in this README and as a reference image for your dashboard.

For detailed installation instructions, see [INSTALLATION.md](INSTALLATION.md).

See [CONFIGURATION.md](docs/CONFIGURATION.md) for detailed configuration options.

## 🔄 Multi-Device Support (v2.0+)

This integration supports **multiple Silence S01 scooters** using a multi-instance approach.

### Quick Start

1. **Configure Silence Private Server** with multiple IMEIs:
   ```json
   {
     "IMEI_List": ["869123456789012", "869987654321098"],
     "BasePort": 19000
   }
   ```
   See: [lorenzo-deluca/silence-private-server#8](https://github.com/lorenzo-deluca/silence-private-server/pull/8)

2. **Add Integration** once per scooter:
   - Go to **Settings → Devices & Services → Add Integration**
   - Search for "Silence Scooter"
   - Enter your scooter's **IMEI** (14-15 digits)
   - Configure trip detection settings
   - Click Submit

3. **Automatic MQTT Discovery** (v2.0+):
   - All sensors and buttons are automatically discovered via MQTT
   - No manual MQTT configuration needed!
   - Just ensure your MQTT broker is connected

4. **Repeat** for each additional scooter

### Finding Your IMEI

Your scooter's IMEI can be found:
- On the scooter frame (near VIN plate)
- In your mobile app (Settings → Device Info)
- On original purchase documentation
- By checking Silence Private Server logs

### Migration from v1.x

**Breaking Change**: v2.0 requires an IMEI for all installations.

When you update:
1. You'll be prompted to enter your IMEI
2. Entity IDs will change (IMEI suffix added)
3. Automations referencing old entity IDs must be updated

**Entity ID Changes**:
- v1: `sensor.silence_scooter_speed`
- v2: `sensor.silence_scooter_speed_9012` (last 4 digits of IMEI)

**Migration Guide**:
1. Backup your Home Assistant configuration
2. Note your current automations using Silence entities
3. Update the integration
4. Enter your IMEI when prompted
5. Update automations with new entity IDs
6. Test thoroughly

See [MIGRATION_V1_TO_V2.md](MIGRATION_V1_TO_V2.md) for detailed migration instructions.

### MQTT Configuration

**Automatic (Recommended)**: MQTT Discovery publishes all sensor/button configs automatically when you add a scooter.

**Manual (Fallback)**: If MQTT Discovery doesn't work, see `examples/silence.yaml` for manual configuration templates.

### Services

#### `silencescooter.reset_tracked_counters`
Reset distance and battery counters for a specific scooter.

**Fields**:
- `device_id` (required): Select the scooter device from dropdown

**Example**:
```yaml
service: silencescooter.reset_tracked_counters
data:
  device_id: <select from UI>
```

### Limitations

- **Maximum scooters**: 5 recommended (performance considerations)
- **IMEI uniqueness**: Each instance must have a unique IMEI
- **MQTT broker**: Required for all scooter communication

### Troubleshooting

**Problem**: Sensors not appearing after adding scooter
- **Solution**: Check MQTT broker connection, verify IMEI in Private Server config

**Problem**: Duplicate entity IDs
- **Solution**: Remove old integration instance, clear entity registry

**Problem**: Migration failed
- **Solution**: Remove integration, reinstall fresh with IMEI

For more help, see: [Issues](https://github.com/noiwid/silence-scooter-homeassistant/issues)

## 📦 Dashboard Dependencies (HACS Frontend)

To use the example dashboard, install these HACS frontend integrations:

### Required
- [**card-mod**](https://github.com/thomasloven/lovelace-card-mod) - Card customization
- [**button-card**](https://github.com/custom-cards/button-card) - Custom buttons
- [**mini-graph-card**](https://github.com/kalkih/mini-graph-card) - Compact graphs
- [**vertical-stack-in-card**](https://github.com/ofekashery/vertical-stack-in-card) - Card layouts
- [**ha-map-card**](https://github.com/nathan-gs/ha-map-card) - Map card

### Optional (for advanced features)
- [**template-entity-row**](https://github.com/thomasloven/lovelace-template-entity-row) - Template rows
- [**fold-entity-row**](https://github.com/thomasloven/lovelace-fold-entity-row) - Collapsible rows
- [**stack-in-card**](https://github.com/custom-cards/stack-in-card) - Advanced stacking

> **Note about `ha-map-card`**
> There’s a known bug in `ha-map-card` **v1.12+** where using `history_start` as an **entity** draws a **duplicate history line**. Bug URL: https://github.com/nathan-gs/ha-map-card/issues/174  
> Until a fix lands, **pin the card to `v1.11.x` (e.g., `v1.11.0`)** in HACS (or use that tag for manual install).


## 📱 Entities Created

Once configured, the integration creates **39+ entities** organized into several categories:

### 📊 Sensors

#### Trip Tracking (Writable Sensors)
- `sensor.scooter_last_trip_distance` (km) - Last trip distance
- `sensor.scooter_last_trip_duration` (min) - Last trip duration
- `sensor.scooter_last_trip_avg_speed` (km/h) - Last trip average speed
- `sensor.scooter_last_trip_max_speed` (km/h) - Last trip maximum speed
- `sensor.scooter_last_trip_battery_consumption` (%) - Battery consumed during last trip

#### Scooter Status
- `sensor.scooter_battery_display` (%) - Current battery level (persistent)
- `sensor.scooter_odo_display` (km) - Odometer reading (persistent)
- `sensor.scooter_status_display` - Scooter status (Off/Starting/Ready/Moving/Charging)
- `sensor.scooter_battery_status` - Battery presence status
- `sensor.scooter_is_moving` - Real-time movement detection
- `sensor.scooter_trip_status` - Current trip status
- `sensor.scooter_end_time_relative` - Time since last trip

#### Energy & Efficiency
- `sensor.scooter_energy_consumption` (kWh) - Total energy consumed
- `sensor.scooter_energy_consumption_daily` (kWh) - Daily energy consumption
- `sensor.scooter_energy_consumption_weekly` (kWh) - Weekly energy consumption
- `sensor.scooter_energy_consumption_monthly` (kWh) - Monthly energy consumption
- `sensor.scooter_energy_consumption_yearly` (kWh) - Yearly energy consumption
- `sensor.scooter_energy_cost_daily` (€) - Daily charging cost
- `sensor.scooter_energy_cost_weekly` (€) - Weekly charging cost
- `sensor.scooter_energy_cost_monthly` (€) - Monthly charging cost
- `sensor.scooter_energy_cost_yearly` (€) - Yearly charging cost
- `sensor.scooter_battery_per_km` (%/km) - Battery consumption per kilometer
- `sensor.scooter_battery_percentage_regeneration` (%) - Regenerative braking efficiency
- `sensor.scooter_estimated_range` (km) - Estimated remaining range

#### Battery Health
- `sensor.scooter_battery_cell_imbalance` (mV) - Cell voltage imbalance
- `sensor.scooter_battery_soc_calculated` (%) - SOC calculated from voltage
- `sensor.scooter_battery_soc_deviation` (%) - Difference between displayed and calculated SOC
- `sensor.scooter_battery_charge_cycles` (cycles) - Cumulative charge cycles

#### Usage Statistics
- `sensor.scooter_distance_per_charge` (km) - Average distance per full charge
- `sensor.scooter_cost_per_km` (€/km) - Average cost per kilometer
- `sensor.scooter_average_trip_distance` (km) - Average trip distance
- `sensor.scooter_active_trip_duration` (min) - Duration of current active trip

#### Trip History
- `sensor.scooter_trips` - Total trip count with history attributes (last 10 trips)
- `sensor.scooter_start_time_iso` - Trip start time in ISO format
- `sensor.scooter_history_start` - History start time for map display

### 🔢 Numbers (Internal State)
- `number.scooter_odo_debut` (km) - Trip start odometer reading
- `number.scooter_odo_fin` (km) - Trip end odometer reading
- `number.scooter_battery_soc_debut` (%) - Trip start battery level
- `number.scooter_battery_soc_fin` (%) - Trip end battery level
- `number.scooter_pause_duration` (min) - Total pause duration during trip
- `number.scooter_tracked_distance` (km) - Manually tracked distance (alternative mode)
- `number.scooter_tracked_battery_used` (%) - Manually tracked battery (alternative mode)
- `number.scooter_energy_consumption_base` (kWh) - Baseline energy consumption

### 📅 DateTime
- `datetime.scooter_start_time` - Current/last trip start time
- `datetime.scooter_end_time` - Current/last trip end time
- `datetime.scooter_last_moving_time` - Last time scooter was moving
- `datetime.scooter_pause_start` - Current pause start time

### 🔘 Switch
- `switch.stop_trip_now` - Manual trip stop button (turn ON to stop current trip)

### 📍 Device Tracker
- `device_tracker.silence_scooter` - GPS location tracker with route history
### Quick Summary

| Category | Count | Description |
|----------|-------|-------------|
| **Numbers** | 11 | Trip metrics, odometer, battery tracking |
| **Sensors** | 23+ | Energy, costs, battery health, statistics |
| **DateTimes** | 4 | Trip timestamps and pause tracking |
| **Switch** | 1 | Manual trip stop control |

### Main Entities

**Trip Tracking:**
- `number.scooter_odo_debut` / `number.scooter_odo_fin` - Trip odometer start/end
- `number.scooter_battery_soc_debut` / `number.scooter_battery_soc_fin` - Battery level start/end
- `datetime.scooter_start_time` / `datetime.scooter_end_time` - Trip timestamps
- `sensor.scooter_last_trip_distance` - Last trip distance
- `sensor.scooter_last_trip_duration` - Last trip duration
- `sensor.scooter_last_trip_avg_speed` / `max_speed` - Speed statistics

**Energy & Costs:**
- `sensor.scooter_energy_consumption` - Total energy consumption (kWh)
- `sensor.scooter_energy_consumption_daily/weekly/monthly/yearly` - Utility meters
- `sensor.scooter_energy_cost_daily/weekly/monthly/yearly` - Energy cost sensors

**Battery Health:**
- `sensor.scooter_battery_cell_imbalance` - Cell voltage difference (mV)
- `sensor.scooter_battery_soc_calculated` - Voltage-based SOC
- `sensor.scooter_battery_charge_cycles` - Total charge cycles

**Controls:**
- `switch.stop_trip_now` - Manual trip stop button

> **📖 See the complete list:** [ENTITIES.md](docs/ENTITIES.md)

## 🔄 How It Works

### Trip Detection Logic

The integration uses a sophisticated multi-layer detection system with built-in resilience for connectivity issues:

#### 1. **Trip Start** 🚀
- Triggered when scooter status changes to "ready" (3) or "moving" (4)
- Records start time, odometer, and battery level

#### 2. **Pause Detection** ⏸️
- **Anti-bounce protection** (Confirmation Delay: 2 min):
  - Filters sensor oscillations and brief signal losses
  - Prevents false stops at traffic lights
  - Only confirmed stops trigger pause mode

- **Pause tolerance** (Max Duration: 5 min):
  - Starts timer when stop is confirmed
  - Quick errands (< 5 min) keep trip active
  - Pause duration is tracked and logged
  - Trip resumes automatically if you restart

#### 3. **Trip End** 🛑

**Automatic End (3 scenarios):**

a) **Normal stop**: Timer expires after 5 minutes of confirmed pause
   - ✅ Use case: Arrived at destination, scooter turned off

b) **Manual stop**: Via `switch.stop_trip_now` button
   - ✅ Use case: Force trip end without waiting

c) **Watchdog offline protection** ⚠️ (Critical feature)
   - Monitors last communication timestamp
   - Triggers if no MQTT message received for 5+ minutes
   - ✅ Use case: Scooter parked in underground garage without signal
   - ✅ Use case: Scooter in tunnel or area with poor connectivity
   - **Prevents "stuck trips"** that would otherwise remain open indefinitely

**Why the Watchdog is essential:**
Without it, if you park your scooter in a location without network coverage (basement, parking garage, elevator), the trip would never end automatically since the integration wouldn't receive the "scooter off" status. The watchdog detects the communication timeout and safely closes the trip based on the last known movement time.

#### 4. **Network Resilience** 📶

The system handles temporary connectivity issues:
- **Short disconnections** (< 2 min): Ignored (anti-bounce)
- **Medium disconnections** (2-5 min): Enters pause mode, trip continues if reconnects
- **Long disconnections** (> 5 min): Watchdog triggers trip end

### Data Flow

```
Scooter (Astra Module)
    ↓ MQTT
Silence Private Server
    ↓ MQTT Topics
Home Assistant MQTT Sensors (silence.yaml)
    ↓ State Changes
Silence Scooter Integration (Python)
    ↓ Automations
Trip Tracking & Statistics
    ↓ Storage
history.json + HA State Machine
```

## 📝 Trip History Data

### History JSON File

All trips are stored in `/config/custom_components/silencescooter/data/history.json` with the following structure:

```json
[
  {
    "start_time": "2025-01-15T14:23:45+01:00",
    "end_time": "2025-01-15T14:48:12+01:00",
    "duration": "22",
    "distance": "8.5",
    "avg_speed": "23.2",
    "max_speed": "45.0",
    "battery": "18.5",
    "outdoor_temp": "12.0",
    "efficiency_wh_km": "121.8"
  },
  {
    "start_time": "2025-01-15T09:15:30+01:00",
    "end_time": "2025-01-15T09:27:45+01:00",
    "duration": "12",
    "distance": "3.2",
    "avg_speed": "16.0",
    "max_speed": "35.0",
    "battery": "8.2",
    "outdoor_temp": "8.5",
    "efficiency_wh_km": "143.8"
  }
]
```

### Field Descriptions

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| `start_time` | ISO 8601 | - | Trip start timestamp with timezone |
| `end_time` | ISO 8601 | - | Trip end timestamp with timezone |
| `duration` | String | minutes | Net trip duration (excluding pauses) |
| `distance` | String | km | Distance traveled (ODO end - ODO start) |
| `avg_speed` | String | km/h | Average speed (distance / duration * 60) |
| `max_speed` | String | km/h | Maximum speed recorded during trip |
| `battery` | String | % | Battery consumed (SOC start - SOC end) |
| `outdoor_temp` | String | °C | Outdoor temperature (from scooter or external sensor) |
| `efficiency_wh_km` | String | Wh/km | Energy efficiency: (battery% / 100 * 5600 Wh) / distance |

### Accessing Trip History

The `sensor.scooter_trips` entity provides:
- **State**: Total number of trips
- **Attributes**: Array of the last 10 trips in the `history` attribute

Example automation to access trip data:

```yaml
automation:
  - alias: "Notify on trip completion"
    trigger:
      - platform: state
        entity_id: sensor.scooter_trips
    action:
      - service: notify.mobile_app
        data:
          message: >
            Trip completed: {{ state_attr('sensor.scooter_trips', 'history')[0].distance }}km
            in {{ state_attr('sensor.scooter_trips', 'history')[0].duration }}min
            ({{ state_attr('sensor.scooter_trips', 'history')[0].efficiency_wh_km }} Wh/km)
```

## 🐛 Troubleshooting

### Integration not loading
- Check logs: **Settings** → **System** → **Logs**
- Ensure Home Assistant version is 2024.11.0+
- Verify `silence.yaml` MQTT sensors are working

### Trip not starting
- Check `sensor.silence_scooter_status` value
- Verify MQTT broker connection
- Enable debug logging (see [DEBUGGING.md](docs/DEBUGGING.md))

### Timer not created
- Ensure Home Assistant 2024.11.0+
- Check logs for timer creation errors
- Timer is auto-created on integration setup

## 📚 Documentation

- [Installation Guide](INSTALLATION.md) - Step-by-step setup instructions
- [Configuration Options](docs/CONFIGURATION.md) - Detailed configuration parameters
- [Entity Reference](docs/ENTITIES.md) - **Complete list of all 39+ entities**
- [Trip History Structure](docs/HISTORY.md) - **Understanding the history.json file**
- [Debugging Guide](docs/DEBUGGING.md) - Troubleshooting and logging
- [FAQ](docs/FAQ.md) - Frequently asked questions

## 🙏 Credits

- **[Lorenzo De Luca](https://github.com/lorenzo-deluca/)** - Silence Private Server
- **[Andrea Gasparini](https://github.com/)** - Original Silence Private Server development
- Silence/Seat Scooter Community

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

This project is not affiliated with, endorsed by, or connected to Silence or Seat. Use at your own risk.

---

**Made with ❤️ for the Silence Scooter community**

[releases-shield]: https://img.shields.io/github/release/noiwid/silence-scooter-homeassistant.svg?style=for-the-badge
[releases]: https://github.com/noiwid/silence-scooter-homeassistant/releases
[license-shield]: https://img.shields.io/github/license/noiwid/silence-scooter-homeassistant.svg?style=for-the-badge
[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
