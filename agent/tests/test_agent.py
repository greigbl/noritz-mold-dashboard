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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent import MyAgent
from agent.myagent import custompy_adaptor, noop_mcp_tools_context


class TestMyAgentNat:
    def test_myagent_is_nat_agent_subclass(self) -> None:
        from datarobot_genai.nat.agent import NatAgent

        assert issubclass(MyAgent, NatAgent)

    def test_init_uses_default_workflow_path(self) -> None:
        agent = MyAgent()

        assert (
            agent.workflow_path == Path(__file__).parents[1] / "agent" / "workflow.yaml"
        )

    @pytest.mark.asyncio
    async def test_noop_mcp_tools_context_returns_empty_tools(self) -> None:
        async with noop_mcp_tools_context(MagicMock()) as tools:
            assert tools == []

    @pytest.mark.asyncio
    @patch("agent.myagent.Config")
    @patch("agent.myagent.MCPConfig")
    @patch("agent.myagent.agent_chat_completion_wrapper", new_callable=AsyncMock)
    @patch("agent.myagent.MyAgent")
    async def test_custompy_adaptor_uses_nat_agent(
        self,
        mock_agent: MagicMock,
        mock_wrapper: AsyncMock,
        mock_mcp_config: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        mock_mcp_config.return_value.server_config = None
        mock_config.return_value.tavily_api_key = None
        completion_create_params = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "hi"}],
            "forwarded_headers": {},
            "authorization_context": {},
        }

        await custompy_adaptor(completion_create_params)

        mock_agent.assert_called_once()
        assert mock_agent.call_args.kwargs["forwarded_headers"] == {}
        mock_wrapper.assert_awaited_once()

    def test_datarobot_mcp_client_gets_tavily_header(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from datarobot_genai.nat.datarobot_mcp_client import (
            DataRobotMCPStreamableHTTPClient,
        )

        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")

        client = DataRobotMCPStreamableHTTPClient("http://localhost:9000/mcp")

        assert client._custom_headers["x-tavily-api-key"] == "tvly-test-key"
        assert client._custom_headers["x-datarobot-tavily-api-key"] == "tvly-test-key"

    def test_workflow_branches_business_alerts_to_search_only(self) -> None:
        workflow_text = (
            Path(__file__).parents[1] / "agent" / "workflow.yaml"
        ).read_text()

        assert "実行モード: search_only" in workflow_text
        assert "種別: spc_rbar" in workflow_text
        assert "種別: business_rule" in workflow_text
        assert "predict_realtime を呼び出してはいけません" in workflow_text
        assert "search_agent を1回だけ呼んでください" in workflow_text
        assert "通常の製造条件入力の場合は" in workflow_text
        assert (
            "アラートと勝手に判断せずに、predict_realtimeを実行してください"
            in workflow_text
        )
