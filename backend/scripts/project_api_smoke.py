#!/usr/bin/env python3
"""Simple smoke test for project-mode API endpoints.

Sequence:
1. POST /projects
2. GET /projects/{id}
3. PUT /projects/{id}/episodes/{ep}/script
4. (optional) POST /projects/{id}/orchestrate

Usage:
    uv run python scripts/project_api_smoke.py --base-url http://localhost:8000/api/v1 --orchestrate
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Dict

try:
    import requests
except ImportError:  # pragma: no cover
    print("This script requires the 'requests' package. Install it via 'uv pip install requests'.", file=sys.stderr)
    sys.exit(1)


def pretty(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Project mode API smoke test")
    parser.add_argument("--base-url", default="http://localhost:8000/api/v1", help="Backend API base URL")
    parser.add_argument("--title", default="Demo Project", help="Project title")
    parser.add_argument("--prompt", default="讲述 AI 与人类携手探索星际的短片", help="Project description prompt")
    parser.add_argument("--duration", type=int, default=180, help="Target duration in seconds")
    parser.add_argument("--orchestrate", action="store_true", help="Trigger single-episode orchestration")
    parser.add_argument("--episode-index", type=int, default=0, help="Episode index to approve/orchestrate")
    parser.add_argument("--approve", action="store_true", help="Approve script when updating episode")
    parser.add_argument("--verbose", action="store_true", help="Print full JSON responses")

    args = parser.parse_args()

    base = args.base_url.rstrip('/')

    def log(step: str, detail: str) -> None:
        print(f"[{step}] {detail}")

    # Step 1: create project
    payload = {
        "user_prompt": f"{args.title}\n\n{args.prompt}",
        "target_duration_seconds": args.duration,
        "mode": "project",
        "aspect_ratio": "16:9",
    }
    log("STEP1", f"POST {base}/projects ...")
    create_resp = requests.post(f"{base}/projects/", json=payload, timeout=60)
    create_resp.raise_for_status()
    project: Dict[str, Any] = create_resp.json()["project"]
    project_id = project["project_id"]
    episodes = project["story_plan"]["episodes"]
    log("STEP1", f"Project {project_id} created with {len(episodes)} episode(s)")
    if args.verbose:
        print(pretty(project))

    # Step 2: fetch project
    log("STEP2", f"GET {base}/projects/{project_id}")
    detail_resp = requests.get(f"{base}/projects/{project_id}", timeout=60)
    detail_resp.raise_for_status()
    project_detail = detail_resp.json()
    if args.verbose:
        print(pretty(project_detail))

    # Step 3: update script for selected episode
    if not episodes:
        log("WARN", "No episodes returned; skipping script update")
    else:
        try:
            episode = episodes[args.episode_index]
        except IndexError:
            log("WARN", f"Episode index {args.episode_index} out of range; skipping script update")
        else:
            episode_id = episode["episode_id"]
            script = episode.get("script_draft") or "This is a placeholder script for smoke testing."
            script_payload = {
                "script_text": script + "\n\n[Smoke Test Updated]",
                "approve": args.approve,
            }
            log("STEP3", f"PUT /projects/{project_id}/episodes/{episode_id}/script (approve={args.approve})")
            update_resp = requests.put(
                f"{base}/projects/{project_id}/episodes/{episode_id}/script",
                json=script_payload,
                timeout=60,
            )
            update_resp.raise_for_status()
            updated = update_resp.json()
            if args.verbose:
                print(pretty(updated))

    # Step 4: optional orchestration
    if args.orchestrate and episodes:
        episode_id = episodes[min(args.episode_index, len(episodes) - 1)]["episode_id"]
        orch_payload = {
            "episode_ids": [episode_id],
            "auto_approve": False,
            "force_rerun": True,
        }
        log("STEP4", f"POST /projects/{project_id}/orchestrate (episode={episode_id})")
        orch_resp = requests.post(
            f"{base}/projects/{project_id}/orchestrate",
            json=orch_payload,
            timeout=120,
        )
        orch_resp.raise_for_status()
        orch_result = orch_resp.json()
        log("STEP4", f"Orchestration status: {orch_result.get('status')}")
        if args.verbose:
            print(pretty(orch_result))
    else:
        log("STEP4", "Skip orchestration (use --orchestrate to enable)")

    log("DONE", "Smoke test finished")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as http_err:
        print(f"HTTP error: {http_err.response.status_code} {http_err.response.text}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
