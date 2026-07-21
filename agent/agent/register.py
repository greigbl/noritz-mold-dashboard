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

"""Runtime registrations required by the NAT workflow."""

import os
from typing import Any

from datarobot_genai.core.telemetry.agent import instrument
from datarobot_genai.dragent.plugins.datarobot_mcp_client import (
    DataRobotMCPStreamableHTTPClient,
)

_original_mcp_client_init = DataRobotMCPStreamableHTTPClient.__init__


def _init_mcp_client_with_tavily_header(
    self: DataRobotMCPStreamableHTTPClient, *args: Any, **kwargs: Any
) -> None:
    """Forward the optional agent runtime credential to the MCP server."""
    _original_mcp_client_init(self, *args, **kwargs)
    if tavily_api_key := os.getenv("TAVILY_API_KEY"):
        self._custom_headers.setdefault("x-tavily-api-key", tavily_api_key)
        self._custom_headers.setdefault("x-datarobot-tavily-api-key", tavily_api_key)


if not getattr(DataRobotMCPStreamableHTTPClient, "_tavily_header_registered", False):
    DataRobotMCPStreamableHTTPClient.__init__ = _init_mcp_client_with_tavily_header  # type: ignore[method-assign]
    DataRobotMCPStreamableHTTPClient._tavily_header_registered = True

instrument()
