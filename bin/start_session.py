#!/usr/bin/env python3
"""Create a RunPod Pod session and wait for ComfyUI."""

from __future__ import annotations

import argparse
import copy
import json
import shlex
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comfy_agent.runpod import (
    RunPodError,
    load_profiles,
    make_session_id,
    proxy_url,
    public_session,
    runpod_request,
    save_current_session,
    session_dir,
    update_session,
    utc_now_iso,
    curl_json_url,
    wait_for_http_json,
)
from comfy_agent.workflow_requirements import extract_workflow_models, iter_workflow_model_refs


ROOT = Path(__file__).resolve().parents[1]


def shell_quote(value: str) -> str:
    return shlex.quote(value)


def build_bootstrap_script(bootstrap: dict[str, Any], comfy_port: int) -> str:
    comfy_dir = bootstrap.get("comfyui_dir", "/opt/ComfyUI")
    repo_url = bootstrap.get("comfyui_repo", "https://github.com/comfyanonymous/ComfyUI.git")
    python_bin = bootstrap.get("python", "python3")
    lines = [
        "set -euo pipefail",
        "echo '[comfy-agent] bootstrap start'",
        f"COMFY_DIR={shell_quote(str(comfy_dir))}",
        "mkdir -p \"$(dirname \"$COMFY_DIR\")\"",
    ]

    if bootstrap.get("install_comfyui", True):
        lines.extend(
            [
                "if [ ! -d \"$COMFY_DIR/.git\" ]; then",
                f"  git clone {shell_quote(str(repo_url))} \"$COMFY_DIR\"",
                "fi",
            ]
        )

    lines.extend(
        [
            "cd \"$COMFY_DIR\"",
            "if [ -d .git ] && [ \"${COMFY_UPDATE_ON_START:-0}\" = \"1\" ]; then",
            "  git pull --ff-only",
            "fi",
            "if [ -f requirements.txt ]; then",
            f"  {python_bin} -m pip install -r requirements.txt",
            "fi",
        ]
    )

    for node in bootstrap.get("custom_nodes", []):
        url = node["git"]
        name = node.get("name") or Path(url).stem.removesuffix(".git")
        dest = f"custom_nodes/{name}"
        lines.extend(
            [
                f"if [ ! -d {shell_quote(dest)} ]; then",
                f"  git clone {shell_quote(url)} {shell_quote(dest)}",
                "fi",
                f"if [ -f {shell_quote(dest + '/requirements.txt')} ]; then",
                f"  {python_bin} -m pip install -r {shell_quote(dest + '/requirements.txt')}",
                "fi",
            ]
        )

    model_lines = []
    for model in bootstrap.get("models", []):
        url = model["url"]
        path = model["path"]
        partial_path = f"{path}.part"
        model_lines.extend(
            [
                f"mkdir -p \"$(dirname {shell_quote(path)})\"",
                f"if [ ! -s {shell_quote(path)} ]; then",
                f"  echo '[comfy-agent] downloading {Path(path).name}'",
                f"  rm -f {shell_quote(partial_path)}",
                f"  curl -L --fail --retry 5 --retry-delay 5 -o {shell_quote(partial_path)} {shell_quote(url)}",
                f"  mv {shell_quote(partial_path)} {shell_quote(path)}",
                "fi",
            ]
        )
    if model_lines and bootstrap.get("background_model_downloads", True):
        log_path = bootstrap.get("model_download_log", "/workspace/comfy-agent-model-download.log")
        lines.extend(
            [
                f"mkdir -p \"$(dirname {shell_quote(str(log_path))})\"",
                "download_comfy_models() {",
                "  set -euo pipefail",
            ]
        )
        lines.extend(f"  {line}" for line in model_lines)
        lines.extend(
            [
                "  echo '[comfy-agent] all downloads done'",
                "}",
                f"echo '[comfy-agent] starting model downloads in background: {log_path}'",
                f"download_comfy_models > {shell_quote(str(log_path))} 2>&1 &",
            ]
        )
    else:
        lines.extend(model_lines)

    extra_commands = bootstrap.get("extra_commands", [])
    if extra_commands:
        lines.append("echo '[comfy-agent] extra setup'")
        lines.extend(str(command) for command in extra_commands)

    if bootstrap.get("start_comfyui", True):
        args = bootstrap.get("comfyui_args", ["--listen", "0.0.0.0", "--enable-cors-header"])
        if "--port" not in args:
            args = [*args, "--port", str(comfy_port)]
        quoted_args = " ".join(shell_quote(str(arg)) for arg in args)
        lines.extend(
            [
                "echo '[comfy-agent] starting ComfyUI'",
                f"exec {python_bin} main.py {quoted_args}",
            ]
        )

    return "\n".join(lines)


