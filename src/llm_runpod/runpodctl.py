from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Sequence

from llm_runpod.config import LaunchConfig


class RunpodctlError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    stdout: str
    stderr: str


def require_runpodctl() -> None:
    if shutil.which("runpodctl") is None:
        raise RunpodctlError(
            "runpodctl is not installed. Install it with `curl -sSL https://cli.runpod.net | bash`, "
            "then run `runpodctl doctor` or set RUNPOD_API_KEY."
        )


def run_command(command: Sequence[str], *, dry_run: bool = False) -> CommandResult:
    if dry_run:
        return CommandResult(tuple(command), "", "")
    require_runpodctl()
    try:
        completed = subprocess.run(command, check=True, text=True, capture_output=True)
    except subprocess.CalledProcessError as error:
        raise RunpodctlError(
            f"Command failed: {shlex.join(command)}\nstdout:\n{error.stdout}\nstderr:\n{error.stderr}"
        ) from error
    return CommandResult(tuple(command), completed.stdout, completed.stderr)


def build_volume_create_command(config: LaunchConfig) -> list[str]:
    command = [
        "runpodctl",
        "network-volume",
        "create",
        "--name",
        config.volume_name,
        "--size",
        str(config.volume_size_gb),
    ]
    if config.data_center_id:
        command.extend(["--data-center-id", config.data_center_id])
    return command


def build_vllm_args(config: LaunchConfig) -> list[str]:
    args = [
        "--host",
        "0.0.0.0",
        "--port",
        str(config.port),
        "--model",
        config.model_id,
        "--served-model-name",
        config.model_id,
        "--download-dir",
        config.model_cache_dir,
        "--tensor-parallel-size",
        str(config.tensor_parallel_size),
        "--max-model-len",
        str(config.max_model_len),
        "--dtype",
        config.dtype,
    ]
    if config.quantization:
        args.extend(["--quantization", config.quantization])
    if config.trust_remote_code:
        args.append("--trust-remote-code")
    args.extend(config.extra_vllm_args)
    return args


def build_pod_create_command(config: LaunchConfig, volume_id: str | None = None) -> list[str]:
    env: dict[str, str] = {
        "HF_HOME": config.hf_home,
        "VLLM_CACHE_ROOT": f"{config.volume_mount_path.rstrip('/')}/vllm",
    }
    if config.hf_token:
        env["HF_TOKEN"] = config.hf_token

    command = [
        "runpodctl",
        "pod",
        "create",
        "--name",
        config.name,
        "--image-name",
        config.image,
        "--gpu-id",
        config.gpu_id,
        "--ports",
        f"{config.port}/http,22/tcp",
        "--env",
        json.dumps(env, separators=(",", ":")),
        "--docker-args",
        shlex.join(build_vllm_args(config)),
    ]
    chosen_volume = volume_id or config.volume_id
    if chosen_volume:
        command.extend(["--network-volume-id", chosen_volume, "--volume-mount-path", config.volume_mount_path])
    if config.data_center_id:
        command.extend(["--data-center-id", config.data_center_id])
    if config.terminate_after:
        command.extend(["--terminate-after", config.terminate_after])
    return command


def extract_first_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def extract_id(payload: dict[str, Any]) -> str | None:
    for key in ("id", "podId", "volumeId"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    for value in payload.values():
        if isinstance(value, dict):
            found = extract_id(value)
            if found:
                return found
    return None


def wait_for_openai_ready(base_url: str, *, timeout_seconds: int = 1800, poll_seconds: int = 10) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: str | None = None
    while time.monotonic() < deadline:
        request = urllib.request.Request(f"{base_url.rstrip('/')}/v1/models")
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                if 200 <= response.status < 300:
                    return
        except urllib.error.URLError as error:
            last_error = str(error)
        time.sleep(poll_seconds)
    raise TimeoutError(f"Timed out waiting for {base_url}/v1/models. Last error: {last_error}")


def redact_command(command: Sequence[str]) -> list[str]:
    redacted: list[str] = []
    skip_next = False
    for item in command:
        if skip_next:
            try:
                env = json.loads(item)
            except json.JSONDecodeError:
                redacted.append(item)
            else:
                if "HF_TOKEN" in env:
                    env["HF_TOKEN"] = "[redacted]"
                redacted.append(json.dumps(env, separators=(",", ":")))
            skip_next = False
            continue
        redacted.append(item)
        if item == "--env":
            skip_next = True
    return redacted


def ensure_auth_env() -> None:
    if not os.getenv("RUNPOD_API_KEY") and not os.getenv("RUNPOD_KEY"):
        raise RunpodctlError("Missing RUNPOD_API_KEY / RUNPOD_KEY. Set one before creating pods or volumes.")
