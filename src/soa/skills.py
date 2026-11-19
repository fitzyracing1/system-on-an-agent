"""Skill library: reusable named procedures stored alongside memory."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from soa.types import Result

SkillHandler = Callable[..., Any]


@dataclass(frozen=True)
class Skill:
    """A named, reusable procedure the planner can run."""

    name: str
    description: str
    handler: SkillHandler
    parameters: tuple[str, ...] = ()


class SkillError(KeyError):
    """Raised when a skill is missing or already registered."""


class SkillLibrary:
    """Registry of named skills."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill, *, overwrite: bool = False) -> None:
        key = skill.name.strip().lower()
        if not key:
            raise ValueError("skill name must not be empty")
        if key in self._skills and not overwrite:
            raise SkillError(f"skill already registered: {skill.name}")
        self._skills[key] = skill

    def get(self, name: str) -> Skill:
        key = name.strip().lower()
        try:
            return self._skills[key]
        except KeyError as exc:
            raise SkillError(f"unknown skill: {name}") from exc

    def has(self, name: str) -> bool:
        return name.strip().lower() in self._skills

    def list(self) -> list[Skill]:
        return [self._skills[k] for k in sorted(self._skills)]

    def names(self) -> list[str]:
        return [skill.name for skill in self.list()]

    def run(self, name: str, **kwargs: Any) -> Result:
        skill = self.get(name)
        try:
            data = skill.handler(**kwargs)
        except TypeError:
            # Allow a positional "text" fallback for simple one-argument skills.
            if "text" in kwargs and len(kwargs) == 1:
                data = skill.handler(kwargs["text"])
            else:
                raise
        if isinstance(data, Result):
            return data
        return Result(ok=True, data=data, action=f"skill.{skill.name}")

    def __len__(self) -> int:
        return len(self._skills)


def builtin_skills() -> list[Skill]:
    """Core skills that ship with the default system.

    These are thin wrappers around bus channels so the planner can
    address them either as skills or as direct bus messages.
    """

    def _echo(text: str = "", **_: Any) -> str:
        return str(text)

    def _remember(text: str = "", fact: str = "", **_: Any) -> str:
        return fact or text

    def _recall(query: str = "", text: str = "", **_: Any) -> str:
        return query or text

    def _read_file(path: str = "", **_: Any) -> dict[str, str]:
        return {"path": path, "method": "read"}

    def _write_file(path: str = "", content: str = "", **_: Any) -> dict[str, str]:
        return {"path": path, "content": content, "method": "write"}

    return [
        Skill("echo", "Send text through the echo (mock) connector.", _echo, ("text",)),
        Skill("remember", "Store a fact in long-term memory.", _remember, ("text",)),
        Skill("recall", "Look up facts in long-term memory.", _recall, ("query",)),
        Skill("read_file", "Read a file through the file connector.", _read_file, ("path",)),
        Skill(
            "write_file",
            "Write a file through the file connector.",
            _write_file,
            ("path", "content"),
        ),
    ]
