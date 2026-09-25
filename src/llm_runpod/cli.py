from __future__ import annotations

import argparse
import json
import os
import shlex
from typing import Sequence

from llm_runpod.config import (
    DEFAULT_GPU,
    DEFAULT_IMAGE,
    DEFAULT_MAX_MODEL_LEN,
    DEFAULT_MODEL_ID,
    DEFAULT_PORT,
    DEFAULT_VOLUME_MOUNT,
    DEFAULT_VOLUME_SIZE_GB,
    LaunchConfig,
    default_name,
    env,
)
from llm_runpod.openai_client import chat
from llm_runpod.runpodctl import (
    build_pod_create_command,
    build_volume_create_command,
    extract_first_json_object,
    extract_id,
    redact_command,
    run_command,
    wait_for_openai_ready,
)
from llm_runpod.vscode import VSCodeConnection, render_vscode_connection


def parse_extra_vllm_args(values: list[str] | None) -> tuple[str, ...]:
    if not values:
        return ()
    parsed: list[str] = []
    for value in values:
        parsed.extend(shlex.split(value))
    return tuple(parsed)


def add_launch_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model-id", default=env("LLM_MODEL_ID", DEFAULT_MODEL_ID))
    parser.add_argument("--name", default=None)
    parser.add_argument("--gpu-id", default=env("RUNPOD_GPU_TYPE_ID", DEFAULT_GPU))
    parser.add_argument("--image", default=env("RUNPOD_VLLM_IMAGE", DEFAULT_IMAGE))
    parser.add_argument("--port", type=int, default=int(env("RUNPOD_LLM_PORT", str(DEFAULT_PORT))))
    parser.add_argument("--volume-id", default=env("RUNPOD_NETWORK_VOLUME_ID"))
    parser.add_argument("--volume-name", default=env("RUNPOD_NETWORK_VOLUME_NAME", "llm-model-cache"))
    parser.add_argument("--volume-size-gb", type=int, default=int(env("RUNPOD_NETWORK_VOLUME_SIZE", str(DEFAULT_VOLUME_SIZE_GB))))
    parser.add_argument("--data-center-id", default=env("RUNPOD_DATA_CENTER_ID"))
    parser.add_argument("--volume-mount-path", default=env("RUNPOD_VOLUME_MOUNT_PATH", DEFAULT_VOLUME_MOUNT))
    parser.add_argument("--hf-token", default=env("HF_TOKEN"))
    parser.add_argument("--tensor-parallel-size", type=int, default=int(env("VLLM_TENSOR_PARALLEL_SIZE", "1")))
    parser.add_argument("--max-model-len", type=int, default=int(env("VLLM_MAX_MODEL_LEN", str(DEFAULT_MAX_MODEL_LEN))))
    parser.add_argument("--dtype", default=env("VLLM_DTYPE", "auto"))
    parser.add_argument("--quantization", default=env("VLLM_QUANTIZATION"))
    parser.add_argument("--trust-remote-code", action="store_true", default=env("VLLM_TRUST_REMOTE_CODE") == "1")
    parser.add_argument("--terminate-after", default=env("RUNPOD_TERMINATE_AFTER"))
    parser.add_argument("--extra-vllm-arg", action="append", default=None)


def config_from_args(args: argparse.Namespace) -> LaunchConfig:
    return LaunchConfig(
        model_id=args.model_id,
        name=args.name or default_name(args.model_id),
        gpu_id=args.gpu_id,
        image=args.image,
        port=args.port,
        volume_id=args.volume_id,
        volume_name=args.volume_name,
        volume_size_gb=args.volume_size_gb,
        data_center_id=args.data_center_id,
        volume_mount_path=args.volume_mount_path,
        hf_token=args.hf_token,
        tensor_parallel_size=args.tensor_parallel_size,
        max_model_len=args.max_model_len,
        dtype=args.dtype,
        quantization=args.quantization,
        trust_remote_code=args.trust_remote_code,
        terminate_after=args.terminate_after,
        extra_vllm_args=parse_extra_vllm_args(args.extra_vllm_arg),
    )


