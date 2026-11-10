"""Tests sans Home Assistant : python -m unittest discover tests"""
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

COMPONENT = Path(__file__).parent.parent / "custom_components" / "silencescooter"


def _load_definitions():
    # Chargé par chemin : le package lui-même importe Home Assistant.
    spec = importlib.util.spec_from_file_location("definitions", COMPONENT / "definitions.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NumberCaps(unittest.TestCase):
    def test_cumulative_counters_have_room(self):
        """Un compteur cumulé qui atteint son max fait échouer number.set_value
        à chaque fin de trajet (panne du 2026-11-05 : base énergie à 1000 kWh)."""
        numbers = _load_definitions().INPUT_NUMBERS
        for key in (
            "scooter_tracked_distance",
            "scooter_tracked_battery_used",
            "scooter_energy_consumption_base",
            "scooter_odo_debut",
            "scooter_odo_fin",
        ):
            self.assertGreaterEqual(numbers[key]["max"], 100000, key)


class RecordTime(unittest.TestCase):
    """Heure de mesure des relevés : bornes d'utilisation."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("record_time", COMPONENT / "record_time.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.usable = staticmethod(module.usable_record_time)

    def setUp(self):
        import datetime as dt
        self.dt = dt
        self.tz = dt.timezone(dt.timedelta(hours=1))
        self.now = dt.datetime(2026, 11, 10, 14, 0, 0, tzinfo=self.tz)
        self.quarter = dt.timedelta(minutes=15)

    def test_recent_reading_is_used(self):
        got = self.usable("2026-11-10T13:51:00+01:00", self.now, self.quarter)
        self.assertEqual(got, self.dt.datetime(2026, 11, 10, 13, 51, tzinfo=self.tz))

    def test_backlog_from_the_previous_trip_is_rejected(self):
        # relevé de 11:01 livré à 14:00 : ne doit pas dater le départ de 14:00
        self.assertIsNone(self.usable("2026-11-10T11:01:30+01:00", self.now, self.quarter))

    def test_reading_before_the_trip_start_is_rejected(self):
        start = self.dt.datetime(2026, 11, 10, 13, 55, tzinfo=self.tz)
        day = self.dt.timedelta(hours=24)
        self.assertIsNone(self.usable("2026-11-10T13:51:00+01:00", self.now, day, start))
        self.assertIsNotNone(self.usable("2026-11-10T13:58:00+01:00", self.now, day, start))

    def test_future_unknown_and_naive_are_rejected(self):
        for state in ("2026-11-10T14:05:00+01:00", "unknown", "unavailable", "", None,
                      "pas une date", "2026-11-10T13:51:00"):
            self.assertIsNone(self.usable(state, self.now, self.quarter), state)


try:
    import jinja2
except ImportError:  # pragma: no cover
    jinja2 = None


@unittest.skipUnless(jinja2, "jinja2 requis")
class BatteryCapacityTemplate(unittest.TestCase):
    """Capacité réelle = énergie cumulée / % cumulés des derniers trajets."""

    def _render(self, energy, soc):
        states = {"number.scooter_capacity_energy_sum": energy, "number.scooter_capacity_soc_sum": soc}
        template = _load_definitions().BATTERY_HEALTH_SENSORS["scooter_battery_capacity"]["value_template"]
        env = jinja2.Environment()
        env.globals["states"] = lambda entity_id: str(states[entity_id])
        return env.from_string(template).render().strip()

    def test_capacity_is_energy_per_hundred_percent(self):
        self.assertEqual(float(self._render(4.79, 100)), 4.79)

    def test_no_value_before_enough_trips(self):
        self.assertEqual(self._render(0.5, 10), "None")
        self.assertEqual(self._render("unknown", "unknown"), "None")

    def test_voltage_based_soc_sensors_are_gone(self):
        sensors = _load_definitions().BATTERY_HEALTH_SENSORS
        self.assertNotIn("scooter_battery_soc_calculated", sensors)
        self.assertNotIn("scooter_battery_soc_deviation", sensors)


@unittest.skipUnless(jinja2, "jinja2 requis")
class EnergyTemplate(unittest.TestCase):
    """scooter_energy_consumption : compteur à vie, hausse plafonnée à 5.6 kWh."""

    def _render(self, base, current, discharged, regenerated):
        states = {
            "sensor.silence_scooter_discharged_energy": discharged,
            "sensor.silence_scooter_regenerated_energy": regenerated,
            "number.scooter_energy_consumption_base": base,
            "sensor.scooter_energy_consumption": current,
        }
        template = _load_definitions().TRIGGER_SENSORS["scooter_energy_consumption"]["value_template"]
        env = jinja2.Environment()
        env.globals["states"] = lambda entity_id: str(states[entity_id])
        return float(env.from_string(template).render().strip())

    def test_normal_increase(self):
        self.assertEqual(self._render(1000, 1000, 1100.5, 100), 1000.5)

    def test_spike_right_after_a_trip_is_rejected(self):
        # base == capteur (cas de chaque fin de trajet / redémarrage) : +50 kWh
        self.assertEqual(self._render(1000, 1000, 1150, 100), 1000)

    def test_spike_mid_trip_is_rejected(self):
        self.assertEqual(self._render(990, 1000, 1150, 100), 1000)

    def test_fresh_install_takes_first_reading(self):
        self.assertEqual(self._render(0, 0, 1154.4, 100), 1054.4)

    def test_catch_up_when_engine_moved_the_base_ahead(self):
        self.assertEqual(self._render(1010, 1000, 1110.2, 100), 1010.2)

    def test_catch_up_ignores_a_spike(self):
        self.assertEqual(self._render(1010, 1000, 1200, 100), 1010)

    def test_never_decreases(self):
        self.assertEqual(self._render(1000, 1000, 1090, 100), 1000)

    def test_unreadable_base_does_not_lift_the_cap(self):
        # base pas encore chargée au démarrage : ce n'est pas "jamais initialisé"
        self.assertEqual(self._render("unknown", 0, 1154.4, 100), 0)

    def test_keeps_value_when_scooter_offline(self):
        self.assertEqual(self._render(1000, 1000, "unknown", "unknown"), 1000)


@unittest.skipUnless(
    all(shutil.which(tool) for tool in ("bash", "jq", "bc")), "bash, jq et bc requis"
)
class HistoryScript(unittest.TestCase):
    def _run(self, history, start, distance):
        args = ["30.0", distance, "10.0", start, start, "50.0", "5.0", "12.0"]
        return subprocess.run(
            ["bash", str(COMPONENT / "scripts" / "history.sh"), *args],
            env={**os.environ, "JSON_FILE": str(history)},
            capture_output=True, text=True, timeout=30,
        )

    def test_trips_are_prepended(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "history.json"
            first = self._run(history, "2026-01-01T10:00:00+01:00", "5.0")
            second = self._run(history, "2026-01-02T10:00:00+01:00", "0.0")
            self.assertEqual((first.returncode, second.returncode), (0, 0), first.stderr + second.stderr)
            trips = json.loads(history.read_text())
            self.assertEqual([t["start_time"][:10] for t in trips], ["2026-01-02", "2026-01-01"])
            self.assertEqual(float(trips[1]["efficiency_wh_km"]), 56.0)  # 5 % de 5600 Wh sur 5 km
            self.assertEqual(trips[0]["efficiency_wh_km"], "0")  # distance nulle : pas de division

    def test_empty_history_is_not_silently_kept_empty(self):
        """Un history.json vide passait pour valide : chaque trajet suivant
        était perdu, code retour 0."""
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "history.json"
            history.write_text("")
            result = self._run(history, "2026-01-01T10:00:00+01:00", "5.0")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(json.loads(history.read_text())), 1)

    def test_corrupt_history_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "history.json"
            history.write_text("{pas du json")
            result = self._run(history, "2026-01-01T10:00:00+01:00", "5.0")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(json.loads(history.read_text())), 1)
            self.assertTrue(list(Path(tmp).glob("history.json.corrupt.*")))


if __name__ == "__main__":
    unittest.main()
