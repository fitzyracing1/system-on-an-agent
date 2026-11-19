"""Load add-ons from a Python file, a directory, or entry points."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType
from typing import Any

from soa.addons.interface import KNOWN_HOOKS, AddonManifest

try:  # Python 3.10+
    from importlib.metadata import entry_points
except ImportError:  # pragma: no cover
    from importlib_metadata import entry_points  # type: ignore


class AddonError(RuntimeError):
    """Raised when an add-on cannot be loaded or is invalid."""


def _has_hook(obj: Any, name: str) -> bool:
    return callable(getattr(obj, name, None))


class AddonLoader:
    """Discover and keep loaded add-ons, and fire their hooks."""

    def __init__(self) -> None:
        self._addons: list[Any] = []

    def add(self, addon: Any) -> Any:
        _validate(addon)
        self._addons.append(addon)
        return addon

    def load_from_path(self, path: str | Path) -> Any:
        addon = load_addon(path)
        return self.add(addon)

    def load_from_entry_points(self, group: str = "soa.addons") -> list[Any]:
        loaded: list[Any] = []
        selected = entry_points()
        try:
            entries = selected.select(group=group)
        except AttributeError:  # pragma: no cover - very old importlib
            entries = [ep for ep in selected.get(group, [])]
        for entry in entries:
            self.add(entry.load()())
            loaded.append(self._addons[-1])
        return loaded

    def list(self) -> list[Any]:
        return list(self._addons)

    def names(self) -> list[str]:
        return [addon.manifest.name for addon in self._addons]

    def fire_before_plan(self, plan: Any, context: Any) -> Any:
        return self._pipe(0, "before_plan", plan, context)

    def fire_after_plan(self, plan: Any, report: Any, context: Any) -> Any:
        return self._pipe(1, "after_plan", plan, report, context)

    def fire_before_step(self, step: Any, context: Any) -> Any:
        return self._pipe(0, "before_step", step, context)

    def fire_after_step(self, step: Any, result: Any, context: Any) -> Any:
        return self._pipe(1, "after_step", step, result, context)

    def fire_on_error(self, step: Any, error: BaseException, context: Any) -> None:
        for addon in self._addons:
            fn = getattr(addon, "on_error", None)
            if callable(fn):
                fn(step, error, context)

    def _pipe(self, index: int, hook: str, *args: Any) -> Any:
        if hook not in KNOWN_HOOKS:
            raise AddonError(f"unknown hook: {hook}")
        values = list(args)
        for addon in self._addons:
            fn = getattr(addon, hook, None)
            if not callable(fn):
                continue
            result = fn(*values)
            if result is not None:
                values[index] = result
        return values[index]

    def __len__(self) -> int:
        return len(self._addons)


def load_addon(path: str | Path) -> Any:
    """Load a single add-on from a Python file or a directory.

    A directory is expected to contain ``soa_addon.py`` or ``addon.py``.
    The module must expose either an ``Addon`` class, a ``create_addon()``
    factory, or a ready-made ``addon`` instance.
    """
    target = Path(path)
    if not target.exists():
        raise AddonError(f"add-on path does not exist: {path}")
    if target.is_dir():
        for name in ("soa_addon.py", "addon.py"):
            candidate = target / name
            if candidate.is_file():
                target = candidate
                break
        else:
            raise AddonError(
                f"add-on directory needs soa_addon.py or addon.py: {path}"
            )
    module = _import_path(target)
    addon = _instantiate(module)
    _validate(addon)
    return addon


def _import_path(file_path: Path) -> ModuleType:
    module_name = f"soa_addon_{file_path.stem}_{abs(hash(file_path.resolve()))}"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise AddonError(f"cannot import add-on: {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 - surface import errors as AddonError
        raise AddonError(f"add-on failed to import: {exc}") from exc
    return module


def _instantiate(module: ModuleType) -> Any:
    if hasattr(module, "create_addon") and callable(module.create_addon):
        return module.create_addon()
    if hasattr(module, "addon") and module.addon is not None:
        return module.addon
    if hasattr(module, "Addon") and callable(module.Addon):
        return module.Addon()
    raise AddonError(
        "add-on module must define Addon, create_addon(), or addon"
    )


def _validate(addon: Any) -> None:
    manifest = getattr(addon, "manifest", None)
    if not isinstance(manifest, AddonManifest):
        raise AddonError("add-on must expose an AddonManifest as manifest")
    declared = list(manifest.hooks)
    missing = [hook for hook in declared if not _has_hook(addon, hook)]
    if missing:
        raise AddonError(
            f"add-on {manifest.name!r} declares hooks it does not implement: "
            + ", ".join(missing)
        )


def maybe_paths(paths: Iterable[str | Path] | None) -> list[Path]:
    return [Path(p) for p in (paths or [])]
