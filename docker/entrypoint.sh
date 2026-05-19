#!/usr/bin/env bash
set -euo pipefail

COMFY_DIR="${COMFY_DIR:-/opt/ComfyUI}"
cd "$COMFY_DIR"

echo "[comfy-agent] nvidia-smi"
nvidia-smi || true

echo "[comfy-agent] torch cuda check"
python3 - <<'PY'
import sys
import torch

print("torch:", torch.__version__)
print("torch cuda:", torch.version.cuda)
print("cuda available:", torch.cuda.is_available())
if not torch.cuda.is_available():
    sys.exit("CUDA is not available to PyTorch")
print("device:", torch.cuda.get_device_name(0))
PY

if [ "${COMFY_UPDATE_ON_START:-1}" = "1" ] && [ -d .git ]; then
  git pull --ff-only
  python3 -m pip install -r requirements.txt
fi

mkdir -p "$COMFY_DIR/models/diffusion_models" "$COMFY_DIR/models/text_encoders" "$COMFY_DIR/models/vae"

exec "$@"