def build_pod_payload(profile: dict[str, Any], session_id: str, pod_name: str) -> dict[str, Any]:
    payload = copy.deepcopy(profile.get("pod", {}))
    if not payload:
        raise RunPodError("profile.pod is required")
    payload["name"] = pod_name

    comfy_port = int(profile.get("comfyui_port", 8188))
    ports = list(payload.get("ports", []))
    comfy_port_spec = f"{comfy_port}/http"
    if comfy_port_spec not in ports:
        ports.append(comfy_port_spec)
    payload["ports"] = ports

    env = dict(payload.get("env", {}))
    env["COMFY_AGENT_SESSION_ID"] = session_id
    payload["env"] = env

    bootstrap = profile.get("bootstrap", {})
    if bootstrap.get("enabled", False):
        payload["dockerStartCmd"] = ["bash", "-lc", build_bootstrap_script(bootstrap, comfy_port)]

    return payload


def bootstrap_length(payload: dict[str, Any]) -> int:
    command = payload.get("dockerStartCmd") or []
    if len(command) >= 3:
        return len(str(command[2]))
    return 0


def load_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise RunPodError(f"{path} must contain a JSON object")
    return data


def resolve_requirements_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    candidate = (ROOT / path).resolve()
    if candidate.exists():
        return candidate
    return (ROOT / "workflows" / value).resolve()


def load_workflow_requirements(values: list[str]) -> list[dict[str, Any]]:
    requirements: list[dict[str, Any]] = []
    for value in values:
        path = resolve_requirements_path(value)
        if path.is_dir():
            path = path / "requirements.json"
        if not path.exists():
            raise RunPodError(f"workflow requirements file not found: {path}")
        requirements.append(load_json_file(path))
    return requirements


def load_workflow_jsons(values: list[str]) -> list[dict[str, Any]]:
    workflows: list[dict[str, Any]] = []
    for value in values:
        path = Path(value)
        if not path.is_absolute():
            path = (ROOT / path).resolve()
        if not path.exists():
            raise RunPodError(f"workflow JSON file not found: {path}")
        workflows.append(load_json_file(path))
    return workflows


