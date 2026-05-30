import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest


PYTHON = sys.executable


class CliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [PYTHON, "-m", "api_purecheck", *args],
            check=False,
            text=True,
            capture_output=True,
        )

    def test_version(self) -> None:
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0)
        self.assertIn("api-purecheck 1.0.0", result.stdout)

    def test_check_dry_run_json_redacts_key(self) -> None:
        result = self.run_cli(
            "check",
            "--base-url",
            "https://example.com/v1",
            "--api-key",
            "TEST_API_KEY_1234567890",
            "--model",
            "gpt-4o",
            "--api-type",
            "openai-compatible",
            "--level",
            "quick",
            "--format",
            "json",
            "--dry-run",
        )
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "dry_run")
        self.assertEqual(payload["config"]["api_key"], "TES****7890")
        self.assertEqual(payload["estimated_request_count"], 3)
        self.assertNotIn("TEST_API_KEY_1234567890", result.stdout)

    def test_dry_run_warns_for_full_openai_endpoint_url(self) -> None:
        result = self.run_cli(
            "check",
            "--base-url",
            "https://example.com/v1/chat/completions",
            "--api-key",
            "TEST_API_KEY_1234567890",
            "--model",
            "gpt-4o",
            "--level",
            "quick",
            "--format",
            "json",
            "--dry-run",
        )
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["effective_base_url"], "https://example.com/v1")
        self.assertTrue(payload["warnings"])

    def test_check_requires_model(self) -> None:
        result = self.run_cli(
            "check",
            "--base-url",
            "https://example.com/v1",
            "--api-key",
            "TEST_API_KEY_1234567890",
            "--dry-run",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("claimed_model is required", result.stderr)

    def test_check_dry_run_html_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "reports" / "report.html"
            result = self.run_cli(
                "check",
                "--base-url",
                "https://example.com/v1",
                "--api-key",
                "TEST_API_KEY_1234567890",
                "--model",
                "gpt-4o",
                "--format",
                "html",
                "--output",
                str(output),
                "--dry-run",
            )
            self.assertEqual(result.returncode, 0)
            html = output.read_text(encoding="utf-8")
            self.assertIn("API PureCheck 纯度报告", html)
            self.assertNotIn("TEST_API_KEY_1234567890", html)

    def test_check_dry_run_markdown_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "reports" / "report.md"
            result = self.run_cli(
                "check",
                "--base-url",
                "https://example.com/v1",
                "--api-key",
                "TEST_API_KEY_1234567890",
                "--model",
                "gpt-4o",
                "--format",
                "markdown",
                "--output",
                str(output),
                "--dry-run",
            )
            self.assertEqual(result.returncode, 0)
            markdown = output.read_text(encoding="utf-8")
            self.assertIn("# API PureCheck 纯度报告", markdown)
            self.assertNotIn("TEST_API_KEY_1234567890", markdown)

    def test_monitor_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Path(temp_dir) / "config.json"
            config.write_text(
                json.dumps(
                    {
                        "base_url": "https://example.com/v1",
                        "api_key": "TEST_MONITOR_API_KEY",
                        "claimed_model": "gpt-4o",
                        "level": "quick",
                        "format": "json",
                    }
                ),
                encoding="utf-8",
            )
            result = self.run_cli(
                "monitor",
                "--config",
                str(config),
                "--runs",
                "2",
                "--interval-seconds",
                "0",
                "--dry-run",
            )
            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["monitor"]["estimated_total_requests"], 6)
            self.assertNotIn("TEST_MONITOR_API_KEY", result.stdout)

    def test_batch_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            batch_file = Path(temp_dir) / "batch.json"
            batch_file.write_text(
                json.dumps(
                    {
                        "defaults": {
                            "api_key": "TEST_BATCH_API_KEY",
                            "level": "quick",
                            "api_type": "openai-compatible",
                        },
                        "targets": [
                            {"base_url": "https://one.example/v1", "claimed_model": "gpt-4o"},
                            {"base_url": "https://two.example/v1", "claimed_model": "deepseek-v4-pro"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = self.run_cli("batch", "--file", str(batch_file), "--dry-run")
            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "dry_run")
            self.assertEqual(payload["target_count"], 2)
            self.assertEqual(payload["estimated_total_requests"], 6)
            self.assertNotIn("TEST_BATCH_API_KEY", result.stdout)

    def test_models_command(self) -> None:
        result = self.run_cli("models", "--provider", "anthropic")
        self.assertEqual(result.returncode, 0)
        self.assertIn("claude-sonnet-4-20250514", result.stdout)
        self.assertNotIn("gpt-4o-mini", result.stdout)

    def test_models_command_deepseek(self) -> None:
        result = self.run_cli("models", "--provider", "deepseek")
        self.assertEqual(result.returncode, 0)
        self.assertIn("deepseek-v4-pro", result.stdout)
        self.assertIn("deepseek-v4-flash", result.stdout)

    def test_models_command_cn_families(self) -> None:
        for provider, expected in [
            ("gpt", "gpt-4o"),
            ("claude", "claude-sonnet-4-20250514"),
            ("kimi", "moonshot-v1-8k"),
            ("glm", "glm-4-flash"),
            ("minimax", "MiniMax-Text-01"),
        ]:
            result = self.run_cli("models", "--provider", provider)
            self.assertEqual(result.returncode, 0)
            self.assertIn(expected, result.stdout)

    def test_profiles_command(self) -> None:
        result = self.run_cli("profiles")
        self.assertEqual(result.returncode, 0)
        self.assertIn("OpenAI GPT", result.stdout)
        self.assertIn("Anthropic Claude", result.stdout)
        self.assertIn("DeepSeek", result.stdout)
        self.assertIn("Moonshot / Kimi", result.stdout)
        self.assertIn("GLM / 智谱", result.stdout)
        self.assertIn("MiniMax", result.stdout)


if __name__ == "__main__":
    unittest.main()
