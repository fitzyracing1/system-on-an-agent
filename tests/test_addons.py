from __future__ import annotations

from pathlib import Path

import pytest

from soa.addons import AddonError, AddonLoader, AddonManifest, HookContext, load_addon
from soa.planner import Step
from soa.system import System


def test_load_dummy_addon_from_directory(dummy_addon_path: Path):
    addon = load_addon(dummy_addon_path)
    assert addon.manifest.name == "dummy"
    assert "before_step" in addon.manifest.hooks


def test_load_dummy_addon_from_file(dummy_addon_path: Path):
    addon = load_addon(dummy_addon_path / "soa_addon.py")
    assert addon.manifest.version == "0.1.0"


def test_missing_path_and_empty_directory(tmp_path: Path):
    with pytest.raises(AddonError, match="does not exist"):
        load_addon(tmp_path / "missing.py")
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(AddonError, match="needs soa_addon.py"):
        load_addon(empty)


def test_module_without_addon_entry_is_rejected(tmp_path: Path):
    path = tmp_path / "addon.py"
    path.write_text("value = 1\n", encoding="utf-8")
    with pytest.raises(AddonError, match="must define"):
        load_addon(path)


def test_addon_without_manifest_is_rejected():
    class Bare:
        pass

    with pytest.raises(AddonError, match="AddonManifest"):
        AddonLoader().add(Bare())


def test_addon_declaring_unimplemented_hook_is_rejected():
    class Incomplete:
        manifest = AddonManifest(
            name="incomplete",
            version="0",
            hooks=("before_step",),
        )

    with pytest.raises(AddonError, match="does not implement"):
        AddonLoader().add(Incomplete())


def test_unknown_hook_in_manifest_is_rejected():
    with pytest.raises(ValueError, match="unknown add-on hooks"):
        AddonManifest(name="x", version="0", hooks=("before_lunch",))


def test_import_error_is_wrapped(tmp_path: Path):
    path = tmp_path / "addon.py"
    path.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    with pytest.raises(AddonError, match="failed to import"):
        load_addon(path)


def test_create_addon_factory_is_used(tmp_path: Path):
    path = tmp_path / "soa_addon.py"
    path.write_text(
        "from soa.addons import AddonManifest\n"
        "class Widget:\n"
        "    manifest = AddonManifest(name='widget', version='1', hooks=())\n"
        "def create_addon():\n"
        "    return Widget()\n",
        encoding="utf-8",
    )
    addon = load_addon(path)
    assert addon.manifest.name == "widget"


def test_addon_instance_export_is_used(tmp_path: Path):
    path = tmp_path / "addon.py"
    path.write_text(
        "from soa.addons import AddonManifest\n"
        "class Addon:\n"
        "    manifest = AddonManifest(name='inst', version='1', hooks=())\n"
        "addon = Addon()\n",
        encoding="utf-8",
    )
    assert load_addon(path).manifest.name == "inst"


def test_hooks_fire_in_order_on_a_run(dummy_addon_path: Path, tmp_path: Path):
    loader = AddonLoader()
    addon = loader.load_from_path(dummy_addon_path)
    system = System(addons=loader, file_root=tmp_path)
    report = system.run("echo hello")
    assert report.ok is True
    assert report.output == "hello"
    assert [name for name, _ in addon.calls] == [
        "before_plan",
        "before_step",
        "after_step",
        "after_plan",
    ]


def test_before_step_can_replace_a_step(tmp_path: Path):
    class Rewrite:
        manifest = AddonManifest(
            name="rewrite",
            version="0",
            hooks=("before_step",),
        )

        def before_step(self, step, context):
            return Step(
                "connector.send",
                {"connector": "echo", "payload": "rewritten"},
                "rewritten",
            )

    loader = AddonLoader()
    loader.add(Rewrite())
    report = System(addons=loader, file_root=tmp_path).run("echo original")
    assert report.output == "rewritten"


def test_on_error_is_fired_for_a_raising_step(tmp_path: Path):
    class Probe:
        manifest = AddonManifest(
            name="probe",
            version="0",
            hooks=("on_error",),
        )
        calls: list[str] = []

        def on_error(self, step, error, context):
            self.calls.append(step.action)

    class BoomBus:
        def dispatch_step(self, action, args):
            raise RuntimeError("nope")

    loader = AddonLoader()
    probe = Probe()
    loader.add(probe)
    system = System(addons=loader, file_root=tmp_path)
    system.bus = BoomBus()  # type: ignore[assignment]
    report = system.run("echo hello")
    assert report.ok is False
    assert probe.calls == ["connector.send"]


def test_loader_names_and_entry_points_group_is_safe():
    loader = AddonLoader()
    assert loader.names() == []
    assert loader.load_from_entry_points("soa.addons.missing") == []


def test_hook_context_carries_the_goal():
    context = HookContext(goal="echo hi")
    assert context.goal == "echo hi"
    assert context.extras == {}
