import unittest

from api_purecheck.config import AuditConfig
from api_purecheck.report import format_report
from api_purecheck.runner import dry_run_report


class ReportTests(unittest.TestCase):
    def test_html_report_escapes_values(self) -> None:
        config = AuditConfig(
            base_url="https://example.com/<v1>",
            api_key="TEST_SECRET_VALUE",
            claimed_model="gpt-4o",
            output_format="html",
        )
        report = dry_run_report(config)
        html = format_report(report, "html")
        self.assertIn("<!doctype html>", html)
        self.assertIn("API PureCheck 纯度报告", html)
        self.assertIn("https://example.com/&lt;v1&gt;", html)
        self.assertNotIn("TEST_SECRET_VALUE", html)
        self.assertIn("TES****ALUE", html)

    def test_text_report_includes_model_profile(self) -> None:
        report = {
            "status": "completed",
            "message": "ok",
            "config": {"base_url": "https://example.com/v1", "api_key": "TES****ALUE", "claimed_model": "gpt-4o", "level": "quick"},
            "claim_consistency": "high",
            "confidence": "medium",
            "top_matches": [{"model": "gpt-4o", "probability": 0.98}],
            "risk_level": "low",
            "checks": {
                "model_identity": {
                    "status": "clean",
                    "summary": "API 自报模型与声称模型一致。",
                    "evidence": [],
                }
            },
            "behavior_fingerprint": {
                "overall": {"score": 0.91, "probe_count": 5},
                "format_following": {"score": 1.0, "probe_count": 3},
            },
            "family_likelihoods": [
                {"family": "gpt", "probability": 0.71, "method": "heuristic-profile"},
                {"family": "unknown/out-of-set", "probability": 0.29, "method": "heuristic-profile"},
            ],
            "model_profile": {
                "claimed": {
                    "model": "gpt-4o",
                    "family": "gpt",
                    "display_name": "OpenAI GPT",
                    "match_type": "exact",
                    "confidence": "high",
                },
                "observed": [
                    {
                        "model": "gpt-4o",
                        "family": "gpt",
                        "display_name": "OpenAI GPT",
                        "match_type": "exact",
                        "confidence": "high",
                        "count": 5,
                    }
                ],
                "family_consistency": "same_family",
            },
        }
        text = format_report(report, "text")
        self.assertIn("模型族画像", text)
        self.assertIn("OpenAI GPT (gpt, exact)", text)
        self.assertIn("same_family", text)
        self.assertIn("行为画像", text)
        self.assertIn("模型族倾向", text)
        self.assertIn("其他模型", text)
        self.assertNotIn("unknown/out-of-set", text)

        markdown = format_report(report, "markdown")
        self.assertIn("# API PureCheck 纯度报告", markdown)
        self.assertIn("## 风险检查", markdown)
        self.assertIn("model_identity: clean", markdown)
        self.assertIn("其他模型", markdown)

        html = format_report(report, "html")
        self.assertIn("其他模型", html)


if __name__ == "__main__":
    unittest.main()
