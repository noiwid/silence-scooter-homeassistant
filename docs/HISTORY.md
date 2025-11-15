# Structure of the `history.json` File

This page documents the structure and content of the `history.json` file, which stores the trip history of your scooter.

## Location

The file is located at:

    /config/custom_components/silencescooter/data/history.json

## General Structure

The file contains a JSON array where each element represents a trip.  
Trips are stored in **reverse chronological order** (most recent first).

    [
      { "most recent trip" },
      { "previous trip" },
      { "..." }
    ]

## Trip Structure

Each trip includes the following fields:

| Field               | Type               | Unit  | Description                                      |
|---------------------|--------------------|-------|--------------------------------------------------|
| `start_time`        | string (ISO 8601)  | –     | Start date and time of the trip                  |
| `end_time`          | string (ISO 8601)  | –     | End date and time of the trip                    |
| `duration`          | string (number)    | minutes | Net duration of the trip (excluding pauses)     |
| `distance`          | string (number)    | km    | Distance traveled                                 |
| `avg_speed`         | string (number)    | km/h  | Average speed                                     |
| `max_speed`         | string (number)    | km/h  | Maximum speed reached                             |
| `battery`           | string (number)    | %     | Battery consumed during the trip                  |
| `outdoor_temp`      | string (number)    | °C    | Outside temperature during the trip               |
| `efficiency_wh_km`  | string (number)    | Wh/km | Energy efficiency (automatically calculated)      |

### Efficiency Calculation

Energy efficiency is automatically calculated by the `history.sh` script using the formula:

    Efficiency (Wh/km) = (Battery% / 100 × 5600 Wh) / Distance (km)

> **Note:** Battery capacity is 5.6 kWh (5600 Wh).

## Full Example File

Here’s an example of a `history.json` file containing 3 trips:

    [
      {
        "start_time": "2025-11-06T14:30:15+01:00",
        "end_time": "2025-11-06T14:52:38+01:00",
        "duration": "20",
        "distance": "8.3",
        "avg_speed": "24.9",
        "max_speed": "48.5",
        "battery": "18.2",
        "outdoor_temp": "16.5",
        "efficiency_wh_km": "122.9"
      },
      {
        "start_time": "2025-11-06T09:15:42+01:00",
        "end_time": "2025-11-06T09:28:10+01:00",
        "duration": "10",
        "distance": "3.7",
        "avg_speed": "22.2",
        "max_speed": "42.0",
        "battery": "8.5",
        "outdoor_temp": "12.8",
        "efficiency_wh_km": "128.6"
      },
      {
        "start_time": "2025-11-05T18:05:20+01:00",
        "end_time": "2025-11-05T18:35:45+01:00",
        "duration": "28",
        "distance": "12.1",
        "avg_speed": "25.9",
        "max_speed": "51.2",
        "battery": "24.8",
        "outdoor_temp": "14.2",
        "efficiency_wh_km": "114.9"
      }
    ]

## Detailed Trip Example

Let’s analyze one trip in detail:

    {
      "start_time": "2025-11-06T14:30:15+01:00",
      "end_time": "2025-11-06T14:52:38+01:00",
      "duration": "20",
      "distance": "8.3",
      "avg_speed": "24.9",
      "max_speed": "48.5",
      "battery": "18.2",
      "outdoor_temp": "16.5",
      "efficiency_wh_km": "122.9"
    }

### Interpretation

- **Trip date:** November 6, 2025  
- **Start time:** 14:30:15  
- **End time:** 14:52:38  
- **Elapsed duration:** ~22 minutes  
- **Net duration:** 20 minutes (2 minutes of cumulative pauses)  
- **Distance:** 8.3 km  
- **Average speed:** 24.9 km/h (over the 20 min net duration)  
- **Max speed:** 48.5 km/h  
- **Battery consumed:** 18.2 %  
- **Temperature:** 16.5 °C  
- **Efficiency:** 122.9 Wh/km (≈ 1019 Wh consumed for this trip)

