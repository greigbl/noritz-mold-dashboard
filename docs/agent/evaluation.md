# Local evaluation for the NAT Agent

This guide evaluates the same NAT `workflow.yaml` used by DRAgent in production. Tests run
the workflow in-process with `execute_dragent_inline_async`, extract the final assistant
message, and pass that text to the DataRobot moderation pipeline.

## Prerequisites

Install the locked Agent dependencies:

```shell
dr task run agent:install
```

Provide the DataRobot credentials and LLM settings required by `workflow.yaml`:

| Variable | Purpose |
|---|---|
| `DATAROBOT_ENDPOINT` | DataRobot API endpoint. |
| `DATAROBOT_API_TOKEN` | API token used by the Agent and evaluator. |
| `LLM_DEPLOYMENT_ID` or gateway settings | LLM used by the Agent workflow. |
| `MCP_DEPLOYMENT_ID` or `EXTERNAL_MCP_URL` | MCP endpoint when an evaluation invokes MCP tools. |

The evaluator also needs a judge LLM deployment. Prefer a capable model different from the
model being evaluated.

## Moderation configuration

Place `moderation.yaml` beside `workflow.yaml`:

```text
agent/
├── moderation.yaml
├── workflow.yaml
└── tests/
    ├── eval_helpers.py
    └── test_agent_eval.py
```

Example:

```yaml
timeout_sec: 60
timeout_action: block

guards:
  - name: Agent Goal Accuracy
    type: ootb
    ootb_type: agent_goal_accuracy
    stage: response
    is_agentic: true
    llm_type: datarobot
    deployment_id: "<YOUR_JUDGE_LLM_DEPLOYMENT_ID>"
    intervention:
      action: block
      message: "Agent failed to achieve the user's goal."
      conditions:
        - comparator: lessThan
          comparand: 0.7
```

## Invoke DRAgent in-process

Create `agent/tests/eval_helpers.py`:

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

This helper loads the NAT workflow through the same DataRobot integration used by the
DRAgent runtime and returns its aggregated OpenAI-compatible response. No local HTTP server
is required.

## Basic quality evaluation

```python
import pytest
from datarobot_dome.api import ModerationPipeline

from tests.eval_helpers import invoke_agent_text


@pytest.fixture(scope="session")
def pipeline():
    return ModerationPipeline.from_yaml("moderation.yaml")


@pytest.mark.eval
async def test_agent_goal_accuracy(pipeline):
    user_prompt = "製造アラートの原因仮説と初動対応を整理してください。"
    response_text = await invoke_agent_text(user_prompt)

    result, _ = pipeline.evaluate_response(response_text, prompt=user_prompt)

    assert not result.blocked, (
        f"Eval failed: {result.blocked_message} | Metrics: {result.metrics}"
    )
```

## Faithfulness evaluation

Configure a `faithfulness` guard with `copy_citations: true`, then pass the reference
context:

```python
@pytest.mark.eval
async def test_agent_faithfulness(pipeline):
    user_prompt = "管理限界を超過した温度アラートの確認項目を整理してください。"
    retrieved_context = [
        "同日ロットを時間帯で層別し、センサー校正と設備設定変更を確認する。"
    ]
    response_text = await invoke_agent_text(user_prompt)

    result, _ = pipeline.evaluate_response(
        response_text,
        prompt=user_prompt,
        retrieved_contexts=retrieved_context,
    )

    assert not result.blocked, f"Faithfulness failed: {result.blocked_message}"
```

## Parametrized cases

```python
TEST_CASES = [
    {
        "prompt": "コーター温度のばらつきについて確認項目を整理してください。",
        "context": ["センサー校正、材料ロット、設定変更、シフト切替を確認する。"],
    },
    {
        "prompt": "品質リスクが高い場合の初動対応を整理してください。",
        "context": ["対象ロットを保留し、異常時間帯と設備履歴を確認する。"],
    },
]


@pytest.mark.eval
@pytest.mark.parametrize("case", TEST_CASES)
async def test_faithfulness_cases(pipeline, case):
    response_text = await invoke_agent_text(case["prompt"])
    result, _ = pipeline.evaluate_response(
        response_text,
        prompt=case["prompt"],
        retrieved_contexts=case["context"],
    )
    assert not result.blocked, (
        f"Failed on '{case['prompt']}': {result.blocked_message}"
    )
```

## Register the evaluation marker

Add the marker to `agent/pyproject.toml` when copying the example into the test suite:

```toml
[tool.pytest.ini_options]
markers = [
    "eval: live evaluation tests requiring DataRobot credentials",
]
```

Run only live evaluations:

```shell
cd agent
uv run pytest tests/ -m eval -v
```

Run unit tests without live evaluation:

```shell
cd agent
uv run pytest tests/ -m "not eval"
```

## CI/CD guidance

Store credentials in the CI secret manager and expose them only to the evaluation job.
Evaluation tests call external LLM and MCP services, so keep them separate from deterministic
unit tests and set explicit timeouts.

```yaml
- name: Run Agent evaluation
  run: cd agent && uv run pytest tests/ -m eval --junitxml=eval-results.xml
  env:
    DATAROBOT_API_TOKEN: ${{ secrets.DATAROBOT_API_TOKEN }}
    DATAROBOT_ENDPOINT: ${{ secrets.DATAROBOT_ENDPOINT }}
```

## Troubleshooting

### Workflow configuration error

Validate before running the evaluation:

```shell
cd agent
uv run nat validate --config_file workflow.yaml
```

### MCP connection error

Confirm the MCP runtime parameter points to a running server and that required credentials
are available. Prompts that trigger `search_agent` or prediction tools require MCP access.

### Evaluator timeout

Increase `timeout_sec` for a cold judge deployment, or warm the deployment before the test.

### Empty response

Inspect the returned `ChatCompletion` and DRAgent logs. The helper intentionally reads
`response.choices[0].message.content`, which is the aggregated assistant response rather than
individual streaming chunks.
