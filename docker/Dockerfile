ARG CUDA_IMAGE=nvidia/cuda:13.0.0-devel-ubuntu22.04
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cu130
FROM ${CUDA_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    COMFY_DIR=/opt/ComfyUI \
    COMFY_UPDATE_ON_START=1 \
    TORCH_INDEX_URL=${TORCH_INDEX_URL}

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --upgrade pip setuptools wheel

RUN python3 -m pip install \
    torch \
    torchvision \
    torchaudio \
    --index-url "${TORCH_INDEX_URL}"

RUN git clone https://github.com/comfyanonymous/ComfyUI.git "${COMFY_DIR}" \
    && cd "${COMFY_DIR}" \
    && python3 -m pip install -r requirements.txt

COPY docker/entrypoint.sh /opt/runpod-comfy-agent/entrypoint.sh
RUN chmod +x /opt/runpod-comfy-agent/entrypoint.sh

WORKDIR /opt/ComfyUI
EXPOSE 8188

ENTRYPOINT ["/opt/runpod-comfy-agent/entrypoint.sh"]
CMD ["python3", "main.py", "--listen", "0.0.0.0", "--port", "8188", "--enable-cors-header"]
