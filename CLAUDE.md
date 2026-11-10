# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Home Assistant **custom integration** (`silencescooter`) for Silence S01 / SEAT MÓ electric scooters. It consumes MQTT telemetry produced by the external [Silence Private Server](https://github.com/lorenzo-deluca/silence-private-server) and layers on automatic trip detection, energy/cost tracking, battery-health diagnostics, and trip history. There is **no build system, no test suite, and no app to run here** — it is pure Python that runs inside Home Assistant's event loop. The repo is distributed via HACS; the only "code" outside `custom_components/silencescooter/` is documentation and dashboard examples.

## Working on this codebase

- **Almost no tests, no lint config.** The only tests are `tests/test_basics.py` (number caps + `history.sh`, no Home Assistant needed): `python -m unittest discover tests` — the `history.sh` ones need `bash`, `jq`, `bc` and are skipped otherwise. Don't invent other `pytest`/`npm`/`make` commands. Real validation happens by loading the integration in a real Home Assistant instance and reading logs (Settings → System → Logs). The logger name is `custom_components.silencescooter`.
- **Async-only.** Everything runs on HA's event loop. Any blocking I/O (file writes, subprocess, the `history.sh` call) MUST go through `hass.async_add_executor_job(...)`. See `helpers.log_event` / `helpers.update_history` for the pattern.
- **Do not bump `version` in `manifest.json` by hand.** A GitHub Action (`.github/workflows/update-version-on-release.yml`) rewrites it from the release tag on publish. Recent commits like `chore: set version to 1.3.7` are produced by that bot, not manually.
- **Python is the requirement, but `history.sh` needs `bash`, `jq`, and `bc`** on the host. This is fine inside HAOS/containers but is why trip history writes go through a shell script rather than pure Python.
- Minimum HA version is **2024.11.0** (declared in `manifest.json` and `hacs.json`); the timer/`datetime` entity features depend on it.

## Architecture: the trip-tracking state machine

The integration's real complexity is **not** the entity platforms — it is the event-driven trip detection engine in `automations.py` (~1900 lines). Understanding the data flow is essential before touching anything:

```
Scooter → MQTT → Silence Private Server → MQTT topics
  → HA MQTT sensors (sensor.silence_scooter_*)        [raw telemetry, external to this repo]
  → automations.py state-change listeners             [the engine]
  → writable/number/datetime entities (sensor.scooter_*, number.scooter_*)  [trip state]
  → history.sh → /config/silencescooter/history.json  [persistence]
```

**Two sensor namespaces, do not confuse them:**
- `sensor.silence_scooter_*` — **raw MQTT telemetry** (speed, odo, battery_soc, status, lat/lon…). Created by MQTT Discovery (see `__init__.publish_mqtt_discovery_configs`) or the manual `examples/silence.yaml`. This integration *reads* these; it does not own them.
- `sensor.scooter_*` / `number.scooter_*` / `datetime.scooter_*` — **owned by this integration**, defined in `definitions.py`, instantiated by the platform files. These hold derived trip state and stats.

### Trip lifecycle (the part most likely to break)

All of this lives in `async_setup_automations()` in `automations.py`. The trip "active" predicate is `is_trip_active()`: a trip is active when `datetime.scooter_end_time` is the sentinel `1970-01-01` (or a future time) and the start is < 24h old.

