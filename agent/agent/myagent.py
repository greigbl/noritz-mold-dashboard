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
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from datarobot_genai.core.agents import InvokeReturn
from datarobot_genai.core.agents.base import UsageMetrics
from datarobot_genai.core.chat import agent_chat_completion_wrapper
from datarobot_genai.core.mcp import MCPConfig
from datarobot_genai.nat.agent import NatAgent
from openai.types.chat import CompletionCreateParams

from agent.config import Config

if TYPE_CHECKING:
    from ragas import MultiTurnSample


@asynccontextmanager
async def noop_mcp_tools_context(
    _mcp_config: MCPConfig,
) -> AsyncGenerator[list[Any], None]:
    """No-op MCP tools context for NAT: tools come from workflow.yaml, not DRUM MCP."""
    yield []


def _json_safe_mcp_kwargs(value: Any) -> Any:
    """Convert framework-created enum instances back to JSON-safe MCP values."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _json_safe_mcp_kwargs(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_mcp_kwargs(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_json_safe_mcp_kwargs(item) for item in value)
    return value


def _patch_nat_mcp_enum_arguments() -> None:
    """Patch NAT MCP tool calls to tolerate enum objects produced by tool wrappers."""
    from nat.builder.function import FunctionInfo
    from nat.plugins.mcp.client import client_impl
    from pydantic import BaseModel

    if getattr(client_impl, "_dr_enum_argument_patch_applied", False):
        return

    def mcp_session_tool_function(tool: Any, function_group: Any) -> Any:
        def _convert_from_str(input_str: str) -> Any:
            return tool.input_schema.model_validate_json(input_str)

        async def _response_fn(
            tool_input: BaseModel | None = None, **kwargs: Any
        ) -> str:
            try:
                session_id = function_group._get_session_id_from_context()

                if function_group._shared_auth_provider and session_id is None:
                    return "User not authorized to call the tool"

                if (
                    not function_group._shared_auth_provider
                    or session_id == function_group._default_user_id
                ):
                    client = function_group.mcp_client
                    if client is None:
                        return "Tool temporarily unavailable. Try again."
                    session_tool = await client.get_tool(tool.name)
                else:
                    if session_id is None:
                        return "Tool temporarily unavailable. Try again."
                    async with function_group._session_usage_context(
                        session_id
                    ) as client:
                        if client is None:
                            return "Tool temporarily unavailable. Try again."
                        session_tool = await client.get_tool(tool.name)

                if tool_input:
                    args = tool_input.model_dump(exclude_none=True, mode="json")
                    return str(await session_tool.acall(args))

                validated_input = session_tool.input_schema.model_validate(
                    _json_safe_mcp_kwargs(kwargs)
                )
                args = validated_input.model_dump(exclude_none=True, mode="json")
                return str(await session_tool.acall(args))
            except Exception as e:
                client_impl.logger.warning(
                    "Error calling tool %s", tool.name, exc_info=True
                )
                return str(e)

        return FunctionInfo.create(
            single_fn=_response_fn,
            description=tool.description,
            input_schema=tool.input_schema,
            converters=[_convert_from_str],
        )

    client_impl.mcp_session_tool_function = mcp_session_tool_function
    client_impl._dr_enum_argument_patch_applied = True


class MyAgent(NatAgent):
    """MyAgent is a custom agent that uses NVIDIA NeMo Agent Toolkit and can be used for creating
    a custom agentic flow defined in workflow.yaml. It utilizes DataRobot's LLM Gateway or a
    specific deployment for language model interactions. This example illustrates 2 agents that
    handle content creation tasks, including planning and writing blog posts.
    """

    def __init__(
        self,
        *args: Any,
        workflow_path: Path = Path(__file__).parent / "workflow.yaml",
        **kwargs: Any,
    ) -> None:
        _patch_nat_mcp_enum_arguments()
        super().__init__(
            *args,
            workflow_path=workflow_path,  # type: ignore[misc]
            **kwargs,
        )


async def custompy_adaptor(
    completion_create_params: CompletionCreateParams,
) -> InvokeReturn | tuple[str, Optional["MultiTurnSample"], UsageMetrics]:
    forwarded_headers: dict[str, str] = completion_create_params.get(  # type: ignore[assignment]
        "forwarded_headers", {}
    )
    authorization_context = completion_create_params.get("authorization_context", {})
    mcp_config = MCPConfig(
        forwarded_headers=forwarded_headers,
        authorization_context=authorization_context,
    )
    server_config = mcp_config.server_config
    headers = server_config["headers"] if server_config else {}
    forwarded_headers.update(headers)
    config = Config()
    if config.tavily_api_key:
        forwarded_headers["x-datarobot-tavily-api-key"] = config.tavily_api_key
    mcp_tools_factory = lambda: noop_mcp_tools_context(mcp_config)  # noqa: E731
    agent = MyAgent(
        verbose=completion_create_params.get("verbose", True),
        timeout=completion_create_params.get("timeout", 90),
        forwarded_headers=forwarded_headers,
    )
    return await agent_chat_completion_wrapper(
        agent, completion_create_params, mcp_tools_factory
    )
