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

import pytest
import yaml


def test_nat_plugin_registration_imports() -> None:
    import agent.register  # noqa: F401


def test_dragent_mcp_client_forwards_tavily_runtime_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datarobot_genai.dragent.plugins.datarobot_mcp_client import (
        DataRobotMCPStreamableHTTPClient,
    )

    import agent.register  # noqa: F401

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")

    client = DataRobotMCPStreamableHTTPClient("http://localhost:9000/mcp")

    assert client.custom_headers["x-tavily-api-key"] == "tvly-test-key"
    assert client.custom_headers["x-datarobot-tavily-api-key"] == "tvly-test-key"


def test_tavily_registration_uses_public_custom_headers_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent.register as register

    class PublicHeadersOnlyClient:
        custom_headers: dict[str, str]

    def initialize_public_headers(
        client: PublicHeadersOnlyClient, *args: object, **kwargs: object
    ) -> None:
        client.custom_headers = {}

    monkeypatch.setattr(
        register, "_original_mcp_client_init", initialize_public_headers
    )
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-public-api-key")
    client = PublicHeadersOnlyClient()

    register._init_mcp_client_with_tavily_header(client)  # type: ignore[arg-type]

    assert client.custom_headers == {
        "x-tavily-api-key": "tvly-public-api-key",
        "x-datarobot-tavily-api-key": "tvly-public-api-key",
    }


def test_workflow_preserves_quality_alert_and_prediction_branches() -> None:
    workflow_text = (Path(__file__).parents[1] / "workflow.yaml").read_text()

    assert "実行モード: search_only" in workflow_text
    assert "種別: spc_rbar" in workflow_text
    assert "種別: business_rule" in workflow_text
    assert "predict_realtime を呼び出してはいけません" in workflow_text
    assert "search_agent を1回だけ呼んでください" in workflow_text
    assert "通常の製造条件入力の場合は" in workflow_text
    assert "predict_realtimeを実行してください" in workflow_text


def test_search_agent_keeps_wikipedia_and_mcp_tools() -> None:
    workflow = yaml.safe_load((Path(__file__).parents[1] / "workflow.yaml").read_text())

    assert workflow["functions"]["wikipedia_search"] == {
        "_type": "wiki_search",
        "max_results": 3,
    }
    assert "wikipedia_search" in workflow["functions"]["search_agent"]["tool_names"]
    assert workflow["function_groups"]["mcp_tools"]["_type"] == "datarobot_mcp_client"


def test_taskfile_runs_nat_through_dragent() -> None:
    taskfile_text = (Path(__file__).parents[1] / "Taskfile.yml").read_text()

    assert "nat dragent serve --config_file workflow.yaml" in taskfile_text
    assert (
        'DRAGENT_CONFIG_FILE="${DRAGENT_CONFIG_FILE:-workflow.yaml}"' in taskfile_text
    )
