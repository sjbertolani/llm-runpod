from __future__ import annotations

import json
import subprocess

from llm_runpod.cli import main
from llm_runpod.config import LaunchConfig
from llm_runpod.openai_client import openai_base_url
from llm_runpod.runpodctl import build_pod_create_command, build_vllm_args, redact_command
from llm_runpod.skills import (
    discover_skills,
    extract_skill_handles,
    render_selected_skill_context,
    render_skill_catalog,
    slug_for_repo,
)
from llm_runpod.state import LastLaunch, load_last_launch, save_last_launch


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


def test_vscode_roo_config_includes_practical_settings(capsys):
    main(
        [
            "vscode",
            "--target",
            "roo",
            "--base-url",
            "https://pod-8000.proxy.runpod.net/v1",
            "--model",
            "org/model",
        ]
    )

    data = json.loads(capsys.readouterr().out)

    assert data["fields"]["API Provider"] == "OpenAI Compatible"
    assert data["fields"]["Context Window"].startswith("Match vLLM")
    assert data["fields"]["Max Output"] == "1024"
    assert data["custom_instructions_command"] == "llm-runpod roo-instructions"


def test_openai_base_url_accepts_root_or_v1_url():
    assert openai_base_url("https://pod-8000.proxy.runpod.net") == "https://pod-8000.proxy.runpod.net/v1"
    assert openai_base_url("https://pod-8000.proxy.runpod.net/v1") == "https://pod-8000.proxy.runpod.net/v1"


def test_slug_for_repo_handles_github_url():
    assert slug_for_repo("https://github.com/RelationalAI/rai-agent-skills") == "RelationalAI-rai-agent-skills"


def test_discover_skills_reads_skill_metadata(tmp_path):
    repo = tmp_path / "repo"
    skill = repo / "plugins" / "rai" / "skills" / "rai-setup"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        """---
name: rai-setup
description: First-time RelationalAI setup.
---

# RAI Setup
""",
        encoding="utf-8",
    )

    skills = discover_skills(repo, repo="https://example.com/repo.git", commit="abc123")

    assert len(skills) == 1
    assert skills[0].name == "rai-setup"
    assert skills[0].description == "First-time RelationalAI setup."
    assert skills[0].path == "plugins/rai/skills/rai-setup/SKILL.md"
    assert skills[0].commit == "abc123"


def test_discover_skills_handles_multiline_description(tmp_path):
    repo = tmp_path / "repo"
    skill = repo / "skills" / "dev-release"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        """---
name: dev-release
description: Bumps the plugin version across manifest files, commits, and
  creates a local git tag for rai-agent-skills.
---

# Release
""",
        encoding="utf-8",
    )

    skills = discover_skills(repo, repo="https://example.com/repo.git")

    assert skills[0].description == (
        "Bumps the plugin version across manifest files, commits, and "
        "creates a local git tag for rai-agent-skills."
    )


def test_skills_install_clones_local_repo_and_lists_registry(tmp_path, monkeypatch, capsys):
    source = tmp_path / "source-skills"
    skill = source / "plugins" / "rai" / "skills" / "rai-pyrel"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        """---
name: rai-pyrel
description: Generate and execute PyRel.
---

# RAI PyRel
""",
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=source, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=source, check=True)
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "commit", "-m", "Add test skill"], cwd=source, check=True, capture_output=True)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)

    main(["skills", "install", str(source)])
    install_output = json.loads(capsys.readouterr().out)

    assert install_output["repo"] == str(source)
    assert install_output["skills"] == ["rai-pyrel"]

    main(["skills", "list"])
    list_output = json.loads(capsys.readouterr().out)

    assert list_output["skills"][0]["name"] == "rai-pyrel"
    assert list_output["skills"][0]["repo"] == str(source)

    main(["skills", "list", "--handles"])
    handles_output = capsys.readouterr().out

    assert "@rai-pyrel: Generate and execute PyRel." in handles_output

    main(["skills", "show", "@rai-pyrel"])
    show_output = capsys.readouterr().out

    assert "# RAI PyRel" in show_output

    main(["skills", "export", "--target", "goose"])
    export_output = json.loads(capsys.readouterr().out)

    assert export_output["target"] == "goose"
    assert export_output["exported"][0]["name"] == "rai-pyrel"
    assert (workspace / ".agents" / "skills" / "rai-pyrel" / "SKILL.md").exists()


def test_extract_skill_handles_ignores_catalog_handle():
    assert extract_skill_handles("Use @skills then @rai-pyrel and @rai-pyrel") == ["rai-pyrel"]


