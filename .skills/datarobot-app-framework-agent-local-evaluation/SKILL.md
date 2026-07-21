# Skill: DataRobot local Agent evaluation

Use this skill when a user wants to evaluate the NAT Agent locally, add LLM-as-a-judge
quality gates, or detect hallucinations with a moderation pipeline.

## Prerequisites

Confirm that:

1. Agent dependencies are installed with `dr task run agent:install`.
2. The user has a DataRobot LLM deployment for the judge model.
3. `DATAROBOT_ENDPOINT` and `DATAROBOT_API_TOKEN` are configured.
4. Agent LLM and MCP runtime parameters required by `workflow.yaml` are configured.

`TARGET_NAME` is not needed when the test passes the aggregated assistant text directly to
the moderation pipeline.

## Implementation

### 1. Add `moderation.yaml`

Copy `examples/moderation.yaml` to `agent/moderation.yaml`, replace the judge deployment ID,
and keep only the guards needed by the use case.

- `agent_goal_accuracy`: general Agent tasks.
- `faithfulness`: grounded responses; requires `copy_citations: true` and
  `retrieved_contexts`.
- `task_adherence`: instruction-following behavior.

### 2. Add the Pytest evaluation

Copy `examples/test_agent_eval.py` to `agent/tests/test_agent_eval.py`. The example invokes
the production NAT workflow in-process with `execute_dragent_inline_async`:

```python
from pathlib import Path

from datarobot_genai.dragent.inline import execute_dragent_inline_async

AGENT_DIR = Path(__file__).parents[1]


async def invoke_agent_text(user_prompt: str) -> str:
    response = await execute_dragent_inline_async(
        {
            "model": "datarobot-llm",
            "messages": [{"role": "user", "content": user_prompt}],
            "stream": False,
        },
        custom_model_dir=AGENT_DIR,
        config_file=AGENT_DIR / "workflow.yaml",
    )
    return response.choices[0].message.content or ""
```

Pass the resulting text to the evaluator:

```python
@pytest.mark.eval
async def test_agent_goal_accuracy(pipeline):
    user_prompt = "製造アラートの原因仮説と初動対応を整理してください。"
    response_text = await invoke_agent_text(user_prompt)

    result, _ = pipeline.evaluate_response(response_text, prompt=user_prompt)

    assert not result.blocked, (
        f"Eval failed: {result.blocked_message} | Metrics: {result.metrics}"
    )
```

### 3. Register the marker

```toml
[tool.pytest.ini_options]
markers = [
    "eval: live evaluation tests requiring DataRobot credentials",
]
```

## Commands

Run live evaluations:

```shell
cd agent && uv run pytest tests/ -m eval -v
```

Skip live evaluations:

```shell
cd agent && uv run pytest tests/ -m "not eval"
```

## Key facts

- The judge deployment ID belongs to the evaluator, not the Agent's own LLM.
- `result.blocked` is true when a configured threshold is breached.
- Faithfulness requires both a citation-aware guard and reference contexts.
- Evaluation runs may call external LLM and MCP services; keep them separate from unit tests.
- `execute_dragent_inline_async` returns an aggregated OpenAI-compatible response, avoiding
  assertions against individual streaming chunks.
- See [`docs/agent/evaluation.md`](../../docs/agent/evaluation.md) for the full guide.
