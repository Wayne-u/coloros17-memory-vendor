import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "collect.py"
spec = importlib.util.spec_from_file_location("memory_vendor_collect", SCRIPT)
collect = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collect)

# Sanitized synthetic fixture. No serials or files copied from a real phone.
LINE = (
    "10-04 14:26:01.440 1234 5678 D Postman-StorageHealthCheckItem: health info map : {"
    "RecordTime=2026-10-04 14:26:01, SerialNum=PRIVATE-NOT-SHARE, "
    "MarketName=Example Phone, DDRDev=Device version:DDR5|Device manufacture:Cxsh|D1y|16G|, "
    "MemoryDev=Device version:EXAMPLE-PART |Device manufacture:SAMSUNG |, "
    "StorageDev=Device version:2000|Device manufacture:SAMSUNG |, StorageSize=512}"
)


class FakeAdb:
    def __init__(self, fail_on=None):
        self.values = {"ro.product.model": "TEST", "ro.build.version.release": "17",
                       "log.tag." + collect.TAGS[0]: "WARN",
                       "log.tag." + collect.TAGS[1]: ""}
        self.fail_on = fail_on

    def property(self, key):
        return self.values[key]

    def set_property(self, key, value):
        if key == self.fail_on and value == "DEBUG":
            raise RuntimeError("Permission denied")
        self.values[key] = value

    def run(self, *args):
        if args[:3] == ("shell", "pm", "path"):
            return "package:/example/PostmanService.apk"
        if args[0] == "shell" and args[1].startswith("date "):
            return "10-04 14:26:00.000"
        raise AssertionError(args)

    def command(self, *args):
        return ["adb", "-s", "TEST"] + list(args)


class FakeProcess:
    def __init__(self, text):
        self.stdout = io.StringIO(text)
        self.running = True

    def poll(self):
        return None if self.running else 0

    def terminate(self):
        self.running = False

    def wait(self, timeout):
        self.running = False
        return 0


class CollectTests(unittest.TestCase):
    def test_extracts_correct_devices_and_excludes_private_fields(self):
        result = collect.parse_line(LINE)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["ram_manufacturer_reported"], "Cxsh")
        self.assertEqual(result["ufs_manufacturer_reported"], "SAMSUNG")
        self.assertEqual(result["ufs_model_reported"], "EXAMPLE-PART")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with contextlib.redirect_stdout(io.StringIO()):
                collect.save_result(result, directory)
            for name in collect.OUTPUT_NAMES:
                text = (directory / name).read_text(encoding="utf-8")
                self.assertNotIn("PRIVATE-NOT-SHARE", text)
                self.assertNotIn("SerialNum", text)
            self.assertEqual(json.loads((directory / collect.OUTPUT_NAMES[0]).read_text(
                encoding="utf-8"))["ufs_model_reported"], "EXAMPLE-PART")
            with self.assertRaises(FileExistsError):
                collect.save_result(result, directory)

    def test_missing_ram_remains_partial(self):
        line = LINE.replace("Device version:DDR5|Device manufacture:Cxsh|D1y|16G|", "null")
        result = collect.parse_line(line)
        self.assertEqual(result["status"], "partial")
        self.assertIsNone(result["ram_manufacturer_reported"])
        self.assertNotIn("ram_manufacturer_interpretation", result)

    def test_rejects_field_names_only_and_unrelated_logs(self):
        self.assertIsNone(collect.parse_line("DDRDev MemoryDev StorageSize"))
        self.assertIsNone(collect.parse_line(LINE.replace("Postman-StorageHealthCheckItem", "OtherTag")))
        self.assertIsNone(collect.parse_line(LINE.replace("Cxsh", "unknown").replace("SAMSUNG", "null")))

    def test_offline_uses_last_valid_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "capture.txt"
            log.write_text(LINE + "\n" + LINE.replace("EXAMPLE-PART", "SECOND-PART") + "\n",
                           encoding="utf-8")
            self.assertEqual(collect.parse_log(log)["ufs_model_reported"], "SECOND-PART")

    def test_live_success_restores_exact_original_values_and_stops_own_process(self):
        adb = FakeAdb()
        originals = adb.values.copy()
        process = FakeProcess(LINE + "\n")
        with patch.object(collect.subprocess, "Popen", return_value=process) as popen:
            with contextlib.redirect_stdout(io.StringIO()):
                result = collect.capture(adb, 5)
        self.assertEqual(result["capture_mode"], "live")
        self.assertEqual(adb.values, originals)
        self.assertFalse(process.running)
        command = popen.call_args.args[0]
        self.assertIn("-T", command)
        self.assertIn("10-04 14:26:00.000", command)
        self.assertNotIn("-c", command)

    def test_setting_failure_restores_prior_changes(self):
        adb = FakeAdb(fail_on="log.tag." + collect.TAGS[1])
        originals = adb.values.copy()
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "Permission denied"):
                collect.capture(adb, 5)
        self.assertEqual(adb.values, originals)

    def test_timeout_restores_properties(self):
        adb = FakeAdb()
        originals = adb.values.copy()
        process = FakeProcess("")
        # Keep the pipe open conceptually; advance time past the deadline.
        with patch.object(collect.subprocess, "Popen", return_value=process):
            with patch.object(collect.time, "monotonic", side_effect=[0, 10]):
                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(TimeoutError):
                        collect.capture(adb, 1)
        self.assertEqual(adb.values, originals)
        self.assertFalse(process.running)

    def test_interrupt_restores_properties(self):
        adb = FakeAdb()
        originals = adb.values.copy()
        with patch.object(collect.subprocess, "Popen", side_effect=KeyboardInterrupt):
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(KeyboardInterrupt):
                    collect.capture(adb, 5)
        self.assertEqual(adb.values, originals)


if __name__ == "__main__":
    unittest.main()
