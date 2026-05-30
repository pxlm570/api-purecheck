from http.client import HTTPConnection
import json
import threading
import unittest

from api_purecheck.web import PureCheckHandler, PureCheckServer


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = PureCheckServer(("127.0.0.1", 0), PureCheckHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.host = "127.0.0.1"
        cls.port = cls.server.server_port

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, method: str, path: str, body: dict[str, object] | None = None) -> tuple[int, str]:
        conn = HTTPConnection(self.host, self.port, timeout=5)
        encoded = None
        headers = {}
        if body is not None:
            encoded = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=encoded, headers=headers)
        response = conn.getresponse()
        text = response.read().decode("utf-8")
        conn.close()
        return response.status, text

    def test_index_page(self) -> None:
        status, text = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("你的中转站，真的纯吗？", text)
        self.assertIn("API PureCheck</span>", text)
        self.assertIn('rel="icon"', text)
        self.assertIn("/favicon.svg?v=1.0.0", text)
        self.assertIn("API 纯度检测台", text)
        self.assertIn("快速 3 次", text)
        self.assertIn("标准 8 次", text)
        self.assertIn("深度 18 次", text)
        self.assertIn("1. 填写检测信息", text)
        self.assertIn("2. 查看检测结论", text)
        self.assertNotIn("data-preset", text)
        self.assertNotIn("preset-button", text)
        self.assertIn("标准模式预计 8 次请求", text)
        self.assertIn("model-family-select", text)
        self.assertIn("/api/model-profiles", text)
        self.assertIn("开始检测", text)
        self.assertIn("预计发起", text)
        self.assertIn("访问诊断", text)
        self.assertIn("模型族画像", text)
        self.assertIn("renderModelProfile", text)
        self.assertIn("行为画像", text)
        self.assertIn("renderBehaviorFingerprint", text)
        self.assertIn("模型族倾向", text)
        self.assertIn("renderFamilyLikelihoods", text)
        self.assertIn("displayModelLabel", text)
        self.assertIn("displayReportForUser", text)
        self.assertIn("其他模型", text)
        self.assertIn("labelProfileConsistency", text)
        self.assertNotIn("applyPreset", text)
        self.assertIn("apiTypeSelect.value = selected.api_types[0]", text)
        self.assertIn("常见 API 类型", text)
        self.assertIn("纯度结论：高度吻合", text)
        self.assertIn("下一步建议", text)
        self.assertIn("renderProgress", text)
        self.assertIn("verdictForReport", text)
        self.assertIn("预计消耗", text)
        self.assertIn("toggle-key-btn", text)
        self.assertIn("aria-pressed=\"false\"", text)
        self.assertIn("keyInput.type = shouldShow ? 'text' : 'password'", text)
        self.assertIn("downloadReport('json')", text)
        self.assertIn("downloadReport('markdown')", text)
        self.assertIn("downloadReport('html')", text)
        self.assertIn("reportToMarkdown", text)

    def test_health(self) -> None:
        status, text = self.request("GET", "/health")
        self.assertEqual(status, 200)
        payload = json.loads(text)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["version"], "1.0.0")
        self.assertEqual(payload["ui"], "2026-05-release")

    def test_favicon_returns_svg_icon(self) -> None:
        status, text = self.request("GET", "/favicon.ico")
        self.assertEqual(status, 200)
        self.assertIn("<svg", text)
        self.assertIn("#111827", text)
        self.assertIn("#38bdf8", text)

        status, text = self.request("GET", "/favicon.svg?v=1.0.0")
        self.assertEqual(status, 200)
        self.assertIn("<svg", text)

    def test_model_profiles_endpoint(self) -> None:
        status, text = self.request("GET", "/api/model-profiles")
        self.assertEqual(status, 200)
        payload = json.loads(text)
        families = [item["family"] for item in payload["profiles"]]
        self.assertIn("gpt", families)
        self.assertIn("claude", families)
        self.assertIn("deepseek", families)
        self.assertIn("kimi", families)
        self.assertIn("glm", families)
        self.assertIn("minimax", families)

    def test_dry_run_endpoint(self) -> None:
        status, text = self.request(
            "POST",
            "/api/dry-run",
            {
                "base_url": "https://example.com/v1",
                "api_key": "TEST_API_KEY_SECRET",
                "claimed_model": "gpt-4o",
                "level": "quick",
            },
        )
        self.assertEqual(status, 200)
        payload = json.loads(text)
        self.assertEqual(payload["status"], "dry_run")
        self.assertEqual(payload["estimated_request_count"], 3)
        self.assertEqual(payload["config"]["api_key"], "TES****CRET")
        self.assertNotIn("TEST_API_KEY_SECRET", text)

    def test_dry_run_validation_error(self) -> None:
        status, text = self.request("POST", "/api/dry-run", {"base_url": "https://example.com/v1"})
        self.assertEqual(status, 400)
        self.assertIn("api_key is required", text)


if __name__ == "__main__":
    unittest.main()
