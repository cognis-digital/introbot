"""INTROBOT MCP server — exposes scan() as an MCP tool for Cognis.Studio."""
from __future__ import annotations
from introbot.core import scan, to_json

def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-introbot[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print("Install the MCP extra: pip install 'cognis-introbot[mcp]'")
        return 1
    app = FastMCP("introbot")

    @app.tool()
    def introbot_scan(target: str) -> str:
        """Find warm-intro paths through your team's combined network graph and draft double-opt-in intro requests from a single contacts manifest.. Returns JSON findings."""
        return to_json(scan(target))

    app.run()
    return 0
