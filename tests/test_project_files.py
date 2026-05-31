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

    def test_release_docs_and_supporting_files_exist(self) -> None:
        check_script = ROOT / "scripts" / "check_windows.ps1"
        self.assertTrue(check_script.exists())
        self.assertTrue((ROOT / ".gitignore").exists())
        self.assertTrue((ROOT / "pyproject.toml").exists())
        self.assertTrue((ROOT / "LICENSE").exists())
        self.assertTrue((ROOT / "CHANGELOG.md").exists())
        self.assertTrue((ROOT / "examples" / "batch.example.json").exists())
        self.assertTrue((ROOT / "docs" / "TROUBLESHOOTING.md").exists())
        self.assertTrue((ROOT / "docs" / "USER_GUIDE.md").exists())
        self.assertTrue((ROOT / "docs" / "RELEASE_NOTES_1.0.0.md").exists())
        self.assertIn("unittest discover", check_script.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
