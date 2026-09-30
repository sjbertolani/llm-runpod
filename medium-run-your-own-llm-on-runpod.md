# Run Whatever Open Source LLM You Want, Then Point VS Code At It

I wanted a small, boring repo that does one thing:

```text
Hugging Face model in
Runpod GPU starts
vLLM serves an OpenAI-compatible API
VS Code points at it
GPU stops when I am done
```

That is it.

No mini data center. No big inference platform. No permanent monthly commitment.
Just a way to try open models as personal coding agents and keep control over
the workflow.

The core stack is:

```text
VS Code / Roo / Continue / Goose
          |
          v
https://<pod-id>-8000.proxy.runpod.net/v1
          |
          v
Runpod GPU pod running vllm/vllm-openai
          |
          v
Any compatible Hugging Face model
```

Because vLLM exposes an OpenAI-compatible API, most coding-agent tools do not
need to know anything special about the model. They just need:

```text
Base URL
API key
Model id
```

For this project, the API key can be a dummy value such as `unused` or
`sk-local`, unless you put your own auth layer in front of the endpoint.

## The Repo Shape

The repo provides a small CLI:

```bash
llm-runpod plan
llm-runpod launch
llm-runpod status
llm-runpod vscode
llm-runpod stop
llm-runpod terminate
```

The intended loop is:

1. Pick a model.
2. Plan the Runpod launch without spending money.
3. Launch the pod.
4. Wait for `/v1/models`.
5. Smoke-test `/v1/chat/completions`.
6. Point VS Code at the endpoint.
7. Stop or terminate the pod when done.

That gives you a repeatable way to try models as they improve.

When a new model looks interesting, run it. If it is bad, stop it. If it is
great, keep the settings in your notes and come back to it later.

## Start Small

Do not start with a 30B or 70B model.

Start with something tiny, just to prove the path:

```text
HuggingFaceTB/SmolLM2-135M-Instruct
```

That model is not the point. It is small, public, fast to download, and good
enough to confirm that Runpod, vLLM, the proxy URL, and your client are all
working.

Once the plumbing is boring, try a coding model:

```text
Qwen/Qwen2.5-Coder-1.5B-Instruct
```

Then move up to larger models.

## The Model That Worked Best So Far

The best experience I have had so far was with:

```text
medismera/Qwen3.8-27B-OBLITERATED-Mythos-Class-Agentic
```

That is not a benchmark claim. It is just the practical result from using it as
a coding-agent backend in VS Code. Compared with Codex and the other open
models/configurations I tried, this one felt the most useful in the actual
workflow.

The working setup was:

```text
Image: vllm/vllm-openai:latest
GPU: NVIDIA A100-SXM4-80GB
Price: $1.59/hr at the time of testing
Model: medismera/Qwen3.8-27B-OBLITERATED-Mythos-Class-Agentic
Max context: 16384
```

For that Qwen model, these vLLM flags mattered:

```bash
--enforce-eager \
--enable-auto-tool-choice \
--tool-call-parser qwen3_coder \
--reasoning-parser qwen3
```

The tool parser made the model return real OpenAI-style `tool_calls`. The
reasoning parser kept the model's internal reasoning out of the visible chat
content.

Those details will vary by model. That is one reason having your own repo is
useful: when a model needs special flags, you can add them, test them, and keep
moving.

## What It Costs

These prices came from the Runpod pod GPU catalog during testing. They change,
so treat this as a rough snapshot.

| Use case | Example GPU | VRAM | Price/hr | 2 hr test | 8 hr/day for 30 days | 24/7 for 30 days |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Tiny smoke test | NVIDIA L4, secure | 24 GB | $0.49 | $0.98 | $117.60 | $357.70 |
| Cheap 7B-ish dev | RTX 3090, community | 24 GB | $0.22 | $0.44 | $52.80 | $160.60 |
| Faster 7B-ish dev | RTX 4090, community | 24 GB | $0.34 | $0.68 | $81.60 | $248.20 |
| 30B-class, quantized | A40, secure | 48 GB | $0.49 | $0.98 | $117.60 | $357.70 |
| 30B-class, roomy | A100 80GB, secure | 80 GB | $1.59 | $3.18 | $381.60 | $1,160.70 |
| Larger models | H100 PCIe, secure | 80 GB | $2.89 | $5.78 | $693.60 | $2,109.70 |

