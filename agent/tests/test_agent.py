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


def test_documentation_matches_nat_dragent_only_runtime() -> None:
    repository_root = Path(__file__).parents[2]
    agent_instructions = (repository_root / "agent" / "AGENTS.md").read_text()
    agent_readme = (repository_root / "docs" / "agent" / "README.md").read_text()
    nat_guide = (
        repository_root / "docs" / "agent" / "frameworks" / "nat.md"
    ).read_text()
    evaluation_guide = (
        repository_root / "docs" / "agent" / "evaluation.md"
    ).read_text()
    evaluation_example = (
        repository_root
        / ".skills"
        / "datarobot-app-framework-agent-local-evaluation"
        / "examples"
        / "test_agent_eval.py"
    ).read_text()
    evaluation_skill = (
        repository_root
        / ".skills"
        / "datarobot-app-framework-agent-local-evaluation"
        / "SKILL.md"
    ).read_text()
    debugging_guide = (repository_root / "docs" / "agent" / "debugging.md").read_text()
    a2a_guide = (repository_root / "docs" / "agent" / "agent2agent.md").read_text()
    vscode_launch = (repository_root / ".vscode" / "launch.json").read_text()
    pycharm_launch = (
        repository_root / ".idea" / "runConfigurations" / "Run_Agent.xml"
    ).read_text()
    changelog = (repository_root / "CHANGELOG.md").read_text()

    for removed_reference in ("MyAgent", "custompy_adaptor", "LangGraph"):
        assert removed_reference not in agent_instructions
    for removed_reference in ("`custom.py`", "`dev.py`", "DRUM", "experimental"):
        assert removed_reference not in agent_readme
    for removed_reference in ("`myagent.py`", "`MyAgent`"):
        assert removed_reference not in nat_guide
    for evaluation_document in (
        evaluation_guide,
        evaluation_example,
        evaluation_skill,
    ):
        assert "agent.myagent" not in evaluation_document
        assert "custompy_adaptor" not in evaluation_document
        assert "execute_dragent_inline_async" in evaluation_document
    compile(evaluation_example, "test_agent_eval.py", "exec")
    for current_runtime_document in (debugging_guide, a2a_guide):
        assert "ENABLE_DRAGENT_SERVER" not in current_runtime_document
        assert "DRUM" not in current_runtime_document
    for launch_configuration in (vscode_launch, pycharm_launch):
        assert "agent/dev.py" not in launch_configuration
        assert "dragent" in launch_configuration

    unreleased = changelog.split("## 11.9.2", maxsplit=1)[0]
    assert "0.26.1" in unreleased
    assert "DRAgent" in unreleased
    assert "DRUM" in unreleased
