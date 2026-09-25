from __future__ import annotations

import os
import time
from dataclasses import dataclass


DEFAULT_MODEL_ID = "medismera/Qwen3.8-27B-OBLITERATED-Mythos-Class-Agentic"
DEFAULT_IMAGE = "vllm/vllm-openai:latest"
DEFAULT_PORT = 8000
DEFAULT_VOLUME_MOUNT = "/workspace"
DEFAULT_VOLUME_SIZE_GB = 300
DEFAULT_GPU = "NVIDIA RTX 4090"
DEFAULT_MAX_MODEL_LEN = 32768


def env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def default_name(model_id: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in model_id)
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return f"llm-{cleaned[:36]}-{time.strftime('%Y%m%d-%H%M%S')}"


@dataclass(frozen=True)
class LaunchConfig:
    model_id: str
    name: str
    gpu_id: str
    image: str
    port: int
    volume_id: str | None
    volume_name: str
    volume_size_gb: int
    data_center_id: str | None
    volume_mount_path: str
    hf_token: str | None
    tensor_parallel_size: int
    max_model_len: int
    dtype: str
    quantization: str | None
    trust_remote_code: bool
    terminate_after: str | None
    extra_vllm_args: tuple[str, ...]

    @property
    def proxy_url(self) -> str:
        raise RuntimeError("proxy_url needs a pod id; use proxy_url_for(pod_id)")

    def proxy_url_for(self, pod_id: str) -> str:
        return f"https://{pod_id}-{self.port}.proxy.runpod.net"

    @property
    def model_cache_dir(self) -> str:
        return f"{self.volume_mount_path.rstrip('/')}/models"

    @property
    def hf_home(self) -> str:
        return f"{self.volume_mount_path.rstrip('/')}/huggingface"