def test_render_skill_catalog_and_selected_context(tmp_path):
    source = tmp_path / "source-skills"
    skill = source / "plugins" / "rai" / "skills" / "rai-setup"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        """---
name: rai-setup
description: Configure RelationalAI.
---

# RAI Setup

Install and configure RAI.
""",
        encoding="utf-8",
    )
    registry_home = tmp_path / "skills"
    repo = discover_skills(source, repo="https://example.com/skills.git", commit="abc123")
    from llm_runpod.skills import SkillRepo, write_registry

    write_registry(
        SkillRepo(
            url="https://example.com/skills.git",
            slug="skills",
            path=str(source),
            commit="abc123",
            skills=tuple(repo),
        ),
        skills_home=registry_home,
    )

    catalog = render_skill_catalog(skills_home=registry_home)
    context = render_selected_skill_context(["rai-setup"], skills_home=registry_home)

    assert "@rai-setup: Configure RelationalAI." in catalog
    assert "## @rai-setup" in context
    assert "# RAI Setup" in context


def test_ask_at_skills_lists_catalog_without_endpoint(tmp_path, monkeypatch, capsys):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)

    main(["ask", "@skills", "--base-url", "https://example.invalid/v1", "--model", "org/model"])

    assert "No skills installed." in capsys.readouterr().out


def test_state_round_trip(tmp_path):
    path = tmp_path / "state.json"
    state = LastLaunch(
        pod_id="pod123",
        model="org/model",
        base_url="https://pod-8000.proxy.runpod.net",
        openai_base_url="https://pod-8000.proxy.runpod.net/v1",
        gpu_id="NVIDIA A100",
        cost_per_hour=1.59,
        volume_id="vol123",
    )

    save_last_launch(state, path=path)

    assert load_last_launch(path=path) == state


def test_roo_instructions_prints_agent_guidance(capsys):
    main(["roo-instructions"])

    output = capsys.readouterr().out

    assert "Use available tools directly" in output
    assert "OpenAI Compatible" in output


def test_goose_setup_uses_state_and_prints_acp_guidance(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    save_last_launch(
        LastLaunch(
            pod_id="pod123",
            model="org/model",
            base_url="https://pod-8000.proxy.runpod.net",
            openai_base_url="https://pod-8000.proxy.runpod.net/v1",
            gpu_id="NVIDIA A100",
        )
    )

    main(["goose"])

    data = json.loads(capsys.readouterr().out)

    assert data["provider"]["provider_type"] == "OpenAI Compatible"
    assert data["provider"]["api_url"] == "https://pod-8000.proxy.runpod.net/v1"
    assert data["provider"]["available_models"] == ["org/model"]
    assert data["vscode"]["stdio_command"] == "goose acp"
    assert data["skills"]["export_command"] == "llm-runpod skills export --target goose"


def test_cleanup_uses_last_state_and_runpodctl(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    save_last_launch(
        LastLaunch(
            pod_id="pod123",
            model="org/model",
            base_url="https://pod-8000.proxy.runpod.net",
            openai_base_url="https://pod-8000.proxy.runpod.net/v1",
            gpu_id="NVIDIA A100",
            cost_per_hour=1.59,
        )
    )
    calls = []

    def fake_run_command(command):
        calls.append(command)

        class Result:
            stdout = "stopped"

        return Result()

    monkeypatch.setattr("llm_runpod.cli.run_command", fake_run_command)

    main(["stop"])

    assert calls == [["runpodctl", "pod", "stop", "pod123"]]
    assert json.loads(capsys.readouterr().out)["cost_per_hour"] == 1.59


def test_status_smoke_uses_models_chat_and_optional_tools(monkeypatch, capsys):
    monkeypatch.setattr(
        "llm_runpod.cli.list_models",
        lambda base_url: {"data": [{"id": "org/model"}]},
    )
    completions = []

    def fake_chat_completion(base_url, model, messages, **kwargs):
        completions.append(kwargs)
        if kwargs.get("tools"):
            return {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {"name": "report_result", "arguments": '{"result":"ready"}'},
                                }
                            ]
                        }
                    }
                ]
            }
        return {"choices": [{"message": {"content": "ready"}}]}

    monkeypatch.setattr("llm_runpod.cli.chat_completion", fake_chat_completion)

    main(["status", "--base-url", "https://pod-8000.proxy.runpod.net/v1", "--model", "org/model", "--tools"])

    report = json.loads(capsys.readouterr().out)

    assert report["models_ok"] is True
    assert report["chat_ok"] is True
    assert report["tools_ok"] is True
    assert len(completions) == 2
