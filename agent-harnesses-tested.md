# Agent Harnesses Tested

Working notes for clients/harnesses that can talk to the Runpod vLLM
OpenAI-compatible endpoint.

| Harness | VS Code story | Skills/context story | Current status | Verdict |
| --- | --- | --- | --- | --- |
| Roo Code | Native VS Code extension. | Has rules/custom instructions and context mentions. We added `@skills` and `@skill-name` conventions in this repo. | Tested with multiple models. Works with the Qwen3.8 27B model when vLLM emits native tool calls. | Best current VS Code path. Needs prompt/rules tuning. |
| Goose | Needs ACP path for VS Code: try a client that launches `goose acp`, or build a small VS Code ACP bridge. | Native skills in `.agents/skills/`, MCP extensions, recipes, subagents, security controls. | Added `llm-runpod goose` and `llm-runpod skills export --target goose`. Not yet tested live against the Runpod endpoint. | Strong next experiment, especially for skills/tools. |
| Pi | No repo integration yet. Potential via RPC/SDK or direct CLI workflow. | Skills, prompt templates, compaction, dynamic context, session trees, extensions. | Roadmap experiment only. | Worth comparing after Goose. |

## Next Goose Test

1. Relaunch a vLLM pod.
2. Run `llm-runpod status --tools`.
3. Run `llm-runpod goose` and configure Goose as an OpenAI-compatible provider.
4. Run `llm-runpod skills export --target goose`.
5. Test Goose CLI/Desktop on the same repo summary/edit task used for Roo.
6. Investigate VS Code ACP client support for `goose acp`.
