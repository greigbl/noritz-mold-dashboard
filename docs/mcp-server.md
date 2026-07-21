# MCP server

An MCP server is a utility that allows the agent to access tools.
The template is configured to automatically connect the agent with an MCP server both locally and in a deployed setting.
The MCP server in this template is provided by the [DataRobot MCP AF Component](https://github.com/datarobot-community/af-component-datarobot-mcp) (App Framework).

## Testing against remote servers

When testing locally, the MCP server connects to a local instance running at `http://localhost:9000` by default. The repository root README lists all development ports.
To modify the port, set the `MCP_SERVER_PORT` environment variable in your `.env` file.

## Google Drive and Tavily tools

Google Drive tools use the existing OAuth flow. Connect Google Drive from the
application Settings page first, then ask the agent to search or read files from
Google Drive. The agent can use the native `gdrive_find_contents` and
`gdrive_read_content` MCP tools when they are relevant.

Tavily tools use an API key. For this application, set `TAVILY_API_KEY`
in the project `.env`; deployment stores it as an Agent runtime credential. The
Agent forwards it to the MCP server as `x-tavily-api-key`, which is
accepted by the native `tavily_search`, `tavily_extract`, `tavily_map`, and
`tavily_crawl` tools.

If you connect an MCP client directly to the MCP server instead of going through
the Agent, pass the key in the MCP client headers:

```json
{
  "x-tavily-api-key": "${env:TAVILY_API_KEY}"
}
```

Older native Tavily tools also accepted `x-datarobot-tavily-api-key`; the
`x-tavily-api-key` form is used here because the current tool implementation
requires that header name.

To test against remote MCP servers:

1. Set the `MCP_DEPLOYMENT_ID` environment variable to test against a deployed MCP server in DataRobot.
2. Set the `EXTERNAL_MCP_URL` environment variable to connect to an external MCP server endpoint (for example: `https://example.com/mcp`).
  
  > [!NOTE]
  > DataRobot bearer tokens and OAuth context are not forwarded to external MCP servers.
  > To send custom headers, set the `EXTERNAL_MCP_HEADERS` environment variable to a JSON string (e.g., `'{"Authorization":"Bearer token123","X-Custom-Header":"value"}'`); it will be parsed using `json.loads()`.
  > To change the transport for MCP server, set the `EXTERNAL_MCP_TRANSPORT` environment variable to `sse` or `streamable-http` (default).

3. When running `dr run deploy`, the project automatically deploys the MCP server from your project, which takes precedence over any MCP servers configured via environment variables for testing purposes.