- **Start** (`handle_scooter_last_start` → `_do_last_start`): triggered when `sensor.scooter_is_moving` goes `→ on` **and** raw `sensor.silence_scooter_status` is `3` (idle/red-light) or `4` (moving). Captures `odo_debut`, `battery_soc_debut`, `start_time`; resets pauses and the `1970` end-time sentinel.
- **Stop is deliberately always delayed** (`handle_trip_status_off`). There is no immediate-stop path any more (it was removed, on purpose) — even `status=0` / battery-removed go through the delayed path. Two timers run concurrently: a **confirmation delay** (`CONF_CONFIRMATION_DELAY`, default 120s, anti-bounce against MQTT flapping / traffic lights) and a **tolerance timer** (`CONF_PAUSE_MAX_DURATION`, default 5min, lets short errands keep the trip alive). If the scooter restarts (`trip_status → on`) both timers are cancelled and the pause is recorded. **Read the long comment block at the top of the delayed-stop branch before changing this** — it documents why an immediate stop on a transient glitch is worse than a 7-minute-late stop.
- **Watchdog** (`watchdog_check_trip_end`, every 5min): closes "stuck" trips when the scooter goes silent (garage/tunnel) — no MQTT update for `CONF_WATCHDOG_DELAY` minutes. Without it, a trip that never receives "scooter off" would stay open forever.
- **Continuous tracking** (`handle_track_odo` / `handle_track_battery`): keep `number.scooter_odo_fin` and `number.scooter_battery_soc_fin` in sync *during* the trip so `do_stop_trip` has good values even if the MQTT sensor is unavailable at the exact stop moment. These also **repair stale `_debut` values** (detecting a > 5 km ODO jump or > 10% SoC jump that indicates the value captured at start was a cached/stale reading). Repair is gated by grace periods (10s after trip start, 10s after HA startup) to avoid racing `_do_last_start`.
- **`do_stop_trip`** (module-level, not a closure): orchestrates the final computation — distance = `odo_fin − odo_debut`, net duration (minus pauses), avg/max speed, battery consumption — then calls `do_update_trips_history`. Guarded by a per-IMEI `stop_trip_in_progress` lock in `hass.data` to prevent double-recording from flapping events.

### Why trip state lives in `hass.data`, not closures

`do_stop_trip` is a module-level function but the tracking handlers are closures inside `async_setup_automations`. They share mutable trip flags (`last_trip_start_monotonic`, `odo_tracking_fired`, `battery_tracking_fired`) via `hass.data[DOMAIN]["trip_tracking_state"]` (one key per IMEI in multi-device, see `_tracking_key`), wrapped in a `_StateRef` shim so the closure code can use `x["value"]` syntax. If you add cross-function trip state, follow this pattern rather than module globals.

### The writable-sensor registry

