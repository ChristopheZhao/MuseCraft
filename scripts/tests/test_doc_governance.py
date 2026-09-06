"""Failure-oriented document checks, isolated from application dependencies."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


spec = importlib.util.spec_from_file_location(
    "doc_governance", Path(__file__).resolve().parents[1] / "check_doc_governance.py"
)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class DocumentGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pid = "PLAN-20260906-001"
        self.plan = f"docs/plans/active/{self.pid}.md"
        self.entry = {"id": self.pid, "status": "in_progress", "file_path": self.plan}
        self.write("docs/plans/PLAN_INDEX.json", json.dumps({"plans": [self.entry]}))
        self.write(self.plan, f"# Test\n- Plan ID: {self.pid}\n- Status: in_progress\n")
        self.write("docs/deferred-plans/DEFERRED_PLAN_INDEX.json", '{"plans": []}')
        self.write("docs/deferred-plans/CURRENT.md", "No active deferred plan\n")
        for path in checker.ENTRY_DOCUMENTS:
            self.write(path, "# Current entry\n")
        self.write(checker.ENTRY_DOCUMENTS[-1],
                   f"# Evidence\n- Document Type: plan-attachment\n- Parent Plan: {self.pid}\n")

    def write(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value, encoding="utf-8")

    def codes(self):
        return {issue["code"] for issue in checker.check(self.root)}

    def test_attachment_is_not_a_new_plan_and_check_is_read_only(self):
        self.write(f"docs/plans/active/{self.pid}-validation.md",
                   f"# Evidence\n- Document Type: plan-attachment\n- Parent Plan: {self.pid}\n"
                   "- Status: completed\nHistorical result, not current lifecycle.\n")
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(self.codes(), set())
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_unknown_attachment_parent_fails(self):
        self.write("docs/plans/active/note.md", "- Document Type: plan-attachment\n"
                   "- Parent Plan: PLAN-20260906-999\n")
        self.assertIn("unknown_attachment_parent", self.codes())

    def test_artifacts_markdown_also_requires_parent(self):
        self.write("docs/plans/artifacts/unknown/review.md", "# Unowned evidence\n")
        self.assertIn("unknown_attachment_parent", self.codes())

    def test_unclassified_file_cannot_hide_as_attachment(self):
        self.write(f"docs/plans/active/{self.pid}-validation.md", "# Undeclared\n")
        self.assertIn("unclassified_attachment", self.codes())

    def test_status_and_archive_path_disagreement_fail(self):
        self.entry["status"] = "archived"
        self.write("docs/plans/PLAN_INDEX.json", json.dumps({"plans": [self.entry]}))
        self.assertTrue({"doc_status_mismatch", "plan_path_mismatch"} <= self.codes())

    def test_duplicate_plan_identity_fails(self):
        self.write("docs/plans/PLAN_INDEX.json", json.dumps({"plans": [self.entry, self.entry]}))
        self.assertIn("duplicate_plan_id", self.codes())

    def test_broken_entry_link_fails_but_code_example_is_not_a_link(self):
        self.write("docs/README.md", '[missing](missing.md)\n```md\n[example](not-a-file.md)\n```')
        errors = [i for i in checker.check(self.root) if i["code"] == "broken_local_link"]
        self.assertEqual([e["detail"] for e in errors], ["missing.md"])

    def test_historical_body_is_scoped_but_replacement_must_resolve(self):
        self.write("docs/old.md", "- Document Status: historical\n- Superseded Scope: old runtime\n"
                   "- Replacement: [current](README.md)\n\n[historical](retired.py)\n")
        self.assertEqual(self.codes(), set())
        self.write("docs/old.md", "- Document Status: historical\n- Superseded Scope: old runtime\n"
                   "- Replacement: [current](absent.md)\n")
        self.assertIn("broken_local_link", self.codes())

    def test_active_guardrail_overdue_and_summary_mismatch_fail(self):
        dp = {"id": "DP-20260331-001", "status": "active", "file_path": "docs/deferred-plans/active/dp.md",
              "updated_at": "2026-09-06T00:00:00Z", "review_after": "2000-01-01"}
        self.write("docs/deferred-plans/DEFERRED_PLAN_INDEX.json", json.dumps({"plans": [dp]}))
        self.write(dp["file_path"], "- Deferred Plan ID: DP-20260331-001\n- Status: active\n"
                   "- Updated At: 2026-09-06T00:00:00Z\n- Review After: 2000-01-01\n")
        self.assertTrue({"guardrail_review_overdue", "guardrail_summary_mismatch"} <= self.codes())

    def test_invalid_index_has_diagnostic(self):
        self.write("docs/plans/PLAN_INDEX.json", '{"plans": "wrong"}')
        self.assertIn("invalid_index", self.codes())


if __name__ == "__main__":
    unittest.main()
