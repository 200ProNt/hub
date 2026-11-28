import unittest
from unittest.mock import patch

from tools import monitor_telemetry as telemetry


class TelemetryTests(unittest.TestCase):
    def test_disks_keep_individual_rates_and_do_not_include_total(self):
        with patch.object(telemetry, "_rows", return_value=[
            ("_Total", 90, 100, 200), ("0 C:", 75, 10, 20), ("1 D:", None, 90, None),
        ]):
            self.assertEqual(telemetry.read("disk"), [
                {"name": "0 C:", "busy": 25, "read": 10, "write": 20},
                {"name": "1 D:", "busy": None, "read": 90, "write": None},
            ])

    def test_gpu_counts_the_busiest_engine_and_keeps_memory_only_adapters(self):
        adapter, other = "luid_0x0_0x1_phys_0", "luid_0x0_0x2_phys_0"
        with patch.object(telemetry, "_rows", side_effect=[
            [(f"pid_{pid}_{adapter}_eng_{engine}_engtype_3D", percent)
             for pid, engine, percent in [(42, 0, 15), (50, 0, 30), (42, 1, 27)]],
            [(adapter, 256), (other, 512)],
        ]):
            self.assertEqual(telemetry.read("gpu"), [
                {"name": "GPU 1", "busy": 45, "memory": 256},
                {"name": "GPU 2", "busy": None, "memory": 512},
            ])

    def test_missing_thermal_provider_does_not_report_a_temperature(self):
        with patch.object(telemetry, "_rows", return_value=[]):
            self.assertEqual(telemetry.read("temperature"), {"cpu": [], "gpu": []})

    def test_thermal_readings_only_use_recognized_hardware(self):
        with patch.object(telemetry, "_rows", return_value=[
            ("/amdcpu/0/temperature/0", "Core", "Temperature", 45.125),
            ("/gpu-nvidia/0/temperature/0", "Core", "Temperature", 39),
            ("/hdd/0/temperature/0", "Drive", "Temperature", 34),
            ("/intelcpu/0/temperature/1", "Core", "Temperature", float("nan")),
        ]):
            self.assertEqual(telemetry.read("temperature"), {
                "cpu": [{"name": "Core", "value": 45.1}],
                "gpu": [{"name": "Core", "value": 39.0}],
            })
