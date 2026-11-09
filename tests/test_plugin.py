"""Run with Hermes's own Python: ~/.hermes/hermes-agent/venv/bin/python -m pytest tests"""
import importlib.util
import json
import os
import stat
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location("xscapes_plugin", ROOT / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def fake_xscapes(tmp_path, monkeypatch):
    """A stand-in xscapes that records its argv and stdin."""
    out = tmp_path / "calls"
    out.mkdir()
    exe = tmp_path / "xscapes"
    exe.write_text(
        "#!/bin/sh\n"
        f'f="{out}/$$"\n'
        'printf "%s\\n" "$*" > "$f.argv"\n'
        'cat > "$f.json"\n'
    )
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("XSCAPES_BIN", str(exe))
    return out


def wait_calls(out, n, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        done = [p for p in out.glob("*.json") if p.stat().st_size > 0]
        if len(done) >= n:
            time.sleep(0.1)
            return sorted(out.glob("*.json"))
        time.sleep(0.05)
    raise AssertionError(f"{len(list(out.glob('*.json')))} calls, want {n}")


class Ctx:
    def __init__(self):
        self.hooks = {}

    def register_hook(self, name, fn, **kw):
        self.hooks.setdefault(name, []).append(fn)


def test_registers_every_event_the_manifest_declares():
    mod = load()
    ctx = Ctx()
    mod.register(ctx)
    manifest = (ROOT / "plugin.yaml").read_text()
    declared = [l.strip()[2:] for l in manifest.splitlines() if l.strip().startswith("- ")]
    assert sorted(ctx.hooks) == sorted(declared) == sorted(mod.EVENTS)


def test_a_tool_call_reaches_xscapes_as_the_shell_hook_wire(fake_xscapes):
    mod = load()
    ctx = Ctx()
    mod.register(ctx)
    ret = ctx.hooks["pre_tool_call"][0](tool_name="terminal", args={"command": "go test ./..."},
                                        session_id="s1", task_id="t9")
    assert ret is None  # never blocks
    (f,) = wait_calls(fake_xscapes, 1)
    got = json.loads(f.read_text())
    assert got["hook_event_name"] == "pre_tool_call"
    assert got["tool_name"] == "terminal"
    assert got["tool_input"] == {"command": "go test ./..."}
    assert got["session_id"] == "s1"
    assert got["extra"] == {"task_id": "t9"}
    assert f.with_suffix(".argv").read_text().split() == ["hook", "pre_tool_call", "hermes"]


def test_the_wire_matches_hermess_own_shell_hooks():
    """The same keyword payload, serialised by Hermes's shell-hook code and by
    the plugin, gives the same fields (Hermes adds profile and kanban_task_id,
    which xscapes does not read)."""
    try:
        from agent import shell_hooks
    except Exception:
        pytest.skip("not running inside Hermes's venv")
    mod = load()
    kw = dict(tool_name="read_file", args={"path": "a.go"}, session_id="s2",
              user_message="hi", duration_ms=12)
    theirs = json.loads(shell_hooks._serialize_payload("post_tool_call", kw))
    ours = json.loads(mod.payload("post_tool_call", kw))
    theirs.pop("profile", None)
    theirs["extra"].pop("kanban_task_id", None)
    assert ours == theirs


def test_a_slow_xscapes_never_holds_the_hook(tmp_path, monkeypatch):
    exe = tmp_path / "xscapes"
    exe.write_text("#!/bin/sh\nsleep 3\n")
    exe.chmod(0o755)
    monkeypatch.setenv("XSCAPES_BIN", str(exe))
    mod = load()
    t0 = time.time()
    mod.send("post_llm_call", {"assistant_response": "done"})
    assert time.time() - t0 < 0.5


def test_no_binary_is_a_quiet_no_op(tmp_path, monkeypatch):
    monkeypatch.setenv("XSCAPES_BIN", str(tmp_path / "missing"))
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    mod = load()
    mod.send("pre_llm_call", {"user_message": "x"})  # must not raise
    assert mod.find_xscapes() is None
