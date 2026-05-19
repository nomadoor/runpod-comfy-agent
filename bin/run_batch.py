#!/usr/bin/env python3
"""Run a resumable sequential batch of ComfyUI jobs."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comfy_agent.runpod import ROOT, RunPodError, load_current_session, write_json
from bin.run_workflow import WorkflowError, load_json, run as run_workflow


DEFAULT_BATCHES_ROOT = ROOT / "sessions" / "manual-batches"


class BatchError(RuntimeError):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def resolve_path(value: str, base_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


def safe_id(value: str) -> str:
    safe = "".join(c if c.isalnum() or c in "._-" else "-" for c in value).strip("-")
    if not safe:
        raise BatchError(f"invalid empty id derived from {value!r}")
    return safe


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        f = path.open("r", encoding="utf-8")
    except OSError as exc:
        raise BatchError(f"could not read jobs file {path}: {exc}") from exc
    with f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise BatchError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(item, dict):
                raise BatchError(f"{path}:{line_no}: each job must be a JSON object")
            rows.append(item)
    return rows


def manifest_latest(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    latest: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise BatchError(f"{path}:{line_no}: invalid manifest JSON: {exc}") from exc
            job_id = item.get("job_id")
            if isinstance(job_id, str) and job_id:
                latest[job_id] = item
    return latest


def append_manifest(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False, sort_keys=True))
        f.write("\n")


def current_batch_root() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        session = load_current_session()
    except RunPodError:
        return DEFAULT_BATCHES_ROOT / f"batch-{stamp}"
    if session.get("status") in {"active", "starting"} and session.get("session_id"):
        return ROOT / "sessions" / str(session["session_id"]) / "batches" / f"batch-{stamp}"
    return DEFAULT_BATCHES_ROOT / f"batch-{stamp}"


def normalize_job(raw_job: dict[str, Any], line_index: int) -> tuple[str, dict[str, Any]]:
    spec_source = raw_job.get("spec")
    if spec_source is not None:
        if not isinstance(spec_source, dict):
            raise BatchError(f"job {line_index}: spec must be an object")
        spec = dict(spec_source)
    else:
        spec = {
            key: value
            for key, value in raw_job.items()
            if key not in {"job_id", "status", "output", "error", "pod_id", "finished_at"}
        }

    candidate_id = raw_job.get("job_id") or spec.get("run_id") or f"{line_index:06d}"
    job_id = safe_id(str(candidate_id))
    spec.setdefault("run_id", job_id)
    spec.setdefault("name", job_id)
    return job_id, spec


def output_paths(run_dir: Path) -> list[str]:
    images_dir = run_dir / "images"
    if not images_dir.exists():
        return []
    return [str(path) for path in sorted(images_dir.iterdir()) if path.is_file()]


def read_timing(run_dir: Path) -> dict[str, Any]:
    timing_path = run_dir / "artifacts" / "timing.json"
    if not timing_path.exists():
        return {}
    timing = load_json(timing_path)
    return timing if isinstance(timing, dict) else {}


def safe_output_paths(run_dir: Path) -> tuple[list[str], str | None]:
    try:
        return output_paths(run_dir), None
    except OSError as exc:
        return [], str(exc)


def safe_read_timing(run_dir: Path) -> dict[str, Any]:
    try:
        return read_timing(run_dir)
    except Exception as exc:  # noqa: BLE001 - manifest should survive malformed timing files.
        return {"error": f"timing_read_failed: {exc}"}


def run_batch(jobs_path: Path, batch_dir_arg: str | None, comfy_url: str | None, dry_run: bool, rerun_done: bool) -> int:
    started = time.monotonic()
    jobs_path = jobs_path.resolve()
    jobs_dir = jobs_path.parent
    jobs = load_jsonl(jobs_path)
    if not jobs:
        raise BatchError(f"no jobs found: {jobs_path}")

    batch_dir = resolve_path(batch_dir_arg, jobs_dir) if batch_dir_arg else current_batch_root()
    batch_dir.mkdir(parents=True, exist_ok=True)
    runs_root = batch_dir / "runs"
    specs_root = batch_dir / "job_specs"
    manifest_path = batch_dir / "manifest.jsonl"
    latest = manifest_latest(manifest_path)

    write_json(
        batch_dir / "batch.json",
        {
            "jobs_path": str(jobs_path),
            "started_at": utc_now_iso(),
            "dry_run": dry_run,
            "runs_root": str(runs_root),
            "manifest": str(manifest_path),
        },
    )

    summary = {"done": 0, "failed": 0, "skipped": 0, "planned": 0}
    seen_job_ids: set[str] = set()
    seen_run_ids: set[str] = set()
    for index, raw_job in enumerate(jobs, start=1):
        job_id, spec = normalize_job(raw_job, index)
        run_id = str(spec["run_id"])
        if job_id in seen_job_ids:
            summary["failed"] += 1
            message = f"duplicate job_id in jobs file: {job_id}"
            append_manifest(
                manifest_path,
                {"job_id": job_id, "status": "failed", "finished_at": utc_now_iso(), "error": message},
            )
            print(f"failed: {message}", file=sys.stderr)
            continue
        if run_id in seen_run_ids:
            summary["failed"] += 1
            message = f"duplicate run_id in jobs file: {run_id}"
            append_manifest(
                manifest_path,
                {"job_id": job_id, "status": "failed", "finished_at": utc_now_iso(), "run_id": run_id, "error": message},
            )
            print(f"failed: {message}", file=sys.stderr)
            continue
        seen_job_ids.add(job_id)
        seen_run_ids.add(run_id)
        previous = latest.get(job_id)
        if previous and previous.get("status") == "done" and not rerun_done:
            summary["skipped"] += 1
            print(f"skip done: {job_id}")
            continue

        spec["runs_root"] = str(runs_root)
        spec_path = specs_root / f"{job_id}.json"
        write_json(spec_path, spec)
        run_dir = runs_root / str(spec["run_id"])

        start_item = {
            "job_id": job_id,
            "status": "running" if not dry_run else "planned",
            "started_at": utc_now_iso(),
            "run_id": spec["run_id"],
            "run_dir": str(run_dir),
            "spec_path": str(spec_path),
        }
        append_manifest(manifest_path, start_item)
        print(f"{start_item['status']}: {job_id}")

        if dry_run:
            try:
                run_workflow(spec_path.resolve(), comfy_url, dry_run=True)
            except Exception as exc:  # noqa: BLE001 - batch jobs should fail independently.
                item = {
                    "job_id": job_id,
                    "status": "failed",
                    "finished_at": utc_now_iso(),
                    "run_id": spec["run_id"],
                    "run_dir": str(run_dir),
                    "spec_path": str(spec_path),
                    "error": str(exc),
                }
                append_manifest(manifest_path, item)
                latest[job_id] = item
                summary["failed"] += 1
                print(f"dry-run failed: {job_id}: {exc}", file=sys.stderr)
                continue
            summary["planned"] += 1
            latest[job_id] = start_item
            continue

        try:
            run_workflow(spec_path.resolve(), comfy_url, dry_run=False)
        except Exception as exc:  # noqa: BLE001 - batch jobs should fail independently.
            item = {
                "job_id": job_id,
                "status": "failed",
                "finished_at": utc_now_iso(),
                "run_id": spec["run_id"],
                "run_dir": str(run_dir),
                "spec_path": str(spec_path),
                "error": str(exc),
            }
            append_manifest(manifest_path, item)
            latest[job_id] = item
            summary["failed"] += 1
            print(f"failed: {job_id}: {exc}", file=sys.stderr)
            continue

        output, output_error = safe_output_paths(run_dir)
        item = {
            "job_id": job_id,
            "status": "done",
            "finished_at": utc_now_iso(),
            "run_id": spec["run_id"],
            "run_dir": str(run_dir),
            "spec_path": str(spec_path),
            "output": output,
            "timing": safe_read_timing(run_dir),
        }
        if output_error:
            item["output_error"] = output_error
        append_manifest(manifest_path, item)
        latest[job_id] = item
        summary["done"] += 1
        print(f"done: {job_id}")

    total_seconds = round(time.monotonic() - started, 3)
    write_json(
        batch_dir / "summary.json",
        {
            **summary,
            "total_jobs": len(jobs),
            "total_seconds": total_seconds,
            "finished_at": utc_now_iso(),
            "manifest": str(manifest_path),
        },
    )
    print(f"batch_dir: {batch_dir}")
    print(f"manifest: {manifest_path}")
    print(f"summary: {summary} total_seconds={total_seconds}")
    return 1 if summary["failed"] else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a resumable jobs.jsonl batch through ComfyUI")
    parser.add_argument("--jobs", required=True, help="Path to jobs.jsonl")
    parser.add_argument("--batch-dir", help="Output directory for batch manifest, specs, and runs")
    parser.add_argument("--comfy-url", help="ComfyUI base URL; overrides current session/spec URLs")
    parser.add_argument("--dry-run", action="store_true", help="Write normalized job specs and manifest without running")
    parser.add_argument("--rerun-done", action="store_true", help="Run jobs even if the latest manifest status is done")
    args = parser.parse_args()

    try:
        return run_batch(Path(args.jobs), args.batch_dir, args.comfy_url, args.dry_run, args.rerun_done)
    except BatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
