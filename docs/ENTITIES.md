# Entités exposées par l'intégration

Cette page documente toutes les entités créées par l'intégration Silence Scooter.

## Table des matières

- [Numbers (11 entités)](#numbers-11-entités)
- [DateTimes (4 entités)](#datetimes-4-entités)
- [Switch (1 entité)](#switch-1-entité)
- [Sensors (23+ entités)](#sensors-23-entités)
  - [Trigger Sensors (5)](#trigger-sensors)
  - [Template Sensors (6)](#template-sensors)
  - [Energy Cost Sensors (4)](#energy-cost-sensors)
  - [Battery Health Sensors (4)](#battery-health-sensors)
  - [Usage Statistics Sensors (3)](#usage-statistics-sensors)
  - [Utility Meters (4)](#utility-meters)
  - [Writable Sensors (3)](#writable-sensors)

---

## Numbers (11 entités)

Ces entités de type `number` stockent des valeurs numériques pour le suivi des trajets et statistiques.

| Entity ID | Nom | Min | Max | Step | Unité | Description |
|-----------|-----|-----|-----|------|-------|-------------|
| `number.scooter_pause_duration` | Durée totale des pauses | 0 | 1440 | 0.1 | minutes | Durée cumulée des pauses pendant le trajet actif |
| `number.scooter_odo_debut` | Odomètre début de trajet | 0 | 100000 | 0.1 | km | Valeur de l'odomètre au début du trajet |
| `number.scooter_odo_fin` | Odomètre fin de trajet | 0 | 100000 | 0.1 | km | Valeur de l'odomètre à la fin du trajet |
| `number.scooter_battery_soc_debut` | Batterie SOC début de trajet | 0 | 100 | 0.1 | % | Niveau de batterie au début du trajet |
| `number.scooter_battery_soc_fin` | Batterie SOC fin de trajet | 0 | 100 | 0.1 | % | Niveau de batterie à la fin du trajet |
| `number.scooter_tracked_distance` | Distance suivie (manuel) | 0 | 100000 | 0.1 | km | Distance cumulée suivie manuellement |
| `number.scooter_tracked_battery_used` | Batterie suivie (manuel) | 0 | 10000 | 0.1 | % | Batterie cumulée consommée suivie manuellement |
| `number.scooter_energy_consumption_base` | Base consommation énergie scooter | 0 | 1000 | 0.001 | kWh | Valeur de base pour le calcul de consommation énergétique |
| `number.scooter_last_trip_distance` | Distance du dernier trajet | 0 | 500 | 0.1 | km | Distance parcourue lors du dernier trajet |
| `number.scooter_last_trip_duration` | Durée du dernier trajet | 0 | 1440 | 0.1 | min | Durée (nette des pauses) du dernier trajet |
| `number.scooter_last_trip_battery_consumption` | Batterie consommée du dernier trajet | 0 | 100 | 0.1 | % | Batterie consommée lors du dernier trajet |

---

## DateTimes (4 entités)

Ces entités stockent des horodatages pour la gestion des trajets.

| Entity ID | Nom | Description |
|-----------|-----|-------------|
| `datetime.scooter_start_time` | Scooter Heure de départ dernier trajet | Horodatage du début du trajet actif/dernier trajet |
| `datetime.scooter_end_time` | Scooter Heure de fin du dernier trajet | Horodatage de fin du trajet (1970-01-01 si trajet en cours) |
| `datetime.scooter_last_moving_time` | Dernier instant en mouvement | Dernier moment où le scooter était en mouvement |
| `datetime.scooter_pause_start` | Début de la pause | Horodatage du début de la pause en cours |

> **Note**: Lorsqu'un trajet est en cours, `datetime.scooter_end_time` est mis à "1970-01-01 00:00:00" pour indiquer qu'il n'y a pas encore de fin.

---

## Switch (1 entité)

| Entity ID | Nom | Description |
|-----------|-----|-------------|
| `switch.stop_trip_now` | Arrêter le trajet maintenant | Active l'arrêt manuel immédiat du trajet en cours |

---

## Sensors (23+ entités)

### Trigger Sensors

Ces sensors se mettent à jour automatiquement via des triggers (changements d'état ou intervalles de temps).

| Entity ID | Nom | Unité | Device Class | State Class | Description |
|-----------|-----|-------|--------------|-------------|-------------|
| `sensor.scooter_start_time_iso` | Scooter - Heure de départ ISO | - | - | - | Heure de départ au format ISO 8601 |
| `sensor.scooter_history_start` | Scooter - History Start | - | - | - | Format relatif pour carte historique ("X hours ago") |
| `sensor.scooter_trip_status` | Scooter - État du trajet | - | - | - | État du trajet actuel (on/off) |
| `sensor.scooter_active_trip_duration` | Scooter - Durée du trajet en cours | minutes | - | - | Durée du trajet actif mis à jour chaque minute |
| `sensor.scooter_energy_consumption` | Scooter - Consommation d'énergie | kWh | energy | total_increasing | Consommation totale d'énergie cumulée |

> **Sensor critique**: `sensor.scooter_energy_consumption` calcule automatiquement la consommation nette (déchargée - régénérée) avec validation anti-rebond (max 5.6 kWh/variation).

---

### Template Sensors

Ces sensors utilisent des templates Jinja2 pour calculer leur valeur.

| Entity ID | Nom | Unité | Description |
|-----------|-----|-------|-------------|
| `sensor.scooter_status_display` | Scooter - Status | - | Affichage textuel du statut du scooter (Éteint, Prêt à conduire, En mouvement, etc.) |
| `sensor.scooter_estimated_range` | Scooter - Autonomie estimée | km | Autonomie calculée basée sur consommation moyenne |
| `sensor.scooter_battery_status` | Scooter - Battery Status | - | État de présence de la batterie (Présente/Absente) |
| `sensor.scooter_battery_per_km` | Scooter - Consommation par km | %/km | Consommation moyenne de batterie par kilomètre |
| `sensor.scooter_is_moving` | Scooter - En mouvement | - | Indicateur de mouvement (on/off) basé sur statut et dernière MAJ |
| `sensor.scooter_end_time_relative` | Scooter - Dernier trajet | - | Temps relatif depuis le dernier trajet ("Il y a X") |

---

### Energy Cost Sensors

Ces sensors calculent automatiquement les coûts énergétiques basés sur le tarif configuré.

| Entity ID | Nom | Unité | State Class | Description |
|-----------|-----|-------|-------------|-------------|
| `sensor.scooter_energy_cost_daily` | Scooter - Coût quotidien de la recharge | € | measurement | Coût énergétique du jour |
| `sensor.scooter_energy_cost_weekly` | Scooter - Coût hebdo de la recharge | € | measurement | Coût énergétique de la semaine |
| `sensor.scooter_energy_cost_monthly` | Scooter - Coût mensuel de la recharge | € | measurement | Coût énergétique du mois |
| `sensor.scooter_energy_cost_yearly` | Scooter - Coût annuel de la recharge | € | measurement | Coût énergétique de l'année |

> **Note**: Le tarif par défaut est 0.215 €/kWh mais peut être personnalisé via le paramètre `tariff_sensor` de la configuration.

---

### Battery Health Sensors

Ces sensors surveillent la santé de la batterie.

| Entity ID | Nom | Unité | State Class | Device Class | Description |
|-----------|-----|-------|-------------|--------------|-------------|
| `sensor.scooter_battery_cell_imbalance` | Batterie - Déséquilibre cellules | mV | measurement | - | Différence de tension entre la cellule la plus haute et la plus basse |
| `sensor.scooter_battery_soc_calculated` | Batterie - SOC calculé (Voltage) | % | measurement | battery | SOC calculé à partir de la tension (46.2V-58.8V pour batterie 14S) |
| `sensor.scooter_battery_soc_deviation` | Batterie - Écart SOC affiché/calculé | % | measurement | - | Différence entre SOC affiché et SOC calculé par tension |
| `sensor.scooter_battery_charge_cycles` | Batterie - Cycles de charge cumulés | cycles | total_increasing | - | Nombre de cycles équivalents complets (charged_energy / 5.6 kWh) |

> **Déséquilibre critique**: Un déséquilibre > 100 mV entre cellules peut indiquer un problème de BMS ou de cellule défaillante.

---

### Usage Statistics Sensors

Ces sensors fournissent des statistiques d'utilisation.

| Entity ID | Nom | Unité | State Class | Description |
|-----------|-----|-------|-------------|-------------|
| `sensor.scooter_distance_per_charge` | Utilisation - Distance par charge | km | measurement | Distance moyenne par cycle de charge complet |
| `sensor.scooter_cost_per_km` | Utilisation - Coût au kilomètre | €/km | measurement | Coût moyen par kilomètre parcouru |
| `sensor.scooter_average_trip_distance` | Utilisation - Distance moyenne par trajet | km | measurement | Distance moyenne calculée sur l'historique des trajets |

---

### Utility Meters

Ces sensors sont des compteurs qui se réinitialisent automatiquement selon leur cycle.

| Entity ID | Nom | Cycle | Source | Description |
|-----------|-----|-------|--------|-------------|
| `sensor.scooter_energy_consumption_daily` | Scooter Energy Consumption Daily | daily | `sensor.scooter_energy_consumption` | Consommation journalière (reset à minuit) |
| `sensor.scooter_energy_consumption_weekly` | Scooter Energy Consumption Weekly | weekly | `sensor.scooter_energy_consumption` | Consommation hebdomadaire (reset le lundi) |
| `sensor.scooter_energy_consumption_monthly` | Scooter Energy Consumption Monthly | monthly | `sensor.scooter_energy_consumption` | Consommation mensuelle (reset le 1er) |
| `sensor.scooter_energy_consumption_yearly` | Scooter Energy Consumption Yearly | yearly | `sensor.scooter_energy_consumption` | Consommation annuelle (reset le 1er janvier) |

> **Note**: Ces compteurs peuvent être restaurés manuellement via le service `silencescooter.restore_energy_costs`.

---

### Writable Sensors

Ces sensors spéciaux peuvent être modifiés par l'intégration et conservent leur valeur même quand le scooter est hors ligne.

| Entity ID | Nom | Unité | Device Class | State Class | Description |
|-----------|-----|-------|--------------|-------------|-------------|
| `sensor.scooter_battery_display` | Niveau de batterie | % | battery | measurement | Affichage persistant du niveau de batterie |
| `sensor.scooter_odo_display` | Odomètre | km | - | total_increasing | Affichage persistant de l'odomètre |
| `sensor.scooter_battery_percentage_regeneration` | Pourcentage énergie régénérée | % | - | measurement | % d'énergie régénérée par freinage (regenerated / (discharged + regenerated)) |

> **Persistance**: Ces sensors conservent leur dernière valeur connue même quand le scooter est éteint ou déconnecté, pour un affichage continu dans Home Assistant.

---

## Voir aussi

- [Structure du fichier history.json](HISTORY.md)
- [Configuration de l'intégration](CONFIGURATION.md)
- [Guide de débogage](DEBUGGING.md)
