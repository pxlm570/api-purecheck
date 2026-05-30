import unittest

from api_purecheck.model_profiles import all_model_names, get_profile, match_model_profile, profile_families


class ModelProfilesTests(unittest.TestCase):
    def test_cn_model_profiles(self) -> None:
        self.assertEqual(profile_families(), ["gpt", "claude", "deepseek", "kimi", "glm", "minimax"])
        self.assertIn("gpt-4o", all_model_names())
        self.assertIn("claude-sonnet-4-20250514", all_model_names())
        self.assertIn("deepseek-v4-pro", all_model_names())
        self.assertIn("moonshot-v1-128k", all_model_names())
        self.assertIn("glm-4-flash", all_model_names())
        self.assertIn("MiniMax-Text-01", all_model_names())

    def test_get_profile(self) -> None:
        profile = get_profile("deepseek")
        self.assertIsNotNone(profile)
        assert profile is not None
        self.assertIn("openai-compatible", profile.api_types)

    def test_match_model_profile_exact_and_prefix(self) -> None:
        exact = match_model_profile("gpt-4o")
        self.assertIsNotNone(exact)
        assert exact is not None
        self.assertEqual(exact.family, "gpt")
        self.assertEqual(exact.match_type, "exact")

        prefix = match_model_profile("claude-opus-4-6")
        self.assertIsNotNone(prefix)
        assert prefix is not None
        self.assertEqual(prefix.family, "claude")
        self.assertEqual(prefix.match_type, "prefix")

        self.assertIsNone(match_model_profile("unknown-model"))


if __name__ == "__main__":
    unittest.main()
