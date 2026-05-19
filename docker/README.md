# Docker image

RunPodで使うComfyUI専用imageです。

- CUDA 13.0 cuDNN runtime
- PyTorch `cu130`
- ComfyUI
- port `8188`
- ComfyUI API用の最小構成
- モデルはPod起動時にworkflowから判定して配置

## build / push

```bash
docker build -f docker/Dockerfile -t nomadoor/runpod-comfy-agent:latest .
docker push nomadoor/runpod-comfy-agent:latest
```

CUDA 12.8へ落とす場合:

```bash
docker build \
  -f docker/Dockerfile \
  --build-arg CUDA_IMAGE=nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04 \
  --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cu128 \
  -t nomadoor/runpod-comfy-agent:cu128 .
```

起動時に `entrypoint.sh` が `nvidia-smi` と `torch.cuda.is_available()` を確認します。
