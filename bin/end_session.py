#!/usr/bin/env python3
"""Terminate the current RunPod ComfyUI session."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comfy_agent.runpod import RunPodError, load_session, public_session, runpod_request, update_session, utc_now_iso


def main() -> int:
    parser = argparse.ArgumentParser(description="Terminate a RunPod ComfyUI session")
    parser.add_argument("--session-id")
    parser.add_argument("--yes", action="store_true", help="Do not ask for confirmation")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        session = load_session(args.session_id)
        pod_id = session["pod_id"]
        if not args.yes:
            answer = input(f"Terminate Pod {pod_id} for session {session['session_id']}? [y/N] ")
            if answer.lower() not in {"y", "yes"}:
                print("cancelled")
                return 0
        if not args.dry_run:
            try:
                runpod_request("DELETE", f"/pods/{pod_id}")
            except RunPodError as exc:
                if "HTTP 404" not in str(exc):
                    raise
        session["status"] = "closed" if not args.dry_run else "close-dry-run"
        session["closed_at"] = utc_now_iso()
        session["updated_at"] = session["closed_at"]
        update_session(session)
        print(json.dumps(public_session(session), indent=2, ensure_ascii=False))
        return 0
    except RunPodError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
