from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class VSCodeConnection:
    base_url: str
    model: str
    api_key: str = "unused"


def env_exports(connection: VSCodeConnection) -> str:
    return "\n".join(
        [
            f"export OPENAI_BASE_URL={connection.base_url}",
            f"export OPENAI_API_KEY={connection.api_key}",
            f"export LLM_MODEL_ID={connection.model}",
        ]
    )


def continue_yaml(connection: VSCodeConnection) -> str:
    return "\n".join(
        [
            "name: Runpod LLM",
            "version: 0.0.1",
            "schema: v1",
            "",
            "models:",
            "  - name: Runpod vLLM",
            "    provider: openai",
            f"    model: {connection.model}",
            f"    apiBase: {connection.base_url}",
            f"    apiKey: {connection.api_key}",
            "    useResponsesApi: false",
            "",
            "tabAutocompleteModel:",
            "  name: Runpod vLLM",
            "  provider: openai",
            f"  model: {connection.model}",
            f"  apiBase: {connection.base_url}",
            f"  apiKey: {connection.api_key}",
        ]
    )


def cline_json(connection: VSCodeConnection) -> str:
    return json.dumps(
        {
            "extension": "Cline",
            "ui": "Cline sidebar -> Settings -> API Configuration",
            "fields": {
                "API Provider": "OpenAI Compatible",
                "Base URL": connection.base_url,
                "API Key": connection.api_key,
                "Model ID": connection.model,
            },
        },
        indent=2,
    )


def roo_json(connection: VSCodeConnection) -> str:
    return json.dumps(
        {
            "extension": "Roo Code",
            "ui": "Roo Code sidebar -> Settings -> API Provider/Profile",
            "fields": {
                "API Provider": "OpenAI Compatible",
                "Base URL": connection.base_url,
                "API Key": connection.api_key,
                "Model ID": connection.model,
                "Context Window": "Match vLLM --max-model-len, e.g. 16384 or 32768",
                "Max Output": "1024",
                "Supports Images": "false unless the served model is multimodal",
                "Prompt Caching": "false unless the endpoint explicitly supports it",
            },
            "custom_instructions_command": "llm-runpod roo-instructions",
        },
        indent=2,
    )


def render_vscode_connection(connection: VSCodeConnection, target: str) -> str:
    if target == "env":
        return env_exports(connection)
    if target == "continue":
        return continue_yaml(connection)
    if target == "cline":
        return cline_json(connection)
    if target == "roo":
        return roo_json(connection)
    if target == "all":
        return "\n\n".join(
            [
                "# Shell environment",
                env_exports(connection),
                "# Continue config.yaml",
                continue_yaml(connection),
                "# Cline",
                cline_json(connection),
                "# Roo Code",
                roo_json(connection),
            ]
        )
    raise ValueError(f"Unknown VS Code target: {target}")
