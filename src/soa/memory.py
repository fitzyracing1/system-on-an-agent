"""Memory: working storage and long-term facts."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Fact:
    """A long-term memory entry."""

    text: str
    tags: tuple[str, ...] = ()


class WorkingMemory:
    """Short-lived key-value store for the current run."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def delete(self, key: str) -> bool:
        return self._store.pop(key, _MISSING) is not _MISSING

    def clear(self) -> None:
        self._store.clear()

    def items(self) -> dict[str, Any]:
        return dict(self._store)

    def __contains__(self, key: str) -> bool:
        return key in self._store

    def __len__(self) -> int:
        return len(self._store)


_MISSING = object()


class LongTermMemory:
    """Durable facts, kept in memory and optionally persisted as JSON."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else None
        self._facts: list[Fact] = []
        if self._path and self._path.exists():
            self._load()

    def remember(self, text: str, tags: Iterable[str] = ()) -> Fact:
        fact = Fact(text=text.strip(), tags=tuple(tags))
        if fact.text:
            self._facts.append(fact)
            self._save()
        return fact

    def recall(self, query: str) -> list[Fact]:
        needle = query.strip().lower()
        if not needle:
            return list(self._facts)
        hits = []
        for fact in self._facts:
            hay = " ".join((fact.text, *fact.tags)).lower()
            if needle in hay:
                hits.append(fact)
        return hits

    def all_facts(self) -> list[Fact]:
        return list(self._facts)

    def clear(self) -> None:
        self._facts.clear()
        self._save()

    def __len__(self) -> int:
        return len(self._facts)

    def _load(self) -> None:
        assert self._path is not None
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        self._facts = [
            Fact(text=item["text"], tags=tuple(item.get("tags") or ()))
            for item in raw
        ]

    def _save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [{"text": f.text, "tags": list(f.tags)} for f in self._facts]
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@dataclass
class Memory:
    """Storage for a System on an Agent: working memory plus long-term facts."""

    working: WorkingMemory = field(default_factory=WorkingMemory)
    long_term: LongTermMemory = field(default_factory=LongTermMemory)

    def remember(self, text: str, tags: Iterable[str] = ()) -> Fact:
        return self.long_term.remember(text, tags)

    def recall(self, query: str) -> list[Fact]:
        return self.long_term.recall(query)
