# Installation Guide

This guide will help you install and configure the Silence Scooter integration for Home Assistant.

## Prerequisites

Before installing this integration, ensure you have:

1. **Home Assistant** installed and running (version 2024.11.0 or later)
2. **Silence Private Server** by Lorenzo Deluca set up and receiving data from your scooter
3. **MQTT** integration configured in Home Assistant and connected to the same MQTT broker as your Silence Private Server
4. **HACS** (Home Assistant Community Store) installed (recommended method)

## Method 1: Installation via HACS (Recommended)

1. Open Home Assistant
2. Go to **HACS** → **Integrations**
3. Click the **three dots menu** (⋮) in the top right corner
4. Select **"Custom repositories"**
5. Add the following information:
   - **Repository**: `https://github.com/noiwid/silence-scooter-homeassistant`
   - **Category**: `Integration`
6. Click **"Add"**
7. Search for **"Silence Scooter"** in HACS
8. Click **"Download"**
9. **Restart Home Assistant**

## Method 2: Manual Installation

1. Download the latest release from the [GitHub releases page](https://github.com/noiwid/silence-scooter-homeassistant/releases)
2. Extract the archive
3. Copy the `custom_components/silencescooter` folder to your Home Assistant's `custom_components` directory:
   ```
   /config/custom_components/silencescooter/
   ```
4. **Restart Home Assistant**

## Configuration

### Step 1: Add the Integration

1. Go to **Settings** → **Devices & Services**
2. Click **"+ Add Integration"**
3. Search for **"Silence Scooter"**
4. Click on it to start the configuration

### Step 2: Configure Parameters

The integration will ask you to configure the following parameters:

| Parameter | Description | Default Value |
|-----------|-------------|---------------|
| **Electricity rate (€/kWh)** | Your electricity cost per kWh for energy cost calculations | `0.25` |
| **Stop confirmation delay (seconds)** | Time to wait before confirming the scooter has stopped (anti-bounce) | `120` |
| **Maximum pause duration (minutes)** | Maximum pause time before automatically ending a trip | `5` |
| **Watchdog period (minutes)** | Frequency of connectivity checks | `5` |

### Step 3: Verify Installation

After adding the integration, you should see:

1. A new device called **"Silence Scooter"** in **Devices & Services**
2. Multiple entities created:
   - Sensors (battery, speed, range, etc.)
   - Numbers (trip metrics, consumption, etc.)
   - Switches (stop trip button)
   - DateTime entities (trip start/end times)

## Setting Up MQTT Sensors

The integration requires MQTT sensors from your Silence Private Server. Add the following to your `configuration.yaml`:

```yaml
mqtt:
  sensor:
    # Basic sensors
    - name: "Silence Scooter Status"
      state_topic: "home/silence-server/YOUR_IMEI/status/STATUS"
      device_class: enum

    - name: "Silence Scooter Battery SOC"
      state_topic: "home/silence-server/YOUR_IMEI/status/SOC"
      unit_of_measurement: "%"
      device_class: battery

    - name: "Silence Scooter Speed"
      state_topic: "home/silence-server/YOUR_IMEI/status/SPEED"
      unit_of_measurement: "km/h"

    - name: "Silence Scooter ODO"
      state_topic: "home/silence-server/YOUR_IMEI/status/ODO"
      unit_of_measurement: "km"
      device_class: distance

    - name: "Silence Scooter Range"
      state_topic: "home/silence-server/YOUR_IMEI/status/RANGE"
      unit_of_measurement: "km"
      device_class: distance

    # Add other sensors as needed (see full list in README.md)
```

**Important**: Replace `YOUR_IMEI` with your scooter's IMEI number.

You can find a complete example in the [silence.yaml.bkp](silence.yaml.bkp) file in this repository.

## Dashboard Setup

The integration includes two ready-to-use Lovelace dashboard configurations:

- **French version**: `examples/lovelace_silence.yaml`
- **English version**: `examples/lovelace_silence_en.yaml`

### Required Custom Cards

To use the provided dashboards, install these custom cards via HACS:

- [button-card](https://github.com/custom-cards/button-card)
- [stack-in-card](https://github.com/custom-cards/stack-in-card)
- [vertical-stack-in-card](https://github.com/ofekashery/vertical-stack-in-card)
- [mini-graph-card](https://github.com/kalkih/mini-graph-card)
- [fold-entity-row](https://github.com/thomasloven/lovelace-fold-entity-row)
- [template-entity-row](https://github.com/thomasloven/lovelace-template-entity-row)
- [map-card](https://github.com/nathan-gs/ha-map-card) (for GPS tracking)

### Adding the Dashboard

1. Copy the content of `examples/lovelace_silence_en.yaml` (or the French version)
2. In Home Assistant, go to **Settings** → **Dashboards**
3. Click **"+ Add Dashboard"**
4. Choose **"New dashboard from scratch"**
5. Click the **⋮ menu** → **"Raw configuration editor"**
6. Paste the dashboard configuration
7. Click **"Save"**

### Adding Images

The dashboard uses two images:

1. **Scooter image**: Place your scooter image at `/config/www/silence/scooter.png`
2. **Last ride image**: Place the last ride header image at `/config/www/Last_ride.png`

Example images are available in the `images/` folder of this repository.

## Energy Dashboard Integration

To integrate with Home Assistant's Energy Dashboard:

1. Go to **Settings** → **Dashboards** → **Energy**
2. Click **"Add consumption"**
3. Select `sensor.scooter_energy_consumption`
4. Configure the electricity cost or use the integration's automatic cost calculation

## Troubleshooting

### Integration Not Appearing

1. Ensure you've restarted Home Assistant after installation
2. Check Home Assistant logs for errors:
   ```
   Settings → System → Logs
   ```
3. Enable debug logging by adding to `configuration.yaml`:
   ```yaml
   logger:
     default: info
     logs:
       custom_components.silencescooter: debug
   ```

### MQTT Sensors Not Updating

1. Verify your MQTT broker is running and accessible
2. Check that your Silence Private Server is publishing data
3. Use an MQTT client (like MQTT Explorer) to verify topics
4. Ensure the IMEI in your MQTT topics matches your scooter

### Trip Not Ending Automatically

1. Check the **watchdog period** setting (default: 5 minutes)
2. Verify the **stop confirmation delay** (default: 120 seconds)
3. Check the **maximum pause duration** (default: 5 minutes)
4. Review logs for any errors during trip detection

### GPS Tracking Not Working

1. Ensure your Silence Private Server is publishing GPS coordinates
2. Verify the `device_tracker.silence_scooter_2` entity exists
3. Check that latitude and longitude sensors are updating
4. Confirm the map-card custom component is installed

## Advanced Configuration

### Customizing Trip Detection

You can adjust trip detection behavior by reconfiguring the integration:

1. Go to **Settings** → **Devices & Services**
2. Find **Silence Scooter** integration
3. Click **"Configure"**
4. Adjust the parameters:
   - **Stop confirmation delay**: Increase to reduce false stop detections
   - **Maximum pause duration**: Increase to allow longer pauses during trips
   - **Watchdog period**: Decrease for more frequent connectivity checks

### Automations

You can create automations based on the integration's entities:

**Example: Notification when battery is low**
```yaml
automation:
  - alias: "Scooter Low Battery Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.scooter_battery_display
        below: 20
    action:
      - service: notify.mobile_app
        data:
          message: "Scooter battery is below 20%!"
```

**Example: Log trip completion**
```yaml
automation:
  - alias: "Log Trip Completion"
    trigger:
      - platform: state
        entity_id: sensor.scooter_is_moving
        to: "off"
    action:
      - service: notify.persistent_notification
        data:
          message: >
            Trip completed:
            Distance: {{ states('sensor.scooter_last_trip_distance') }} km
            Duration: {{ states('sensor.scooter_last_trip_duration') }} min
            Battery used: {{ states('sensor.scooter_last_trip_battery_consumption') }}%
```

## Support

If you encounter issues:

1. Check the [GitHub Issues](https://github.com/noiwid/silence-scooter-homeassistant/issues) page
2. Review the [README.md](README.md) for detailed feature documentation
3. Enable debug logging and check Home Assistant logs
4. Create a new issue with:
   - Your Home Assistant version
   - Integration version
   - Relevant log entries
   - Steps to reproduce the problem

## Uninstallation

To remove the integration:

1. Go to **Settings** → **Devices & Services**
2. Find **Silence Scooter** integration
3. Click the **⋮ menu** → **"Delete"**
4. Confirm deletion
5. (Optional) Remove the integration files from `custom_components/silencescooter/`
6. Restart Home Assistant
