from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class HandoffTests(unittest.TestCase):
    def test_staged_unstaged_and_untracked_files_are_all_handed_off(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            def git(*args):
                return subprocess.run(["git", "-C", folder, *args], check=True, capture_output=True)
            git("init", "-q")
            (repo / "staged file.txt").write_text("new")
            git("add", "staged file.txt")
            (repo / "staged file.txt").write_text("edited again")
            (repo / "untracked.txt").write_text("new")
            result = subprocess.run(["bash", str(ROOT / "scripts/make-handoff.sh"),
                                     "--repo", folder, "--check", "exit 7"],
                                    capture_output=True, text=True, check=True)
            files = result.stdout.split("- Changed files:")[1].split("- Key decisions:")[0]
            self.assertIn("staged file.txt", files)
            self.assertIn("untracked.txt", files)
            self.assertEqual(1, files.count("staged file.txt"))
            self.assertIn("exit 7", result.stdout)
