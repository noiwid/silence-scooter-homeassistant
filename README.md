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

Once configured, the integration creates the following entities:

### Numbers
- `number.scooter_odo_debut` / `number.scooter_odo_fin` - Trip odometer start/end
- `number.scooter_battery_soc_debut` / `number.scooter_battery_soc_fin` - Battery level start/end
- `number.scooter_last_trip_distance` - Last trip distance
- `number.scooter_last_trip_duration` - Last trip duration
- `number.scooter_last_trip_avg_speed` / `max_speed` - Speed statistics
- And more... (see [ENTITIES.md](docs/ENTITIES.md) for complete list)

### Sensors
- `sensor.scooter_energy_consumption` - Total energy consumption
- `sensor.scooter_energy_consumption_daily/weekly/monthly/yearly` - Utility meters
- `sensor.scooter_energy_cost_*` - Energy cost sensors
- `sensor.scooter_trips_history` - Trip history with JSON attributes
- `sensor.scooter_battery_health` - Battery health metrics
- And more...

### DateTime
- `datetime.scooter_start_time` / `end_time` - Trip timestamps
- `datetime.scooter_last_moving_time` - Last movement timestamp
- `datetime.scooter_pause_start` - Pause detection

### Switch
- `switch.stop_trip_now` - Manual trip stop button

### Timer
- `timer.scooter_stop_trip_tolerance` - Pause tolerance timer (auto-created)

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

- [Installation Guide](docs/INSTALLATION.md)
- [Configuration Options](docs/CONFIGURATION.md)
- [Entity Reference](docs/ENTITIES.md)
- [Debugging Guide](docs/DEBUGGING.md)
- [FAQ](docs/FAQ.md)

## 🙏 Credits

- **[Lorenzo Deluca](https://github.com/lorenzo-deluca/)** - Silence Private Server
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
