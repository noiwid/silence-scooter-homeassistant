# Exposed Entities by the Integration  
This page documents all entities created by the Silence Scooter integration.

## Table of Contents  
- [Numbers (11 entities)](#numbers-11-entities)  
- [DateTimes (4 entities)](#datetimes-4-entities)  
- [Switch (1 entity)](#switch-1-entity)  
- [Sensors (23+ entities)](#sensors-23+-entities)  
  - [Trigger Sensors (5)](#trigger-sensors)  
  - [Template Sensors (6)](#template-sensors)  
  - [Energy Cost Sensors (4)](#energy-cost-sensors)  
  - [Battery Health Sensors (4)](#battery-health-sensors)  
  - [Usage Statistics Sensors (3)](#usage-statistics-sensors)  
  - [Utility Meters (4)](#utility-meters)  
  - [Writable Sensors (3)](#writable-sensors)  

---

## Numbers (11 entities)  
These `number` type entities store numeric values for trips and statistics tracking.

| Entity ID                               | Name                              | Min | Max     | Step  | Unit     | Description                                                   |
|----------------------------------------|-----------------------------------|-----|---------|-------|----------|---------------------------------------------------------------|
| `number.scooter_pause_duration`         | Total pause duration              | 0   | 1440    | 0.1   | minutes  | Cumulative pause duration during the active trip             |
| `number.scooter_odo_debut`              | Odometer at trip start            | 0   | 100000  | 0.1   | km       | Odometer value at the beginning of the trip                   |
| `number.scooter_odo_fin`                | Odometer at trip end              | 0   | 100000  | 0.1   | km       | Odometer value at the end of the trip                         |
| `number.scooter_battery_soc_debut`      | Battery SOC at trip start         | 0   | 100     | 0.1   | %        | Battery level at the beginning of the trip                   |
| `number.scooter_battery_soc_fin`        | Battery SOC at trip end           | 0   | 100     | 0.1   | %        | Battery level at the end of the trip                         |
| `number.scooter_tracked_distance`       | Manually tracked distance         | 0   | 100000  | 0.1   | km       | Manually tracked cumulative distance                          |
| `number.scooter_tracked_battery_used`   | Manually tracked battery used     | 0   | 10000   | 0.1   | %        | Manually tracked cumulative battery consumed                 |
| `number.scooter_energy_consumption_base`| Base scooter energy consumption   | 0   | 1000    | 0.001 | kWh      | Base value for energy consumption calculation                |
| `number.scooter_last_trip_distance`     | Last trip distance                | 0   | 500     | 0.1   | km       | Distance covered during the last trip                         |
| `number.scooter_last_trip_duration`     | Last trip duration                | 0   | 1440    | 0.1   | min      | Duration (net of pauses) of the last trip                     |
| `number.scooter_last_trip_battery_consumption` | Battery consumed last trip | 0   | 100     | 0.1   | %        | Battery consumed during the last trip                         |

---

## DateTimes (4 entities)  
These entities store timestamps for trip management.

| Entity ID                            | Name                                   | Description                                                       |
|-------------------------------------|----------------------------------------|-------------------------------------------------------------------|
| `datetime.scooter_start_time`       | Scooter – Start time of last trip      | Timestamp when the active/last trip started                      |
| `datetime.scooter_end_time`         | Scooter – End time of last trip        | Timestamp of end of trip (1970-01-01 if trip still in progress) |
| `datetime.scooter_last_moving_time` | Last time in motion                    | Last moment when the scooter was moving                          |
| `datetime.scooter_pause_start`      | Pause start                            | Timestamp when the current pause began                           |

> **Note**: When a trip is ongoing, `datetime.scooter_end_time` is set to "1970-01-01 00:00:00" to indicate there is no end yet.

---

## Switch (1 entity)  
| Entity ID                | Name                   | Description                              |
|--------------------------|------------------------|------------------------------------------|
| `switch.stop_trip_now`    | Stop the trip now      | Triggers an immediate manual stop of the active trip |

---

## Sensors (23+ entities)

### Trigger Sensors  
These sensors update automatically via triggers (state changes or timed intervals).

| Entity ID                                | Name                           | Unit | Device Class | State Class       | Description                                               |
|-----------------------------------------|--------------------------------|------|--------------|-------------------|-----------------------------------------------------------|
| `sensor.scooter_start_time_iso`         | Scooter – Start time ISO       | –    | –            | –                 | Start time in ISO 8601 format                              |
| `sensor.scooter_history_start`          | Scooter – History Start        | –    | –            | –                 | Relative format for history card ("X hours ago")          |
| `sensor.scooter_trip_status`            | Scooter – Trip status          | –    | –            | –                 | Current trip state (on/off)                                |
| `sensor.scooter_active_trip_duration`   | Scooter – Active trip duration | min  | –            | –                 | Duration of the active trip updated each minute           |
| `sensor.scooter_energy_consumption`     | Scooter – Energy consumption   | kWh  | energy       | total_increasing  | Cumulative net energy consumption (discharged − regenerated) |

> **Critical sensor**: `sensor.scooter_energy_consumption` calculates net consumption with anti-bounce validation (max variation 5.6 kWh).  

### Template Sensors  
These sensors use Jinja2 templates to compute their values.

| Entity ID                             | Name                              | Unit  | Description                                              |
|--------------------------------------|-----------------------------------|-------|----------------------------------------------------------|
| `sensor.scooter_status_display`      | Scooter – Status                  | –     | Text display of scooter status (Off, Ready, Moving, etc) |
| `sensor.scooter_estimated_range`     | Scooter – Estimated range         | km    | Estimated autonomy based on average consumption          |
| `sensor.scooter_battery_status`      | Scooter – Battery Status          | –     | Battery presence status (Present/Absent)                 |
| `sensor.scooter_battery_per_km`      | Scooter – Consumption per km      | %/km  | Average battery consumption per kilometre                |
| `sensor.scooter_is_moving`           | Scooter – Is Moving               | –     | Movement indicator (on/off) based on status and last update |
| `sensor.scooter_end_time_relative`   | Scooter – Last Trip               | –     | Relative time since last trip ("X ago")                  |

### Energy Cost Sensors  
These sensors automatically compute energy costs based on the configured tariff.

| Entity ID                             | Name                                 | Unit | State Class | Description                          |
|--------------------------------------|--------------------------------------|------|-------------|--------------------------------------|
| `sensor.scooter_energy_cost_daily`   | Scooter – Daily recharge cost        | €    | measurement | Daily energy cost for recharging      |
| `sensor.scooter_energy_cost_weekly`  | Scooter – Weekly recharge cost       | €    | measurement | Weekly energy cost for recharging     |
| `sensor.scooter_energy_cost_monthly` | Scooter – Monthly recharge cost      | €    | measurement | Monthly energy cost for recharging    |
| `sensor.scooter_energy_cost_yearly`  | Scooter – Yearly recharge cost       | €    | measurement | Yearly energy cost for recharging     |

> **Note**: The default tariff is 0.215 €/kWh but can be customized via the `tariff_sensor` configuration parameter.  

### Battery Health Sensors  
These sensors monitor the health of the battery.

| Entity ID                               | Name                               | Unit | State Class | Device Class | Description                                                              |
|----------------------------------------|------------------------------------|------|-------------|--------------|--------------------------------------------------------------------------|
| `sensor.scooter_battery_cell_imbalance`| Battery – Cell imbalance            | mV   | measurement  | –            | Difference in voltage between the highest and lowest cell                |
| `sensor.scooter_battery_soc_calculated`| Battery – SOC calculated (Voltage) | %    | measurement  | battery       | SOC computed from voltage (46.2 V–58.8 V for 14S battery)                 |
| `sensor.scooter_battery_soc_deviation` | Battery – SOC displayed/calculated deviation | % | measurement  | –    | Difference between displayed SOC and SOC calculated from voltage         |
| `sensor.scooter_battery_charge_cycles` | Battery – Cumulative charge cycles | cycles | total_increasing | –        | Equivalent full charge cycles (charged_energy / 5.6 kWh)                |

> **Critical imbalance**: A cell imbalance > 100 mV may indicate a BMS or cell fault.  

### Usage Statistics Sensors  
These sensors provide usage statistics.

| Entity ID                           | Name                         | Unit | State Class | Description                                              |
|-----------------------------------|------------------------------|------|-------------|----------------------------------------------------------|
| `sensor.scooter_distance_per_charge`| Usage – Distance per charge  | km   | measurement  | Average distance per full charge cycle                   |
| `sensor.scooter_cost_per_km`        | Usage – Cost per kilometre   | €/km | measurement  | Average cost per kilometre travelled                      |
| `sensor.scooter_average_trip_distance`| Usage – Average trip distance | km | measurement  | Average distance computed from the trip history          |

### Utility Meters  
These sensors are counters that reset automatically according to their cycle.

| Entity ID                              | Name                           | Cycle  | Source                           | Description                                       |
|---------------------------------------|--------------------------------|--------|----------------------------------|---------------------------------------------------|
| `sensor.scooter_energy_consumption_daily`   | Scooter Energy Consumption Daily   | daily   | `sensor.scooter_energy_consumption`   | Daily consumption (resets at midnight)            |
| `sensor.scooter_energy_consumption_weekly`  | Scooter Energy Consumption Weekly  | weekly  | `sensor.scooter_energy_consumption`   | Weekly consumption (resets on Monday)             |
| `sensor.scooter_energy_consumption_monthly` | Scooter Energy Consumption Monthly | monthly | `sensor.scooter_energy_consumption`   | Monthly consumption (resets on the 1st)           |
| `sensor.scooter_energy_consumption_yearly`  | Scooter Energy Consumption Yearly  | yearly  | `sensor.scooter_energy_consumption`   | Yearly consumption (resets on Jan 1)              |

> **Note**: These counters can be restored manually via the `silencescooter.restore_energy_costs` service.  

### Writable Sensors  
These special sensors can be modified by the integration and retain their value even when the scooter is offline.

| Entity ID                                    | Name                          | Unit | Device Class | State Class       | Description                                                       |
|---------------------------------------------|-------------------------------|------|--------------|-------------------|-------------------------------------------------------------------|
| `sensor.scooter_battery_display`             | Battery level                  | %    | battery      | measurement         | Persistent display of battery level                               |
| `sensor.scooter_odo_display`                 | Odometer                       | km   | –            | total_increasing   | Persistent display of odometer                                    |
| `sensor.scooter_battery_percentage_regeneration`| Regenerated energy percentage | %    | –            | measurement         | Percentage of energy regenerated via braking (regenerated / (discharged + regenerated)) |

> **Persistence**: These sensors retain their last known value even when the scooter is turned off or disconnected, maintaining continuous display in Home Assistant.

---

## See also  
- [Structure of the `history.json` file](HISTORY.md)  
- [Integration configuration](CONFIGURATION.md)  
- [Debugging guide](DEBUGGING.md)
