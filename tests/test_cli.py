from __future__ import annotations

import io
from pathlib import Path

from soa.cli import main
from soa.system import System


def run_cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def test_skills_list_includes_builtins():
    code, out, err = run_cli("skills", "list")
    assert code == 0
    assert err == ""
    assert "echo:" in out
    assert "remember:" in out


def test_connectors_list_includes_echo_and_file():
    code, out, err = run_cli("connectors", "list")
    assert code == 0
    assert "echo (mock)" in out
    assert "file (local-file)" in out


def test_run_echo_goal_end_to_end():
    code, out, err = run_cli("run", "echo hello from system on an agent")
    assert code == 0
    assert err == ""
    assert "goal: echo hello from system on an agent" in out
    assert "plan: 1 step (rules)" in out
    assert "ok: true" in out
    assert "output: hello from system on an agent" in out


def test_run_json_and_multi_step():
    code, out, err = run_cli("run", "echo hi then remember hi was said", "--json")
    assert code == 0
    assert err == ""
    assert '"ok": true' in out
    assert "hi was said" in out
    assert '"source": "rules"' in out


def test_run_with_dummy_addon(dummy_addon_path: Path):
    code, out, err = run_cli(
        "--addon",
        str(dummy_addon_path),
        "run",
        "echo hooked",
    )
    assert code == 0
    assert "output: hooked" in out
    assert err == ""


def test_bad_addon_path_exits_nonzero(tmp_path: Path):
    code, out, err = run_cli("--addon", str(tmp_path / "missing.py"), "run", "echo x")
    assert code == 2
    assert "does not exist" in err


def test_failed_run_returns_error_status(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, out, err = run_cli("run", "read missing.txt")
    assert code == 1
    assert "ok: false" in out


def test_system_remembers_across_steps(tmp_path: Path):
    system = System(file_root=tmp_path)
    first = system.run("remember rivers flow then recall rivers")
    assert first.ok is True
    assert first.results[1].data == "rivers flow"


def test_system_writes_and_reads_a_file(tmp_path: Path):
    system = System(file_root=tmp_path)
    report = system.run("write hello to notes.txt then read notes.txt")
    assert report.ok is True
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "hello"
    assert report.results[-1].data == "hello"


def test_memory_flag_persists_facts_between_runs(tmp_path: Path):
    store = tmp_path / "memory.json"
    code, out, err = run_cli("--memory", str(store), "run", "remember rivers flow")
    assert code == 0
    assert store.exists()
    code, out, err = run_cli("--memory", str(store), "run", "recall rivers")
    assert code == 0
    assert "rivers flow" in out


def test_failed_run_reports_the_steps_it_skipped(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, out, err = run_cli("run", "read missing.txt then echo never")
    assert code == 1
    assert "skipped: 1 step(s)" in out
