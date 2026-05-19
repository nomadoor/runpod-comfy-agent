# RunPod Session Setup

This project keeps RunPod infrastructure actions behind local CLIs:

```bash
python bin/start_session.py --profile cheap_24gb
python bin/run_workflow.py --spec runspecs/z-image-turbo.example.json
python bin/session_status.py --watch 10
python bin/end_session.py --yes
python bin/reap_sessions.py --include-orphans --yes
```

Reusable code lives under `comfy_agent/`. CLI entrypoints live under `bin/`; new
library-style code should go into the package rather than being added to the
entrypoints. The repo root is kept mostly to Markdown documents and top-level
directories.

## Configuration

Copy the example profile and edit it by hand:

```bash
cp config/profiles.example.json config/profiles.json
```

Set the model download URLs in `bootstrap.models`. The profile example uses these
ComfyUI paths:

```text
models/diffusion_models/
models/text_encoders/
models/vae/
```

Do not put API keys directly in `config/profiles.json`. Use an environment
variable:

```bash
export RUNPOD_API_KEY=...
```

The CLIs also read a git-ignored repo-local `.env` file:

```bash
RUNPOD_API_KEY=...
```

`config/profiles.json`, `.env*`, and `sessions/` are ignored by git.

Also set either:

```json
{
  "pod": {
    "imageName": "YOUR_REGISTRY/runpod-comfy-agent:latest"
  }
}
```

If the image is in a private registry, create a RunPod container registry auth
entry and set its ID in the profile:

```json
{
  "pod": {
    "containerRegistryAuthId": "your-registry-auth-id"
  }
}
```

For the first real test, a public image is simpler.

or:

```json
{
  "pod": {
    "templateId": "your-template-id"
  }
}
```

The repo includes a Docker image definition under `docker/`:

```bash
docker build -f docker/Dockerfile -t YOUR_REGISTRY/runpod-comfy-agent:latest .
docker push YOUR_REGISTRY/runpod-comfy-agent:latest
```

That image installs CUDA PyTorch and ComfyUI, then the session bootstrap downloads
models on each Pod start.

The default image is CUDA 13.0 / PyTorch `cu130`. If the chosen RunPod host
driver does not support that combination, build and use the documented CUDA 12.8
fallback tag instead.

## Start A Session

```bash
python bin/start_session.py --profile cheap_24gb
```

If a workflow needs extra custom nodes or models, declare them in a requirements
JSON and pass it at session start:

```bash
python bin/start_session.py \
  --profile cheap_24gb \
  --workflow-requirements workflows/requirements.example.json
```

Multiple `--workflow-requirements` flags can be passed. They are merged into the
profile's `bootstrap.custom_nodes`, `bootstrap.models`, and
`bootstrap.extra_commands` for that session only.

`start_session.py` will:

- create one RunPod Pod for the session
- include `comfy-session-<session_id>` in the Pod name
- expose `8188/http`
- optionally run the bootstrap script from the profile
- wait for `https://<pod_id>-8188.proxy.runpod.net/system_stats`
- write `sessions/<session_id>/session.json`
- write `sessions/current.json`

The example profile defaults to `max_runtime_minutes: 120`. This is stored in
`session.json` and enforced by `reap_sessions.py`; it is not a RunPod-side timer
by itself.

The health check uses `curl`, not Python `urllib`, because RunPod's HTTP proxy
returned `403 / 1010` to `urllib` during manual testing while `curl` worked.

Use `--dry-run` to inspect the create payload before renting a Pod:

```bash
python bin/start_session.py --profile cheap_24gb --dry-run
```

## End A Session

```bash
python bin/end_session.py --yes
```

This reads the current session and deletes the Pod through RunPod.

## Monitor A Session

```bash
python bin/session_status.py
python bin/session_status.py --watch 10
python bin/session_status.py --json
```

This uses the RunPod REST API to read the current Pod details and
`/billing/pods` history for the session Pod. It reports:

- Pod/session status
- GPU and hourly cost when returned by RunPod
- elapsed runtime
- estimated active cost from elapsed time and hourly cost
- billing records returned by RunPod for the session period

If `/billing/pods` fails or is unavailable, the command still prints Pod status
and estimated cost from Pod details when possible.

Current account credit balance is documented in the RunPod Billing console, but
there is no dedicated balance endpoint wired here yet.

Pod logs are documented by RunPod as Console UI logs: container logs and system
logs. The REST API docs currently expose billing and Pod management endpoints,
but this project does not yet have a documented Pod logs API to call. The
container image prints startup checks to stdout so they are visible in RunPod's
Pod Logs panel.

## Reap Leaked Pods

```bash
python bin/reap_sessions.py --include-orphans --yes
```

Without `--yes`, it only prints what it would terminate.

Run this after work sessions, and also whenever you suspect a local script exited
before calling `end_session.py`.

## Bootstrap Strategy

The first implementation prepares the Pod through `dockerStartCmd`, because it is
available at Pod creation time. The script can:

- clone ComfyUI if it is not already present
- install `requirements.txt`
- clone optional custom node repos listed in the profile or workflow requirements
- download model files into the configured ComfyUI model paths
- start ComfyUI on port `8188`

This is intentionally simple. If the chosen RunPod template already has its own
startup logic, either disable `bootstrap.enabled` or move that logic into
`bootstrap.extra_commands`.

Model downloads can easily dominate startup time. Set `health_timeout_seconds`
large enough for the total model size and network speed, or prefer a RunPod
network volume / prebuilt image once the model set stabilizes.

If the model list grows, watch the generated `dockerStartCmd` size with:

```bash
python bin/start_session.py --profile cheap_24gb --dry-run
```
