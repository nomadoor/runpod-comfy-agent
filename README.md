# RunPod Comfy Agent

Local CLI tools for starting a RunPod Pod, running ComfyUI workflows, collecting
images, and terminating the Pod safely.

## Main Flow

```bash
python3 bin/start_session.py --profile cheap_24gb --workflow-json workflows/Z-Image-Turbo.json
python3 bin/run_workflow.py --spec runspecs/z-image-turbo.example.json
python3 bin/end_session.py --yes
python3 bin/reap_sessions.py --include-orphans
```

Human-facing images are collected in:

```text
sessions/<session_id>/images/
```

Detailed replay artifacts are kept under each run's `artifacts/` directory.

## Docs

- [Setup](docs/RUNPOD_SETUP.md)
- [Rules](docs/RUNPOD_COMFYUI_RULES.md)
- [Run Spec](docs/RUN_SPEC.md)
- [Current Status](docs/RUNPOD_STATUS.md)
- [Architecture Review](docs/ARCHITECTURE_REVIEW.md)
- [Git Notes](docs/GIT_USAGE.md)

