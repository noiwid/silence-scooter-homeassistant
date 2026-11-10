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
