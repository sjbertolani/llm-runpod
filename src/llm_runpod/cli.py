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
from llm_runpod.openai_client import chat, chat_completion, list_models
from llm_runpod.runpodctl import (
    build_pod_create_command,
    build_volume_create_command,
    extract_first_json_object,
    extract_id,
    redact_command,
    run_command,
    wait_for_openai_ready,
)
from llm_runpod.skills import (
    all_skills,
    extract_skill_handles,
    export_skills_for_goose,
    install_skill_repo,
    read_skill_markdown,
    render_selected_skill_context,
    render_skill_catalog,
)
from llm_runpod.state import LastLaunch, load_last_launch, save_last_launch
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
    state = LastLaunch(
        pod_id=pod_id,
        model=config.model_id,
        base_url=base_url,
        openai_base_url=openai_base_url,
        gpu_id=config.gpu_id,
        volume_id=volume_id,
    )
    save_last_launch(state)
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
    if args.prompt.strip() == "@skills":
        print(render_skill_catalog())
        return

    selected_skills = render_selected_skill_context(extract_skill_handles(args.prompt))
    system = args.system
    if selected_skills:
        system = f"{system}\n\n{selected_skills}"

    answer = chat(args.base_url, args.model, args.prompt, system=system, temperature=args.temperature)
    print(answer)


def vscode(args: argparse.Namespace) -> None:
    connection = VSCodeConnection(base_url=args.base_url, model=args.model, api_key=args.api_key)
    print(render_vscode_connection(connection, args.target))


def status(args: argparse.Namespace) -> None:
    state = load_last_launch()
    base_url = args.base_url or (state.openai_base_url if state else None)
    model = args.model or (state.model if state else DEFAULT_MODEL_ID)
    if not base_url:
        raise SystemExit("No base URL provided and no .llm-runpod/state.json found.")

    report: dict[str, object] = {
        "base_url": base_url,
        "model": model,
        "models_ok": False,
        "chat_ok": False,
    }
    if state:
        report["pod_id"] = state.pod_id
        report["gpu_id"] = state.gpu_id
        report["cost_per_hour"] = state.cost_per_hour

    models_payload = list_models(base_url)
    models = [item.get("id") for item in models_payload.get("data", []) if isinstance(item, dict)]
    report["models_ok"] = True
    report["served_models"] = models
    report["model_found"] = model in models

    chat_payload = chat_completion(
        base_url,
        model,
        [{"role": "user", "content": "Reply with exactly: ready"}],
        max_tokens=32,
        timeout=args.timeout,
    )
    message = chat_payload["choices"][0]["message"]
    report["chat_ok"] = "ready" in str(message.get("content", "")).lower()
    report["chat_content"] = message.get("content")

    if args.tools:
        tool_payload = chat_completion(
            base_url,
            model,
            [{"role": "user", "content": "Use the provided tool to report the word ready."}],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "report_result",
                        "description": "Report a short result string",
                        "parameters": {
                            "type": "object",
                            "properties": {"result": {"type": "string"}},
                            "required": ["result"],
                        },
                    },
                }
            ],
            tool_choice="auto",
            max_tokens=128,
            timeout=args.timeout,
        )
        tool_message = tool_payload["choices"][0]["message"]
        report["tools_ok"] = bool(tool_message.get("tool_calls"))
        report["tool_calls"] = tool_message.get("tool_calls")

    print(json.dumps(report, indent=2))


def cleanup_pod(args: argparse.Namespace) -> None:
    state = load_last_launch()
    pod_id = args.pod_id or (state.pod_id if state else None)
    if not pod_id:
        raise SystemExit("No pod id provided and no .llm-runpod/state.json found.")
    action = "stop" if args.command == "stop" else "remove"
    result = run_command(["runpodctl", "pod", action, pod_id])
    print(
        json.dumps(
            {
                "pod_id": pod_id,
                "action": args.command,
                "model": state.model if state else None,
                "cost_per_hour": state.cost_per_hour if state else None,
                "stdout": result.stdout.strip(),
            },
            indent=2,
        )
    )


def roo_instructions(args: argparse.Namespace) -> None:
    print(
        "\n".join(
            [
                "Use this project as a self-hosted OpenAI-compatible coding-agent backend.",
                "",
                "Behavior:",
                "- Be concise and action-oriented.",
                "- Use available tools directly instead of narrating long plans.",
                "- Read small, relevant file sets before broad repo scans.",
                "- Prefer concrete edits and verification over extended brainstorming.",
                "- Emit valid tool calls when tools are available; do not print fake tool JSON.",
                "- If a request includes `@skills`, list installed skill handles.",
                "- If a request includes `@skill-name`, treat that as a request to load and follow that skill's instructions.",
                "",
                "Recommended Roo settings:",
                "- API Provider: OpenAI Compatible",
                "- API Key: unused",
                "- Context window: match the vLLM `max_model_len` value",
                "- Max output: 1024 to start",
                "- Supports images: false unless the served model is actually multimodal",
                "- Prompt caching: false unless the endpoint explicitly supports it",
            ]
        )
    )


