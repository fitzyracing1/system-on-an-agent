"""In-process checks of the MCP JSON-RPC handling (no MCP SDK needed)."""

from __future__ import annotations

import io
import json
from pathlib import Path

from soa.mcp_server import SUPPORTED_PROTOCOL_VERSIONS, TOOLS, MCPServer
from soa.system import System


def _init(msg_id: int, version: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "method": "initialize",
        "params": {"protocolVersion": version},
    }


def make_server(tmp_path: Path) -> MCPServer:
    return MCPServer(System(file_root=tmp_path))


def test_initialize_negotiates_version(tmp_path: Path):
    server = make_server(tmp_path)
    ok = server.handle(_init(1, "2025-06-18"))
    assert ok["result"]["protocolVersion"] == "2025-06-18"
    unknown = server.handle(_init(2, "1999-01-01"))
    assert unknown["result"]["protocolVersion"] == SUPPORTED_PROTOCOL_VERSIONS[0]
    assert unknown["result"]["capabilities"] == {"tools": {"listChanged": False}}


def test_notifications_get_no_response(tmp_path: Path):
    server = make_server(tmp_path)
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert server.initialized is True


def test_errors(tmp_path: Path):
    server = make_server(tmp_path)
    missing = server.handle({"jsonrpc": "2.0", "id": 3, "method": "nope"})
    assert missing["error"]["code"] == -32601
    bad_tool = server.handle(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "rm_rf"}}
    )
    assert bad_tool["error"]["code"] == -32602
    assert server.handle("garbage")["error"]["code"] == -32600


def test_serve_reads_lines_and_reports_parse_errors(tmp_path: Path):
    server = make_server(tmp_path)
    lines = [
        b"not json\n",
        b"\n",
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode() + b"\n",
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).encode() + b"\n",
    ]
    out = io.BytesIO()
    assert server.serve(io.BytesIO(b"".join(lines)), out) == 0
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert replies[0]["error"]["code"] == -32700
    assert replies[1] == {"jsonrpc": "2.0", "id": 1, "result": {}}
    assert [t["name"] for t in replies[2]["result"]["tools"]] == [t["name"] for t in TOOLS]


def test_every_tool_has_annotations():
    for tool in TOOLS:
        annotations = tool["annotations"]
        assert annotations["openWorldHint"] is False
        assert isinstance(annotations["readOnlyHint"], bool)
