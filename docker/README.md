# Docker Image

This folder defines the reusable RunPod image for the project.

The image:

- starts from an NVIDIA CUDA 13.0 cuDNN runtime base by default
- installs Python, Git, Curl, and CUDA PyTorch wheels
- clones the latest ComfyUI source at build time
- installs ComfyUI requirements
- exposes port `8188`
- optionally updates ComfyUI on container start with `COMFY_UPDATE_ON_START=1`

It is intentionally minimal: it does not install or start JupyterLab. Only
ComfyUI is exposed.

Build:

```bash
docker build -f docker/Dockerfile -t YOUR_REGISTRY/runpod-comfy-agent:latest .
```

The default build args are:

```text
CUDA_IMAGE=nvidia/cuda:13.0.0-cudnn-runtime-ubuntu22.04
TORCH_INDEX_URL=https://download.pytorch.org/whl/cu130
```

The CUDA/PyTorch choice follows the PyTorch CUDA 13.0 wheel index. If a custom
node is not compatible with CUDA 13.0 yet, rebuild with a different
`CUDA_IMAGE`/`TORCH_INDEX_URL` pair and update `config/profiles.json`.

If NVIDIA changes image tag availability, override the base image:

```bash
docker build \
  -f docker/Dockerfile \
  --build-arg CUDA_IMAGE=nvidia/cuda:13.0.0-cudnn-runtime-ubuntu22.04 \
  --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cu130 \
  -t YOUR_REGISTRY/runpod-comfy-agent:latest .
```

CUDA 12.8 fallback build:

```bash
docker build \
  -f docker/Dockerfile \
  --build-arg CUDA_IMAGE=nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04 \
  --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cu128 \
  -t YOUR_REGISTRY/runpod-comfy-agent:cu128 .
```

At container start, `entrypoint.sh` logs `nvidia-smi` and checks
`torch.cuda.is_available()`. If the selected RunPod host driver cannot support
the image/PyTorch CUDA combination, the container exits before model downloads
begin.

Push:

```bash
docker push YOUR_REGISTRY/runpod-comfy-agent:latest
```

Then put the pushed image in:

```json
{
  "pod": {
    "imageName": "YOUR_REGISTRY/runpod-comfy-agent:latest"
  }
}
```

The current `start_session.py` still sends a `dockerStartCmd` bootstrap script.
With this image, set:

```json
{
  "bootstrap": {
    "comfyui_dir": "/opt/ComfyUI",
    "install_comfyui": false
  }
}
```

Models are intentionally not baked into the image. The profile downloads them on
Pod startup into `/opt/ComfyUI/models/...`.

Set `COMFY_UPDATE_ON_START=0` in `pod.env` if you want the exact ComfyUI version
from image build time instead of pulling the latest source at container start.
