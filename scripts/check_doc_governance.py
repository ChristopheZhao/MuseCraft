#!/usr/bin/env python3
"""Read-only checks over existing document owners; no lifecycle mutations."""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re


STATUSES = {
    "draft", "in_progress", "testing", "awaiting_user_confirmation",
    "completed", "blocked", "superseded", "archived",
}
ENTRY_DOCUMENTS = (
    "AGENTS.md", "backend/AGENTS.md", "docs/README.md", "docs/governance.md",
    "docs/plans/artifacts/PLAN-20260906-070/reconciliation.md",
)


def field(text: str, name: str) -> str | None:
    match = re.search(r"^- " + re.escape(name) + r":\s*([^\n]+)", text, re.M)
    return match.group(1).strip() if match else None


def check(root: Path) -> list[dict[str, str]]:
    root = root.resolve()
    issues: list[dict[str, str]] = []

    def error(code: str, path: str, detail: str) -> None:
        issues.append({"code": code, "path": path, "detail": detail})

    def read_index(path: str) -> list[dict]:
        try:
            value = json.loads((root / path).read_text(encoding="utf-8"))
            plans = value["plans"]
            if not isinstance(plans, list) or not all(isinstance(p, dict) for p in plans):
                raise ValueError("plans must be a list of objects")
            return plans
        except (OSError, ValueError, KeyError, TypeError) as exc:
            error("invalid_index", path, str(exc))
            return []

    def local_file(path: object) -> Path | None:
        if not isinstance(path, str) or not path or Path(path).is_absolute():
            return None
        target = (root / path).resolve()
        return target if target.is_relative_to(root) and target.is_file() else None

    plans = read_index("docs/plans/PLAN_INDEX.json")
    ids: set[str] = set()
    registered: set[str] = set()
    for plan in plans:
        pid = plan.get("id")
        path = plan.get("file_path", "")
        label = str(path)
        if not isinstance(pid, str) or not re.fullmatch(r"PLAN-\d{8}-\d{3}", pid):
            error("invalid_plan_id", label, str(pid))
        elif pid in ids:
            error("duplicate_plan_id", label, pid)
        else:
            ids.add(pid)
        target = local_file(path)
        if target is None:
            error("missing_plan_file", label, "expected a repository-local file")
            continue
        if path in registered:
            error("duplicate_plan_path", label, "multiple plans share a file")
        registered.add(path)
        text = target.read_text(encoding="utf-8")
        if field(text, "Plan ID") != pid:
            error("plan_id_mismatch", path, str(pid))
        status = plan.get("status")
        if not isinstance(status, str) or status not in STATUSES:
            error("invalid_plan_status", path, str(status))
        if field(text, "Status") != status:
            error("doc_status_mismatch", path, f"index={status}; doc={field(text, 'Status')}")
        prefix = "docs/plans/archive/" if status == "archived" else "docs/plans/active/"
        if not path.startswith(prefix):
            error("plan_path_mismatch", path, f"expected {prefix}")

    for folder in ("docs/plans/active", "docs/plans/archive", "docs/plans/artifacts"):
        for target in sorted((root / folder).rglob("*")):
            if not target.is_file():
                continue
            path = target.relative_to(root).as_posix()
            if path in registered:
                continue
            if target.suffix != ".md":
                if folder == "docs/plans/artifacts":
                    continue  # Binary/log evidence is described by its parent's attachment.
                error("unclassified_attachment", path, "declare attachment ownership or move to artifacts")
                continue
            text = target.read_text(encoding="utf-8")
            if field(text, "Document Type") != "plan-attachment":
                error("unclassified_attachment", path, "missing Document Type: plan-attachment")
            if field(text, "Parent Plan") not in ids:
                error("unknown_attachment_parent", path, str(field(text, "Parent Plan")))

    deferred = read_index("docs/deferred-plans/DEFERRED_PLAN_INDEX.json")
    active = [p for p in deferred if p.get("status") == "active"]
    if len(active) > 1:
        error("multiple_active_guardrails", "docs/deferred-plans/DEFERRED_PLAN_INDEX.json", str(len(active)))
    for plan in deferred:
        path = str(plan.get("file_path", ""))
        target = local_file(path)
        if target is None:
            error("missing_deferred_file", path, "expected a repository-local file")
            continue
        text = target.read_text(encoding="utf-8")
        for name, key in (("Deferred Plan ID", "id"), ("Status", "status"),
                          ("Updated At", "updated_at"), ("Review After", "review_after")):
            if field(text, name) != plan.get(key):
                error("deferred_mirror_mismatch", path, name)
        if plan.get("status") == "active":
            try:
                if date.fromisoformat(plan["review_after"]) < date.today():
                    error("guardrail_review_overdue", path, plan["review_after"])
            except (KeyError, TypeError, ValueError):
                error("invalid_guardrail_review_date", path, "expected ISO date")
    current = root / "docs/deferred-plans/CURRENT.md"
    if not current.is_file():
        error("missing_guardrail_summary", "docs/deferred-plans/CURRENT.md", "summary absent")
    elif active:
        text = current.read_text(encoding="utf-8")
        if field(text, "Deferred Plan ID") != active[0].get("id") or field(text, "Status") != "active":
            error("guardrail_summary_mismatch", "docs/deferred-plans/CURRENT.md", "active plan differs")
    elif current.is_file() and field(current.read_text(encoding="utf-8"), "Status") == "active":
        error("guardrail_summary_mismatch", "docs/deferred-plans/CURRENT.md", "no active plan")

    link_sources: dict[str, str] = {}
    for path in ENTRY_DOCUMENTS:
        target = local_file(path)
        if target is None:
            error("missing_entry_document", path, "maintained entry absent")
        else:
            link_sources[path] = target.read_text(encoding="utf-8")
    for target in sorted((root / "docs").rglob("*.md")):
        text = target.read_text(encoding="utf-8")
        if field(text, "Document Status") == "historical":
            path = target.relative_to(root).as_posix()
            replacement = field(text, "Replacement")
            if not field(text, "Superseded Scope") or not replacement:
                error("incomplete_supersession", path, "scope and replacement required")
            elif not re.search(r"\[[^\]]+\]\([^)]+\)", replacement):
                error("incomplete_supersession", path, "replacement must contain a Markdown link")
            else:
                link_sources[path] = replacement
    for path, text in link_sources.items():
        # Ignore examples; this is a local file-target check, not a Markdown renderer.
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        for match in re.finditer(r"!?\[[^\]\n]*\]\((<[^>]+>|[^\s)]+)(?:\s+\"[^\"]*\")?\)", text):
            ref = match.group(1).strip("<>").split("#", 1)[0]
            if not ref or re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", ref):
                continue
            target = (root / path).parent / ref
            if not target.exists():
                error("broken_local_link", path, ref)
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    issues = check(args.root)
    if args.json:
        print(json.dumps({"ok": not issues, "issues": issues}, ensure_ascii=False, indent=2))
    else:
        for issue in issues:
            print(f"{issue['code']}: {issue['path']}: {issue['detail']}")
        print(f"Document governance: {len(issues)} issue(s)")
    return int(bool(issues))


if __name__ == "__main__":
    raise SystemExit(main())
