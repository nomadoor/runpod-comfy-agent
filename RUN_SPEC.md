# Run Spec

`run_workflow.py` reads a JSON run spec, applies it to a ComfyUI workflow API JSON,
and saves the exact workflow used for the run.

Basic usage:

```bash
python bin/run_workflow.py --spec runspecs/z-image-turbo.example.json
```

If `start_session.py` has created `sessions/current.json`, `run_workflow.py` uses
that session's `comfyui_url` and stores runs under
`sessions/<session_id>/runs/`.

You can still override the URL:

```bash
COMFYUI_URL=https://xxxxx-8188.proxy.runpod.net \
python bin/run_workflow.py --spec runspecs/z-image-turbo.example.json
```

Image-to-image usage:

```bash
python bin/run_workflow.py --spec runspecs/flux-style.example.json
```

Dry run:

```bash
python bin/run_workflow.py --spec runspecs/flux-style.example.json --dry-run
```

## Fields

- `name`: Optional run directory prefix.
- `workflow_json`: Required path to the workflow API JSON template.
- `comfy_url`: Optional ComfyUI URL. `--comfy-url` or `COMFYUI_URL` can also be used.
- `runs_root`: Optional output root. Defaults to `sessions/manual-runs`.
- `inputs.images`: Optional images to upload before prompt submission.
- `patches`: Optional node input edits.
- `timeout_seconds`: Optional polling timeout.
- `poll_interval_seconds`: Optional history polling interval.

Patch by node input:

```json
{
  "node": "6",
  "field": "text",
  "value": "new prompt"
}
```

Patch by JSON path:

```json
{
  "path": ["31", "inputs", "seed"],
  "value": 5678
}
```

The original workflow template is never overwritten. Each run writes:

```text
sessions/manual-runs/<run_id>/
  README.md
  images/
  inputs/
  artifacts/
    run_spec_used.json
    workflow_used.json
    payload.json
    history.json
    timing.json
```

`images/` is the human-facing output folder. `artifacts/` is for exact replay,
debugging, ComfyUI history, and timing logs.
