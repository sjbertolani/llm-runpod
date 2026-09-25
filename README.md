# llm-runpod

Launch an arbitrary Hugging Face LLM on a Runpod GPU pod and expose it as an
OpenAI-compatible API you can point coding-agent tooling at.

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

## Ask The Model

Once the endpoint is ready:

```bash
llm-runpod ask \
  --base-url https://<pod-id>-8000.proxy.runpod.net/v1 \
  --model medismera/Qwen3.8-27B-OBLITERATED-Mythos-Class-Agentic \
  "Write a Python function that topologically sorts a graph."
```

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

Runpod proxy URLs are public. Treat the endpoint as exposed while the pod is
running, and terminate the pod when you are done.

## Cleanup

Terminate the pod when you are done:

```bash
runpodctl pod remove <pod-id>
```

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