`automations.py` cannot call HA services to set its own `sensor.scooter_*` values (sensors aren't service-settable). Instead, `ScooterWritableSensor` and `ScooterUtilityMeterSensor` register themselves into `hass.data[DOMAIN]["sensors"][entity_id]` inside `async_added_to_hass`, and `automations.set_writable_sensor_value()` looks them up and calls `async_set_native_value()` directly. The `restore_energy_costs` service mutates utility-meter sensor objects (`_attr_native_value`, `_cycle_start_value`) the same way. Numbers and datetimes, by contrast, *are* set via normal `hass.services.async_call("number"/"datetime", "set_value", …)`.

## Multi-device (multi-scooter) mode

Single-scooter is the default and must stay **byte-for-byte backward compatible with v1.0.4** (no IMEI in entity IDs, device identifier `("silence_scooter", "Silence Scooter")`). Multi-device mode (opt-in checkbox + IMEI) inserts `_XXXX` (last 4 IMEI digits) after the first `scooter_` token in every entity ID.

The single mechanism for this is **`helpers.insert_imei_in_entity_id(entity_id, imei, multi_device)`**. Almost every entity reference in `automations.py` and `do_stop_trip` goes through a local `entity_id(base)` helper that wraps it. **Any new entity reference or template must be routed through this helper / `adapt_template_for_multi_device` (in `sensor.py`) or it will silently break multi-device installs.** When `multi_device=False` the function is a no-op, which is what preserves single-device compatibility.

## File map

- `__init__.py` — entry setup/unload/reload, service registration (`reset_tracked_counters`, `restore_energy_costs`), **MQTT Discovery publisher** (publishes ~50 sensor/binary_sensor/button configs per IMEI), and the one-time persistent-data migration.
- `const.py` — domain, config keys + defaults, **and persistent paths**. Note `PERSISTENT_DATA_PATH = /config/silencescooter/` lives *outside* the integration folder; pre-1.3.3 data lived in `custom_components/.../data/` (which HACS wipes on update) and is migrated once at startup via `_migrate_persistent_data`.
- `definitions.py` — declarative dicts that define every owned entity: `WRITABLE_SENSORS`, `INPUT_NUMBERS`, `INPUT_DATETIMES`, `INPUT_BOOLEANS`, `TRIGGER_SENSORS`, `TEMPLATE_SENSORS`, `ENERGY_COST_SENSORS`, `BATTERY_HEALTH_SENSORS`, `USAGE_STATISTICS_SENSORS`, `UTILITY_METERS`. Most derived sensors are Jinja `value_template`s evaluated by `ScooterTemplateSensor`/`ScooterTriggerSensor`. **Add a sensor by adding to the right dict here**, not by writing a new class.
- `sensor.py` — sensor entity classes + `async_setup_entry`, which iterates the definition dicts. `ScooterTemplateSensor` (template-evaluated), `ScooterTriggerSensor` (re-evaluates on triggers / time pattern), `ScooterWritableSensor` (set by automations), `ScooterTripsSensor` (trip count + `history` attribute = last 10 trips), `ScooterUtilityMeterSensor`, `ScooterErrorDetectionSensor` (diagnostic surface for `errors.py`).
- `number.py` / `datetime.py` / `switch.py` — the internal-state entity platforms. All extend `RestoreEntity` so trip state survives HA restarts.
- `automations.py` — the trip engine (see above). `async_setup_automations` returns a list of cancel callbacks; `setup_persistent_sensors_update` mirrors raw MQTT into the persistent display sensors (`scooter_battery_display`, `scooter_odo_display`, regeneration %).
- `helpers.py` — `insert_imei_in_entity_id`, `get_device_info`, date validators (`is_date_valid` rejects the `1970` sentinel), `log_event`, and `update_history` (the subprocess bridge to `history.sh`).
- `errors.py` — `ErrorDetector`, one instance per config entry, with category/severity enums and rolling-window pattern detection; surfaced through `ScooterErrorDetectionSensor`. Get the active detector via `get_error_detector(hass[, entry_id])`.
- `config_flow.py` — UI config + options flow; discovers candidate tariff/temperature sensors by keyword/device-class.
- `scripts/history.sh` — bash/`jq` appender that prepends a trip to `history.json`. Path comes from the `JSON_FILE` env var set by `helpers.update_history`; it also computes `efficiency_wh_km` using a hard-coded **5.6 kWh** pack capacity.
- `examples/silence.yaml` — fallback **manual** MQTT config (only needed if Discovery is disabled). `lovelace_silence*.yaml` — example dashboards (FR/EN).
- `translations/` + `strings.json` — config-flow i18n (FR/EN).

## Conventions and gotchas

- **Code comments and log strings are bilingual** (mostly French, some English). Match the surrounding language of the file/function you edit rather than imposing one.
- **`1970-01-01` is a sentinel**, not a bug — it marks "trip in progress / no end time yet". `is_date_valid()` treats `1969`/`1970` strings as invalid on purpose.
- **Battery capacity 5.6 kWh (S01) is hard-coded in several places** (`history.sh`, `const.DEFAULT_BATTERY_CAPACITY`, several templates in `definitions.py`). If you make it configurable, all of these must change together.
- **Defensive value clamping is intentional everywhere** (distance capped at 500 km, duration at 1440 min, battery consumption clamped to 0–100%, energy templates reject negatives). These guard against upstream MQTT sensor glitches poisoning history and utility meters — see the dated comment in the `scooter_energy_consumption` template. Don't remove them as "dead code."
- **Trip-history validation is two-tier** (`do_update_trips_history`): only physically impossible data (avg speed > 120 km/h) is hard-rejected; merely suspicious trips are logged as soft warnings and still recorded. This deliberately loosens earlier strict validation that was dropping real trips.
- The README documents `docs/CONFIGURATION.md`, `docs/DEBUGGING.md`, and `docs/FAQ.md`, but **only `docs/ENTITIES.md` and `docs/HISTORY.md` actually exist.** Don't link to the missing ones as if they're present.
- `.gitignore` excludes `.claude/`, `*.log`, and `*.perso` — local session artifacts won't be committed.

- **Deploy from git, never from the Windows working tree**: a CRLF `history.sh` fails under bash on the HA host. `.gitattributes` (`* text=auto eol=lf`) makes `git archive <ref> custom_components/silencescooter | ssh … tar -x` emit LF; after deploying, compare md5 on the host with `git show <ref>:<file> | md5sum`.
