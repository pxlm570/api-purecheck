from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading
import unittest

from api_purecheck.config import AuditConfig
from api_purecheck.runner import RunOptions, run_audit


class FakeAnthropicHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if payload.get("model") == "api-purecheck-invalid-model":
            body = b'{"type":"error","error":{"type":"not_found_error","message":"model not found"}}'
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if payload.get("stream"):
            body = (
                "event: message_start\n"
                'data: {"type":"message_start","message":{"id":"msg_test","type":"message","role":"assistant","model":"claude-sonnet-4-20250514","content":[]}}\n\n'
                "event: content_block_delta\n"
                'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"PURECHECK_STREAM_OK"}}\n\n'
                "event: message_delta\n"
                'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}\n\n'
                "event: message_stop\n"
                'data: {"type":"message_stop"}\n\n'
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        messages = payload.get("messages", [])
        prompt = messages[-1].get("content", "") if messages else ""
        if "17 + 25" in prompt:
            text = "42"
        elif '{"answer":"purecheck"}' in prompt:
            text = '{"answer":"purecheck"}'
        elif "PURECHECK_OK" in prompt:
            text = "PURECHECK_OK"
        elif "三个人里谁最高" in prompt:
            text = "小王"
        elif "alpha、beta、gamma" in prompt:
            text = "alpha\nbeta\ngamma"
        else:
            text = "ok"
        response = {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": payload.get("model", "claude-sonnet-4-20250514"),
            "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 3},
        }
        body = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class AnthropicRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = HTTPServer(("127.0.0.1", 0), FakeAnthropicHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_run_audit_with_anthropic_api_type(self) -> None:
        config = AuditConfig(
            base_url=self.base_url,
            api_key="TEST_ANTHROPIC_KEY",
            claimed_model="claude-sonnet-4-20250514",
            api_type="anthropic",
            level="quick",
            output_format="json",
        )
        report = run_audit(config, RunOptions(timeout_seconds=5))
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["request_count"], 3)
        self.assertEqual(report["claim_consistency"], "high")
        self.assertEqual(report["config"]["api_type"], "anthropic")
        self.assertNotIn("TEST_ANTHROPIC_KEY", json.dumps(report, ensure_ascii=False))

    def test_standard_run_checks_anthropic_stream(self) -> None:
        config = AuditConfig(
            base_url=self.base_url,
            api_key="TEST_ANTHROPIC_KEY",
            claimed_model="claude-sonnet-4-20250514",
            api_type="anthropic",
            level="standard",
            output_format="json",
        )
        report = run_audit(config, RunOptions(timeout_seconds=5))
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["planned_request_count"], 8)
        self.assertEqual(report["checks"]["stream_integrity"]["status"], "clean")
        self.assertEqual(report["checks"]["error_leakage"]["status"], "clean")
        self.assertIn("content_block_delta", report["stream_result"]["raw_event_types"])
        self.assertEqual(report["stream_result"]["event_type_counts"]["content_block_delta"], 1)
        self.assertEqual(report["stream_result"]["event_type_counts"]["message_stop"], 1)


class AnthropicV1OnlyHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/v1/messages":
            body = b"<!doctype html><html><body>Home</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        messages = payload.get("messages", [])
        prompt = messages[-1].get("content", "") if messages else ""
        if "17 + 25" in prompt:
            text = "42"
        elif '{"answer":"purecheck"}' in prompt:
            text = '{"answer":"purecheck"}'
        elif "PURECHECK_OK" in prompt:
            text = "PURECHECK_OK"
        elif "三个人里谁最高" in prompt:
            text = "小王"
        elif "alpha、beta、gamma" in prompt:
            text = "alpha\nbeta\ngamma"
        else:
            text = "ok"
        response = {
            "id": "msg_v1_test",
            "type": "message",
            "role": "assistant",
            "model": payload.get("model", "claude-opus-4-6"),
            "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 3},
        }
        body = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class AnthropicPathFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = HTTPServer(("127.0.0.1", 0), AnthropicV1OnlyHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_root_base_url_uses_v1_messages_for_anthropic(self) -> None:
        config = AuditConfig(
            base_url=self.base_url,
            api_key="TEST_ANTHROPIC_KEY",
            claimed_model="claude-opus-4-6",
            api_type="anthropic",
            level="quick",
            output_format="json",
        )
        report = run_audit(config, RunOptions(timeout_seconds=5))
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["claim_consistency"], "high")
        self.assertGreaterEqual(report["top_matches"][0]["probability"], 0.97)


if __name__ == "__main__":
    unittest.main()
