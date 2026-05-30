from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ProjectFilesTests(unittest.TestCase):
    def test_windows_start_script_exists(self) -> None:
        script = ROOT / "scripts" / "start_windows.bat"
        ps1 = ROOT / "scripts" / "start_windows.ps1"
        self.assertTrue(script.exists())
        self.assertTrue(ps1.exists())
        text = script.read_text(encoding="utf-8")
        self.assertIn("start_windows.ps1", text)
        self.assertIn("powershell.exe", text)
        self.assertIn("api_purecheck serve", ps1.read_text(encoding="utf-8"))
        self.assertIn("http://127.0.0.1:8765", ps1.read_text(encoding="utf-8"))

    def test_release_docs_and_package_script_exist(self) -> None:
        release_doc = ROOT / "docs" / "RELEASE.md"
        package_script = ROOT / "scripts" / "package_source.ps1"
        check_script = ROOT / "scripts" / "check_windows.ps1"
        self.assertTrue(release_doc.exists())
        self.assertTrue(package_script.exists())
        self.assertTrue(check_script.exists())
        self.assertTrue((ROOT / "LICENSE").exists())
        self.assertTrue((ROOT / "CHANGELOG.md").exists())
        self.assertTrue((ROOT / "CONTRIBUTING.md").exists())
        self.assertTrue((ROOT / "examples" / "batch.example.json").exists())
        self.assertTrue((ROOT / "docs" / "TROUBLESHOOTING.md").exists())
        self.assertTrue((ROOT / "docs" / "STATUS.md").exists())
        self.assertTrue((ROOT / "docs" / "MANUAL_TESTS.md").exists())
        self.assertTrue((ROOT / "docs" / "USER_ACTIONS.md").exists())
        self.assertTrue((ROOT / "docs" / "RELEASE_NOTES_1.0.0.md").exists())
        self.assertTrue((ROOT / "docs" / "GITHUB_RELEASE_CHECKLIST.md").exists())
        package_script_text = package_script.read_text(encoding="utf-8")
        self.assertIn("Compress-Archive", package_script_text)
        self.assertIn('"api_purecheck"', package_script_text)
        self.assertIn('"LICENSE"', package_script_text)
        self.assertIn("api-purecheck-windows.zip", package_script_text)
        self.assertIn("docs/USER_GUIDE.md", package_script_text)
        self.assertIn("scripts/start_windows.bat", package_script_text)
        self.assertNotIn('"tests"', package_script_text)
        self.assertNotIn('"scripts",', package_script_text)
        self.assertNotIn('"PROJECT_PLAN.md"', package_script_text)
        self.assertNotIn('"AGENTS.md"', package_script_text)
        self.assertNotIn('"pyproject.toml"', package_script_text)
        self.assertNotIn('".gitignore"', package_script_text)
        self.assertNotIn("scripts/check_windows.ps1", package_script_text)
        self.assertNotIn("scripts/ui_smoke_check.ps1", package_script_text)
        self.assertNotIn("scripts/package_source.ps1", package_script_text)
        self.assertIn("unittest discover", check_script.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
