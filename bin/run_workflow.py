#!/usr/bin/env python3
"""Run a ComfyUI workflow from a flexible run spec.

This is intentionally small: it applies per-run patches to a workflow API JSON,
uploads input images when requested, submits the prompt, polls history, and
downloads output images into a run directory.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comfy_agent.runpod import ROOT, load_current_session, RunPodError as SessionError

DEFAULT_RUNS_ROOT = ROOT / "sessions" / "manual-runs"


class WorkflowError(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def resolve_path(value: str, base_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    candidate = (base_dir / path).resolve()
    if candidate.exists():
        return candidate
    return (ROOT / path).resolve()


def make_run_id(prefix: str | None) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if prefix:
        safe = "".join(c if c.isalnum() or c in "._-" else "-" for c in prefix).strip("-")
        if safe:
            return f"{safe}-{stamp}"
    return f"run-{stamp}"


def normalize_base_url(url: str) -> str:
    return url.rstrip("/")


def curl(args: list[str], *, output: Path | None = None, timeout: int = 120) -> str:
    cmd = ["curl", "-fsS", "--max-time", str(timeout), *args]
    if output is not None:
        cmd.extend(["-o", str(output)])
    try:
        result = subprocess.run(cmd, check=False, text=True, capture_output=True)
    except FileNotFoundError as exc:
        raise WorkflowError("curl is required for RunPod proxy access, but it was not found") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise WorkflowError(f"curl failed with exit code {result.returncode}: {detail}")
    return result.stdout


def curl_json(args: list[str], *, timeout: int = 120) -> Any:
    text = curl(args, timeout=timeout)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"Expected JSON response, got: {text[:500]}") from exc


def apply_patch_entry(workflow: dict[str, Any], patch: dict[str, Any]) -> None:
    if "path" in patch:
        path = patch["path"]
        if not isinstance(path, list) or not path:
            raise WorkflowError(f"patch.path must be a non-empty list: {patch}")
        target: Any = workflow
        for key in path[:-1]:
            target = target[str(key)] if isinstance(target, dict) else target[int(key)]
        last = path[-1]
        if isinstance(target, dict):
            target[str(last)] = patch.get("value")
        else:
            target[int(last)] = patch.get("value")
        return

    node = str(patch.get("node", ""))
    field = patch.get("field")
    if not node or field is None:
        raise WorkflowError(f"patch requires either path or node+field: {patch}")
    if node not in workflow:
        raise WorkflowError(f"patch refers to missing node {node}")
    inputs = workflow[node].setdefault("inputs", {})
    inputs[str(field)] = patch.get("value")


def upload_image(base_url: str, image: dict[str, Any], spec_dir: Path) -> str:
    local_path_value = image.get("local_path")
    node = str(image.get("node", ""))
    field = str(image.get("field", "image"))
    if not local_path_value or not node:
        raise WorkflowError(f"image input requires local_path and node: {image}")
    local_path = resolve_path(str(local_path_value), spec_dir)
    if not local_path.exists():
        raise WorkflowError(f"input image does not exist: {local_path}")

    remote_name = str(image.get("remote_name") or local_path.name)
    overwrite = "true" if image.get("overwrite", True) else "false"
    form_file = f"image=@{local_path};filename={remote_name}"
    response = curl_json(
        [
            "-X",
            "POST",
            "-F",
            form_file,
            "-F",
            f"overwrite={overwrite}",
            f"{base_url}/upload/image",
        ],
        timeout=int(image.get("timeout_seconds", 300)),
    )
    uploaded_name = response.get("name")
    if not uploaded_name:
        raise WorkflowError(f"upload response did not include a name: {response}")
    return str(uploaded_name)


def apply_image_inputs(workflow: dict[str, Any], uploaded: list[tuple[dict[str, Any], str]]) -> None:
    for image, uploaded_name in uploaded:
        node = str(image["node"])
        field = str(image.get("field", "image"))
        if node not in workflow:
            raise WorkflowError(f"image input refers to missing node {node}")
        workflow[node].setdefault("inputs", {})[field] = uploaded_name


def submit_prompt(base_url: str, payload_path: Path) -> str:
    response = curl_json(
        [
            "-X",
            "POST",
            "-H",
            "Content-Type: application/json",
            "--data-binary",
            f"@{payload_path}",
            f"{base_url}/prompt",
        ],
        timeout=60,
    )
    if response.get("node_errors"):
        raise WorkflowError(f"ComfyUI rejected the prompt: {json.dumps(response, ensure_ascii=False)}")
    prompt_id = response.get("prompt_id")
    if not prompt_id:
        raise WorkflowError(f"ComfyUI response did not include prompt_id: {response}")
    return str(prompt_id)


def poll_history(
    base_url: str, prompt_id: str, timeout_seconds: int, interval_seconds: float
) -> tuple[dict[str, Any], dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    last: Any = None
    polls = 0
    start = time.monotonic()
    while time.monotonic() < deadline:
        polls += 1
        history = curl_json([f"{base_url}/history/{prompt_id}"], timeout=60)
        last = history
        entry = history.get(prompt_id) if isinstance(history, dict) else None
        if entry:
            status = entry.get("status", {})
            if status.get("completed"):
                return entry, {"polls": polls, "poll_seconds": round(time.monotonic() - start, 3)}
            if status.get("status_str") == "error":
                return entry, {"polls": polls, "poll_seconds": round(time.monotonic() - start, 3)}
        time.sleep(interval_seconds)
    raise WorkflowError(f"Timed out waiting for prompt {prompt_id}; last history: {last}")


def collect_images(history_entry: dict[str, Any]) -> list[dict[str, str]]:
    images: list[dict[str, str]] = []
    outputs = history_entry.get("outputs", {})
    for node_output in outputs.values():
        for image in node_output.get("images", []):
            images.append(
                {
                    "filename": image.get("filename", ""),
                    "subfolder": image.get("subfolder", ""),
                    "type": image.get("type", "output"),
                }
            )
    return [image for image in images if image["filename"]]


def download_images(base_url: str, images: list[dict[str, str]], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    for image in images:
        query = urlencode(image)
        target = output_dir / Path(image["filename"]).name
        curl([f"{base_url}/view?{query}"], output=target, timeout=300)
        downloaded.append(target)
    return downloaded


def run(spec_path: Path, comfy_url_arg: str | None, dry_run: bool) -> int:
    total_started = time.monotonic()
    timing: dict[str, Any] = {
        "started_at": utc_now_iso(),
        "steps": {},
    }
    spec = load_json(spec_path)
    spec_dir = spec_path.parent
    current_session = None
    try:
        current_session = load_current_session()
    except SessionError:
        current_session = None
    comfy_url = comfy_url_arg or spec.get("comfy_url") or os.environ.get("COMFYUI_URL")
    if not comfy_url and current_session and current_session.get("status") in {"active", "starting"}:
        comfy_url = current_session.get("comfyui_url")
    if not comfy_url and not dry_run:
        raise WorkflowError("ComfyUI URL is required via --comfy-url, spec.comfy_url, or COMFYUI_URL")
    base_url = normalize_base_url(str(comfy_url or "http://dry-run.invalid"))

    workflow_path_value = spec.get("workflow_json")
    if not workflow_path_value:
        raise WorkflowError("spec.workflow_json is required")
    workflow_path = resolve_path(str(workflow_path_value), spec_dir)
    workflow = load_json(workflow_path)

    run_id = str(spec.get("run_id") or make_run_id(spec.get("name") or workflow_path.stem))
    if spec.get("runs_root"):
        runs_root = resolve_path(str(spec["runs_root"]), spec_dir)
    elif current_session and current_session.get("session_id") and current_session.get("status") in {"active", "starting"}:
        runs_root = ROOT / "sessions" / current_session["session_id"] / "runs"
    else:
        runs_root = DEFAULT_RUNS_ROOT
    if comfy_url_arg and not spec.get("runs_root") and current_session and current_session.get("comfyui_url") != base_url:
        runs_root = DEFAULT_RUNS_ROOT
    run_dir = runs_root / run_id
    output_dir = run_dir / "images"
    input_dir = run_dir / "inputs"
    artifacts_dir = run_dir / "artifacts"
    run_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    uploaded: list[tuple[dict[str, Any], str]] = []
    upload_started = time.monotonic()
    if not dry_run:
        for image in spec.get("inputs", {}).get("images", []):
            uploaded_name = upload_image(base_url, image, spec_dir)
            uploaded.append((image, uploaded_name))
            local_path = resolve_path(str(image["local_path"]), spec_dir)
            input_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_path, input_dir / local_path.name)
    else:
        for image in spec.get("inputs", {}).get("images", []):
            uploaded.append((image, str(image.get("remote_name") or Path(image["local_path"]).name)))
    timing["steps"]["upload_inputs_seconds"] = round(time.monotonic() - upload_started, 3)

    apply_image_inputs(workflow, uploaded)
    for patch in spec.get("patches", []):
        apply_patch_entry(workflow, patch)

    payload = {"prompt": workflow}
    write_json(artifacts_dir / "workflow_used.json", workflow)
    write_json(artifacts_dir / "payload.json", payload)
    write_json(artifacts_dir / "run_spec_used.json", spec)

    if dry_run:
        print(f"dry-run: wrote {artifacts_dir / 'workflow_used.json'}")
        return 0

    submit_started = time.monotonic()
    prompt_id = submit_prompt(base_url, artifacts_dir / "payload.json")
    timing["steps"]["submit_seconds"] = round(time.monotonic() - submit_started, 3)
    timing["prompt_id"] = prompt_id
    print(f"prompt_id: {prompt_id}")
    history_entry, poll_timing = poll_history(
        base_url,
        prompt_id,
        int(spec.get("timeout_seconds", 900)),
        float(spec.get("poll_interval_seconds", 2.0)),
    )
    timing["steps"].update(poll_timing)
    write_json(artifacts_dir / "history.json", {prompt_id: history_entry})

    status = history_entry.get("status", {})
    if status.get("status_str") == "error":
        raise WorkflowError(f"ComfyUI execution failed; see {artifacts_dir / 'history.json'}")

    images = collect_images(history_entry)
    download_started = time.monotonic()
    downloaded = download_images(base_url, images, output_dir)
    timing["steps"]["download_outputs_seconds"] = round(time.monotonic() - download_started, 3)
    timing["finished_at"] = utc_now_iso()
    timing["total_seconds"] = round(time.monotonic() - total_started, 3)
    timing["status"] = status.get("status_str", "unknown")
    timing["outputs"] = [str(path.relative_to(run_dir)) for path in downloaded]
    write_json(artifacts_dir / "timing.json", timing)
    if downloaded:
        preview_lines = "\n".join(f"- [{path.name}](images/{path.name})" for path in downloaded)
    else:
        preview_lines = "- No images downloaded"
    (run_dir / "README.md").write_text(
        f"# {run_id}\n\n"
        f"status: `{timing['status']}`  \n"
        f"total: `{timing['total_seconds']}s`  \n"
        f"prompt_id: `{prompt_id}`\n\n"
        f"## Images\n\n{preview_lines}\n\n"
        f"## Details\n\nMachine-readable files are in `artifacts/`.\n",
        encoding="utf-8",
    )
    print(f"status: {status.get('status_str', 'unknown')}")
    for path in downloaded:
        print(f"output: {path}")
    print(f"timing: {artifacts_dir / 'timing.json'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a ComfyUI workflow from a run spec JSON")
    parser.add_argument("--spec", required=True, help="Path to run_spec.json")
    parser.add_argument("--comfy-url", help="ComfyUI base URL; overrides spec.comfy_url and COMFYUI_URL")
    parser.add_argument("--dry-run", action="store_true", help="Write payload/workflow_used without contacting ComfyUI")
    args = parser.parse_args()

    try:
        return run(Path(args.spec).resolve(), args.comfy_url, args.dry_run)
    except WorkflowError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
