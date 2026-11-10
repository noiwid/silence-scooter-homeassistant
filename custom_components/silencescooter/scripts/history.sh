#!/bin/bash
# JSON_FILE is passed as an environment variable by the integration
# (see helpers.update_history). Falls back to the new persistent path.
JSON_FILE="${JSON_FILE:-/config/silencescooter/history.json}"

# Vérifier si le nombre correct d'arguments est passé
if [ "$#" -ne 8 ]; then
    echo "Usage: $0 avg_speed distance duration start_time end_time max_speed battery outdoor_temp"
    exit 1
fi

# Dépendances dures : sans jq/bc on refuse d'écrire plutôt que de corrompre.
for dep in jq bc; do
    if ! command -v "$dep" > /dev/null 2>&1; then
        echo "Missing required dependency: $dep" >&2
        exit 2
    fi
done

# Récupération des paramètres
START_TIME="$4"
END_TIME="$5"
DURATION="$3"
DISTANCE="$2"
AVG_SPEED="$1"
MAX_SPEED="$6"
BATTERY="$7"
OUTDOOR_TEMP="$8"

TARGET_DIR=$(dirname "$JSON_FILE")

# Verrou anti-écritures concurrentes (deux do_stop_trip qui se chevauchent).
# flock est présent sur HAOS/containers ; s'il manque, on continue sans verrou
# (comportement historique). NOTE: forme `flock FD` bloquante uniquement — le
# flock de busybox ne connaît pas -w, et le timeout=30s du subprocess côté
# intégration (helpers.update_history) borne de toute façon l'attente.
if command -v flock > /dev/null 2>&1; then
    exec 9> "${JSON_FILE}.lock"
    if ! flock 9; then
        echo "Could not acquire lock on ${JSON_FILE}.lock" >&2
        exit 3
    fi
fi

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

# Écriture atomique : fichier temporaire DANS le dossier cible (même
# filesystem => mv atomique ; l'ancien tmp.json relatif au CWD de HA pouvait
# entrer en collision entre deux écritures et traverser les filesystems).
TMP_FILE=$(mktemp "${TARGET_DIR}/history.XXXXXX.tmp" 2> /dev/null) || TMP_FILE="${TARGET_DIR}/history.$$.tmp"

cleanup() {
    rm -f "$TMP_FILE"
}
trap cleanup EXIT

if [ ! -f "$JSON_FILE" ]; then
    # Premier trajet : créer le fichier
    if echo "[$NEW_TRIP]" > "$TMP_FILE" && mv "$TMP_FILE" "$JSON_FILE"; then
        exit 0
    fi
    echo "Failed to create $JSON_FILE" >&2
    exit 4
fi

# Un fichier VIDE passe `jq .` sans erreur, puis la fusion ne produit rien et
# écrasait history.json par du vide à chaque trajet, code retour 0. On exige
# donc un tableau JSON.
if ! jq -e 'type == "array"' "$JSON_FILE" > /dev/null 2>&1; then
    # Fichier corrompu : on le PRÉSERVE pour récupération manuelle au lieu de
    # l'écraser (l'ancien comportement remplaçait silencieusement des mois
    # d'historique par le seul nouveau trajet).
    CORRUPT_COPY="${JSON_FILE}.corrupt.$(date +%s)"
    cp -f "$JSON_FILE" "$CORRUPT_COPY" 2> /dev/null
    echo "Existing history is invalid JSON — preserved as $CORRUPT_COPY, starting fresh" >&2
    if echo "[$NEW_TRIP]" > "$TMP_FILE" && mv "$TMP_FILE" "$JSON_FILE"; then
        exit 0
    fi
    echo "Failed to rewrite $JSON_FILE" >&2
    exit 4
fi

# Sauvegarde roulante avant chaque écriture (un seul .bak, pas d'accumulation)
cp -f "$JSON_FILE" "${JSON_FILE}.bak" 2> /dev/null

# Ajouter le nouveau trajet en premier
if jq --argjson new_trip "$NEW_TRIP" '. as $arr | [$new_trip] + $arr' "$JSON_FILE" > "$TMP_FILE" \
    && jq -e 'type == "array" and length > 0' "$TMP_FILE" > /dev/null 2>&1 \
    && mv "$TMP_FILE" "$JSON_FILE"; then
    exit 0
fi

echo "Failed to append trip to $JSON_FILE (original left untouched)" >&2
exit 4