The useful number is the two-hour test cost.

A $1.59/hr GPU is expensive if you forget it for a month. It is very reasonable
if you use it for an evening to find out whether a model is worth your time.

## GPU Sizing

Very rough rule:

```text
fp16/bf16 weights need about 2 GB of VRAM per billion parameters
```

Then add room for context, KV cache, framework overhead, and batching.

| Model size | Comfortable starting point |
| --- | --- |
| 135M to 1.5B | Any small CUDA GPU; L4 is plenty |
| 7B | 16-24 GB VRAM |
| 13B | 24-48 GB VRAM |
| 27B-34B | 48-80 GB VRAM, or quantization |
| 70B | 80 GB+ quantized, or multiple GPUs |

The repo does not solve model fit for you. It gives you a repeatable launch and
test loop so you can find the right model/GPU combination empirically.

## Launch Shape

Under the hood, the important pieces are simple:

```bash
runpodctl pod create \
  --image-name vllm/vllm-openai:latest \
  --gpu-id "NVIDIA L4" \
  --ports "8000/http" \
  --env '{"HF_HOME":"/workspace/huggingface","VLLM_CACHE_ROOT":"/workspace/vllm"}' \
  --docker-args "--model HuggingFaceTB/SmolLM2-135M-Instruct --served-model-name HuggingFaceTB/SmolLM2-135M-Instruct --host 0.0.0.0 --port 8000 --download-dir /workspace/models --max-model-len 4096 --dtype auto"
```

The details that matter:

- expose port `8000/http`
- bind vLLM to `0.0.0.0`
- wait for `/v1/models`
- test `/v1/chat/completions`
- stop or terminate the pod when finished

## Connect VS Code

Most tools use the same values:

```bash
export OPENAI_BASE_URL=https://<pod-id>-8000.proxy.runpod.net/v1
export OPENAI_API_KEY=unused
export LLM_MODEL_ID=HuggingFaceTB/SmolLM2-135M-Instruct
```

For Roo Code or Cline:

```text
API Provider: OpenAI Compatible
Base URL: https://<pod-id>-8000.proxy.runpod.net/v1
API Key: unused
Model ID: <your-model-id>
```

For the Qwen 27B model, my Roo settings were:

```text
Model ID: medismera/Qwen3.8-27B-OBLITERATED-Mythos-Class-Agentic
Context window: 16384
Max output: 1024
Supports images: false
Prompt caching: false
```

The same endpoint can also be tried with Continue, Goose, Open WebUI, or any
other client that understands an OpenAI-compatible API.

## Why Bother?

The benefit is not that this is easier than using a hosted coding agent.

The benefit is control.

You control:

- which model runs
- which GPU runs it
- when the GPU is on
- what endpoint VS Code talks to
- what data leaves your machine
- which experimental models you try next
- how quickly you can switch when better models appear

Over time, open models will keep changing. Some will be disappointing. Some will
be surprisingly good. This workflow makes trying them cheap, fast, and
reversible.

You do not have to pick a permanent winner.

You can start one, test it, stop it, and move on.

## What I Learned

The hard parts were mostly operational:

- a pod being `RUNNING` does not mean vLLM is listening yet
- first boot includes model download and warmup
- Runpod proxy URLs show a waiting page until the service binds
- tool-call behavior depends on model-specific vLLM flags
- context length and GPU memory are linked
- forgetting to stop the pod is the most expensive mistake

Once those are handled, the workflow feels ordinary:

```text
choose model
launch GPU
get OpenAI-compatible URL
point VS Code at it
stop GPU
```

That is the whole idea.

Not owning the hardware. Owning the workflow.
