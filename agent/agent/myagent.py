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
import os
from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, AsyncIterator, Optional, cast

import litellm
from datarobot_genai.core.agents import InvokeReturn, make_system_prompt
from datarobot_genai.core.agents.base import UsageMetrics
from datarobot_genai.core.chat import agent_chat_completion_wrapper
from datarobot_genai.core.mcp import MCPConfig
from datarobot_genai.langgraph.agent import datarobot_agent_class_from_langgraph
from datarobot_genai.langgraph.llm import get_llm
from datarobot_genai.langgraph.mcp import mcp_tools_context
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from openai.types.chat import CompletionCreateParams

if TYPE_CHECKING:
    from ragas import MultiTurnSample

litellm.modify_params = True

_PLACEHOLDER_MODELS = frozenset({"unknown"})


def _json_safe_mcp_kwargs(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {k: _json_safe_mcp_kwargs(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe_mcp_kwargs(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_json_safe_mcp_kwargs(v) for v in value)
    return value


def _agent_forwarded_headers(
    forwarded_headers: dict[str, str], mcp_config: MCPConfig
) -> dict[str, str]:
    server_config = mcp_config.server_config or {}
    server_headers = server_config.get("headers") or {}
    headers = {**server_headers, **forwarded_headers}
    if tavily_api_key := os.environ.get("TAVILY_API_KEY"):
        headers["x-datarobot-tavily-api-key"] = tavily_api_key
    return headers


@asynccontextmanager
async def _mcp_tools_context(mcp_config: MCPConfig) -> AsyncIterator[list[BaseTool]]:
    server_config = mcp_config.server_config
    if server_config and "url" not in server_config:
        yield []
        return
    async with mcp_tools_context(mcp_config) as tools:
        yield tools


prompt_template = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a helpful assistant that plans and writes content based on the "
            "user's topic. Chat history is provided via {chat_history} (it may be empty). "
            "Use it when helpful to stay consistent across turns.",
        ),
        (
            "user",
            "The topic is {topic}. Make sure you find any interesting and "
            f"relevant information given the current year is {datetime.now().year}.",
        ),
    ]
)


def graph_factory(
    llm: BaseChatModel, tools: list[BaseTool], verbose: bool = False
) -> StateGraph[MessagesState]:
    agent_planner = create_agent(
        llm,
        tools=tools,
        system_prompt=make_system_prompt(
            "You are a content planner. You create brief, structured outlines for blog articles. "
            "You identify the most important points and cite relevant sources. Keep it simple and to the point - "
            "this is just an outline for the writer.\n"
            "\n"
            "You have access to tools that can help you research and gather information. Use these tools when "
            "required to collect accurate and up-to-date information about the topic for your planning and research.\n"
            "\n"
            "Create a simple outline with:\n"
            "1. 10-15 key points or facts (bullet points only, no paragraphs)\n"
            "2. 2-3 relevant sources or references\n"
            "3. A brief suggested structure (intro, 2-3 sections, conclusion)\n"
            "\n"
            "Do NOT write paragraphs or detailed explanations. Just provide a focused list.",
        ),
        name="planner_agent",
        debug=verbose,
    )

    agent_writer = create_agent(
        llm,
        tools=tools,
        system_prompt=make_system_prompt(
            "You are a content writer working with a planner colleague.\n"
            "You write opinion pieces based on the planner's outline and context. You provide objective and "
            "impartial insights backed by the planner's information. You acknowledge when your statements are "
            "opinions versus objective facts.\n"
            "\n"
            "You have access to tools that can help you verify facts and gather additional supporting information. "
            "Use these tools when required to ensure accuracy and find relevant details while writing.\n"
            "\n"
            "1. Use the content plan to craft a compelling blog post.\n"
            "2. Structure with an engaging introduction, insightful body, and summarizing conclusion.\n"
            "3. Sections/Subtitles are properly named in an engaging manner.\n"
            "4. CRITICAL: Keep the total output under 500 words. Each section should have 1-2 brief paragraphs.\n"
            "\n"
            "Write in markdown format, ready for publication.",
        ),
        name="writer_agent",
        debug=verbose,
    )

    def planner_to_writer_relay(state: MessagesState) -> MessagesState:
        last = state["messages"][-1]
        if isinstance(last, AIMessage):
            return {"messages": [HumanMessage(content=last.content)]}
        return {"messages": []}

    langgraph_workflow = StateGraph(MessagesState)
    langgraph_workflow.add_node("planner_node", agent_planner)
    langgraph_workflow.add_node("planner_to_writer_relay", planner_to_writer_relay)
    langgraph_workflow.add_node("writer_node", agent_writer)
    langgraph_workflow.add_edge(START, "planner_node")
    langgraph_workflow.add_edge("planner_node", "planner_to_writer_relay")
    langgraph_workflow.add_edge("planner_to_writer_relay", "writer_node")
    langgraph_workflow.add_edge("writer_node", END)
    return langgraph_workflow


MyAgent = datarobot_agent_class_from_langgraph(graph_factory, prompt_template)


async def custompy_adaptor(
    completion_create_params: CompletionCreateParams,
) -> InvokeReturn | tuple[str, Optional["MultiTurnSample"], UsageMetrics]:
    forwarded_headers = cast(
        dict[str, str], completion_create_params.get("forwarded_headers", {})
    )
    authorization_context = cast(
        dict[str, Any], completion_create_params.get("authorization_context", {})
    )
    mcp_config = MCPConfig(
        **_json_safe_mcp_kwargs(
            {
                "forwarded_headers": forwarded_headers,
                "authorization_context": authorization_context,
            }
        )
    )
    agent_forwarded_headers = _agent_forwarded_headers(forwarded_headers, mcp_config)
    mcp_tools_factory = lambda: _mcp_tools_context(mcp_config)  # noqa: E731
    model_name = completion_create_params.get("model")
    agent = MyAgent(
        llm=get_llm(
            model_name=model_name if model_name not in _PLACEHOLDER_MODELS else None
        ),
        verbose=completion_create_params.get("verbose", True),  # type: ignore[arg-type]
        timeout=completion_create_params.get("timeout", 90),  # type: ignore[arg-type]
        forwarded_headers=agent_forwarded_headers,
    )
    return await agent_chat_completion_wrapper(
        agent, completion_create_params, mcp_tools_factory
    )
