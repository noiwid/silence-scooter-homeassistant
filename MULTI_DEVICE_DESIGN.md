# Conception du Support Multi-Appareils
## Silence Scooter Home Assistant Integration

**Date**: 15 novembre 2025
**Objectif**: Ajouter le support de plusieurs scooters Silence S01
**Issue**: #2 - Support multiple Silence S01 scooters (multi-device)
**Référence**: PR #8 sur silence-private-server (support multi-IMEI)

---

## 1. Analyse du Problème

### Contexte
Le serveur privé Silence a été mis à jour (PR #8) pour supporter plusieurs IMEI :
- Chaque IMEI a son propre thread
- Chaque IMEI a son propre port TCP (BasePort + index)
- Configuration via `IMEI_List` dans configuration.json
- Topics MQTT déjà structurés avec IMEI : `home/silence-server/{IMEI}/status/*`

### Problème Actuel
L'intégration Home Assistant est conçue pour un seul scooter :
- Device ID fixe : `("silence_scooter", "Silence Scooter")`
- Entity IDs sans IMEI : `sensor.silence_scooter_speed`
- Config flow en mode single-instance
- ~80-100 références hardcodées aux entity IDs dans automations.py
- Aucune isolation par IMEI

### Conséquences Sans Modification
Avec 2+ scooters :
- **Collision des entity IDs** : tous les scooters partagent les mêmes entités
- **Données mélangées** : l'historique, les trajets, les positions GPS sont fusionnés
- **Automations défaillantes** : détection de trajet incorrecte
- **Services ambigus** : reset_tracked_counters → quel scooter ?

---

## 2. Solutions Envisagées

### Option A: Multi-Instances (RECOMMANDÉE ✅)
**Principe** : Permettre l'installation de l'intégration plusieurs fois, une par scooter

**Avantages** :
- ✅ Simple à implémenter (~20 heures vs 60-90 heures)
- ✅ Isolation naturelle des données (chaque instance = namespace séparé)
- ✅ UI Home Assistant standard (ajout/suppression d'instances)
- ✅ Backward compatible (utilisateurs actuels non impactés)
- ✅ Pas de modifications massives dans automations.py
- ✅ Chaque instance a sa propre configuration

**Inconvénients** :
- ❌ Configuration MQTT séparée pour chaque scooter (acceptable)
- ❌ Services globaux plus complexes (mais rarement utilisés)

**Modifications Requises** :
1. Retirer `single_instance_allowed` du config flow
2. Ajouter champ IMEI obligatoire dans le config flow
3. Modifier `get_device_info()` pour utiliser l'IMEI comme identifiant unique
4. Modifier entity IDs pour inclure l'IMEI
5. Mettre à jour la documentation (MQTT config par scooter)

**Effort Estimé** : 20-30 heures de dev + 10 heures de test

---

### Option B: Multi-Appareils dans Une Instance
**Principe** : Une seule instance gérant plusieurs scooters

**Avantages** :
- ✅ Configuration centralisée
- ✅ Services globaux simplifiés

**Inconvénients** :
- ❌ Très complexe (~60-90 heures de dev)
- ❌ Modifications massives dans automations.py (~100+ endroits)
- ❌ Risque élevé de régression
- ❌ UI custom nécessaire pour sélectionner le scooter
- ❌ Gestion d'état complexe (hass.data par IMEI)

**Effort Estimé** : 60-90 heures de dev + 20-30 heures de test

**Verdict** : ❌ Trop complexe pour le bénéfice apporté

---

## 3. Solution Retenue : Option A (Multi-Instances)

### Architecture Proposée

```
Home Assistant
├── Integration Instance 1 (IMEI: 869123456789012)
│   ├── Device: "Silence Scooter (869123456789012)"
│   ├── Entities: sensor.silence_scooter_speed_869123456789012
│   ├── MQTT: home/silence-server/869123456789012/status/*
│   └── Automations: isolées pour ce scooter
│
├── Integration Instance 2 (IMEI: 869987654321098)
│   ├── Device: "Silence Scooter (869987654321098)"
│   ├── Entities: sensor.silence_scooter_speed_869987654321098
│   ├── MQTT: home/silence-server/869987654321098/status/*
│   └── Automations: isolées pour ce scooter
│
└── ...
```

### Principes de Conception

#### 1. Identifiant Unique : IMEI
- **Champ obligatoire** dans le config flow
- **Validation** : 15 chiffres (format IMEI standard)
- **Stockage** : `config_entry.data[CONF_IMEI]`
- **Unicité** : vérification qu'aucune autre instance n'utilise le même IMEI

#### 2. Device Info IMEI-Aware
```python
def get_device_info(imei: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={("silence_scooter", imei)},
        name=f"Silence Scooter ({imei})",
        manufacturer="Seat",
        model="Mo",
    )
```

#### 3. Entity IDs avec Suffixe IMEI
```python
def generate_entity_id(base_id: str, imei: str) -> str:
    """Generate unique entity ID with IMEI suffix."""
    # Utiliser les 4 derniers chiffres pour la lisibilité
    imei_short = imei[-4:] if len(imei) >= 4 else imei
    return f"{base_id}_{imei_short}"

# Exemples:
# sensor.silence_scooter_speed → sensor.silence_scooter_speed_9012
# sensor.silence_scooter_odo → sensor.silence_scooter_odo_9012
```

#### 4. Namespace Séparé par Instance
Chaque instance stocke ses données dans :
```python
hass.data[DOMAIN][entry.entry_id] = {
    "imei": entry.data[CONF_IMEI],
    "sensors": {},  # Isolé par instance
    "config": entry.data,
}
```

#### 5. Configuration MQTT par Scooter
L'utilisateur doit configurer les topics MQTT pour chaque IMEI :
```yaml
# Scooter 1 (IMEI: 869123456789012)
mqtt:
  sensor:
    - name: "Silence Scooter Speed 9012"
      state_topic: "home/silence-server/869123456789012/status/speed"
      unique_id: "silence_scooter_speed_869123456789012"

# Scooter 2 (IMEI: 869987654321098)
  sensor:
    - name: "Silence Scooter Speed 1098"
      state_topic: "home/silence-server/869987654321098/status/speed"
      unique_id: "silence_scooter_speed_869987654321098"
```

---

## 4. Plan d'Implémentation Détaillé

### Phase 1: Configuration (4 heures) ✅

#### Fichier: `const.py`
**Ligne à modifier** : Ajouter après ligne 1
```python
CONF_IMEI = "imei"
```

#### Fichier: `config_flow.py`
**A. Retirer single_instance_allowed**
- **Ligne 122-123** : Supprimer le check single_instance

**B. Ajouter champ IMEI**
- **Ligne 138-190** : Ajouter dans le formulaire
```python
import homeassistant.helpers.config_validation as cv

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_IMEI): cv.string,  # Nouveau champ
    # ... autres champs existants
})
```

**C. Validation de l'IMEI**
- **Ligne 74-110** : Ajouter dans `validate_input()`
```python
def validate_imei(imei: str) -> str:
    """Validate IMEI format."""
    # Enlever espaces/tirets
    imei_clean = imei.replace(" ", "").replace("-", "")

    # Vérifier longueur (15 chiffres pour IMEI)
    if not imei_clean.isdigit() or len(imei_clean) != 15:
        raise ValueError("IMEI must be 15 digits")

    return imei_clean

async def validate_input(hass, data):
    """Validate user input."""
    imei = validate_imei(data[CONF_IMEI])

    # Vérifier unicité : aucune autre instance ne doit utiliser cet IMEI
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get(CONF_IMEI) == imei:
            raise AlreadyConfigured(f"IMEI {imei} already configured")

    return {"title": f"Silence Scooter ({imei[-4:]})", "imei": imei}
```

**D. Stocker l'IMEI**
- **Ligne 191-196** : Créer l'entry avec IMEI
```python
return self.async_create_entry(
    title=validated["title"],
    data={
        CONF_IMEI: validated["imei"],
        **{k: v for k, v in user_input.items() if k != CONF_IMEI}
    }
)
```

---

### Phase 2: Device Info & Helpers (4 heures) ✅

#### Fichier: `helpers.py`

**Ligne 15-22** : Modifier `get_device_info()`
```python
from homeassistant.helpers.entity import DeviceInfo

def get_device_info(imei: str) -> DeviceInfo:
    """Return device info for Silence Scooter with IMEI."""
    imei_short = imei[-4:] if len(imei) >= 4 else imei

    return DeviceInfo(
        identifiers={("silence_scooter", imei)},  # IMEI complet comme ID
        name=f"Silence Scooter ({imei_short})",   # 4 derniers chiffres pour la lisibilité
        manufacturer="Seat",
        model="Mo",
    )

def generate_entity_id(base_id: str, imei: str) -> str:
    """Generate unique entity ID with IMEI suffix."""
    imei_short = imei[-4:] if len(imei) >= 4 else imei
    return f"{base_id}_{imei_short}"
```

---

### Phase 3: Entity Classes (8 heures) ✅

#### Fichier: `sensor.py`

**A. Modifier async_setup_entry() (Ligne 43-139)**
```python
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Silence Scooter sensors."""

    # Récupérer IMEI
    imei = config_entry.data.get(CONF_IMEI)
    if not imei:
        raise ConfigEntryNotReady("IMEI not configured")

    entities = []

    # Writable sensors avec IMEI
    for sensor_id, config in WRITABLE_SENSORS.items():
        entities.append(ScooterWritableSensor(hass, sensor_id, config, imei))

    # Template sensors avec IMEI
    for sensor_id, config in TEMPLATE_SENSORS.items():
        entities.append(ScooterTemplateSensor(hass, sensor_id, config, imei))

    # ... autres sensors avec IMEI

    async_add_entities(entities, True)
```

**B. Modifier ScooterWritableSensor (Ligne 140-235)**
```python
class ScooterWritableSensor(SensorEntity, RestoreEntity):
    """Writable sensor with IMEI support."""

    def __init__(
        self,
        hass: HomeAssistant,
        sensor_id: str,
        config: dict,
        imei: str,  # Nouveau paramètre
    ) -> None:
        """Initialize the sensor."""
        self._hass = hass
        self._sensor_id = sensor_id
        self._config = config
        self._imei = imei  # Stocker IMEI

        # Entity ID avec suffixe IMEI
        imei_short = imei[-4:] if len(imei) >= 4 else imei
        self.entity_id = f"sensor.{sensor_id}_{imei_short}"
        self._attr_unique_id = f"{sensor_id}_{imei}"
        self._attr_name = f"{config['name']} ({imei_short})"

        # Device info avec IMEI
        self._attr_device_info = get_device_info(imei)

        # ... reste du code
```

**C. Même pattern pour les autres classes** :
- `ScooterTemplateSensor` (Ligne 238-336)
- `ScooterTriggerSensor` (Ligne 339-407)
- `ScooterTripsSensor` (Ligne 410-496)
- `ScooterDefaultTariffSensor` (Ligne 499-527)
- `ScooterUtilityMeterSensor` (Ligne 530-548)

#### Fichier: `number.py`

**Ligne 15-82** : Ajouter paramètre `imei` à `ScooterNumber`
```python
class ScooterNumber(NumberEntity):
    """Number entity with IMEI support."""

    def __init__(self, hass, number_id, config, imei):
        self._imei = imei
        imei_short = imei[-4:] if len(imei) >= 4 else imei
        self.entity_id = f"number.{number_id}_{imei_short}"
        self._attr_unique_id = f"{number_id}_{imei}"
        # ... reste
```

#### Fichier: `datetime.py`

**Ligne 20-160** : Même pattern
```python
class ScooterDatetime(DatetimeEntity):
    """Datetime entity with IMEI support."""

    def __init__(self, hass, datetime_id, config, imei):
        self._imei = imei
        imei_short = imei[-4:] if len(imei) >= 4 else imei
        self.entity_id = f"datetime.{datetime_id}_{imei_short}"
        # ... reste
```

#### Fichier: `switch.py`

**Ligne 16-62** : Même pattern
```python
class ScooterSwitch(SwitchEntity):
    """Switch entity with IMEI support."""

    def __init__(self, hass, imei):
        self._imei = imei
        imei_short = imei[-4:] if len(imei) >= 4 else imei
        self.entity_id = f"switch.stop_trip_now_{imei_short}"
        # ... reste
```

---

### Phase 4: Automations (6 heures) ✅

#### Fichier: `automations.py`

**Stratégie** : Passer l'IMEI à `async_setup_automations()` et créer des entity IDs dynamiques

**A. Signature de la fonction (Ligne 332)**
```python
async def async_setup_automations(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    imei: str,  # Nouveau paramètre
) -> list:
    """Setup automations for a specific scooter IMEI."""

    # Helper pour générer entity IDs
    def entity_id(base: str) -> str:
        imei_short = imei[-4:] if len(imei) >= 4 else imei
        return f"{base}_{imei_short}"
```

**B. Remplacer toutes les références hardcodées (Lignes 279-311)**
```python
# Avant:
ENTITY_SPEED = "sensor.silence_scooter_speed"

# Après:
ENTITY_SPEED = entity_id("sensor.silence_scooter_speed")
ENTITY_LATITUDE = entity_id("sensor.silence_scooter_silence_latitude")
ENTITY_LONGITUDE = entity_id("sensor.silence_scooter_silence_longitude")
# ... etc pour toutes les entités
```

**C. Device Tracker avec IMEI (Ligne 292)**
```python
# Avant:
DEVICE_TRACKER_ID = "silence_scooter"

# Après:
imei_short = imei[-4:] if len(imei) >= 4 else imei
DEVICE_TRACKER_ID = f"silence_scooter_{imei_short}"
```

**D. Listeners avec entity IDs dynamiques**
Exemple (Ligne 1378-1390) :
```python
# Avant:
async_track_state_change_event(
    hass,
    ["sensor.silence_scooter_battery_soc"],
    update_battery_display
)

# Après:
async_track_state_change_event(
    hass,
    [entity_id("sensor.silence_scooter_battery_soc")],
    update_battery_display
)
```

---

### Phase 5: Integration Setup (2 heures) ✅

#### Fichier: `__init__.py`

**A. Passer IMEI aux plateformes (Ligne 35-39)**
```python
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Silence Scooter from a config entry."""

    # Récupérer et valider IMEI
    imei = entry.data.get(CONF_IMEI)
    if not imei:
        _LOGGER.error("IMEI not found in config entry")
        return False

    # Stocker l'IMEI dans hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "imei": imei,
        "sensors": {},
        "config": entry.data,
    }

    # Charger les plateformes (ils récupèrent IMEI depuis entry.data)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Setup automations avec IMEI
    cancel_listeners = await async_setup_automations(hass, entry, imei)
    hass.data[DOMAIN][entry.entry_id]["cancel_listeners"] = cancel_listeners

    # ... reste du code
```

**B. Services avec IMEI (Ligne 45-163)**
```python
async def reset_tracked_counters(call: ServiceCall) -> None:
    """Reset tracked counters for a specific IMEI."""
    target_imei = call.data.get("imei")  # Optionnel : service global ou par IMEI

    # Si IMEI fourni, ne réinitialiser que ce scooter
    if target_imei:
        for entry_id, data in hass.data[DOMAIN].items():
            if data.get("imei") == target_imei:
                imei_short = target_imei[-4:] if len(target_imei) >= 4 else target_imei
                # Reset entities pour cet IMEI
                await hass.services.async_call(
                    "number",
                    "set_value",
                    {
                        "entity_id": f"number.scooter_tracked_distance_{imei_short}",
                        "value": 0,
                    },
                )
                # ... autres resets
                break
    else:
        # Réinitialiser tous les scooters (comportement actuel)
        for entry_id, data in hass.data[DOMAIN].items():
            imei = data.get("imei")
            if imei:
                # Reset pour chaque IMEI
                pass
```

---

### Phase 6: Documentation (2 heures) ✅

#### Fichier: `strings.json`

Ajouter description pour le champ IMEI :
```json
{
  "config": {
    "step": {
      "user": {
        "data": {
          "imei": "IMEI of your Silence Scooter (15 digits)",
          ...
        },
        "description": "Enter your scooter's IMEI to configure this instance. You can add multiple scooters by installing the integration multiple times."
      }
    }
  }
}
```

#### Fichier: `examples/silence.yaml`

Mettre à jour avec exemple multi-scooters :
```yaml
# Configuration for multiple Silence S01 scooters
# Each scooter needs its own MQTT configuration with its unique IMEI

# ===== SCOOTER 1 (IMEI: 869123456789012) =====
mqtt:
  button:
    - name: "Silence Scooter Turn On 9012"
      command_topic: "home/silence-server/869123456789012/command/TURN_ON_SCOOTER"
      unique_id: "silence_scooter_turn_on_869123456789012"
      device:
        identifiers: ["869123456789012"]
        name: "Silence Scooter (9012)"
        manufacturer: "Seat"
        model: "Mo"

  sensor:
    - name: "Silence Scooter Speed 9012"
      state_topic: "home/silence-server/869123456789012/status/speed"
      unique_id: "silence_scooter_speed_869123456789012"
      device:
        identifiers: ["869123456789012"]
    # ... autres sensors pour scooter 1

# ===== SCOOTER 2 (IMEI: 869987654321098) =====
  button:
    - name: "Silence Scooter Turn On 1098"
      command_topic: "home/silence-server/869987654321098/command/TURN_ON_SCOOTER"
      unique_id: "silence_scooter_turn_on_869987654321098"
      device:
        identifiers: ["869987654321098"]
        name: "Silence Scooter (1098)"
        manufacturer: "Seat"
        model: "Mo"

  sensor:
    - name: "Silence Scooter Speed 1098"
      state_topic: "home/silence-server/869987654321098/status/speed"
      unique_id: "silence_scooter_speed_869987654321098"
      device:
        identifiers: ["869987654321098"]
    # ... autres sensors pour scooter 2
```

#### Fichier: `README.md`

Ajouter section multi-device :
```markdown
## Multi-Device Support

This integration supports multiple Silence S01 scooters. To add multiple scooters:

1. **Configure Silence Private Server** with multiple IMEIs in `configuration.json`:
   ```json
   {
     "IMEI_List": ["869123456789012", "869987654321098"],
     "BasePort": 19000
   }
   ```

2. **Configure MQTT** for each scooter in `configuration.yaml` (see `examples/silence.yaml`)

3. **Add Integration** once per scooter:
   - Go to Settings → Devices & Services → Add Integration
   - Search for "Silence Scooter"
   - Enter the IMEI of the scooter (15 digits)
   - Configure the integration
   - Repeat for each additional scooter

Each scooter will appear as a separate device with its own entities, trips history, and automations.
```

---

## 5. Backward Compatibility

### Stratégie

**Utilisateurs existants (sans IMEI)** :
- ❌ IMEI devient **obligatoire** dans cette version
- ⚠️ **Breaking change** : nécessite reconfiguration

**Migration Path** :
1. Utilisateur met à jour l'intégration
2. Config flow détecte absence d'IMEI
3. Demande à l'utilisateur d'entrer l'IMEI de son scooter
4. Recréé les entités avec suffixe IMEI
5. ⚠️ Perte de l'historique (entity IDs changent)

**Alternative : Mode Compatibilité (Optionnel)**
Pour éviter la perte d'historique :
```python
def generate_entity_id(base_id: str, imei: str | None) -> str:
    """Generate entity ID with optional IMEI suffix."""
    if imei:
        imei_short = imei[-4:] if len(imei) >= 4 else imei
        return f"{base_id}_{imei_short}"
    return base_id  # Pas de suffixe si IMEI absent (mode legacy)
```

**Recommandation** :
- Rendre IMEI obligatoire pour simplifier le code
- Documenter clairement le breaking change
- Fournir un script de migration d'historique (optionnel)

---

## 6. Tests à Effectuer

### Tests Unitaires
- ✅ Validation IMEI (format, longueur, caractères)
- ✅ Unicité IMEI (pas de doublon entre instances)
- ✅ Génération entity ID avec IMEI
- ✅ Device info avec IMEI

### Tests d'Intégration
- ✅ Installation de 1 scooter
- ✅ Installation de 2 scooters simultanés
- ✅ Installation de 3 scooters simultanés
- ✅ Suppression d'une instance
- ✅ Reconfiguration d'une instance

### Tests Fonctionnels
- ✅ Détection de trajet par scooter (isolation)
- ✅ Device tracker par scooter (positions séparées)
- ✅ Historique par scooter (pas de mélange)
- ✅ Services par scooter (`reset_tracked_counters`)
- ✅ MQTT routing (bon scooter reçoit bonnes données)

### Tests de Performance
- ✅ Latence avec 3 scooters vs 1 scooter
- ✅ Utilisation mémoire avec 3 scooters
- ✅ Pas de régression sur automations

---

## 7. Effort Estimé

| Phase | Tâches | Heures |
|-------|--------|--------|
| 1. Configuration | Config flow + validation IMEI | 4h |
| 2. Helpers | Device info + entity ID helper | 4h |
| 3. Entities | 4 fichiers (sensor, number, datetime, switch) | 8h |
| 4. Automations | Entity IDs dynamiques | 6h |
| 5. Setup | __init__.py + services | 2h |
| 6. Documentation | strings.json + examples + README | 2h |
| **Total Dev** | | **26h** |
| 7. Tests | Unitaires + intégration + fonctionnels | 10h |
| **Total** | | **36h** |

**Estimation finale** : **36-40 heures** (4-5 jours pour 1 développeur)

---

## 8. Risques et Mitigations

### Risque 1: Breaking Change (ÉLEVÉ)
**Impact** : Utilisateurs existants doivent reconfigurer
**Mitigation** :
- Documenter clairement dans release notes
- Fournir guide de migration
- Version bump majeure (2.0.0)

### Risque 2: MQTT Configuration Complexe (MOYEN)
**Impact** : Utilisateurs doivent dupliquer config MQTT pour chaque scooter
**Mitigation** :
- Exemple complet dans `examples/silence.yaml`
- Documentation step-by-step dans README
- FAQ dans issue #2

### Risque 3: Confusion Entity IDs (FAIBLE)
**Impact** : Utilisateurs doivent utiliser nouveaux entity IDs avec suffixe
**Mitigation** :
- Utiliser 4 derniers chiffres (lisibilité)
- Afficher IMEI dans device name
- Autocomplete dans automations

### Risque 4: Performance avec 3+ Scooters (FAIBLE)
**Impact** : Latence potentielle avec beaucoup de scooters
**Mitigation** :
- Tester avec 3 scooters
- Profiling si nécessaire
- Limiter à 5 scooters max (documentation)

---

## 9. Checklist d'Implémentation

### Pré-Dev
- [x] ~~Analyse du problème~~
- [x] ~~Exploration de l'architecture~~
- [x] ~~Conception de la solution~~
- [ ] Validation de la conception par un agent
- [ ] Approbation de l'approche

### Développement
- [ ] Phase 1: Configuration
  - [ ] Ajouter CONF_IMEI dans const.py
  - [ ] Retirer single_instance_allowed
  - [ ] Ajouter champ IMEI dans config flow
  - [ ] Implémenter validation IMEI
  - [ ] Vérifier unicité IMEI
- [ ] Phase 2: Helpers
  - [ ] Modifier get_device_info()
  - [ ] Créer generate_entity_id()
- [ ] Phase 3: Entities
  - [ ] Modifier sensor.py (6 classes)
  - [ ] Modifier number.py (1 classe)
  - [ ] Modifier datetime.py (1 classe)
  - [ ] Modifier switch.py (1 classe)
- [ ] Phase 4: Automations
  - [ ] Ajouter paramètre IMEI à async_setup_automations()
  - [ ] Créer helper entity_id()
  - [ ] Remplacer entity IDs hardcodées
  - [ ] Modifier device tracker ID
  - [ ] Mettre à jour listeners
- [ ] Phase 5: Setup
  - [ ] Récupérer IMEI dans async_setup_entry()
  - [ ] Passer IMEI aux plateformes
  - [ ] Mettre à jour services
- [ ] Phase 6: Documentation
  - [ ] Mettre à jour strings.json
  - [ ] Mettre à jour examples/silence.yaml
  - [ ] Mettre à jour README.md
  - [ ] Ajouter section multi-device

### Tests
- [ ] Tests unitaires
  - [ ] Validation IMEI
  - [ ] Unicité IMEI
  - [ ] Génération entity ID
  - [ ] Device info
- [ ] Tests d'intégration
  - [ ] 1 scooter
  - [ ] 2 scooters
  - [ ] 3 scooters
  - [ ] Suppression instance
  - [ ] Reconfiguration
- [ ] Tests fonctionnels
  - [ ] Détection trajet isolée
  - [ ] Device tracker séparé
  - [ ] Historique séparé
  - [ ] Services par scooter
  - [ ] MQTT routing

### Post-Dev
- [ ] Version bump (2.0.0)
- [ ] Release notes
- [ ] Guide de migration
- [ ] Fermer issue #2
- [ ] Push sur branche feature

---

## 10. Conclusion

La solution **multi-instances** est la meilleure approche pour ajouter le support de plusieurs scooters :

✅ **Avantages** :
- Simple à implémenter (26h dev vs 60-90h)
- Isolation naturelle des données
- UI Home Assistant standard
- Backward compatible avec migration documentée
- Risque faible de régression

✅ **Impact utilisateur** :
- Configuration claire : 1 instance = 1 scooter
- Gestion facile des scooters (ajout/suppression)
- Expérience utilisateur familière (standard Home Assistant)

✅ **Faisabilité technique** :
- Modifications ciblées (13 fichiers)
- Pas de refactoring massif
- Tests compréhensibles
- Déploiement progressif possible

**Recommandation** : ✅ GO pour l'implémentation

**Prochaine étape** : Lancer un agent de validation pour vérifier cette conception
