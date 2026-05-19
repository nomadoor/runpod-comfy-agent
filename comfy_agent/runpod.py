"""Shared helpers for the RunPod ComfyUI MVP CLIs."""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "profiles.json"
SESSIONS_ROOT = ROOT / "sessions"
CURRENT_SESSION_PATH = SESSIONS_ROOT / "current.json"
RUNPOD_REST_BASE = "https://rest.runpod.io/v1"


class RunPodError(RuntimeError):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)


def load_profiles(path: Path = CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        raise RunPodError(f"missing config: {path}. Copy config/profiles.example.json to config/profiles.json")
    data = load_json(path)
    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        raise RunPodError(f"{path} must contain a top-level profiles object")
    return profiles


def get_api_key() -> str:
    api_key = os.environ.get("RUNPOD_API_KEY", "").strip()
    if not api_key:
        raise RunPodError("RUNPOD_API_KEY is required")
    return api_key


def runpod_request(method: str, path: str, payload: Any | None = None, query: dict[str, Any] | None = None) -> Any:
    url = f"{RUNPOD_REST_BASE}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query, doseq=True)}"
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {get_api_key()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            text = response.read().decode("utf-8")
            if not text:
                return None
            return json.loads(text)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RunPodError(f"RunPod API {method} {path} failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RunPodError(f"RunPod API {method} {path} failed: {exc}") from exc


def proxy_url(pod_id: str, port: int) -> str:
    return f"https://{pod_id}-{port}.proxy.runpod.net"


def curl_json_url(url: str, timeout_seconds: int = 20) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [
                "curl",
                "-fsS",
                "--max-time",
                str(timeout_seconds),
                "-H",
                "Accept: application/json",
                "-H",
                "User-Agent: runpod-comfy-agent/0.1",
                url,
            ],
            check=False,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise RunPodError("curl is required for RunPod proxy health checks, but it was not found") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RunPodError(f"curl health check failed with exit code {result.returncode}: {detail}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RunPodError(f"health check expected JSON, got: {result.stdout[:500]}") from exc


def wait_for_http_json(url: str, timeout_seconds: int, interval_seconds: float = 5.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error = ""
    while time.monotonic() < deadline:
        try:
            return curl_json_url(url, timeout_seconds=20)
        except Exception as exc:  # noqa: BLE001 - we want a compact health retry loop.
            last_error = str(exc)
            time.sleep(interval_seconds)
    raise RunPodError(f"timed out waiting for {url}; last error: {last_error}")


def make_session_id(prefix: str = "comfy") -> str:
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"


def session_dir(session_id: str) -> Path:
    return SESSIONS_ROOT / session_id


def save_current_session(session: dict[str, Any]) -> None:
    write_json(CURRENT_SESSION_PATH, {"session_id": session["session_id"], "session_path": str(session_dir(session["session_id"]))})


def load_current_session() -> dict[str, Any]:
    if not CURRENT_SESSION_PATH.exists():
        raise RunPodError("no current session. Pass --session-id or run start_session.py first")
    pointer = load_json(CURRENT_SESSION_PATH)
    path = Path(pointer["session_path"]) / "session.json"
    if not path.exists():
        raise RunPodError(f"current session file is missing: {path}")
    return load_json(path)


def load_session(session_id: str | None = None) -> dict[str, Any]:
    if session_id:
        path = session_dir(session_id) / "session.json"
        if not path.exists():
            raise RunPodError(f"session not found: {path}")
        return load_json(path)
    return load_current_session()


def update_session(session: dict[str, Any]) -> None:
    write_json(session_dir(session["session_id"]) / "session.json", session)


def public_session(session: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in session.items() if "key" not in k.lower() and "token" not in k.lower()}
