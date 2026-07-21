# Agent Development Instructions

This project uses a NAT (NVIDIA NeMo Agent Toolkit) workflow served exclusively by DRAgent.
The runtime is declarative: orchestration, LLMs, sub-agents, and MCP tools are configured in
`workflow.yaml`. Python startup registrations belong in `agent/register.py`.

## Dependencies

After changing Agent Python code or dependencies, run:

```shell
dr task run agent:install
```

When a custom Docker context is present, dependency changes can trigger a full execution
environment rebuild during deployment.

## File structure

```text
agent/
├── agent/
│   ├── __init__.py       # Package exports
│   ├── config.py         # Runtime configuration
│   └── register.py       # NAT plugin startup registrations and instrumentation
├── tests/                # Agent tests
├── workflow.yaml         # DRAgent/NAT workflow definition
├── pyproject.toml        # Dependencies and nat.plugins entry point
└── Taskfile.yml          # Install, lint, test, serve, and CLI tasks
```

The `nat.plugins` entry point in `pyproject.toml` loads `agent.register` when NAT starts.
Do not add a second front server or a parallel agent entry point.

## Workflow configuration

`workflow.yaml` must define these sections as needed:

- `general.front_end`: the `dragent_fastapi` server and optional A2A metadata.
- `functions`: NAT functions and sub-agents.
- `function_groups`: MCP and optional remote A2A clients.
- `authentication`: authentication providers used by function groups.
- `llms`: DataRobot LLM components or routers.
- `workflow`: the top-level NAT workflow and its `tool_names`.

Every name in `workflow.tool_names` must be declared under `functions` or
`function_groups`. Keep all orchestration and routing rules in `workflow.yaml`.

## MCP tools

The MCP server is an independent service. Connect through the NAT function group:

```yaml
function_groups:
  mcp_tools:
    _type: datarobot_mcp_client
```

Add `mcp_tools` to the relevant workflow's `tool_names`. Do not import implementation code
from `mcp_server/` into the Agent package.

## Custom NAT tools

Register custom Python tools from `agent/register.py` using `nat_tool`, then add a matching
entry under `functions` and include the name in `workflow.tool_names`. Use
`typing.Annotated` to describe tool parameters. See
[`docs/agent/frameworks/nat.md`](../docs/agent/frameworks/nat.md) for a complete example.

## Testing

When an Agent behavior changes, add or update tests under `agent/tests` first. Run:

```shell
dr task run agent:lint
dr task run agent:test
```

Validate the NAT configuration directly when editing `workflow.yaml`:

```shell
uv run nat validate --config_file workflow.yaml
```

## Local execution

Start the DRAgent server:

```shell
dr run agent:dev
```

Run the workflow in-process:

```shell
dr task run agent:cli -- -- execute --user_prompt "Agent-specific prompt"
```

Validate a deployed Agent:

```shell
dr task run agent:cli -- -- execute-deployment \
  --user_prompt "Agent-specific prompt" \
  --deployment_id <deployment_id>
```

The deployment is successful only when the command returns an Agent response without an
error.
