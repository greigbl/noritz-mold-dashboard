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
"""NAT custom tool registration and workflow plugins.

Register tools with a **module-level call** after the function is defined::

    nat_tool(my_function, "my_function")

Do **not** use ``@nat_tool()`` as a decorator with no arguments; that raises
``TypeError: nat_tool() missing 2 required positional arguments: 'fn' and 'name'``.

Each tool name must also appear under ``functions`` in ``workflow.yaml`` and in
``workflow.tool_names``. See ``docs/agent/frameworks/nat.md``.

Framework-specific NAT plugins are loaded from datarobot-genai and NAT
entrypoints. When Mem0 is enabled, memory registration lives in
``agent.register_memory`` so it can be shared by every workflow template.
"""

from typing import Any


def _patch_datarobot_mcp_tavily_headers() -> None:
    """Forward the Tavily credential through NAT's DataRobot MCP client.

    datarobot_mcp_client currently exposes MCPServerConfig.custom_headers, but
    its DataRobot streamable HTTP wrapper does not pass those headers to the
    underlying MCP client for the default shared session. The native Tavily MCP
    tools require x-tavily-api-key, so inject it when the client is created.
    """
    from datarobot_genai.nat.datarobot_mcp_client import (  # noqa: PLC0415
        DataRobotMCPStreamableHTTPClient,
    )

    if getattr(DataRobotMCPStreamableHTTPClient, "_tavily_header_patch", False):
        return

    original_init = DataRobotMCPStreamableHTTPClient.__init__

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)

        from agent.config import Config  # noqa: PLC0415

        tavily_api_key = Config().tavily_api_key
        if tavily_api_key:
            self._custom_headers["x-tavily-api-key"] = tavily_api_key

    DataRobotMCPStreamableHTTPClient.__init__ = patched_init  # type: ignore[method-assign]
    DataRobotMCPStreamableHTTPClient._tavily_header_patch = True


_patch_datarobot_mcp_tavily_headers()
