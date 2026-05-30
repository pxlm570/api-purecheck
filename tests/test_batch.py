import unittest

from api_purecheck.batch import attention_targets, summarize_reports


class BatchSummaryTests(unittest.TestCase):
    def test_summarize_reports_and_attention_targets(self) -> None:
        reports = [
            {
                "status": "completed",
                "risk_level": "low",
                "claim_consistency": "high",
                "config": {"base_url": "https://ok.example/v1", "claimed_model": "gpt-4o"},
                "checks": {"model_identity": {"status": "clean"}},
            },
            {
                "status": "completed",
                "risk_level": "medium",
                "claim_consistency": "low",
                "config": {"base_url": "https://bad.example/v1", "claimed_model": "gpt-4o"},
                "checks": {"model_identity": {"status": "anomaly"}},
            },
            {
                "status": "auth_error",
                "risk_level": "unknown",
                "claim_consistency": "unavailable",
                "config": {"base_url": "https://auth.example/v1", "claimed_model": "gpt-4o"},
                "checks": {},
            },
        ]

        summary = summarize_reports(reports)
        self.assertEqual(summary["status_counts"]["completed"], 2)
        self.assertEqual(summary["risk_counts"]["medium"], 1)
        self.assertEqual(summary["claim_consistency_counts"]["unavailable"], 1)

        attention = attention_targets(reports)
        self.assertEqual(len(attention), 2)
        self.assertEqual(attention[0]["base_url"], "https://bad.example/v1")
        self.assertEqual(attention[0]["anomaly_checks"], ["model_identity"])


if __name__ == "__main__":
    unittest.main()
