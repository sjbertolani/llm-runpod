# Models Tested

Working notes from VS Code/Roo + Runpod + vLLM testing. This is not a benchmark;
it is a practical log of what felt usable as a coding-agent backend.

| Model | GPU / Cost | Context | vLLM flags | Roo behavior | Verdict |
| --- | --- | ---: | --- | --- | --- |
| `Qwen/Qwen2.5-Coder-1.5B-Instruct` | A40, `$0.49/hr` in our test | 8k | `--enable-auto-tool-choice --tool-call-parser hermes` | Ran, but tool behavior and responses were weak/weird for agent use. | Good plumbing smoke test, not a good coding agent. |
| `Qwen/Qwen2.5-Coder-14B-Instruct` | A40 class | 16k-ish target | Tried tool parsing | Chat worked, but tool calls came back as text markup rather than native OpenAI `tool_calls`. | Not ideal for Roo until tool parsing is solved. |
| `mistralai/Mistral-Nemo-Instruct-2407` | A40, `$0.49/hr` in our test | 32k | `--enable-auto-tool-choice --tool-call-parser mistral` | Native tool calls worked. Architect-style prompts could be verbose/planning-heavy. | Solid fallback on cheaper GPU. |
| `medismera/Qwen3.8-27B-OBLITERATED-Mythos-Class-Agentic` | A100 80GB, `$1.59/hr` in our test | 16k | `--enforce-eager --enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3` | Best experience so far in Roo/VS Code. Native tool calls worked, and reasoning parser kept scratchpad out of visible content. | Current best candidate. More expensive, but worth retesting for real tasks. |

## Queue

- Try `Qwen3-Coder-Next`.
- Try `EssentialAI/rnj-1-instruct`: https://huggingface.co/EssentialAI/rnj-1-instruct
