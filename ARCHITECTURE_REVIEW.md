# Architecture Review Notes

This document summarizes the current MVP architecture for review.

The project goal is to control a RunPod-hosted ComfyUI instance from a local
workspace. The intended full loop is:

```text
start one RunPod Pod for a session
bootstrap ComfyUI, models, and optional custom nodes
run multiple ComfyUI workflow API JSONs against that Pod
download outputs locally
terminate the Pod at the end
reap leaked Pods if something went wrong
```

The design deliberately avoids creating a Pod per workflow. A session owns one
Pod, and workflow runs happen inside that session.

## Current Status

Manually verified in an earlier test:

- local machine can reach RunPod ComfyUI through `https://<pod_id>-8188.proxy.runpod.net`
- `/system_stats`, `/queue`, `/prompt`, `/history`, `/view`, and `/upload/image` work
- `Z-Image-Turbo.json` can run after models are installed
- a generated image can be uploaded into another workflow
- `Flux.2_klein_9b.json` can run with a patched prompt/image input
- outputs and `workflow_used.json` can be saved locally

Implemented but not yet tested against a newly created Pod:

- RunPod Pod creation CLI
- bootstrap script injection through `dockerStartCmd`
- session JSON creation
- terminate CLI
- reaper CLI
- reusable Docker image definition under `docker/`
- session status/cost monitor CLI

## Architecture

### Local Control Plane

The local repo is the control plane. It stores:

- workflow templates in `workflows/`
- run specs in `runspecs/`
- session metadata in `sessions/<session_id>/session.json`
- output artifacts in `sessions/<session_id>/runs/<run_id>/`

RunPod credentials are not stored in the repo. The CLIs read `RUNPOD_API_KEY`
from the environment.

### RunPod Session

A session is one RunPod Pod.

`start_session.py` creates the Pod and writes:

```text
sessions/<session_id>/session.json
sessions/current.json
```

The session records:

- `session_id`
- `pod_id`
- `pod_name`
- `profile`
- `comfyui_url`
- `status`
- `started_at`
- `max_runtime_minutes`
- `max_cost_per_hour`

`run_workflow.py` uses `sessions/current.json` automatically when no explicit
ComfyUI URL is provided.

### Bootstrap Strategy

The current MVP uses RunPod Pod creation fields to pass a startup command:

```text
dockerStartCmd: ["bash", "-lc", "<generated bootstrap script>"]
```

The generated script can:

- clone ComfyUI
- install ComfyUI requirements
- clone optional custom node repos listed in the profile
- install custom node requirements
- download model files to configured paths
- start ComfyUI on `0.0.0.0:8188`

This keeps Pod setup deterministic from the local profile. It also avoids
depending on a browser-only terminal session after the Pod is running.

Open design question: whether to keep this startup-script approach long term or
move to a custom Docker image / RunPod template once the setup stabilizes.

Current direction: keep a project-owned Docker image under `docker/`, avoid
RunPod templates for now, and keep models out of the image so they can be
downloaded on each Pod start.

The default Docker build targets CUDA 13.0 / PyTorch `cu130`. A CUDA 12.8 /
`cu128` fallback can be built from the same Dockerfile. The container entrypoint
checks `nvidia-smi` and `torch.cuda.is_available()` before model downloads, so
driver/CUDA mismatch should fail early.

Workflow-specific setup can be supplied at session start with
`--workflow-requirements <json>`. These files are merged into the profile
bootstrap for that session only.

## File Responsibilities

### `RUNPOD_COMFYUI_RULES.md`

Project rules and operating principles. This is the source of truth for safety
and scope decisions.

Important rules:

- one Pod per work session, not one Pod per workflow
- do not overwrite original workflow templates
- save exact workflow used for every run
- terminate Pods at the end
- reaper must detect leaked Pods from the RunPod side, not only local session files

### `AGENTS.md`

Short operational instructions for AI agents in this repo. It mirrors the core
rules from `RUNPOD_COMFYUI_RULES.md`.

### `config/profiles.example.json`

Example profile configuration. Intended to be copied to:

```text
config/profiles.json
```

The profile controls:

- allowed GPU types
- cloud type
- disk and volume size
- image or template
- exposed ports
- max runtime
- max cost per hour
- bootstrap behavior
- model download URLs and destination paths
- optional custom node repos

The example intentionally uses placeholders:

