import tempfile
from pathlib import Path
import unittest

from api_purecheck.probes import build_probes, load_probes_from_file
from api_purecheck.runner import estimate_request_count


class ProbeFileTests(unittest.TestCase):
    def test_builtin_probe_counts(self) -> None:
        self.assertEqual(len(build_probes("quick")), 3)
        self.assertEqual(len(build_probes("standard")), 6)
        self.assertEqual(len(build_probes("deep")), 16)
        self.assertEqual(estimate_request_count("quick"), 3)
        self.assertEqual(estimate_request_count("standard"), 8)
        self.assertEqual(estimate_request_count("deep"), 18)

    def test_load_custom_probes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "probes.json"
            path.write_text(
                """
[
  {
    "probe_id": "custom.ok",
    "title": "OK",
    "prompt": "Only output OK",
    "validator": "contains",
    "expected": "OK",
    "max_tokens": 16
  }
]
""",
                encoding="utf-8",
            )
            probes = load_probes_from_file(path)
            self.assertEqual(len(probes), 1)
            self.assertEqual(probes[0].probe_id, "custom.ok")
            self.assertEqual(probes[0].expected, "OK")

    def test_reject_invalid_validator(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "probes.json"
            path.write_text(
                '[{"prompt": "x", "validator": "bad"}]',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_probes_from_file(path)


if __name__ == "__main__":
    unittest.main()
