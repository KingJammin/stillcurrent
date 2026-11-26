import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CLI = Path(__file__).resolve().parents[1] / "stillcurrent"
DATE = "2026-11-25"


class CleanupComparison(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "fixture"
        self.repo.mkdir()
        self.git("init")
        self.write("README.md", "[Setup](old-guide.md)\n")
        self.write("docs/setup.md", "# Setup\n")
        self.write("prototype/layout.json", '{"layout":"square"}\n')
        self.write("packaging.json", '{"layout":"prototype/layout.json"}\n')
        self.write("retired.py", "# Retired report generator\n")
        self.write("legacy.py", 'def read_v1(record):\n    return record["name"]\n')
        self.write("app.py", "from legacy import read_v1\n")
        self.profile = {
            "scope": "Integration fixture",
            "docs": ["README.md"],
            "references": [
                {"id": "prototype", "path": "prototype/layout.json",
                 "search": ["packaging.json"], "expectation": "move", "critical": True},
                {"id": "legacy", "path": "legacy.py", "token": "from legacy import read_v1",
                 "search": ["app.py"], "expectation": "retained", "critical": True},
                {"id": "retired", "path": "retired.py", "search": ["app.py"],
                 "expectation": "retire"},
            ],
            "artifact_rules": [
                {"id": "retired-file", "patterns": ["retired.py"], "title": "Retired file",
                 "next_step": "Verify callers and remove it."},
            ],
        }
        self.profile_path = self.root / "profile.json"
        self.profile_path.write_text(json.dumps(self.profile))
        self.commit("Stale guide, live prototype and retired file")
        audit = self.scan()
        self.assertEqual(audit.returncode, 0, audit.stderr)
        self.baseline = self.root / "before.json"
        self.baseline.write_text(audit.stdout)

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.repo), "-c", "user.name=Fixture", "-c",
             "user.email=fixture@example.invalid", *args],
            check=True, capture_output=True, text=True,
        ).stdout.strip()

    def write(self, path, content):
        destination = self.repo / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content)

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-m", message)

    def scan(self, *args):
        return subprocess.run(
            [sys.executable, str(CLI), str(self.repo), "--profile", str(self.profile_path),
             "--as-of", DATE, "--format", "json", *args],
            capture_output=True, text=True,
        )

    def compare(self, *findings):
        arguments = [argument for finding in findings for argument in ("--finding", finding)]
        return self.scan("--compare", str(self.baseline), *arguments)

    def apply_fixes(self):
        self.write("README.md", "[Setup](docs/setup.md)\n")
        self.write("assets/layout.json", (self.repo / "prototype/layout.json").read_text())
        self.write("packaging.json", '{"layout":"assets/layout.json"}\n')
        (self.repo / "prototype/layout.json").unlink()
        (self.repo / "retired.py").unlink()

    def test_verify_cleanup_and_retained_behavior(self):
        self.apply_fixes()
        self.commit("Fix guide and packaging, remove verified orphan")
        result = self.compare("doc:README.md", "reference:prototype", "artifact:retired-file")
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(result.stdout)
        self.assertEqual(evidence["resolved"], [
            "artifact:retired-file", "doc:README.md", "reference:prototype",
        ])
        self.assertEqual(evidence["regressions"], [])
        self.assertEqual(evidence["candidate_score"], 100)
        packaged = json.loads((self.repo / "packaging.json").read_text())
        self.assertEqual(json.loads((self.repo / packaged["layout"]).read_text()), {"layout": "square"})
        self.assertEqual(
            subprocess.check_output(
                [sys.executable, "-B", "-c", 'from app import read_v1; print(read_v1({"name":"v1"}))'],
                cwd=self.repo, text=True,
            ).strip(),
            "v1",
        )

    def test_lost_compatibility_evidence_blocks_verification(self):
        self.apply_fixes()
        self.write("app.py", "pass\n")
        self.commit("Fix guidance but lose legacy compatibility")
        result = self.compare("doc:README.md")
        self.assertEqual(result.returncode, 1, result.stderr)
        evidence = json.loads(result.stdout)
        self.assertEqual(evidence["resolved"], ["doc:README.md"])
        self.assertEqual(evidence["regressions"], [
            {"id": "reference:legacy", "before": "pass", "after": "unknown"},
        ])
        self.assertIsNone(evidence["candidate_score"])

    def test_changing_profile_cannot_hide_a_finding(self):
        self.apply_fixes()
        self.commit("Fix selected findings")
        self.profile["docs"] = []
        self.profile_path.write_text(json.dumps(self.profile))
        result = self.compare("doc:README.md")
        self.assertEqual(result.returncode, 2)
        self.assertIn("profile_sha256 differs", result.stderr)

    def test_unfixed_target_is_not_verified(self):
        self.write("notes.md", "# Unrelated notes\n")
        self.commit("Make an unrelated change")
        result = self.compare("doc:README.md")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(result.stdout)["remaining"], ["doc:README.md"])
