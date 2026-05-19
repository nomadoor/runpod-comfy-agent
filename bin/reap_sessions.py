#!/usr/bin/env python3
"""Terminate expired or orphaned comfy-session Pods."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comfy_agent.runpod import (
    RunPodError,
    SESSIONS_ROOT,
    load_json,
    parse_iso,
    public_session,
    runpod_request,
    update_session,
    utc_now_iso,
)


def local_sessions() -> dict[str, dict[str, Any]]:
    sessions: dict[str, dict[str, Any]] = {}
    for path in SESSIONS_ROOT.glob("*/session.json"):
        try:
            session = load_json(path)
        except Exception:
            continue
        pod_id = session.get("pod_id")
        if pod_id:
            sessions[pod_id] = session
    return sessions


def is_expired(session: dict[str, Any], now: datetime) -> bool:
    if session.get("status") not in {"active", "starting"}:
        return False
    started_at = parse_iso(session["started_at"])
    max_minutes = int(session.get("max_runtime_minutes", 0))
    if max_minutes <= 0:
        return False
    age_minutes = (now - started_at).total_seconds() / 60
    return age_minutes >= max_minutes


def main() -> int:
    parser = argparse.ArgumentParser(description="Terminate leaked comfy-session Pods")
    parser.add_argument("--yes", action="store_true", help="Actually terminate matched Pods")
    parser.add_argument("--include-orphans", action="store_true", help="Terminate comfy-session Pods missing local session.json")
    args = parser.parse_args()

    try:
        sessions = local_sessions()
        pods = runpod_request("GET", "/pods", query={"desiredStatus": "RUNNING"})
        now = datetime.now(timezone.utc)
        candidates: list[tuple[dict[str, Any], str]] = []

        for session in sessions.values():
            if is_expired(session, now):
                candidates.append((session, "expired-local-session"))

        for pod in pods or []:
            pod_id = pod.get("id")
            name = pod.get("name", "")
            if not name.startswith("comfy-session-"):
                continue
            if pod_id not in sessions and args.include_orphans:
                candidates.append(
                    (
                        {
                            "session_id": name.removeprefix("comfy-session-"),
                            "pod_id": pod_id,
                            "pod_name": name,
                            "status": "orphan",
                            "started_at": pod.get("lastStartedAt") or utc_now_iso(),
                        },
                        "orphan-runpod-pod",
                    )
                )

        if not candidates:
            print("no Pods to reap")
            return 0

        for session, reason in candidates:
            print(json.dumps({"reason": reason, **public_session(session)}, indent=2, ensure_ascii=False))
            if args.yes:
                runpod_request("DELETE", f"/pods/{session['pod_id']}")
                if reason == "expired-local-session":
                    session["status"] = "reaped"
                    session["closed_at"] = utc_now_iso()
                    session["updated_at"] = session["closed_at"]
                    update_session(session)
            else:
                print("dry-run: pass --yes to terminate")
        return 0
    except RunPodError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
