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

from pathlib import Path

import yaml

WORKFLOW_PATH = Path(__file__).parents[1] / "agent" / "workflow.yaml"


def test_workflow_keeps_only_search_as_sub_agent():
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text())

    assert list(workflow["functions"].keys()) == ["search_agent"]
    assert workflow["workflow"]["tool_names"] == ["mcp_tools", "search_agent"]


def test_search_agent_uses_search_tools_without_prediction():
    workflow = WORKFLOW_PATH.read_text()

    assert "search_agent:" in workflow
    assert "gdrive_find_contents" in workflow
    assert "gdrive_read_content" in workflow
    assert "tavily_search" in workflow
    assert "tavily_extract" in workflow
    assert "predict_realtimeを呼び出してはいけません" in workflow
    assert "外部検索URL:" in workflow
    assert "URL取得不可" in workflow


def test_workflow_owns_quality_assessment_and_advice_phases():
    workflow = WORKFLOW_PATH.read_text()

    assert "あなた自身が品質判定と現場向けの最終回答作成を担当します" in workflow
    assert "predict_realtimeは必ず1回だけ呼ぶ" in workflow
    assert "良品の場合は検索せず" in workflow
    assert "search_agent を1回呼ぶ" in workflow
    assert "根拠付き原因考察" in workflow
    assert "### 🔗 参照URL" in workflow
    assert "最終回答の「参照URL」に必ず転記する" in workflow
    assert "Triage" not in workflow
    assert "TRIAGE" not in workflow