def merge_named_items(base: list[dict[str, Any]], extra: list[dict[str, Any]], key_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    merged = [copy.deepcopy(item) for item in base]
    seen: set[tuple[str, ...]] = set()
    for item in merged:
        seen.add(tuple(str(item.get(key, "")) for key in key_fields))
    for item in extra:
        marker = tuple(str(item.get(key, "")) for key in key_fields)
        if marker in seen:
            continue
        merged.append(copy.deepcopy(item))
        seen.add(marker)
    return merged


def apply_workflow_requirements(profile: dict[str, Any], requirements: list[dict[str, Any]]) -> dict[str, Any]:
    if not requirements:
        return profile
    profile = copy.deepcopy(profile)
    bootstrap = profile.setdefault("bootstrap", {})
    bootstrap["enabled"] = True

    custom_nodes = list(bootstrap.get("custom_nodes", []))
    models = list(bootstrap.get("models", []))
    extra_commands = list(bootstrap.get("extra_commands", []))

    for req in requirements:
        custom_nodes = merge_named_items(custom_nodes, req.get("custom_nodes", []), ("git",))
        models = merge_named_items(models, req.get("models", []), ("path",))
        extra_commands.extend(req.get("extra_commands", []))

    bootstrap["custom_nodes"] = custom_nodes
    bootstrap["models"] = models
    bootstrap["extra_commands"] = extra_commands
    return profile


def apply_workflow_json_requirements(profile: dict[str, Any], workflows: list[dict[str, Any]]) -> dict[str, Any]:
    if not workflows:
        return profile
    profile = copy.deepcopy(profile)
    bootstrap = profile.setdefault("bootstrap", {})
    bootstrap["enabled"] = True
    comfy_dir = str(bootstrap.get("comfyui_dir", "/opt/ComfyUI"))
    models = [
        model
        for model in bootstrap.get("models", [])
        if model.get("url") and model.get("url") != "PUT_DIRECT_DOWNLOAD_URL_HERE"
    ]
    inferred_models: list[dict[str, Any]] = []
    for workflow in workflows:
        inferred_models.extend(extract_workflow_models(workflow, comfy_dir))
    bootstrap["models"] = merge_named_items(models, inferred_models, ("path",))
    return profile


def workflow_model_checks(workflows: list[dict[str, Any]]) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for workflow in workflows:
        for ref in iter_workflow_model_refs(workflow):
            marker = (ref["class_type"], ref["input_name"], ref["filename"])
            if marker in seen:
                continue
            checks.append(
                {
                    "class_type": ref["class_type"],
                    "input_name": ref["input_name"],
                    "filename": ref["filename"],
                }
            )
            seen.add(marker)
    return checks


def object_info_has_value(object_info: dict[str, Any], class_type: str, input_name: str, filename: str) -> bool:
    node_info = object_info.get(class_type) if isinstance(object_info, dict) else None
    if not isinstance(node_info, dict):
        return False
    input_info = node_info.get("input") or {}
    if not isinstance(input_info, dict):
        return False
    for group_name in ("required", "optional"):
        group = input_info.get(group_name) or {}
        if not isinstance(group, dict):
            continue
        config = group.get(input_name)
        if isinstance(config, list) and config and isinstance(config[0], list):
            return filename in config[0]
    return False


def wait_for_workflow_models(comfyui_url: str, checks: list[dict[str, str]], timeout_seconds: int) -> None:
    if not checks:
        return
    deadline = time.monotonic() + timeout_seconds
    pending = checks
    last_error = ""
    while time.monotonic() < deadline:
        next_pending: list[dict[str, str]] = []
        for check in pending:
            try:
                object_info = curl_json_url(f"{comfyui_url}/object_info/{check['class_type']}", timeout_seconds=20)
                if not object_info_has_value(
                    object_info,
                    check["class_type"],
                    check["input_name"],
                    check["filename"],
                ):
                    next_pending.append(check)
            except Exception as exc:  # noqa: BLE001 - compact readiness retry loop.
                last_error = str(exc)
                next_pending.append(check)
        if not next_pending:
            return
        pending = next_pending
        time.sleep(5)

    details = "\n".join(
        f"- {item['class_type']}.{item['input_name']}: {item['filename']}" for item in pending
    )
    suffix = f"; last error: {last_error}" if last_error else ""
    raise RunPodError(f"timed out waiting for workflow models to appear in ComfyUI:\n{details}{suffix}")


def enforce_profile_guards(profile_name: str, profile: dict[str, Any], *, dry_run: bool) -> None:
    if "max_runtime_minutes" not in profile:
        raise RunPodError(f"profile {profile_name} must set max_runtime_minutes")
    if "max_cost_per_hour" not in profile:
        raise RunPodError(f"profile {profile_name} must set max_cost_per_hour")
    pod = profile.get("pod", {})
    if not pod.get("gpuTypeIds") and not pod.get("templateId"):
        raise RunPodError(f"profile {profile_name} must set pod.gpuTypeIds or pod.templateId")
    image_name = str(pod.get("imageName", ""))
    if not dry_run and image_name in {"PUT_IMAGE_NAME_HERE", "YOUR_REGISTRY/runpod-comfy-agent:latest"} and not pod.get("templateId"):
        raise RunPodError(f"profile {profile_name} must set a real pod.imageName or pod.templateId")
    bootstrap = profile.get("bootstrap", {})
    if bootstrap.get("enabled", False) and not dry_run:
        for model in bootstrap.get("models", []):
            url = str(model.get("url", ""))
            if not url or url == "PUT_DIRECT_DOWNLOAD_URL_HERE":
                raise RunPodError(f"profile {profile_name} has an unset model URL for {model.get('name') or model.get('path')}")


def pod_cost_per_hour(pod: dict[str, Any]) -> float | None:
    for key in ("adjustedCostPerHr", "costPerHr"):
        value = pod.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    machine = pod.get("machine") or {}
    for key in ("currentPricePerGpu", "costPerHr"):
        value = machine.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Start a RunPod ComfyUI session")
    parser.add_argument("--profile", default="l4")
    parser.add_argument("--config", default="config/profiles.json")
    parser.add_argument("--session-prefix", default="comfy")
    parser.add_argument(
        "--workflow-requirements",
        action="append",
        default=[],
        help="Path to a workflow requirements JSON file; may be passed multiple times",
    )
    parser.add_argument(
        "--workflow-json",
        action="append",
        default=[],
        help="Path to a workflow API JSON file; loader nodes are inspected and known model URLs are added",
    )
    parser.add_argument("--no-wait", action="store_true", help="Create the Pod but do not wait for ComfyUI")
    parser.add_argument("--dry-run", action="store_true", help="Print the RunPod create payload without calling RunPod")
    args = parser.parse_args()

    try:
        profiles = load_profiles(Path(args.config))
        if args.profile not in profiles:
            raise RunPodError(f"unknown profile: {args.profile}")
        profile = profiles[args.profile]
        workflow_jsons = load_workflow_jsons(args.workflow_json)
        profile = apply_workflow_requirements(profile, load_workflow_requirements(args.workflow_requirements))
        profile = apply_workflow_json_requirements(profile, workflow_jsons)
        enforce_profile_guards(args.profile, profile, dry_run=args.dry_run)

        session_id = make_session_id(args.session_prefix)
        pod_name = f"comfy-session-{session_id}"
        payload = build_pod_payload(profile, session_id, pod_name)
        if args.dry_run:
            length = bootstrap_length(payload)
            if length:
                print(f"dry-run: dockerStartCmd script length={length} chars", file=sys.stderr)
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0

        pod = runpod_request("POST", "/pods", payload)
        pod_id = pod.get("id")
        if not pod_id:
            raise RunPodError(f"RunPod create response did not include pod id: {json.dumps(pod, ensure_ascii=False)}")
        observed_cost = pod_cost_per_hour(pod)
        max_cost = float(profile["max_cost_per_hour"])
        if observed_cost is not None and observed_cost > max_cost:
            runpod_request("DELETE", f"/pods/{pod_id}")
            raise RunPodError(
                f"created Pod cost {observed_cost} exceeds profile max_cost_per_hour {max_cost}; Pod was terminated"
            )
        comfy_port = int(profile.get("comfyui_port", 8188))
        comfyui_url = proxy_url(pod_id, comfy_port)
        now = utc_now_iso()
        session = {
            "session_id": session_id,
            "pod_id": pod_id,
            "pod_name": pod_name,
            "profile": args.profile,
            "status": "starting",
            "started_at": now,
            "updated_at": now,
            "max_runtime_minutes": int(profile["max_runtime_minutes"]),
            "max_cost_per_hour": profile["max_cost_per_hour"],
            "comfyui_url": comfyui_url,
            "runpod_pod": {
                "id": pod.get("id"),
                "name": pod.get("name"),
                "desiredStatus": pod.get("desiredStatus"),
                "costPerHr": pod.get("costPerHr"),
                "adjustedCostPerHr": pod.get("adjustedCostPerHr"),
                "gpu": pod.get("gpu"),
                "ports": pod.get("ports"),
            },
        }
        update_session(session)
        save_current_session(session)

        if not args.no_wait:
            wait_for_http_json(f"{comfyui_url}/system_stats", int(profile.get("health_timeout_seconds", 900)))
            wait_for_workflow_models(
                comfyui_url,
                workflow_model_checks(workflow_jsons),
                int(profile.get("model_ready_timeout_seconds", profile.get("health_timeout_seconds", 900))),
            )
            session["status"] = "active"
            session["updated_at"] = utc_now_iso()
            update_session(session)

        print(json.dumps(public_session(session), indent=2, ensure_ascii=False))
        print(
            "REMINDER: run 'python bin/end_session.py --yes' when done, "
            "or 'python bin/reap_sessions.py --include-orphans' to check for leaked Pods.",
            file=sys.stderr,
        )
        return 0
    except RunPodError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