### Consistency Check

You can verify the data consistency:

1. **Average speed** = Distance / Duration = 8.3 km / (20 min / 60) = 24.9 km/h ✓  
2. **Energy consumed** = 18.2 % × 5.6 kWh = 1.019 kWh = 1019 Wh  
3. **Efficiency** = 1019 Wh / 8.3 km = 122.8 Wh/km ≈ 122.9 Wh/km ✓  

## Trip Validation

Before recording a trip, the integration performs multiple data checks.

### Automatic Validations

1. **Minimum duration:** Reject if `duration < 1.5 min` **and** `distance > 2 km` (physically impossible)  
2. **Maximum speed:** Reject if `avg_speed > 120 km/h` (beyond scooter limit)  
3. **Speed consistency:** Reject if deviation > 30 % between calculated and recorded speed  
4. **Valid max speed:** Reject if `max_speed = 0` while `avg_speed > 10 km/h`  

### Example of a Rejected Trip

    ⚠️ TRIP REJECTED – Data validation failed:
      - Trip too short: 0.8 min for 5.2 km
      - Speed inconsistency: calculated = 390.0 vs recorded = 24.9
    Trip data: distance = 5.2 km, duration = 0.8 min, avg_speed = 24.9 km/h, battery = 5.2 %

## Accessing Data from Home Assistant

### Via Sensor

The `sensor.scooter_trips` entity exposes the full history in its `history` attribute:

    {{ state_attr('sensor.scooter_trips', 'history') }}

### Via Template

You can extract statistics using templates:

    # Total number of trips
    {{ state_attr('sensor.scooter_trips', 'history') | length }}

    # Total distance traveled
    {{ state_attr('sensor.scooter_trips', 'history') | map(attribute='distance') | map('float') | sum }}

    # Average efficiency
    {% set trips = state_attr('sensor.scooter_trips', 'history') %}
    {{ (trips | map(attribute='efficiency_wh_km') | map('float') | sum / trips | length) | round(1) }}

### Via Lovelace

Use the provided example dashboard (`examples/lovelace_silence.yaml`) which displays the trip history in a table format.

## File Maintenance

### Backup

It’s recommended to back up the file regularly:

    cp /config/custom_components/silencescooter/data/history.json \
       /config/backups/history_$(date +%Y%m%d).json

### Cleanup

To delete trips older than 6 months:

    jq '[.[] | select(
      (.start_time | fromdateiso8601) > (now - 15552000)
    )]' history.json > history_cleaned.json
    mv history_cleaned.json history.json

### Reset

To start with an empty history:

    echo "[]" > /config/custom_components/silencescooter/data/history.json

## Date Format

Dates use the **ISO 8601** format with timezone:

    YYYY-MM-DDTHH:MM:SS+TZ:TZ

Examples:
- `2025-11-06T14:30:15+01:00` (winter time Europe/Paris)
- `2025-07-15T14:30:15+02:00` (summer time Europe/Paris)

> **Important:** The timezone is always included to avoid ambiguity.

## Troubleshooting

### The file is empty or corrupted

If the file is empty (`[]`) or corrupted, the integration will automatically recreate it on the next trip.

### Trips are not being recorded

1. Check file permissions:

       ls -l /config/custom_components/silencescooter/data/history.json

2. Check Home Assistant logs:

       grep "update_history" /config/home-assistant.log

3. Check that the bash script exists:

       ls -l /config/custom_components/silencescooter/scripts/history.sh

### Invalid JSON Format

Validate the file manually:

       jq . /config/custom_components/silencescooter/data/history.json

If there’s an error, back up and reset:

       cp history.json history.json.backup
       echo "[]" > history.json

## See Also

- [Complete list of entities](ENTITIES.md)
- [Configuration guide](CONFIGURATION.md)
- [Debugging guide](DEBUGGING.md)
