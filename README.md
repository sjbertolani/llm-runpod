# llm-runpod

Launch an arbitrary Hugging Face LLM on a Runpod GPU pod and expose it as an
OpenAI-compatible API you can point coding-agent tooling at.

Background: [Own your LLM workflow](https://medium.com/@steve.bertolani/own-your-llm-workflow-6d0088ee7a76)

The default model is:

```text
medismera/Qwen3.8-27B-OBLITERATED-Mythos-Class-Agentic
```

Under the hood this starts a `vllm/vllm-openai` server on port `8000`, stores
model downloads on a Runpod network volume, and returns a base URL shaped like:

```text
https://<pod-id>-8000.proxy.runpod.net/v1
```

## Setup

Install this project locally:

```bash
python -m pip install -e ".[dev]"
```

Install and authenticate `runpodctl`:

```bash
curl -sSL https://cli.runpod.net | bash
runpodctl doctor
```

For non-interactive runs, set:

```bash
export RUNPOD_API_KEY=...
export HF_TOKEN=...   # optional, required for private or gated HF models
```

## Plan A Launch

Use `plan` first. It prints the Runpod commands without creating billable
resources.

```bash
llm-runpod plan \
  --model-id medismera/Qwen3.8-27B-OBLITERATED-Mythos-Class-Agentic \
  --gpu-id "NVIDIA RTX 6000 Ada" \
  --volume-id <existing-network-volume-id> \
  --max-model-len 8192 \
  --trust-remote-code
```

If you do not pass `--volume-id`, the launch flow creates a network volume first.
When using a network volume, keep the pod and volume in the same data center:

```bash
llm-runpod plan \
  --data-center-id US-MO-2 \
  --gpu-id "NVIDIA RTX 6000 Ada"
```

## Launch

Use `--terminate-after` as a cost guard. It should be an ISO timestamp accepted
by Runpod.

```bash
llm-runpod launch \
  --model-id medismera/Qwen3.8-27B-OBLITERATED-Mythos-Class-Agentic \
  --gpu-id "NVIDIA RTX 6000 Ada" \
  --volume-id <existing-network-volume-id> \
  --max-model-len 8192 \
  --trust-remote-code \
  --terminate-after 2026-09-25T23:59:00Z
```

The command waits for `GET /v1/models` to succeed, then prints:

```json
{
  "pod_id": "...",
  "volume_id": "...",
  "base_url": "https://<pod-id>-8000.proxy.runpod.net",
  "openai_base_url": "https://<pod-id>-8000.proxy.runpod.net/v1"
}
```

For a 27B model, start with a 48GB+ GPU such as RTX 6000 Ada, A40, A100, or H100.
If vLLM reports memory pressure, lower `--max-model-len`, use an appropriate
`--quantization`, or set `--tensor-parallel-size 2` with a multi-GPU pod.

Launch also saves the most recent pod connection details to
`.llm-runpod/state.json` so follow-up commands can use the last endpoint.

## Ask The Model

Once the endpoint is ready:

```bash
llm-runpod ask \
  --base-url https://<pod-id>-8000.proxy.runpod.net/v1 \
  --model medismera/Qwen3.8-27B-OBLITERATED-Mythos-Class-Agentic \
  "Write a Python function that topologically sorts a graph."
```

## Check Status

When Roo appears to hang, first verify the endpoint directly:

```bash
llm-runpod status
llm-runpod status --tools
```

`status` uses `.llm-runpod/state.json` when available. It checks `/v1/models`,
runs a tiny chat completion, and with `--tools` verifies native OpenAI
`tool_calls`.

Many coding-agent tools can use the same endpoint by setting:

```bash
export OPENAI_BASE_URL=https://<pod-id>-8000.proxy.runpod.net/v1
export OPENAI_API_KEY=unused
export LLM_MODEL_ID=medismera/Qwen3.8-27B-OBLITERATED-Mythos-Class-Agentic
```

## Connect VS Code

After launch, print ready-to-use VS Code agent settings:

```bash
llm-runpod vscode \
  --base-url https://<pod-id>-8000.proxy.runpod.net/v1 \
  --model medismera/Qwen3.8-27B-OBLITERATED-Mythos-Class-Agentic
```

For Continue, print only the `config.yaml` snippet:

```bash
llm-runpod vscode \
  --target continue \
  --base-url https://<pod-id>-8000.proxy.runpod.net/v1 \
  --model medismera/Qwen3.8-27B-OBLITERATED-Mythos-Class-Agentic
```

Continue uses an OpenAI-compatible provider config like:

```yaml
models:
  - name: Runpod vLLM
    provider: openai
    model: medismera/Qwen3.8-27B-OBLITERATED-Mythos-Class-Agentic
    apiBase: https://<pod-id>-8000.proxy.runpod.net/v1
    apiKey: unused
    useResponsesApi: false
```

For Cline or Roo Code, use the extension settings UI:

```text
API Provider: OpenAI Compatible
Base URL: https://<pod-id>-8000.proxy.runpod.net/v1
API Key: unused
Model ID: medismera/Qwen3.8-27B-OBLITERATED-Mythos-Class-Agentic
```

For Roo custom instructions tuned for self-hosted models:

```bash
llm-runpod roo-instructions
```

## Try Goose

Goose can use the same Runpod vLLM endpoint as a custom OpenAI-compatible
provider:

```bash
llm-runpod goose \
  --base-url https://<pod-id>-8000.proxy.runpod.net/v1 \
  --model medismera/Qwen3.8-27B-OBLITERATED-Mythos-Class-Agentic
```

The command prints Goose Desktop/CLI setup values, plus the ACP commands to try
for editor integration:

```bash
goose acp
GOOSE_SERVER__SECRET_KEY='change-me' goose serve
```

For VS Code, prefer an ACP client that can launch `goose acp`. If that is not
usable, the next path is a small VS Code extension that speaks Goose ACP over
stdio, HTTP, or WebSocket. As a fallback, Roo could be adapted to use Goose as
the underlying agent backend.

Runpod proxy URLs are public. Treat the endpoint as exposed while the pod is
running, and terminate the pod when you are done.

## Install Skill Repos

This project can track agent skills from GitHub repos. The first target is the
RelationalAI skill pack:

```bash
llm-runpod skills install https://github.com/RelationalAI/rai-agent-skills
llm-runpod skills list
llm-runpod skills list --handles
llm-runpod skills export --target goose
```

The installer clones or updates the repo under `.llm-runpod/skills/repos/`,
discovers every `SKILL.md`, and writes `.llm-runpod/skills/registry.json` with
the skill names, descriptions, source paths, repo URL, and commit hash.

The Goose export copies installed skills into `.agents/skills/`, which Goose
uses as its project-level skill directory.

This is the registry layer, not the full tool bridge yet. Markdown skills can
teach the agent what to do, but executable actions still need tools exposed by
Roo, MCP servers, local CLIs, or a future gateway. For the RelationalAI skills,
that means the environment still needs the `relationalai` Python package plus
the required Snowflake/RAI configuration and credentials before those workflows
can actually run.

For now, skills can be selected explicitly with `@` handles:

```bash
llm-runpod ask @skills
llm-runpod skills show @rai-pyrel
llm-runpod ask --base-url https://<pod-id>-8000.proxy.runpod.net/v1 \
  --model medismera/Qwen3.8-27B-OBLITERATED-Mythos-Class-Agentic \
  "@rai-pyrel help me write a PyRel model for customers and orders"
```

`@skills` prints a copyable catalog of installed handles. Any other `@skill`
handle in an `ask` prompt loads that skill's `SKILL.md` into the system prompt
for that request. Automatic skill selection is a later gateway feature.

## Cleanup

Terminate the pod when you are done:

```bash
llm-runpod stop
llm-runpod terminate
runpodctl pod remove <pod-id>
```

`stop` releases GPU billing while keeping the pod disk. `terminate` deletes the
last launched pod recorded in `.llm-runpod/state.json`.

Delete the network volume only if you do not want to keep the downloaded model
cache:

```bash
runpodctl network-volume delete <volume-id>
```

## Development

```bash
python -m pytest -q
PYTHONPATH=src python -m llm_runpod.cli plan --model-id Qwen/Qwen2.5-Coder-7B-Instruct
```