```text
PUT_IMAGE_NAME_HERE
PUT_DIRECT_DOWNLOAD_URL_HERE
```

`start_session.py` refuses to run a real Pod when these are still present.

The current example expects a project-owned image:

```text
YOUR_REGISTRY/runpod-comfy-agent:latest
```

That value is also treated as a placeholder until replaced with a real pushed
image.

### `docker/`

Reusable Docker image asset.

Current files:

- `docker/Dockerfile`: CUDA + Python + PyTorch + latest ComfyUI source
- `docker/entrypoint.sh`: optional `git pull` on start, then runs ComfyUI
- `docker/README.md`: build/push instructions

The image does not include models. Model downloads remain in the session
bootstrap profile.

### `comfy_agent/`

Reusable Python package for code that should survive beyond the root CLI
scripts.

Current modules:

- `comfy_agent.runpod`: RunPod API/session/profile/health-check helpers

Root CLI files should stay thin and import reusable behavior from this package.

### `comfy_agent/runpod.py`

Shared helpers for the RunPod CLIs.

Responsibilities:

- load/write JSON
- load profiles
- read `RUNPOD_API_KEY`
- call RunPod REST API
- build RunPod proxy URLs
- wait for HTTP JSON health checks
- load and update session files
- write `sessions/current.json`
- strip key/token-looking fields from printed session output

### `bin/start_session.py`

Creates one RunPod Pod and waits for ComfyUI.

Main flow:

```text
load profile
load workflow requirements if provided
merge required custom nodes/models into bootstrap
validate safety guards
create session_id and pod_name
build RunPod create payload
optionally generate bootstrap dockerStartCmd
POST /pods
check observed cost against max_cost_per_hour
write session.json
write sessions/current.json
wait for /system_stats unless --no-wait
mark session active
```

Safety behavior:

- requires `max_runtime_minutes`
- requires `max_cost_per_hour`
- requires explicit GPU list or template
- refuses unset model URLs on real start
- refuses placeholder image name on real start
- if created Pod reports a cost higher than the profile max, it immediately
  deletes the Pod and errors
- the example profile defaults `max_runtime_minutes` to 120 minutes; this is
  enforced by `reap_sessions.py`, not by a RunPod-side timer
- dry-run prints the generated `dockerStartCmd` script length to stderr

Important caveat:

The exact RunPod image/template must be supplied by `config/profiles.json`.
The repo does not currently know which image is best for the user's account.

### `bin/run_workflow.py`

Runs a ComfyUI workflow from a flexible run spec.

Main flow:

```text
load run spec
load workflow template
use current session's comfyui_url if no URL is provided
upload input images if requested
patch workflow node inputs
write workflow_used.json
POST /prompt
poll /history/<prompt_id>
download outputs with /view
save history and outputs
```

It uses `curl` internally for ComfyUI HTTP calls because Python
`urllib.request` hit a RunPod proxy `403 / 1010` during manual testing, while
`curl` worked. `bin/start_session.py` health checks use the same curl-based path
via `comfy_agent.runpod.wait_for_http_json`.

### `bin/end_session.py`

Terminates the current or specified session Pod.

Main flow:

```text
load session
ask confirmation unless --yes
DELETE /pods/<pod_id>
mark session closed
write session.json
```

### `bin/session_status.py`

Reads the current session, fetches RunPod Pod details, fetches `/billing/pods`
for the Pod, and prints current runtime/cost estimates. Supports `--watch` for
near-real-time polling.

If `/billing/pods` fails, it continues with Pod detail based estimates and shows
the billing error in the output.

It does not fetch Pod logs. RunPod documents Pod container/system logs in the
console UI, but no Pod logs REST endpoint is currently wired into this project.

### `bin/reap_sessions.py`

Cleanup tool for billing safety.

Main flow:

```text
read local sessions
GET /pods?desiredStatus=RUNNING
find expired local sessions
optionally find orphan RunPod Pods named comfy-session-*
print candidates
terminate only when --yes is passed
```

Use:

```bash
python bin/reap_sessions.py --include-orphans
python bin/reap_sessions.py --include-orphans --yes
```

### `RUNPOD_SETUP.md`

Operational guide for configuring profiles, starting a session, ending a
session, and reaping leaked Pods.

### `RUN_SPEC.md`

Documents run spec format for `run_workflow.py`.

### `runspecs/*.example.json`

