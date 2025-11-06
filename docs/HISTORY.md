# Structure du fichier history.json

Cette page documente la structure et le contenu du fichier `history.json` qui stocke l'historique des trajets de votre scooter.

## Emplacement

Le fichier est situé à :
```
/config/custom_components/silencescooter/data/history.json
```

## Structure générale

Le fichier contient un tableau JSON où chaque élément représente un trajet. Les trajets sont stockés dans l'ordre **anti-chronologique** (le plus récent en premier).

```json
[
  { "trajet le plus récent" },
  { "trajet précédent" },
  { "..." }
]
```

## Structure d'un trajet

Chaque trajet contient les champs suivants :

| Champ | Type | Unité | Description |
|-------|------|-------|-------------|
| `start_time` | string (ISO 8601) | - | Date et heure de début du trajet |
| `end_time` | string (ISO 8601) | - | Date et heure de fin du trajet |
| `duration` | string (number) | minutes | Durée nette du trajet (hors pauses) |
| `distance` | string (number) | km | Distance parcourue |
| `avg_speed` | string (number) | km/h | Vitesse moyenne |
| `max_speed` | string (number) | km/h | Vitesse maximale atteinte |
| `battery` | string (number) | % | Batterie consommée pendant le trajet |
| `outdoor_temp` | string (number) | °C | Température extérieure pendant le trajet |
| `efficiency_wh_km` | string (number) | Wh/km | Efficacité énergétique (calculée automatiquement) |

### Calcul de l'efficacité

L'efficacité énergétique est calculée automatiquement par le script `history.sh` selon la formule :

```
Efficacité (Wh/km) = (Battery% / 100 × 5600 Wh) / Distance (km)
```

> **Note**: La capacité de la batterie est de 5.6 kWh (5600 Wh).

## Exemple de fichier complet

Voici un exemple de fichier `history.json` contenant 3 trajets :

```json
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
```

## Exemple de trajet détaillé

Analysons un trajet en détail :

```json
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
```

### Interprétation

- **Trajet effectué le** : 6 novembre 2025
- **Heure de départ** : 14h30:15
- **Heure d'arrivée** : 14h52:38
- **Durée totale écoulée** : ~22 minutes
- **Durée nette** : 20 minutes (2 minutes de pauses cumulées)
- **Distance** : 8.3 km
- **Vitesse moyenne** : 24.9 km/h (sur la durée nette de 20 min)
- **Vitesse max** : 48.5 km/h
- **Batterie consommée** : 18.2%
- **Température** : 16.5°C
- **Efficacité** : 122.9 Wh/km (soit ~1019 Wh consommés pour ce trajet)

### Vérification de cohérence

On peut vérifier la cohérence des données :

1. **Vitesse moyenne** = Distance / Durée = 8.3 km / (20 min / 60) = 24.9 km/h ✓
2. **Énergie consommée** = 18.2% × 5.6 kWh = 1.019 kWh = 1019 Wh
3. **Efficacité** = 1019 Wh / 8.3 km = 122.8 Wh/km ≈ 122.9 Wh/km ✓

## Validation des trajets

L'intégration effectue plusieurs validations avant d'enregistrer un trajet dans l'historique :

### Validations automatiques

1. **Durée minimale** : Rejet si `duration < 1.5 min` ET `distance > 2 km` (physiquement impossible)
2. **Vitesse maximale** : Rejet si `avg_speed > 120 km/h` (dépassement limite scooter)
3. **Cohérence vitesse** : Rejet si écart > 30% entre vitesse calculée et enregistrée
4. **Vitesse max cohérente** : Rejet si `max_speed = 0` alors que `avg_speed > 10 km/h`

### Exemple de trajet rejeté

```
⚠️ TRIP REJECTED - Data validation failed:
  - Trip too short: 0.8 min for 5.2 km
  - Speed inconsistency: calculated=390.0 vs recorded=24.9
Trip data: distance=5.2 km, duration=0.8 min, avg_speed=24.9 km/h, battery=5.2%
```

## Accéder aux données depuis Home Assistant

### Via sensor

Le sensor `sensor.scooter_trips` expose l'historique complet dans son attribut `history` :

```yaml
{{ state_attr('sensor.scooter_trips', 'history') }}
```

### Via template

Vous pouvez extraire des statistiques avec des templates :

```yaml
# Nombre total de trajets
{{ state_attr('sensor.scooter_trips', 'history') | length }}

# Distance totale parcourue
{{ state_attr('sensor.scooter_trips', 'history') | map(attribute='distance') | map('float') | sum }}

# Efficacité moyenne
{% set trips = state_attr('sensor.scooter_trips', 'history') %}
{{ (trips | map(attribute='efficiency_wh_km') | map('float') | sum / trips | length) | round(1) }}
```

### Via Lovelace

Utilisez l'exemple de dashboard fourni (`examples/lovelace_silence.yaml`) qui affiche l'historique sous forme de tableau.

## Maintenance du fichier

### Sauvegarde

Nous recommandons de sauvegarder régulièrement le fichier :

```bash
cp /config/custom_components/silencescooter/data/history.json \
   /config/backups/history_$(date +%Y%m%d).json
```

### Nettoyage

Pour supprimer les anciens trajets (> 6 mois) :

```bash
jq '[.[] | select(
  (.start_time | fromdateiso8601) > (now - 15552000)
)]' history.json > history_cleaned.json
mv history_cleaned.json history.json
```

### Réinitialisation

Pour repartir avec un historique vide :

```bash
echo "[]" > /config/custom_components/silencescooter/data/history.json
```

## Format des dates

Les dates utilisent le format **ISO 8601** avec timezone :

```
YYYY-MM-DDTHH:MM:SS+TZ:TZ
```

Exemples :
- `2025-11-06T14:30:15+01:00` (heure d'hiver Europe/Paris)
- `2025-07-15T14:30:15+02:00` (heure d'été Europe/Paris)

> **Important** : Le timezone est toujours inclus pour éviter les ambiguïtés.

## Troubleshooting

### Le fichier est vide ou corrompu

Si le fichier est vide (`[]`) ou corrompu, l'intégration le réinitialisera automatiquement au prochain trajet.

### Les trajets ne s'enregistrent pas

1. Vérifiez les permissions du fichier :
   ```bash
   ls -l /config/custom_components/silencescooter/data/history.json
   ```

2. Vérifiez les logs Home Assistant :
   ```
   grep "update_history" /config/home-assistant.log
   ```

3. Vérifiez que le script bash existe :
   ```bash
   ls -l /config/custom_components/silencescooter/scripts/history.sh
   ```

### Format JSON invalide

Validez manuellement le fichier :

```bash
jq . /config/custom_components/silencescooter/data/history.json
```

Si erreur, sauvegardez et réinitialisez :

```bash
cp history.json history.json.backup
echo "[]" > history.json
```

## Voir aussi

- [Liste complète des entités](ENTITIES.md)
- [Guide de configuration](CONFIGURATION.md)
- [Guide de débogage](DEBUGGING.md)
