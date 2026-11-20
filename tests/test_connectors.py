from __future__ import annotations

from pathlib import Path

import pytest

from soa.connectors import (
    ConnectorRegistry,
    EchoConnector,
    FileConnector,
    FileConnectorError,
)


def test_echo_connector_returns_payload_and_records_it():
    echo = EchoConnector()
    result = echo.send("hello from system on an agent")
    assert result.ok is True
    assert result.data == "hello from system on an agent"
    assert echo.sent == ["hello from system on an agent"]


def test_file_connector_read_write_list(tmp_path: Path):
    files = FileConnector(root=tmp_path)
    written = files.write("notes.txt", "payload")
    assert written == tmp_path / "notes.txt"
    assert files.read("notes.txt") == "payload"
    assert "notes.txt" in files.list(".")
    result = files.send({"method": "read", "path": "notes.txt"})
    assert result.ok is True
    assert result.data == "payload"
    listed = files.send({"method": "list", "path": "."})
    assert "notes.txt" in listed.data


def test_file_connector_rejects_path_escape(tmp_path: Path):
    files = FileConnector(root=tmp_path)
    with pytest.raises(FileConnectorError, match="escapes"):
        files.resolve("../outside.txt")
    result = files.send({"method": "read", "path": "../outside.txt"})
    assert result.ok is False
    assert "escapes" in result.error


def test_file_connector_unknown_method_and_bad_payload(tmp_path: Path):
    files = FileConnector(root=tmp_path)
    assert files.send({"method": "delete", "path": "x"}).ok is False
    assert files.send(123).ok is False


def test_file_connector_missing_directory(tmp_path: Path):
    files = FileConnector(root=tmp_path)
    result = files.call("list", path="nope")
    assert result.ok is False


def test_file_connector_send_string_path_reads(tmp_path: Path):
    files = FileConnector(root=tmp_path)
    (tmp_path / "a.txt").write_text("A", encoding="utf-8")
    assert files.send("a.txt").data == "A"


def test_connector_registry():
    registry = ConnectorRegistry([EchoConnector()])
    assert "echo" in registry
    assert registry.names() == ["echo"]
    assert registry.get("ECHO").name == "echo"
    with pytest.raises(ValueError, match="already registered"):
        registry.register(EchoConnector())
    registry.register(EchoConnector(name="echo-2"))
    assert len(registry) == 2
    with pytest.raises(KeyError, match="unknown connector"):
        registry.get("missing")


def test_file_connector_send_string_with_method(tmp_path: Path):
    files = FileConnector(root=tmp_path)
    (tmp_path / "a.txt").write_text("A", encoding="utf-8")
    assert files.send("a.txt", method="read").data == "A"
    written = files.send("b.txt", method="write", content="B")
    assert written.ok is True
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "B"
