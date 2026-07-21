# Debugging the NAT Agent

The local Agent runs on DRAgent. NAT loads `agent/workflow.yaml` and imports
`agent.register` through the `nat.plugins` entry point.

## Prerequisites

- Run `dr start` so the project `.env` and virtual environment exist.
- Configure `DATAROBOT_API_TOKEN`, `DATAROBOT_ENDPOINT`, and required LLM/MCP values.
- Install dependencies with `dr task run agent:install`.

## Validate configuration

Before debugging execution, validate the workflow schema:

```shell
cd agent
uv run nat validate --config_file workflow.yaml
```

## Run locally

Start the DRAgent server:

```shell
dr run agent:dev
```

The default address is `http://localhost:8842`. The Taskfile runs:

```shell
nat dragent serve --config_file workflow.yaml --reload true --port 8842
```

For a single in-process execution, no server is needed:

```shell
task agent:cli -- execute --user_prompt "Your prompt"
```

Query a deployment:

```shell
task agent:cli -- execute-deployment \
  --user_prompt "Your prompt" \
  --deployment_id <deployment_id>
```

## VS Code

The repository launch configuration starts the NAT console script under `debugpy` with
these arguments:

```text
dragent serve --config_file workflow.yaml --reload false --port 8842
```

1. Select `agent/.venv/bin/python` as the interpreter.
2. Put breakpoints in `agent/agent/register.py`, custom tool modules, or the installed
   `datarobot_genai`/`nat` code.
3. Select **Python Debugger: Agent** and press **F5**.
4. Send a request from another terminal.

`justMyCode` is disabled so framework code can also be inspected. Auto-reload is disabled
for debugger stability; restart the launch configuration after code changes.

## PyCharm

The **Run Agent** configuration executes `agent/.venv/bin/nat` from the `agent/` working
directory with the same DRAgent arguments.

1. Select `agent/.venv/bin/python` as the project interpreter.
2. Add breakpoints in registration or tool code.
3. Start **Run Agent** with the debugger.
4. Send a CLI or HTTP request after the server is ready.

## Logging

Set the NAT log level before starting the server:

```shell
export NAT_LOG_LEVEL=DEBUG
dr run agent:dev
```

Supported values are `DEBUG`, `INFO`, `WARNING`, `ERROR`, and `CRITICAL`.

The workflow also has a `verbose` setting. Enable it temporarily when inspecting routing and
tool selection, but avoid logging credentials or raw authorization headers.

## Common issues

### Configuration does not load

- Confirm the working directory is `agent/`.
- Confirm `workflow.yaml` exists at the Agent component root.
- Run `nat validate` and fix the first schema error.

### MCP tools are unavailable

- Confirm `mcp_tools` is declared under `function_groups`.
- Confirm it appears in the relevant `tool_names` list.
- Check the MCP URL/deployment runtime parameter and authentication headers.

### Breakpoints are not hit

- Disable auto-reload while debugging so the code stays in the debugger process.
- Put breakpoints on code exercised by the selected routing branch.
- Wait until the DRAgent server reports that it is ready before sending the request.

### Import error

- Confirm `agent/pyproject.toml` contains the `nat.plugins` entry point.
- Re-run `dr task run agent:install` after changing package metadata.
- Use imports rooted at the inner Agent package, such as `from agent.tools import tool_name`.

### Empty or chunk-like output

Use the DRAgent CLI or `execute_dragent_inline_async` for aggregated results. Application
clients should consume DRAgent events and render text deltas rather than stringifying event
objects.

## Deployed Agent

Use the deployment activity logs and tracing views to inspect LLM calls, tool invocations,
and errors. Reproduce the prompt with `execute-deployment` before changing runtime
parameters.
