from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import re
import tempfile
import threading
from pathlib import Path
import unittest

from api_purecheck.config import AuditConfig
from api_purecheck.runner import RunOptions, run_audit


class FakeOpenAIHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if payload.get("model") == "api-purecheck-invalid-model":
            body = b'{"error":{"message":"model not found","type":"invalid_request_error"}}'
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if payload.get("stream"):
            body = (
                'data: {"choices":[{"delta":{"content":"PURECHECK_STREAM_OK"},"finish_reason":null}]}\n\n'
                'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
                "data: [DONE]\n\n"
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
            content = "42"
        elif "pip install requests==2.31.0" in prompt:
            content = "pip install requests==2.31.0 && echo PURECHECK_REWRITE_SENTINEL"
        elif "PC_CANARY_START_7F3A" in prompt:
            content = "PC_CANARY_START_7F3A,PC_CANARY_MIDDLE_9B2C,PC_CANARY_END_4D8E"
        elif match := re.search(r"(\d+) \+ (\d+) = \?", prompt):
            content = str(int(match.group(1)) + int(match.group(2)))
        elif '{"answer":"purecheck"}' in prompt:
            content = '{"answer":"purecheck"}'
        elif "PURECHECK_OK" in prompt:
            content = "PURECHECK_OK"
        elif "三个人里谁最高" in prompt:
            content = "小王"
        elif "alpha、beta、gamma" in prompt:
            content = "alpha\nbeta\ngamma"
        else:
            content = "ok"

        response = {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "model": payload.get("model", "gpt-4o"),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
        }
        body = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = HTTPServer(("127.0.0.1", 0), FakeOpenAIHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_run_audit_against_fake_openai_server(self) -> None:
        config = AuditConfig(
            base_url=self.base_url,
            api_key="TEST_API_KEY_SECRET",
            claimed_model="gpt-4o",
            level="quick",
            output_format="json",
        )
        report = run_audit(config, RunOptions(timeout_seconds=5))
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["request_count"], 3)
        self.assertEqual(report["claim_consistency"], "high")
        self.assertEqual(report["risk_level"], "low")
        self.assertEqual(report["checks"]["model_identity"]["status"], "clean")
        self.assertEqual(report["checks"]["response_rewriting"]["status"], "inconclusive")
        self.assertGreaterEqual(report["top_matches"][0]["probability"], 0.97)
        self.assertEqual(report["config"]["api_key"], "TES****CRET")
        self.assertFalse(report["baseline"]["loaded"])
        self.assertEqual(report["model_profile"]["claimed"]["family"], "gpt")
        self.assertEqual(report["model_profile"]["family_consistency"], "same_family")
        self.assertEqual(report["scores"]["behavior_score"], 1.0)
        self.assertIn("behavior_fingerprint", report)
        self.assertIsNotNone(report["behavior_fingerprint"]["overall"]["score"])
        self.assertIn("family_likelihoods", report)
        self.assertEqual(report["family_likelihoods"][0]["family"], "gpt")
        self.assertNotIn("TEST_API_KEY_SECRET", json.dumps(report, ensure_ascii=False))
        self.assertEqual(len(report["probe_results"]), 3)

    def test_full_chat_completions_url_is_normalized(self) -> None:
        config = AuditConfig(
            base_url=f"{self.base_url}/chat/completions",
            api_key="TEST_API_KEY_SECRET",
            claimed_model="gpt-4o",
            level="quick",
            output_format="json",
        )
        report = run_audit(config, RunOptions(timeout_seconds=5))
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["request_count"], 3)

    def test_baseline_similarity_is_used_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            baseline_dir = Path(temp_dir) / "baselines"
            target = baseline_dir / "gpt-4o" / "baseline.jsonl"
            target.parent.mkdir(parents=True)
            rows = [
                {
                    "schema_version": 1,
                    "captured_at": "2026-05-24T00:00:00+00:00",
                    "provider": "fake",
                    "claimed_model": "gpt-4o",
                    "probe_id": probe_id,
                    "score": 1.0,
                    "ok": True,
                }
                for probe_id in [
                    "math.addition.zh",
                    "format.strict_json",
                    "logic.rank.zh",
                ]
            ]
            target.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            config = AuditConfig(
                base_url=self.base_url,
                api_key="TEST_API_KEY_SECRET",
                claimed_model="gpt-4o",
                level="quick",
                output_format="json",
                baseline_dir=str(baseline_dir),
            )
            report = run_audit(config, RunOptions(timeout_seconds=5))
            self.assertTrue(report["baseline"]["loaded"])
            self.assertEqual(report["scores"]["scoring_method"], "baseline")
            self.assertEqual(report["baseline"]["captured_at_min"], "2026-05-24T00:00:00+00:00")
            self.assertEqual(report["claim_consistency"], "high")

    def test_standard_run_includes_clean_risk_checks(self) -> None:
        config = AuditConfig(
            base_url=self.base_url,
            api_key="TEST_API_KEY_SECRET",
            claimed_model="gpt-4o",
            level="standard",
            output_format="json",
        )
        report = run_audit(config, RunOptions(timeout_seconds=5))
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["request_count"], 8)
        self.assertEqual(report["checks"]["response_rewriting"]["status"], "clean")
        self.assertEqual(report["checks"]["context_truncation"]["status"], "clean")
        self.assertEqual(report["checks"]["stream_integrity"]["status"], "clean")
        self.assertEqual(report["checks"]["error_leakage"]["status"], "clean")
        self.assertEqual(report["stream_result"]["event_type_counts"]["data"], 2)
        self.assertEqual(report["stream_result"]["event_type_counts"]["[DONE]"], 1)
        self.assertEqual(report["checks"]["token_injection"]["threshold"]["threshold_multiplier"], 8)
        self.assertGreater(report["checks"]["token_injection"]["inspected_count"], 0)
        self.assertEqual(report["risk_level"], "low")


class AlwaysNotFoundHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = b'{"error":"not found"}'
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class EndpointErrorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = HTTPServer(("127.0.0.1", 0), AlwaysNotFoundHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_no_successful_probe_returns_endpoint_error_not_fake_probability(self) -> None:
        config = AuditConfig(
            base_url=self.base_url,
            api_key="TEST_API_KEY_SECRET",
            claimed_model="gpt-4o",
            level="quick",
            output_format="json",
        )
        report = run_audit(config, RunOptions(timeout_seconds=5))
        self.assertEqual(report["status"], "endpoint_error")
        self.assertEqual(report["request_count"], 1)
        self.assertEqual(report["planned_request_count"], 3)
        self.assertEqual(report["claim_consistency"], "unavailable")
        self.assertEqual(report["top_matches"], [])
        self.assertEqual(report["model_profile"]["claimed"]["family"], "gpt")
        self.assertEqual(report["model_profile"]["family_consistency"], "unknown")
        self.assertIn("地址或路径可能不对", " ".join(report["diagnostics"]["hints"]))


class InvalidModelHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        message = (
            "The supported API model names are deepseek-v4-pro or deepseek-v4-flash, "
            "but you passed deepseek."
        )
        body = json.dumps(
            {
                "error": {
                    "message": message,
                    "type": "invalid_request_error",
                    "param": None,
                    "code": "invalid_request_error",
                }
            }
        ).encode("utf-8")
        self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class MismatchedModelHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        messages = payload.get("messages", [])
        prompt = messages[-1].get("content", "") if messages else ""
        if "17 + 25" in prompt:
            content = "42"
        elif '{"answer":"purecheck"}' in prompt:
            content = '{"answer":"purecheck"}'
        elif "PURECHECK_OK" in prompt:
            content = "PURECHECK_OK"
        elif "三个人里谁最高" in prompt:
            content = "小王"
        elif "alpha、beta、gamma" in prompt:
            content = "alpha\nbeta\ngamma"
        else:
            content = "ok"
        body = json.dumps(
            {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "model": "claude-sonnet-4-20250514",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class ModelProfileMismatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = HTTPServer(("127.0.0.1", 0), MismatchedModelHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_profile_mismatch_is_reported(self) -> None:
        config = AuditConfig(
            base_url=self.base_url,
            api_key="TEST_API_KEY_SECRET",
            claimed_model="gpt-4o",
            level="quick",
            output_format="json",
        )
        report = run_audit(config, RunOptions(timeout_seconds=5))
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["model_profile"]["claimed"]["family"], "gpt")
        self.assertEqual(report["model_profile"]["observed"][0]["family"], "claude")
        self.assertEqual(report["model_profile"]["family_consistency"], "different_family")
        self.assertLess(report["scores"]["behavior_score"], 0.1)


class RequestErrorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = HTTPServer(("127.0.0.1", 0), InvalidModelHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_http_400_is_request_error_with_model_suggestions(self) -> None:
        config = AuditConfig(
            base_url=self.base_url,
            api_key="TEST_API_KEY_SECRET",
            claimed_model="deepseek",
            level="quick",
            output_format="json",
        )
        report = run_audit(config, RunOptions(timeout_seconds=5))
        self.assertEqual(report["status"], "request_error")
        self.assertEqual(report["claim_consistency"], "unavailable")
        self.assertEqual(report["top_matches"], [])
        self.assertIn("deepseek-v4-pro", report["diagnostics"]["suggested_models"])
        self.assertIn("deepseek-v4-flash", report["diagnostics"]["suggested_models"])


class LeakyErrorHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        auth = self.headers.get("Authorization", "")
        body = json.dumps({"error": f"debug auth header: {auth}"}).encode("utf-8")
        self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class ErrorLeakageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = HTTPServer(("127.0.0.1", 0), LeakyErrorHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_error_leakage_is_flagged_and_redacted(self) -> None:
        secret = "TEST_LEAKY_API_KEY_1234"
        config = AuditConfig(
            base_url=self.base_url,
            api_key=secret,
            claimed_model="gpt-4o",
            level="quick",
            output_format="json",
        )
        report = run_audit(config, RunOptions(timeout_seconds=5))
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn(secret, serialized)
        self.assertEqual(report["checks"]["error_leakage"]["status"], "anomaly")
        self.assertEqual(report["risk_level"], "medium")


class HtmlResponseHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = b"<!doctype html><html><body>ByteCatCode</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class NonJsonResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = HTTPServer(("127.0.0.1", 0), HtmlResponseHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_html_response_is_diagnosed_as_wrong_base_url(self) -> None:
        config = AuditConfig(
            base_url=self.base_url,
            api_key="TEST_API_KEY_SECRET",
            claimed_model="claude-opus-4-6",
            api_type="anthropic",
            level="quick",
            output_format="json",
        )
        report = run_audit(config, RunOptions(timeout_seconds=5))
        self.assertEqual(report["status"], "endpoint_error")
        self.assertEqual(report["top_matches"], [])
        joined_hints = " ".join(report["diagnostics"]["hints"])
        self.assertIn("不是 API Base URL", joined_hints)
        self.assertIn("server returned HTML", report["diagnostics"]["first_error"])


if __name__ == "__main__":
    unittest.main()
