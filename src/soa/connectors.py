"""Connectors: pluggable input and output."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from soa.types import Result


@runtime_checkable
class Connector(Protocol):
    """A pluggable I/O surface the bus can call."""

    name: str
    kind: str

    def send(self, payload: Any, **kwargs: Any) -> Result:
        ...


@dataclass
class EchoConnector:
    """Mock connector that returns whatever it is sent."""

    name: str = "echo"
    kind: str = "mock"
    sent: list[Any] = field(default_factory=list)

    def send(self, payload: Any, **kwargs: Any) -> Result:
        self.sent.append(payload)
        return Result(ok=True, data=payload, action="connector.echo")


class FileConnectorError(ValueError):
    """Raised for unsafe or missing file-connector paths."""


@dataclass
class FileConnector:
    """Local file I/O, confined to a root directory."""

    root: Path = field(default_factory=lambda: Path.cwd())
    name: str = "file"
    kind: str = "local-file"

    def __post_init__(self) -> None:
        self.root = Path(self.root).resolve()

    def send(self, payload: Any, **kwargs: Any) -> Result:
        if isinstance(payload, str):
            method = kwargs.get("method", "read")
            return self.call(method, path=payload, **kwargs)
        if isinstance(payload, dict):
            data = {**payload, **kwargs}
            method = data.pop("method", "read")
            return self.call(method, **data)
        return Result(ok=False, error="file connector expected a path or dict payload")

    def call(self, method: str, **kwargs: Any) -> Result:
        try:
            if method == "read":
                return Result(ok=True, data=self.read(kwargs["path"]), action="connector.file.read")
            if method == "write":
                path = self.write(kwargs["path"], kwargs.get("content", ""))
                return Result(ok=True, data=str(path), action="connector.file.write")
            if method in {"list", "ls"}:
                listing = self.list(kwargs.get("path", "."))
                return Result(ok=True, data=listing, action="connector.file.list")
        except (OSError, FileConnectorError, KeyError) as exc:
            return Result(ok=False, error=str(exc), action=f"connector.file.{method}")
        return Result(ok=False, error=f"unknown file method: {method}")

    def resolve(self, path: str | Path) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (self.root / candidate).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise FileConnectorError(f"path escapes file connector root: {path}") from exc
        return resolved

    def read(self, path: str | Path) -> str:
        target = self.resolve(path)
        return target.read_text(encoding="utf-8")

    def write(self, path: str | Path, content: str) -> Path:
        target = self.resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def list(self, path: str | Path = ".") -> list[str]:
        target = self.resolve(path)
        if not target.exists():
            raise FileConnectorError(f"no such directory: {path}")
        if target.is_file():
            return [target.name]
        return sorted(p.name for p in target.iterdir())


class ConnectorRegistry:
    """Named set of connectors the bus can address."""

    def __init__(self, connectors: list[Connector] | None = None) -> None:
        self._items: dict[str, Connector] = {}
        for connector in connectors or []:
            self.register(connector)

    def register(self, connector: Connector, *, overwrite: bool = False) -> None:
        key = connector.name.strip().lower()
        if key in self._items and not overwrite:
            raise ValueError(f"connector already registered: {connector.name}")
        self._items[key] = connector

    def get(self, name: str) -> Connector:
        try:
            return self._items[name.strip().lower()]
        except KeyError as exc:
            raise KeyError(f"unknown connector: {name}") from exc

    def list(self) -> list[Connector]:
        return [self._items[k] for k in sorted(self._items)]

    def names(self) -> list[str]:
        return [connector.name for connector in self.list()]

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, name: str) -> bool:
        return name.strip().lower() in self._items