def goose(args: argparse.Namespace) -> None:
    state = load_last_launch()
    base_url = args.base_url or (state.openai_base_url if state else None)
    model = args.model or (state.model if state else DEFAULT_MODEL_ID)
    if not base_url:
        raise SystemExit("No base URL provided and no .llm-runpod/state.json found.")

    payload = {
        "purpose": "Configure Goose to use this Runpod vLLM endpoint as an OpenAI-compatible provider.",
        "provider": {
            "provider_type": "OpenAI Compatible",
            "display_name": args.display_name,
            "api_url": base_url,
            "api_key": args.api_key,
            "available_models": [model],
            "streaming_support": True,
        },
        "desktop_steps": [
            "Open Goose Desktop settings.",
            "Go to Models / Configure Providers.",
            "Add a custom provider.",
            "Choose OpenAI Compatible.",
            "Use the API URL, API key, and model id from this output.",
            "If Goose offers an API-key-required toggle, leave it enabled with the dummy key unless your endpoint rejects auth headers.",
        ],
        "cli_steps": [
            "Run `goose configure`.",
            "Choose Configure Providers.",
            "Choose a custom/OpenAI-compatible provider if available.",
            "Use the API URL, API key, and model id from this output.",
        ],
        "skills": {
            "goose_project_skill_dir": ".agents/skills/",
            "export_command": "llm-runpod skills export --target goose",
            "list_in_goose": "goose skills list",
        },
        "vscode": {
            "preferred_path": "Use a VS Code ACP client that can launch `goose acp`.",
            "stdio_command": "goose acp",
            "server_command": "GOOSE_SERVER__SECRET_KEY='change-me' goose serve",
            "server_url": "http://127.0.0.1:3284/acp",
            "fallback": "If no suitable ACP client works, build a small VS Code extension that talks to Goose ACP, or adapt Roo to launch/use Goose as its agent backend.",
        },
        "notes": [
            "Goose is the agent harness; Runpod/vLLM remains the model-serving layer.",
            "The served model must support tool calls well for Goose to behave like a coding agent.",
            "For the current Qwen3.8 27B model, keep the vLLM qwen3_coder tool parser and qwen3 reasoning parser.",
        ],
    }
    print(json.dumps(payload, indent=2))


def skills_install(args: argparse.Namespace) -> None:
    skill_repo = install_skill_repo(args.repo_url)
    print(
        json.dumps(
            {
                "repo": skill_repo.url,
                "path": skill_repo.path,
                "commit": skill_repo.commit,
                "skills": [skill.name for skill in skill_repo.skills],
            },
            indent=2,
        )
    )


def skills_list(args: argparse.Namespace) -> None:
    if args.handles:
        print(render_skill_catalog())
    else:
        print(json.dumps({"skills": all_skills()}, indent=2))


def skills_show(args: argparse.Namespace) -> None:
    if args.skill == "@skills":
        print(render_skill_catalog())
        return
    print(read_skill_markdown(args.skill))


def skills_export(args: argparse.Namespace) -> None:
    if args.target != "goose":
        raise SystemExit(f"Unsupported skill export target: {args.target}")
    exported = export_skills_for_goose()
    print(json.dumps({"target": "goose", "exported": exported}, indent=2))


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

    status_parser = subparsers.add_parser("status", help="Smoke-test an OpenAI-compatible endpoint.")
    status_parser.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL"))
    status_parser.add_argument("--model", default=os.getenv("LLM_MODEL_ID"))
    status_parser.add_argument("--timeout", type=int, default=90)
    status_parser.add_argument("--tools", action="store_true", help="Also test native OpenAI tool calls.")
    status_parser.set_defaults(func=status)

    stop_parser = subparsers.add_parser("stop", help="Stop the last launched Runpod pod, releasing GPU billing.")
    stop_parser.add_argument("--pod-id")
    stop_parser.set_defaults(func=cleanup_pod)

    terminate_parser = subparsers.add_parser("terminate", help="Delete the last launched Runpod pod.")
    terminate_parser.add_argument("--pod-id")
    terminate_parser.set_defaults(func=cleanup_pod)

    roo_instructions_parser = subparsers.add_parser("roo-instructions", help="Print recommended Roo custom instructions.")
    roo_instructions_parser.set_defaults(func=roo_instructions)

    goose_parser = subparsers.add_parser("goose", help="Print Goose setup for this Runpod vLLM endpoint.")
    goose_parser.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL"))
    goose_parser.add_argument("--model", default=os.getenv("LLM_MODEL_ID"))
    goose_parser.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY", "unused"))
    goose_parser.add_argument("--display-name", default="Runpod vLLM")
    goose_parser.set_defaults(func=goose)

    skills_parser = subparsers.add_parser("skills", help="Install and inspect local agent skill repos.")
    skills_subparsers = skills_parser.add_subparsers(dest="skills_command", required=True)

    skills_install_parser = skills_subparsers.add_parser("install", help="Clone or update a GitHub skill repo.")
    skills_install_parser.add_argument("repo_url")
    skills_install_parser.set_defaults(func=skills_install)

    skills_list_parser = skills_subparsers.add_parser("list", help="List skills installed into this repo.")
    skills_list_parser.add_argument("--handles", action="store_true", help="Print copyable @skill handles for prompting.")
    skills_list_parser.set_defaults(func=skills_list)

    skills_show_parser = skills_subparsers.add_parser("show", help="Print one selected skill's SKILL.md instructions.")
    skills_show_parser.add_argument("skill", help="Skill name or @skill handle. Use @skills for the handle catalog.")
    skills_show_parser.set_defaults(func=skills_show)

    skills_export_parser = skills_subparsers.add_parser("export", help="Export installed skills into another agent's skill layout.")
    skills_export_parser.add_argument("--target", choices=["goose"], required=True)
    skills_export_parser.set_defaults(func=skills_export)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
