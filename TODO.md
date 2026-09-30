# TODO

Keep this repo simple: launch a self-hosted OpenAI-compatible LLM on Runpod,
connect it to VS Code/Roo, and make the day-to-day agent experience smoother.

## Implemented In Current Prototype

- `llm-runpod status`
  - Checks `/v1/models`.
  - Runs a tiny chat completion.
  - Runs a tiny tool-call smoke test with `--tools`.
  - Prints a concise health report that helps diagnose Roo hangs.

- Pod state tracking and cleanup commands
  - Saves the last launched pod id/model/base URL under `.llm-runpod/state.json`.
  - Adds `llm-runpod stop` to stop the last launched pod.
  - Adds `llm-runpod terminate` to delete the last launched pod.
  - Cleanup commands print resource id and last known metadata.

- Roo helpers
  - Extends `llm-runpod vscode --target roo` with richer profile guidance.
  - Prints recommended Roo settings: OpenAI Compatible, base URL, model id,
    context window, max output, image support, prompt caching, and dummy API key.
  - Adds `llm-runpod roo-instructions` for self-hosted model behavior guidance.

- Skill invocation
  - Keeps `@skills` as the explicit catalog command.
  - Keeps `@skill-name` handles for manual skill selection.
  - Injects selected skill markdown into `llm-runpod ask` requests.

- Goose experiment support
  - Adds `llm-runpod goose` to print custom OpenAI-compatible provider setup
    for the current Runpod vLLM endpoint.
  - Adds `llm-runpod skills export --target goose` to copy installed skills into
    Goose's `.agents/skills/` project layout.
  - Tracks the VS Code path: prefer a Goose ACP client/extension, otherwise
    build a small VS Code ACP bridge or adapt Roo to launch Goose.

- Model comparison log
  - Adds `models-tested.md`.
  - Seeds it with what we learned from Qwen 1.5B, Mistral Nemo, Qwen 14B, and
    the Qwen3.8 27B obliterated model.

## Next Implementation Pass

1. Add model-family presets
   - Add `--preset qwen3-coder`, `--preset mistral-tools`, and `--preset generic`.
   - Presets should add known-good vLLM flags such as tool-call parser,
     reasoning parser, `--enable-auto-tool-choice`, and `--enforce-eager` when
     appropriate.
   - Keep explicit `--extra-vllm-arg` overrides available.

2. Add context-budget guidance
   - Document recommended Roo settings for 16k and 32k context models.
   - Add a warning when model context is small and the user tries to use a large
     coding-agent workflow.
   - Prefer practical settings over a full tokenizer integration for now.

3. Improve Roo skill ergonomics
   - Add a compact prompt snippet that can be pasted into Roo so it knows the
     `@skills` and `@skill-name` convention.
   - Later: add automatic skill suggestion based on descriptions, but do not
     build a complex gateway in this repo yet.

4. Try Goose in VS Code
   - Configure Goose against the Runpod vLLM endpoint.
   - Export installed skills to `.agents/skills/`.
   - Test Goose CLI/Desktop on the same repo tasks used for Roo.
   - Investigate VS Code ACP clients that can launch `goose acp`.
   - If no adequate client exists, prototype a small VS Code extension that
     talks to Goose ACP over stdio, HTTP, or WebSocket.
   - Fallback: modify/adapt Roo so it can use Goose as the agent backend.

## Follow-Up Features

- Add `llm-runpod open-webui` to print or run a local Open WebUI setup pointed
  at the Runpod vLLM endpoint.
- Add Pi as a harness experiment:
  - Configure Pi against the Runpod vLLM endpoint.
  - Compare its skills, prompt templates, compaction, session tree, and RPC/SDK
    mode against Roo and Goose.
  - Record results in a future `agent-harnesses-tested.md`.
- Try `Qwen3-Coder-Next` as a Roo/VS Code coding-agent candidate.
- Try `EssentialAI/rnj-1-instruct` as a Roo/VS Code coding-agent candidate:
  https://huggingface.co/EssentialAI/rnj-1-instruct
- Keep the larger gateway/Langfuse/ClickHouse/model-routing platform idea for a
  future sibling repo copied from this prototype.
