# Copyright 2026 DataRobot, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Copy this file to agent/tests/test_agent_eval.py and customize its cases."""

from pathlib import Path

import pytest
from datarobot_dome.api import ModerationPipeline
from datarobot_genai.dragent.inline import execute_dragent_inline_async

AGENT_DIR = Path(__file__).parents[1]


async def invoke_agent_text(user_prompt: str) -> str:
    """Execute the NAT workflow in-process and return the final assistant text."""
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


@pytest.fixture(scope="session")
def pipeline():
    """Load the evaluation pipeline once for the test session."""
    return ModerationPipeline.from_yaml("moderation.yaml")


@pytest.mark.eval
async def test_agent_goal_accuracy(pipeline):
    """The Agent response should achieve the user's stated goal."""
    user_prompt = "製造アラートの原因仮説と初動対応を整理してください。"
    response_text = await invoke_agent_text(user_prompt)

    result, _ = pipeline.evaluate_response(response_text, prompt=user_prompt)

    assert not result.blocked, (
        f"Eval failed: {result.blocked_message} | Metrics: {result.metrics}"
    )


@pytest.mark.eval
async def test_agent_faithfulness(pipeline):
    """The Agent response should stay grounded in the supplied context."""
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
    """All configured manufacturing cases should pass faithfulness evaluation."""
    response_text = await invoke_agent_text(case["prompt"])
    result, _ = pipeline.evaluate_response(
        response_text,
        prompt=case["prompt"],
        retrieved_contexts=case["context"],
    )
    assert not result.blocked, f"Failed on '{case['prompt']}': {result.blocked_message}"


@pytest.mark.eval
def test_pipeline_catches_hallucination(pipeline):
    """The evaluator should reject a response contradicted by its reference context."""
    result, _ = pipeline.evaluate_response(
        "設備履歴の確認は不要です。",
        prompt="温度アラートでは何を確認すべきですか？",
        retrieved_contexts=["温度アラートでは設備履歴とセンサー校正を確認する。"],
    )
    assert result.blocked, "The evaluation pipeline should catch the contradiction."
