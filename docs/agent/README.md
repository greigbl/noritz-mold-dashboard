# Agent

The Agent component implements the manufacturing-quality workflow. It uses NVIDIA NeMo
Agent Toolkit (NAT) for orchestration and DRAgent as its front server. The workflow is
defined declaratively in `agent/workflow.yaml` and connects to the independently deployed
MCP server over HTTP.

## Architecture

```text
Frontend / FastAPI backend
          |
          v
       DRAgent
          |
          v
  NAT workflow.yaml
     |          |
     v          v
DataRobot LLM  MCP server
```

DRAgent provides asynchronous execution, streaming responses, A2A endpoints, and the
deployment interface consumed by the application backend. NAT builds the functions,
function groups, authentication providers, and top-level workflow from YAML.

## File structure

```text
agent/
├── agent/
│   ├── __init__.py       # Package exports
│   ├── config.py         # Runtime and deployment configuration
│   └── register.py       # NAT plugin registrations, headers, and telemetry
├── tests/
│   ├── test_agent.py
│   └── test_nat_runtime.py
├── workflow.yaml         # DRAgent/NAT workflow
├── pyproject.toml        # Dependencies and nat.plugins entry point
├── Taskfile.yml          # Development commands
└── uv.lock               # Locked dependencies
```

The `nat.plugins` entry point in `pyproject.toml` imports `agent.register` during NAT
startup. `workflow.yaml` remains at the Agent component root so the local server, CLI, and
deployed runtime all load the same configuration.

## Workflow

The current top-level workflow is a `per_user_tool_calling_agent`. It has two execution
paths:

1. Manufacturing conditions: call `predict_realtime` once, classify the quality risk, and
   search only for warning or high-risk outcomes.
2. Existing alerts with `search_only`: do not call `predict_realtime`; call `search_agent`
   once and combine the retrieved evidence with the alert details.

The `search_agent` is also a NAT tool-calling workflow. It can use MCP search tools and the
built-in Wikipedia function declared in `workflow.yaml`.

### Required YAML sections

| Section | Purpose |
|---|---|
| `general.front_end` | Configures `dragent_fastapi` and A2A metadata. |
| `functions` | Declares the search sub-agent and built-in functions. |
| `function_groups` | Connects the Agent to the MCP server. |
| `authentication` | Configures authentication used by external clients. |
| `llms` | Selects the DataRobot LLM component. |
| `workflow` | Defines top-level tools, routing rules, and response format. |

Every entry in `tool_names` must exist under `functions` or `function_groups`.

## MCP integration

The Agent does not import MCP server code. NAT creates a streamable HTTP client from the
`datarobot_mcp_client` function group:

```yaml
function_groups:
  mcp_tools:
    _type: datarobot_mcp_client
```

`agent/register.py` forwards the optional Tavily runtime credential through the client's
public `custom_headers` API. Authentication and MCP endpoint selection are supplied through
runtime parameters.

For server-side tool implementation, see [MCP server](../mcp-server.md).

## Configuration

`agent/agent/config.py` loads settings from environment variables, runtime parameters,
`.env`, file secrets, and Pulumi outputs. Common values include:

| Variable | Purpose |
|---|---|
| `LLM_DEPLOYMENT_ID` | DataRobot LLM deployment to use when configured. |
| `LLM_DEFAULT_MODEL` | Default model identifier. |
| `USE_DATAROBOT_LLM_GATEWAY` | Routes LLM calls through the DataRobot gateway. |
| `MCP_DEPLOYMENT_ID` | Co-deployed MCP server deployment ID. |
| `EXTERNAL_MCP_URL` | External MCP endpoint override. |
| `TAVILY_API_KEY` | Optional search credential forwarded to the MCP server. |
| `AGENT_PORT` | Local DRAgent port; defaults to `8842`. |

Never place credentials in `workflow.yaml`, Python source, or frontend code.

## Development

Install dependencies:

```shell
dr task run agent:install
```

Run lint and tests:

```shell
dr task run agent:lint
dr task run agent:test
```

Validate the NAT configuration:

```shell
cd agent
uv run nat validate --config_file workflow.yaml
```

Start the full application:

```shell
dr run dev
```

Start only the Agent server:

```shell
dr run agent:dev
```

Execute the local workflow in-process:

```shell
dr task run agent:cli -- -- execute --user_prompt "Your prompt"
```

Execute a deployed Agent:

```shell
dr task run agent:cli -- -- execute-deployment \
  --user_prompt "Your prompt" \
  --deployment_id <deployment_id>
```

## Testing and evaluation

Unit tests verify workflow routing, DRAgent startup commands, runtime credential forwarding,
and configuration compatibility. For LLM-based quality evaluation, use the in-process
DRAgent helper described in [Local evaluation](./evaluation.md). This exercises the same
`workflow.yaml` without relying on a removed compatibility adapter.

## Related documentation

- [NAT workflow guide](./frameworks/nat.md)
- [Local evaluation](./evaluation.md)
- [Debugging](./debugging.md)
- [Agent-to-Agent](./agent2agent.md)
- [A2A authentication](./agent2agent-auth.md)
