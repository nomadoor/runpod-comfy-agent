# RunPod Comfy Agent

Use this skill when operating RunPod-hosted ComfyUI through this repository's
local CLI tools.

## Core Rules

- Use the project CLIs. Do not call the RunPod API directly.
- Read the workflow API JSON before starting a Pod.
- Start sessions with `bin/start_session.py --workflow-json <workflow.json>` so
  model requirements are inferred from loader nodes.
- If a workflow model is not registered, stop and ask before creating a Pod.
- Do not swap model files or quantization variants unless the user explicitly
  approves it.
- Do not overwrite source workflow files.
- Do not choose high-cost GPUs without explicit user approval.

## Standard Flow

```bash
python3 bin/start_session.py --profile cheap_24gb --workflow-json workflows/Z-Image-Turbo.json
python3 bin/run_workflow.py --spec runspecs/z-image-turbo.example.json
python3 bin/end_session.py --yes
python3 bin/reap_sessions.py --include-orphans
```

If the user explicitly says not to terminate, leave the Pod running and report
the session id, Pod id, URL, cost/hour, and current elapsed time.

## Outputs

- Human-facing gallery: `sessions/<session_id>/images/`
- Per-run images: `sessions/<session_id>/runs/<run_id>/images/`
- Replay/debug artifacts: `sessions/<session_id>/runs/<run_id>/artifacts/`
- Per-run timing: `sessions/<session_id>/runs/<run_id>/artifacts/timing.json`

## Before Final Response

- Confirm Pod status.
- Terminate and run the reaper unless the user explicitly told you not to.
- Report image locations, session id, cost/hour, elapsed time, and termination
  status.
- If something failed, report whether any Pod is still running.

For detailed project rules, read `docs/RUNPOD_COMFYUI_RULES.md`.

