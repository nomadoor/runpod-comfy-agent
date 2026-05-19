# RunPod ComfyUI Status

Last updated: 2026-05-19

## Verified

- RunPod API key can be read from a git-ignored local `.env`.
- Docker Hub image can be pulled by RunPod:
  - `nomadoor/runpod-comfy-agent:latest`
  - digest: `sha256:4a5fee7d27e585a6168ed9c851c24e18eef92fd7c170daefa70c16647bd94c87`
- The image uses CUDA 13.0 runtime + PyTorch `cu130` + latest ComfyUI at build time.
- Smoke test Pod created successfully through `bin/start_session.py`.
- ComfyUI API responded through RunPod proxy at `/system_stats`.
- Smoke test Pod was terminated through `bin/end_session.py`.
- `bin/reap_sessions.py --include-orphans` reported no leftover Pods.

## Smoke Test Result

```text
session_id: comfy-20260519-080737
pod_id: uhl71jjj3f937u
status: active -> closed
gpu: NVIDIA L4
cost/hour: 0.39
ComfyUI: 0.21.1
PyTorch: 2.12.0+cu130
VRAM: about 23.7GB
```

This smoke test intentionally skipped model downloads. It only verified Pod
creation, image pull, ComfyUI startup, proxy access, terminate, and reaper.

## Current CLI Entry Points

```bash
python3 bin/start_session.py --profile cheap_24gb
python3 bin/run_workflow.py --spec runspecs/<spec>.json
python3 bin/session_status.py
python3 bin/end_session.py --yes
python3 bin/reap_sessions.py --include-orphans
```

## Current Required Local Files

- `.env`
  - contains `RUNPOD_API_KEY`
  - git-ignored
- `config/profiles.json`
  - contains real local runtime settings
  - git-ignored

## Next Required Work

1. Replace model URL placeholders in `config/profiles.json` or workflow
   requirements JSON.
2. Run one real workflow with model downloads enabled.
3. Confirm output image download through `bin/run_workflow.py`.
4. Optionally split GPU profiles into explicit names such as `l4`, `rtx4090`,
   `l40s`, and `a100_80gb`.

