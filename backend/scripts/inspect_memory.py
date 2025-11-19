import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable


def pretty_print(title: str, payload: Any) -> None:
    print(f"\n=== {title} ===")
    if payload is None:
        print("<None>")
        return
    try:
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    except TypeError:
        text = str(payload)
    print(text)


def _load_rows(conn: sqlite3.Connection, workflow_id: str, needle: str = None) -> Iterable[dict]:
    if needle:
        cursor = conn.execute(
            "SELECT content FROM memories WHERE task_id=? AND content LIKE ? ORDER BY created_at DESC",
            (workflow_id, f"%{needle}%"),
        )
    else:
        cursor = conn.execute(
            "SELECT content FROM memories WHERE task_id=? ORDER BY created_at DESC",
            (workflow_id,),
        )
    for row in cursor:
        try:
            yield json.loads(row[0])
        except Exception:
            continue


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect persisted memory (SQLite)")
    parser.add_argument("workflow_id", help="Workflow/task identifier")
    parser.add_argument("--slot", help="Keyword to search within stored content (e.g., project.concept_plan)")
    parser.add_argument("--shared", help="Keyword to search within stored content (e.g., intelligent_style_design)")
    parser.add_argument("--db", help="SQLite file path", default=str(Path("backend/storage/memory.sqlite")))
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"SQLite database not found at {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        needles = []
        if args.slot:
            needles.append((f"slot:{args.slot}", args.slot))
        if args.shared:
            needles.append((f"shared:{args.shared}", args.shared))
        if not needles:
            needles.append(("all", None))

        for title, key in needles:
            rows = list(_load_rows(conn, args.workflow_id, key))
            pretty_print(title, rows[:5] if rows else None)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