def print_plan(config: LaunchConfig, *, include_volume_create: bool) -> None:
    plan: dict[str, object] = {
        "model_id": config.model_id,
        "server": "vLLM OpenAI-compatible API",
        "image": config.image,
        "port": config.port,
        "gpu_id": config.gpu_id,
        "pod_command": redact_command(build_pod_create_command(config, volume_id="<volume-id>" if include_volume_create else None)),
        "openai_base_url": f"https://<pod-id>-{config.port}.proxy.runpod.net/v1",
    }
    if include_volume_create:
        plan["volume_command"] = build_volume_create_command(config)
    print(json.dumps(plan, indent=2))


def launch(args: argparse.Namespace) -> None:
    config = config_from_args(args)
    if args.dry_run:
        print_plan(config, include_volume_create=not bool(config.volume_id))
        return

    volume_id = config.volume_id
    if not volume_id:
        volume_result = run_command(build_volume_create_command(config))
        volume_payload = extract_first_json_object(volume_result.stdout)
        volume_id = extract_id(volume_payload)
        if not volume_id:
            raise SystemExit(f"Could not find volume id in runpodctl output:\n{volume_result.stdout}")

    pod_result = run_command(build_pod_create_command(config, volume_id=volume_id))
    pod_payload = extract_first_json_object(pod_result.stdout)
    pod_id = extract_id(pod_payload)
    if not pod_id:
        raise SystemExit(f"Could not find pod id in runpodctl output:\n{pod_result.stdout}")

    base_url = config.proxy_url_for(pod_id)
    if not args.no_wait:
        wait_for_openai_ready(base_url, timeout_seconds=args.wait_timeout)

    openai_base_url = f"{base_url}/v1"
    print(
        json.dumps(
            {
                "pod_id": pod_id,
                "volume_id": volume_id,
                "base_url": base_url,
                "openai_base_url": openai_base_url,
                "vscode_command": f"llm-runpod vscode --base-url {openai_base_url} --model {config.model_id}",
            },
            indent=2,
        )
    )


def ask(args: argparse.Namespace) -> None:
    answer = chat(args.base_url, args.model, args.prompt, system=args.system, temperature=args.temperature)
    print(answer)


def vscode(args: argparse.Namespace) -> None:
    connection = VSCodeConnection(base_url=args.base_url, model=args.model, api_key=args.api_key)
    print(render_vscode_connection(connection, args.target))


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Launch and talk to arbitrary LLMs on Runpod.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    launch_parser = subparsers.add_parser("launch", help="Create a vLLM pod for a Hugging Face model.")
    add_launch_args(launch_parser)
    launch_parser.add_argument("--dry-run", action="store_true")
    launch_parser.add_argument("--no-wait", action="store_true")
    launch_parser.add_argument("--wait-timeout", type=int, default=1800)
    launch_parser.set_defaults(func=launch)

    plan_parser = subparsers.add_parser("plan", help="Print the Runpod commands without creating anything.")
    add_launch_args(plan_parser)
    plan_parser.set_defaults(dry_run=True, func=lambda args: print_plan(config_from_args(args), include_volume_create=not bool(args.volume_id)))

    ask_parser = subparsers.add_parser("ask", help="Send one prompt to an OpenAI-compatible model endpoint.")
    ask_parser.add_argument("prompt")
    ask_parser.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL"), required=os.getenv("OPENAI_BASE_URL") is None)
    ask_parser.add_argument("--model", default=os.getenv("LLM_MODEL_ID", DEFAULT_MODEL_ID))
    ask_parser.add_argument("--system", default="You are a precise, practical coding agent.")
    ask_parser.add_argument("--temperature", type=float, default=0.2)
    ask_parser.set_defaults(func=ask)

    vscode_parser = subparsers.add_parser("vscode", help="Print VS Code agent extension settings for this endpoint.")
    vscode_parser.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL"), required=os.getenv("OPENAI_BASE_URL") is None)
    vscode_parser.add_argument("--model", default=os.getenv("LLM_MODEL_ID", DEFAULT_MODEL_ID))
    vscode_parser.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY", "unused"))
    vscode_parser.add_argument("--target", choices=["all", "env", "continue", "cline", "roo"], default="all")
    vscode_parser.set_defaults(func=vscode)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
