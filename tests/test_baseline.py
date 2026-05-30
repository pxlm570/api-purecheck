from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import tempfile
import threading
from pathlib import Path
import unittest

from api_purecheck.baseline import BaselineOptions, collect_baseline, load_baseline_stats
from api_purecheck.config import AuditConfig


class FakeBaselineHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        response = {
            "id": "chatcmpl-baseline",
            "object": "chat.completion",
            "model": payload.get("model", "gpt-4o"),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "42"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 8, "completion_tokens": 1, "total_tokens": 9},
        }
        body = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class BaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = HTTPServer(("127.0.0.1", 0), FakeBaselineHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_collect_baseline_writes_jsonl_without_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "baselines" / "gpt-4o.jsonl"
            config = AuditConfig(
                base_url=self.base_url,
                api_key="TEST_BASELINE_API_KEY",
                claimed_model="gpt-4o",
                level="quick",
            )
            report = collect_baseline(config, BaselineOptions(provider="openai", output=str(output)))
            text = output.read_text(encoding="utf-8")
            rows = [json.loads(line) for line in text.splitlines()]
            self.assertEqual(report["rows"], 3)
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]["provider"], "openai")
            self.assertEqual(rows[0]["claimed_model"], "gpt-4o")
            self.assertNotIn("TEST_BASELINE_API_KEY", text)
            self.assertNotIn("TEST_BASELINE_API_KEY", json.dumps(report, ensure_ascii=False))
            stats = load_baseline_stats(Path(temp_dir) / "baselines")
            self.assertIn("gpt-4o", stats)
            self.assertEqual(stats["gpt-4o"].rows, 3)
            self.assertTrue(stats["gpt-4o"].captured_at_min)
            self.assertTrue(stats["gpt-4o"].captured_at_max)


if __name__ == "__main__":
    unittest.main()
