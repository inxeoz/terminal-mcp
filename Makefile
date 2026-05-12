.PHONY: run inspect dev install stop-inspector

install:
	pip install -e .

run:
	i4z-terminal-mcp

stop-inspector:
	@fuser -k 6277/tcp 2>/dev/null || true
	@fuser -k 6274/tcp 2>/dev/null || true

# Open MCP Inspector with no auth (local dev)
inspect: stop-inspector
	DANGEROUSLY_OMIT_AUTH=true npx @modelcontextprotocol/inspector i4z-terminal-mcp

dev: stop-inspector
	DANGEROUSLY_OMIT_AUTH=true npx @modelcontextprotocol/inspector i4z-terminal-mcp
