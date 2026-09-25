from __future__ import annotations

import json

from llm_runpod.cli import main
from llm_runpod.config import LaunchConfig
from llm_runpod.runpodctl import build_pod_create_command, build_vllm_args, redact_command


def test_plan_prints_vllm_runpod_commands(capsys):
    main(["plan", "--model-id", "org/model", "--volume-id", "vol_123", "--terminate-after", "2026-09-25T23:00:00Z"])

    data = json.loads(capsys.readouterr().out)

    assert data["model_id"] == "org/model"
    assert data["server"] == "vLLM OpenAI-compatible API"
    assert data["openai_base_url"] == "https://<pod-id>-8000.proxy.runpod.net/v1"
    assert "--network-volume-id" in data["pod_command"]
    assert "volume_command" not in data


def test_vllm_args_include_arbitrary_model_and_cache_dir():
    config = LaunchConfig(
        model_id="medismera/Qwen3.8-27B-OBLITERATED-Mythos-Class-Agentic",
        name="test",
        gpu_id="NVIDIA RTX 4090",
        image="vllm/vllm-openai:latest",
        port=8000,
        volume_id="vol_123",
        volume_name="cache",
        volume_size_gb=300,
        data_center_id="US-MO-2",
        volume_mount_path="/workspace",
        hf_token="secret",
        tensor_parallel_size=1,
        max_model_len=8192,
        dtype="auto",
        quantization=None,
        trust_remote_code=True,
        terminate_after=None,
        extra_vllm_args=("--gpu-memory-utilization", "0.92"),
    )

    args = build_vllm_args(config)
    command = build_pod_create_command(config)
    redacted = redact_command(command)

    assert "--model" in args
    assert "medismera/Qwen3.8-27B-OBLITERATED-Mythos-Class-Agentic" in args
    assert "--trust-remote-code" in args
    assert "--gpu-memory-utilization" in args
    assert "secret" not in " ".join(redacted)
    assert "[redacted]" in " ".join(redacted)


def test_vscode_continue_config(capsys):
    main(
        [
            "vscode",
            "--target",
            "continue",
            "--base-url",
            "https://pod-8000.proxy.runpod.net/v1",
            "--model",
            "org/model",
        ]
    )

    output = capsys.readouterr().out

    assert "provider: openai" in output
    assert "model: org/model" in output
    assert "apiBase: https://pod-8000.proxy.runpod.net/v1" in output
    assert "useResponsesApi: false" in output


def test_vscode_cline_config(capsys):
    main(
        [
            "vscode",
            "--target",
            "cline",
            "--base-url",
            "https://pod-8000.proxy.runpod.net/v1",
            "--model",
            "org/model",
            "--api-key",
            "unused",
        ]
    )

    data = json.loads(capsys.readouterr().out)

    assert data["fields"]["API Provider"] == "OpenAI Compatible"
    assert data["fields"]["Base URL"] == "https://pod-8000.proxy.runpod.net/v1"
    assert data["fields"]["Model ID"] == "org/model"
