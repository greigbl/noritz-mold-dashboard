# NAT Agent

The Agent uses NVIDIA NeMo Agent Toolkit (NAT) with a YAML-first configuration. DRAgent
loads `agent/workflow.yaml`, builds the workflow, and exposes it through its HTTP, CLI, and
deployment interfaces.

## Files

| File | Purpose |
|---|---|
| `agent/workflow.yaml` | Declares the front end, functions, MCP clients, LLMs, and orchestration. |
| `agent/agent/register.py` | Performs Python-side NAT registrations and telemetry setup. |
| `agent/pyproject.toml` | Declares dependencies and the `nat.plugins` entry point. |

The plugin entry point imports `agent.register` automatically during NAT startup:

```toml
[project.entry-points.'nat.plugins']
nat_agent = "agent.register"
```

## Workflow requirements

NAT validates `workflow.yaml` against registered configuration schemas. Follow these rules:

1. Every name in `tool_names` must exist under `functions` or `function_groups`.
2. MCP clients belong under `function_groups`, not as Python imports.
3. Custom Python tools require both a `nat_tool` registration and a matching YAML function.
4. Use `typing.Annotated` descriptions for custom tool parameters.
5. Keep authentication and credentials in runtime configuration, never in YAML literals.
6. Validate the file after every structural change.

```shell
cd agent
uv run nat validate --config_file workflow.yaml
```

## Front end

DRAgent is configured under `general.front_end`:

```yaml
general:
  front_end:
    _type: dragent_fastapi
    step_adaptor:
      mode: 'off'
```

Optional A2A server metadata and skills are declared beneath the same front-end block.

## Functions and sub-agents

Built-in functions and nested workflows are declared under `functions`. For example:

```yaml
functions:
  wikipedia_search:
    _type: wiki_search
    max_results: 3
  search_agent:
    _type: per_user_tool_calling_agent
    llm_name: datarobot_llm
    description: Search internal and external evidence.
    tool_names:
      - mcp_tools
      - wikipedia_search
    system_prompt: |
      Search for evidence and return a concise source summary.
```

Nested tool-calling workflows follow the same validation rule: every item in their
`tool_names` must be declared.

## MCP tools

Configure the MCP server as a function group:

```yaml
function_groups:
  mcp_tools:
    _type: datarobot_mcp_client
```

Then reference `mcp_tools` from the top-level workflow or a nested function. The Agent and
MCP server remain separate services and communicate through the MCP protocol.

## LLM configuration

The default DataRobot LLM component is configured in YAML:

```yaml
llms:
  datarobot_llm:
    _type: datarobot-llm-component
```

Functions select it with `llm_name: datarobot_llm`. For provider failover, replace the
component with `datarobot-llm-router`; see [LLM provider fallback](../llm-fallback.md).

## Top-level workflow

The manufacturing Agent uses a tool-calling workflow:

```yaml
workflow:
  _type: per_user_tool_calling_agent
  llm_name: datarobot_llm
  tool_names:
    - mcp_tools
    - search_agent
  system_prompt: |
    Route manufacturing requests according to the configured business rules.
```

Routing guarantees such as tool call counts and forbidden tools belong in the system prompt
and should be protected by tests.

## Custom local tools

Define and register a tool in `agent/agent/register.py`:

```python
from typing import Annotated

from datarobot_genai.nat.tool import nat_tool


def word_counter(text: Annotated[str, "Text to count."]) -> str:
    return str(len(text.split()))


nat_tool(word_counter, "word_counter", description="Count words in text.")
```

Declare the same name in YAML and expose it through `tool_names`:

```yaml
functions:
  word_counter:
    _type: word_counter
    description: Count words in text.

workflow:
  _type: per_user_tool_calling_agent
  llm_name: datarobot_llm
  tool_names:
    - word_counter
```

Registration alone is insufficient; NAT builds callable functions from the YAML definition.

## Runtime credential forwarding

When an MCP tool needs a runtime credential, forward it through the public
`custom_headers` API on `DataRobotMCPStreamableHTTPClient`. Do not mutate private client
attributes. The MCP server reads approved headers and resolves its own configuration.

## Local execution

Serve the Agent:

```shell
dr run agent:dev
```

Run the workflow without starting a server:

```shell
dr task run agent:cli -- -- execute --user_prompt "Your prompt"
```

Query a deployed Agent:

```shell
dr task run agent:cli -- -- execute-deployment \
  --user_prompt "Your prompt" \
  --deployment_id <deployment_id>
```

For in-process Pytest evaluation, use `execute_dragent_inline_async` as documented in
[Local evaluation](../evaluation.md).
