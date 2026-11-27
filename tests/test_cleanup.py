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
        self.baseline = self.root / "before.json"
        self.commit("Stale guide, live prototype and retired file")
        self.save_baseline()

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

    def save_baseline(self):
        self.profile_path.write_text(json.dumps(self.profile))
        audit = self.scan()
        self.assertEqual(audit.returncode, 0, audit.stderr)
        self.baseline.write_text(audit.stdout)
        return json.loads(audit.stdout)

    def save_scored_baseline(self):
        # The retirement candidate is unreferenced but still tracked, so its
        # reference check would lower code coverage enough to withhold the score.
        self.profile["references"] = [rule for rule in self.profile["references"]
                                      if rule["id"] != "retired"]
        self.assertIsNotNone(self.save_baseline()["score"])

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

    def test_new_broken_link_is_detected_at_the_same_score(self):
        self.save_scored_baseline()
        self.write("README.md", "\n[Setup](./old-guide.md)\n[New](new-guide.md)\n")
        self.commit("Move the old link and introduce another broken link")
        cleanup = self.compare("doc:README.md")
        weekly = self.scan("--compare", str(self.baseline), "--monitor", "--as-of", "2026-12-02")
        for result in (cleanup, weekly):
            with self.subTest(args=result.args):
                self.assertEqual(result.returncode, 1, result.stderr)
                evidence = json.loads(result.stdout)
                self.assertEqual(evidence["baseline_score"], evidence["candidate_score"])
                self.assertIsNotNone(evidence["baseline_score"])
                self.assertEqual(evidence["regressions"], [])
                self.assertEqual(evidence["resolved_findings"], [])
                self.assertEqual(
                    [(item["check_id"], item["target"]) for item in evidence["new_findings"]],
                    [("doc:README.md", "new-guide.md")],
                )
        self.assertFalse(json.loads(cleanup.stdout)["verified"])
        self.assertTrue(json.loads(weekly.stdout)["alert"])

    def test_selected_link_can_clear_while_other_links_remain(self):
        self.write("README.md", "[Setup](old-guide.md)\n[Other](another-guide.md)\n")
        self.commit("Record two broken links")
        baseline = self.save_baseline()
        target = next(item for item in baseline["findings"]
                      if item.get("target") == "old-guide.md")
        self.write("README.md", "[Setup](docs/setup.md)\n[Other](another-guide.md)\n")
        self.commit("Fix just the selected link")
        result = self.compare(target["id"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["resolved_findings"], [target])

    def test_monitor_notices_retention_expiry_on_the_same_commit(self):
        self.profile["artifact_rules"][0]["retain_until"] = DATE
        self.save_scored_baseline()
        unchanged = self.scan("--compare", str(self.baseline), "--monitor")
        self.assertEqual(unchanged.returncode, 0, unchanged.stderr)
        self.assertFalse(json.loads(unchanged.stdout)["alert"])
        expired = self.scan("--compare", str(self.baseline), "--monitor", "--as-of", "2026-11-26")
        self.assertEqual(expired.returncode, 1, expired.stderr)
        evidence = json.loads(expired.stdout)
        self.assertEqual(evidence["baseline_commit"], evidence["candidate_commit"])
        self.assertTrue(evidence["score_dropped"])
        self.assertEqual([item["path"] for item in evidence["new_findings"]], ["retired.py"])

    def test_local_markdown_headings_and_unsupported_fragments(self):
        self.write("README.md", """# Setup ##

[Same](#setup)
[Cross](docs/setup.md#read-caf%C3%A9)
[Repeated](docs/setup.md#read-café-1)
[Setext](docs/setup.md#next-steps)
[Custom](docs/setup.md#manual-ID)
[Existing code](app.py#L500)
[Plain view](docs/setup.md?plain=1#L500)
[Remote](https://example.invalid/page.md#missing)
[Text fragment](docs/setup.md#:~:text=hello)
[Bad local](#missing)
[Ignored heading](docs/setup.md#pretend)
[Ignored comment heading](docs/setup.md#hidden)
[Bad cross][cross]
[cross]: /docs/setup.md#missing
""")
        self.write("docs/setup.md", """# Read _Café_
# Read **Café**
<a name="manual-ID"></a>

Next steps
----------

~~~markdown
<!--
# Pretend
~~~

<!--
# Hidden
-->
""")
        self.commit("Add local heading links and controls")
        result = self.scan()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            {row["target"] for row in json.loads(result.stdout)["findings"]
             if row.get("kind") == "missing_heading"},
            {"README.md#missing", "docs/setup.md#pretend", "docs/setup.md#hidden",
             "docs/setup.md#missing"},
        )

    def test_heading_regression_under_an_already_failing_doc(self):
        self.save_scored_baseline()
        self.write("README.md", "[Setup](old-guide.md)\n[Details](docs/setup.md#old-details)\n")
        self.commit("Add a stale heading under the existing failed check")
        result = self.scan("--compare", str(self.baseline), "--monitor")
        self.assertEqual(result.returncode, 1, result.stderr)
        evidence = json.loads(result.stdout)
        self.assertEqual(evidence["baseline_score"], evidence["candidate_score"])
        self.assertEqual(evidence["regressions"], [])
        self.assertEqual(
            [(item["target"], item["kind"]) for item in evidence["new_findings"]],
            [("docs/setup.md#old-details", "missing_heading")],
        )
