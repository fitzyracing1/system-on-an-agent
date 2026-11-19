"""Start the MCP server as a subprocess and drive it with the official MCP client."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest

mcp = pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

EXPECTED_TOOLS = {
    "plan_goal",
    "run_goal",
    "memory_remember",
    "memory_recall",
    "list_skills",
    "run_skill",
    "list_connectors",
}


def _field(obj: Any, *names: str) -> Any:
    """Read a field that is camelCase in mcp 1.x and snake_case in mcp 2.x."""
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    raise AttributeError(names)


def _structured(result: Any) -> Any:
    data = _field(result, "structuredContent", "structured_content")
    if data is None:
        data = json.loads(result.content[0].text)
    return data


def _is_error(result: Any) -> bool:
    return bool(_field(result, "isError", "is_error"))


def run_session(file_root: Path, body, *extra_args: str) -> Any:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "soa", "--file-root", str(file_root), *extra_args, "mcp"],
    )

    async def main() -> Any:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                return await body(session, init)

    return asyncio.run(asyncio.wait_for(main(), timeout=60))


def test_initialize_and_list_tools(tmp_path: Path):
    async def body(session, init):
        info = _field(init, "serverInfo", "server_info")
        tools = (await session.list_tools()).tools
        return info.name, info.version, tools

    name, version, tools = run_session(tmp_path, body)
    assert name == "system-on-an-agent"
    assert version == "0.1.0"
    assert {tool.name for tool in tools} == EXPECTED_TOOLS
    for tool in tools:
        assert tool.description
        schema = _field(tool, "inputSchema", "input_schema")
        assert schema["type"] == "object"


def test_plan_goal_does_not_run(tmp_path: Path):
    async def body(session, init):
        return await session.call_tool("plan_goal", {"goal": "write hi to a.txt then read a.txt"})

    result = run_session(tmp_path, body)
    assert not _is_error(result)
    data = _structured(result)
    assert data["source"] == "rules"
    assert len(data["steps"]) == 2
    assert not (tmp_path / "a.txt").exists()


def test_run_goal_writes_and_reads_inside_file_root(tmp_path: Path):
    async def body(session, init):
        return await session.call_tool(
            "run_goal", {"goal": "write hello to notes.txt then read notes.txt"}
        )

    result = run_session(tmp_path, body)
    assert not _is_error(result)
    data = _structured(result)
    assert data["ok"] is True
    assert data["results"][-1]["data"] == "hello"
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "hello"


def test_run_goal_cannot_escape_file_root(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()

    async def body(session, init):
        return await session.call_tool("run_goal", {"goal": "write x to ../escape.txt"})

    result = run_session(root, body)
    assert _is_error(result)
    assert _structured(result)["ok"] is False
    assert not (tmp_path / "escape.txt").exists()


def test_memory_round_trip_and_persistence(tmp_path: Path):
    memory_file = tmp_path / "memory.json"

    async def write(session, init):
        await session.call_tool("memory_remember", {"fact": "rivers flow", "tags": ["nature"]})
        return await session.call_tool("memory_recall", {"query": "nature"})

    data = _structured(run_session(tmp_path, write, "--memory-file", str(memory_file)))
    assert data["facts"] == [{"text": "rivers flow", "tags": ["nature"]}]

    async def read(session, init):
        return await session.call_tool("memory_recall", {"query": "rivers"})

    data = _structured(run_session(tmp_path, read, "--memory-file", str(memory_file)))
    assert [fact["text"] for fact in data["facts"]] == ["rivers flow"]


def test_skills_and_connectors(tmp_path: Path):
    async def body(session, init):
        skills = await session.call_tool("list_skills", {})
        echo = await session.call_tool("run_skill", {"name": "echo", "args": {"text": "hi"}})
        missing = await session.call_tool("run_skill", {"name": "nope"})
        connectors = await session.call_tool("list_connectors", {})
        return skills, echo, missing, connectors

    skills, echo, missing, connectors = run_session(tmp_path, body)
    names = {skill["name"] for skill in _structured(skills)["skills"]}
    assert {"echo", "remember", "recall", "read_file", "write_file"} <= names
    assert _structured(echo)["ok"] is True
    assert _structured(echo)["data"] == "hi"
    assert _is_error(missing)
    assert "unknown skill" in missing.content[0].text
    kinds = {c["name"]: c["kind"] for c in _structured(connectors)["connectors"]}
    assert kinds == {"echo": "mock", "file": "local-file"}


def test_bad_arguments_are_tool_errors(tmp_path: Path):
    async def body(session, init):
        return await session.call_tool("run_goal", {})

    result = run_session(tmp_path, body)
    assert _is_error(result)
    assert "missing required argument: goal" in result.content[0].text
