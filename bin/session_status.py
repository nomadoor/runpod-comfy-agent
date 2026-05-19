#!/usr/bin/env python3
"""Show current RunPod session status and cost estimates."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comfy_agent.runpod import RunPodError, load_session, parse_iso, runpod_request, utc_now_iso


def cost_per_hour_from_pod(pod: dict[str, Any]) -> float | None:
    for key in ("adjustedCostPerHr", "costPerHr"):
        value = pod.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    machine = pod.get("machine") or {}
    for key in ("currentPricePerGpu", "costPerHr"):
        value = machine.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    return None


def billing_for_session(session: dict[str, Any]) -> list[dict[str, Any]]:
    return runpod_request(
        "GET",
        "/billing/pods",
        query={
            "bucketSize": "hour",
            "grouping": "podId",
            "podId": session["pod_id"],
            "startTime": session["started_at"],
            "endTime": utc_now_iso(),
        },
    ) or []


def build_status(session: dict[str, Any]) -> dict[str, Any]:
    pod = runpod_request("GET", f"/pods/{session['pod_id']}")
    billing_error = None
    try:
        billing = billing_for_session(session)
    except RunPodError as exc:
        billing = []
        billing_error = str(exc)

    now = datetime.now(timezone.utc)
    started_at = parse_iso(session["started_at"])
    elapsed_seconds = max(0.0, (now - started_at).total_seconds())

    hourly_cost = cost_per_hour_from_pod(pod) or cost_per_hour_from_pod(session.get("runpod_pod", {}))
    estimated_active_cost = None
    if hourly_cost is not None:
        estimated_active_cost = hourly_cost * elapsed_seconds / 3600

    billed_amount = sum(float(row.get("amount") or 0) for row in billing)
    billed_ms = sum(int(row.get("timeBilledMs") or 0) for row in billing)

    return {
        "session_id": session["session_id"],
        "pod_id": session["pod_id"],
        "pod_name": session.get("pod_name"),
        "session_status": session.get("status"),
        "pod_desired_status": pod.get("desiredStatus"),
        "pod_runtime_status": pod.get("runtimeStatus") or pod.get("status"),
        "gpu": pod.get("gpu") or pod.get("machine", {}).get("gpuTypeId"),
        "cost_per_hour": hourly_cost,
        "started_at": session["started_at"],
        "elapsed_seconds": round(elapsed_seconds, 1),
        "elapsed_minutes": round(elapsed_seconds / 60, 2),
        "estimated_active_cost": None if estimated_active_cost is None else round(estimated_active_cost, 6),
        "billing_amount_returned": round(billed_amount, 6),
        "billing_time_billed_ms_returned": billed_ms,
        "billing_error": billing_error,
        "comfyui_url": session.get("comfyui_url"),
        "logs_note": "Pod container/system logs are documented in the RunPod console; no Pod logs REST endpoint is currently wired here.",
    }


def print_plain(status: dict[str, Any]) -> None:
    print(f"session: {status['session_id']}")
    print(f"pod: {status['pod_id']} ({status.get('pod_name')})")
    print(f"status: session={status.get('session_status')} pod={status.get('pod_desired_status')} runtime={status.get('pod_runtime_status')}")
    print(f"gpu: {status.get('gpu')}")
    print(f"elapsed: {status['elapsed_minutes']} min")
    print(f"cost/hour: {status.get('cost_per_hour')}")
    print(f"estimated active cost: {status.get('estimated_active_cost')}")
    print(f"billing returned: amount={status['billing_amount_returned']} time_billed_ms={status['billing_time_billed_ms_returned']}")
    if status.get("billing_error"):
        print(f"billing error: {status['billing_error']}")
    print(f"comfyui: {status.get('comfyui_url')}")
    print(status["logs_note"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Show current RunPod session status and cost estimates")
    parser.add_argument("--session-id")
    parser.add_argument("--json", action="store_true", help="Print JSON")
    parser.add_argument("--watch", type=float, help="Refresh every N seconds")
    args = parser.parse_args()

    try:
        while True:
            session = load_session(args.session_id)
            status = build_status(session)
            if args.json:
                print(json.dumps(status, indent=2, ensure_ascii=False))
            else:
                print_plain(status)
            if not args.watch:
                return 0
            print()
            time.sleep(args.watch)
    except RunPodError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
