"""MCP server that lets Claude (Desktop / Claude Code) send TripPilot trips to Google My Maps.

It runs on your Mac and drives your own signed-in Chrome profile via mymaps_sync.py.
Register it in your MCP client, for example in Claude Code:

    claude mcp add trippilot-mymaps -- /ABS/PATH/.venv/bin/python /ABS/PATH/automation/mcp_server.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

try:  # mcp SDK 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp SDK 1.x
    from mcp.server.fastmcp import FastMCP as _Server

ROOT = Path(__file__).resolve().parent.parent
SYNC = Path(__file__).resolve().parent / "mymaps_sync.py"
sys.path.insert(0, str(ROOT))

server = _Server("trippilot-mymaps")


def _run(*args: str, timeout: int = 600) -> dict:
    """Playwright's sync API can't run inside the server's event loop, so use a child process."""
    proc = subprocess.run([sys.executable, str(SYNC), "--json", *args],
                          capture_output=True, text=True, timeout=timeout)
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"ok": False, "message": (proc.stderr or proc.stdout)[-800:]}


@server.tool()
def mymaps_check_login() -> dict:
    """Check whether the local Chrome profile is signed in to Google My Maps."""
    return _run("check")


@server.tool()
def mymaps_login() -> dict:
    """Open a Chrome window on this Mac so the user can sign in to Google once (waits up to 5 minutes)."""
    return _run("login", timeout=360)


@server.tool()
def send_csv_to_mymaps(csv_path: str, title: str) -> dict:
    """Create a Google My Map from a TripPilot CSV export, grouped by category.
    Returns the map URL, how many places were placed, and any that were not."""
    return _run("import", csv_path, "--title", title)


@server.tool()
def send_plan_to_mymaps(plan_json_path: str, destination: str, title: str) -> dict:
    """Create a Google My Map from a TripPilot plan JSON download (Download plan · JSON)."""
    from agent import to_mymaps_csv

    plan = json.loads(Path(plan_json_path).expanduser().read_text(encoding="utf-8"))
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(to_mymaps_csv(plan, destination))
    return _run("import", f.name, "--title", title)


if __name__ == "__main__":
    server.run()