Example run specs:

- `z-image-turbo.example.json`: text-to-image workflow patch example
- `flux-style.example.json`: image input upload plus prompt patch example

These are not strict schemas. They are practical examples for the MVP.

### `workflows/requirements.example.json`

Example setup manifest for a workflow. It can declare:

- `custom_nodes`: Git repos to clone under `ComfyUI/custom_nodes`
- `models`: files to download before ComfyUI starts
- `extra_commands`: shell commands to run before ComfyUI starts

This is separate from `runspecs/`: requirements affect Pod setup, while run specs
affect ComfyUI prompt execution.

### `workflows/*.json`

ComfyUI workflow API JSON templates.

Current files:

- `Z-Image-Turbo.json`
- `Flux.2_klein_9b.json`

These templates must not be overwritten. Per-run changes should be expressed in
run specs and saved into each run directory as `workflow_used.json`.

### `sessions/`

Runtime output and session state.

`sessions/` is intentionally ignored by git. In a full session,
`run_workflow.py` writes under:

```text
sessions/<session_id>/runs/<run_id>/
```

## Expected Workflow

Prepare local config:

```bash
cp config/profiles.example.json config/profiles.json
```

Edit:

- `pod.imageName` or `pod.templateId`
- `bootstrap.models[].url`
- GPU list / disk sizes / runtime limits if needed

Set secret:

```bash
export RUNPOD_API_KEY=...
```

Inspect Pod create payload without renting:

```bash
python bin/start_session.py --profile cheap_24gb --dry-run
```

Start:

```bash
python bin/start_session.py --profile cheap_24gb
```

Optional workflow setup:

```bash
python bin/start_session.py \
  --profile cheap_24gb \
  --workflow-requirements workflows/requirements.example.json
```

Run workflows:

```bash
python bin/run_workflow.py --spec runspecs/z-image-turbo.example.json
python bin/run_workflow.py --spec runspecs/flux-style.example.json
```

Monitor:

```bash
python bin/session_status.py --watch 10
```

Terminate:

```bash
python bin/end_session.py --yes
```

Cleanup check:

```bash
python bin/reap_sessions.py --include-orphans
```

## Review Questions

Please review especially:

1. Is `dockerStartCmd` bootstrap acceptable for MVP, or should this move to a
   custom image/template immediately?
2. Are the RunPod REST payload fields in `config/profiles.example.json`
   appropriate and current?
3. Is the cost guard robust enough, given that the create response may not always
   contain a reliable hourly cost?
4. Should the reaper identify Pods by name only, or should it also use env /
   labels / template IDs where available?
5. Is model downloading in startup script acceptable, or should model state live
   on a RunPod network volume?
6. Should `run_workflow.py` keep shelling out to `curl`, or should we revisit a
   Python HTTP client with headers that satisfy the RunPod proxy?
7. What should be the minimal `config/profiles.json` fields for a safe first
   real run?

## Known Risks / Gaps

- No real automated Pod create test has been run yet.
- The example image name is a placeholder.
- Model URLs are placeholders.
- Startup model downloads may make Pod start slow and may fail on expiring URLs.
  The example `health_timeout_seconds` is set to 3600 seconds, but this still
  needs to match actual model size and network speed.
- If ComfyUI startup takes longer than `health_timeout_seconds`, the Pod remains
  rented until `end_session.py` or `reap_sessions.py` is run.
- The two-hour runtime limit is currently a local reaper policy. If the reaper is
  never run, RunPod will not automatically terminate from this setting alone.
- Private Docker registries require RunPod container registry auth configuration
  through `containerRegistryAuthId`, or the image should be public for first test.
- `reap_sessions.py` can terminate orphan Pods by name; this is intentional but
  should be reviewed carefully.
- There is no formal JSON schema for profiles, run specs, or workflow requirements yet.
- `__pycache__/` exists locally and should probably be ignored if this becomes a
  proper git repo.

## References Used For Implementation

- RunPod REST create Pod:
  https://docs.runpod.io/api-reference/pods/POST/pods
- RunPod REST list Pods:
  https://docs.runpod.io/api-reference/pods/GET/pods
- RunPod REST delete Pod:
  https://docs.runpod.io/api-reference/pods/DELETE/pods/podId
- RunPod HTTP proxy URL format:
  https://docs.runpod.io/pods/configuration/expose-ports
