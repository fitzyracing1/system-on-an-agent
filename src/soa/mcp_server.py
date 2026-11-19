"""Model Context Protocol (MCP) server over stdio for a System on an Agent.

The server speaks newline-delimited JSON-RPC 2.0 on stdin/stdout, as the
MCP stdio transport requires. It has no third-party dependencies and opens
no network sockets: everything runs in-process against one ``System``.

Tools exposed (all backed by the real planner, memory, skills, and bus):

- ``plan_goal``        plan a goal with the rule-based planner, without running it
- ``run_goal``         plan and run a goal on the bus, returning the run report
- ``memory_remember``  store a fact in long-term memory
- ``memory_recall``    look up facts in long-term memory
- ``list_skills``      list the skill library
- ``run_skill``        run one named skill through the bus
- ``list_connectors``  list the registered connectors
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import IO, Any

from soa import __version__
from soa.system import System, _jsonable
from soa.types import Message

SERVER_NAME = "system-on-an-agent"
# Newest first. The handshake picks the client's version when we support it.
SUPPORTED_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")

INSTRUCTIONS = (
    "System on an Agent: a rule-based planner, memory, skills, and connectors in one agent. "
    "Goal forms the planner understands: 'echo hello', 'remember <fact>', 'recall <query>', "
    "'read <path>', 'write <text> to <path>', 'list skills', 'list connectors'. "
    "Join steps with 'then'. File paths are confined to the server's file root."
)

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class ToolInputError(ValueError):
    """Raised when tool arguments are missing or have the wrong type."""


def _str_arg(args: dict[str, Any], key: str, *, required: bool = True, default: str = "") -> str:
    value = args.get(key, None)
    if value is None:
        if required:
            raise ToolInputError(f"missing required argument: {key}")
        return default
    if not isinstance(value, str):
        raise ToolInputError(f"argument {key} must be a string")
    return value


def _tool(
    name: str,
    title: str,
    description: str,
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
    *,
    read_only: bool,
    destructive: bool = False,
    idempotent: bool = False,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return {
        "name": name,
        "title": title,
        "description": description,
        "inputSchema": schema,
        "annotations": {
            "title": title,
            "readOnlyHint": read_only,
            "destructiveHint": destructive,
            "idempotentHint": idempotent,
            "openWorldHint": False,
        },
    }


TOOLS: list[dict[str, Any]] = [
    _tool(
        "plan_goal",
        "Plan a goal",
        "Plan a goal with the System on an Agent planner and return the steps without "
        "running them.",
        {"goal": {"type": "string", "description": "The goal, e.g. 'echo hi then remember hi'."}},
        ["goal"],
        read_only=True,
        idempotent=True,
    ),
    _tool(
        "run_goal",
        "Run a goal",
        "Plan a goal and run every step on the bus (memory, skills, echo and file "
        "connectors). Returns the plan, each step result, and the output. File writes are "
        "confined to the server's file root.",
        {"goal": {"type": "string", "description": "The goal to plan and run."}},
        ["goal"],
        read_only=False,
        destructive=True,
    ),
    _tool(
        "memory_remember",
        "Remember a fact",
        "Store a fact in long-term memory.",
        {
            "fact": {"type": "string", "description": "The fact to store."},
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional tags that recall also matches.",
            },
        },
        ["fact"],
        read_only=False,
    ),
    _tool(
        "memory_recall",
        "Recall facts",
        "Look up facts in long-term memory by case-insensitive substring. An empty query "
        "returns every fact.",
        {"query": {"type": "string", "description": "Text to search for. Optional."}},
        read_only=True,
        idempotent=True,
    ),
    _tool(
        "list_skills",
        "List skills",
        "List the skills in the skill library with their descriptions and parameters.",
        read_only=True,
        idempotent=True,
    ),
    _tool(
        "run_skill",
        "Run a skill",
        "Run one named skill through the bus. Use list_skills for names and parameters, "
        "e.g. name='echo', args={'text': 'hi'}.",
        {
            "name": {"type": "string", "description": "The skill name."},
            "args": {
                "type": "object",
                "description": "Keyword arguments for the skill.",
                "additionalProperties": True,
            },
        },
        ["name"],
        read_only=False,
        destructive=True,
    ),
    _tool(
        "list_connectors",
        "List connectors",
        "List the registered connectors and their kinds.",
        read_only=True,
        idempotent=True,
    ),
]


class MCPServer:
    """A minimal MCP server exposing a ``System`` as tools."""

    def __init__(self, system: System) -> None:
        self.system = system
        self.initialized = False
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "plan_goal": self._plan_goal,
            "run_goal": self._run_goal,
            "memory_remember": self._memory_remember,
            "memory_recall": self._memory_recall,
            "list_skills": self._list_skills,
            "run_skill": self._run_skill,
            "list_connectors": self._list_connectors,
        }

    # ------------------------------------------------------------------ tools

    def _plan_goal(self, args: dict[str, Any]) -> dict[str, Any]:
        goal = _str_arg(args, "goal")
        plan = self.system.planner.plan(goal, self.system.skills.names())
        return {
            "goal": plan.goal,
            "source": plan.source,
            "steps": [
                {"action": s.action, "args": _jsonable(s.args), "description": s.description}
                for s in plan.steps
            ],
        }

    def _run_goal(self, args: dict[str, Any]) -> dict[str, Any]:
        report = self.system.run(_str_arg(args, "goal"))
        return report.as_dict()

    def _memory_remember(self, args: dict[str, Any]) -> dict[str, Any]:
        fact = _str_arg(args, "fact")
        if not fact.strip():
            raise ToolInputError("fact must not be empty")
        tags = args.get("tags") or []
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            raise ToolInputError("tags must be a list of strings")
        stored = self.system.memory.remember(fact, tags)
        return {
            "stored": stored.text,
            "tags": list(stored.tags),
            "count": len(self.system.memory.long_term),
        }

    def _memory_recall(self, args: dict[str, Any]) -> dict[str, Any]:
        query = _str_arg(args, "query", required=False)
        hits = self.system.memory.recall(query)
        return {"query": query, "facts": [{"text": f.text, "tags": list(f.tags)} for f in hits]}

    def _list_skills(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "skills": [
                {"name": s.name, "description": s.description, "parameters": list(s.parameters)}
                for s in self.system.skills.list()
            ]
        }

    def _run_skill(self, args: dict[str, Any]) -> dict[str, Any]:
        name = _str_arg(args, "name")
        skill_args = args.get("args") or {}
        if not isinstance(skill_args, dict):
            raise ToolInputError("args must be an object")
        if not self.system.skills.has(name):
            raise ToolInputError(f"unknown skill: {name}")
        payload = {str(k): v for k, v in skill_args.items() if k != "name"}
        result = self.system.bus.dispatch(Message("skill", "run", {"name": name, **payload}))
        return {
            "ok": result.ok,
            "data": _jsonable(result.data),
            "error": result.error,
            "action": result.action,
        }

    def _list_connectors(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "connectors": [{"name": c.name, "kind": c.kind} for c in self.system.connectors.list()]
        }

    def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Run a tool and return an MCP ``CallToolResult``."""
        handler = self._handlers[name]
        try:
            data = handler(args)
        except ToolInputError as exc:
            return _tool_error(str(exc))
        except Exception as exc:  # noqa: BLE001 - report any core failure as a tool error
            return _tool_error(f"{type(exc).__name__}: {exc}")
        is_error = data.get("ok") is False
        return {
            "content": [{"type": "text", "text": json.dumps(data, indent=2)}],
            "structuredContent": data,
            "isError": is_error,
        }

    # --------------------------------------------------------------- protocol

    def handle(self, message: Any) -> dict[str, Any] | None:
        """Handle one decoded JSON-RPC message. Returns a response or ``None``."""
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _error(None, INVALID_REQUEST, "invalid JSON-RPC message")
        method = message.get("method")
        msg_id = message.get("id")
        is_request = "id" in message
        if not isinstance(method, str):
            # A response to a server request (we send none) or garbage: ignore responses.
            if is_request and ("result" in message or "error" in message):
                return None
            return _error(msg_id, INVALID_REQUEST, "missing method")
        params = message.get("params") or {}
        if not isinstance(params, dict):
            if not is_request:
                return None
            return _error(msg_id, INVALID_PARAMS, "params must be an object")
        if not is_request:
            if method == "notifications/initialized":
                self.initialized = True
            return None
        try:
            result = self._dispatch(method, params)
        except _RPCError as exc:
            return _error(msg_id, exc.code, exc.message)
        except Exception as exc:  # noqa: BLE001
            return _error(msg_id, INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def _dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            requested = params.get("protocolVersion")
            version = (
                requested
                if requested in SUPPORTED_PROTOCOL_VERSIONS
                else SUPPORTED_PROTOCOL_VERSIONS[0]
            )
            return {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": SERVER_NAME,
                    "title": "System on an Agent",
                    "version": __version__,
                },
                "instructions": INSTRUCTIONS,
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": TOOLS}
        if method == "tools/call":
            name = params.get("name")
            if not isinstance(name, str) or name not in self._handlers:
                raise _RPCError(INVALID_PARAMS, f"unknown tool: {name}")
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict):
                raise _RPCError(INVALID_PARAMS, "arguments must be an object")
            return self.call_tool(name, arguments)
        raise _RPCError(METHOD_NOT_FOUND, f"method not found: {method}")

    def serve(self, stdin: IO[bytes] | None = None, stdout: IO[bytes] | None = None) -> int:
        """Serve newline-delimited JSON-RPC until stdin closes."""
        reader = stdin or sys.stdin.buffer
        writer = stdout or sys.stdout.buffer
        for raw in reader:
            line = raw.strip()
            if not line:
                continue
            try:
                message = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                response: dict[str, Any] | None = _error(None, PARSE_ERROR, "parse error")
            else:
                response = self.handle(message)
            if response is not None:
                writer.write(json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n")
                writer.flush()
        return 0


class _RPCError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _tool_error(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": True}


def serve(system: System) -> int:
    """Serve ``system`` over stdio.

    stdout carries only protocol messages, so anything else that prints
    (an add-on, say) is redirected to stderr while the server runs.
    """
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    saved = sys.stdout
    sys.stdout = sys.stderr
    try:
        return MCPServer(system).serve(stdin, stdout)
    finally:
        sys.stdout = saved
