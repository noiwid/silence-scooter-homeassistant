#!/bin/bash
#JSON_FILE="/config/silence_history.json"
JSON_FILE="/config/custom_components/silencescooter/data/history.json"

# Vérifier si le nombre correct d'arguments est passé
if [ "$#" -ne 8 ]; then
    echo "Usage: $0 avg_speed distance duration start_time end_time max_speed battery outdoor_temp"
    exit 1
fi
# Récupération des paramètres
START_TIME="$4"
END_TIME="$5"
DURATION="$3"
DISTANCE="$2"
AVG_SPEED="$1"
MAX_SPEED="$6"
BATTERY="$7"
OUTDOOR_TEMP="$8"

# Calcul de l'efficacité énergétique (Wh/km)
# Capacité batterie = 5.6 kWh = 5600 Wh
# Efficacité = (Battery% / 100 * 5600) / Distance
# NOTE: Use high precision (scale=10) for intermediate calculations to avoid rounding errors
EFFICIENCY="0"
if [ "$(echo "$DISTANCE > 0" | bc)" -eq 1 ]; then
    # Calculate with high precision, then round to 1 decimal
    EFFICIENCY=$(echo "scale=10; result = ($BATTERY / 100 * 5600) / $DISTANCE; scale=1; result / 1" | bc)
fi

# Créer l'entrée JSON
NEW_TRIP=$(jq -n \
    --arg start_time "$START_TIME" \
    --arg end_time "$END_TIME" \
    --arg duration "$DURATION" \
    --arg distance "$DISTANCE" \
    --arg avg_speed "$AVG_SPEED" \
    --arg max_speed "$MAX_SPEED" \
    --arg battery "$BATTERY" \
    --arg outdoor_temp "$OUTDOOR_TEMP" \
    --arg efficiency "$EFFICIENCY" \
    '{start_time: $start_time, end_time: $end_time, duration: $duration, distance: $distance, avg_speed: $avg_speed, max_speed: $max_speed, battery: $battery, outdoor_temp: $outdoor_temp, efficiency_wh_km: $efficiency}')

# Vérifier si le fichier JSON existe et est valide
if [ ! -f "$JSON_FILE" ] || ! jq . "$JSON_FILE" > /dev/null 2>&1; then
    echo "[$NEW_TRIP]" > "$JSON_FILE"
else
    # Ajouter le nouveau trajet en premier
    jq --argjson new_trip "$NEW_TRIP" '. as $arr | [$new_trip] + $arr' "$JSON_FILE" > tmp.json && mv tmp.json "$JSON_FILE"
fi