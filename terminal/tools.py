from mcp.types import Tool

TOOLS = [
    Tool(
        name="create_terminal",
        description="Create a new persistent terminal session",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Unique name for the terminal"}
            },
            "required": ["name"],
        },
    ),
    Tool(
        name="list_terminals",
        description="List all active terminal sessions",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="terminal_status",
        description="Get metadata about a terminal session",
        inputSchema={
            "type": "object",
            "properties": {
                "terminal_id": {"type": "string", "description": "Terminal ID"}
            },
            "required": ["terminal_id"],
        },
    ),
    Tool(
        name="send_input",
        description="Send text/commands to a terminal's stdin",
        inputSchema={
            "type": "object",
            "properties": {
                "terminal_id": {"type": "string", "description": "Terminal ID"},
                "text": {"type": "string", "description": "Text to send (newline optional for commands)"},
            },
            "required": ["terminal_id", "text"],
        },
    ),
    Tool(
        name="read_output",
        description="Read incremental terminal output since a cursor position",
        inputSchema={
            "type": "object",
            "properties": {
                "terminal_id": {"type": "string", "description": "Terminal ID"},
                "since": {"type": "integer", "description": "Cursor offset to read from", "default": 0},
                "max_bytes": {"type": "integer", "description": "Maximum bytes to return"},
            },
            "required": ["terminal_id"],
        },
    ),
    Tool(
        name="send_signal",
        description="Send a signal (SIGINT, SIGTERM, SIGKILL) to a terminal's process group",
        inputSchema={
            "type": "object",
            "properties": {
                "terminal_id": {"type": "string", "description": "Terminal ID"},
                "signal": {
                    "type": "string",
                    "description": "Signal name",
                    "enum": ["SIGINT", "SIGTERM", "SIGKILL"],
                },
            },
            "required": ["terminal_id", "signal"],
        },
    ),
    Tool(
        name="kill_terminal",
        description="Destroy a terminal session and free its resources",
        inputSchema={
            "type": "object",
            "properties": {
                "terminal_id": {"type": "string", "description": "Terminal ID"}
            },
            "required": ["terminal_id"],
        },
    ),
    Tool(
        name="wait_for_output",
        description="Wait until a pattern appears in terminal output",
        inputSchema={
            "type": "object",
            "properties": {
                "terminal_id": {"type": "string", "description": "Terminal ID"},
                "pattern": {"type": "string", "description": "Pattern to wait for"},
                "timeout": {"type": "number", "description": "Timeout in seconds", "default": 30},
            },
            "required": ["terminal_id", "pattern"],
        },
    ),
    Tool(
        name="search_output",
        description="Search terminal history buffer for a query",
        inputSchema={
            "type": "object",
            "properties": {
                "terminal_id": {"type": "string", "description": "Terminal ID"},
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["terminal_id", "query"],
        },
    ),
    Tool(
        name="web_url",
        description="Get the web UI URL where terminal sessions can be viewed in a browser",
        inputSchema={"type": "object", "properties": {}},
    ),
]
