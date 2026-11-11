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
                                        session_id="s1", task_id="t9", tool_call_id="c1")
    assert ret is None  # never blocks
    (f,) = wait_calls(fake_xscapes, 1)
    got = json.loads(f.read_text())
    assert got["hook_event_name"] == "pre_tool_call"
    assert got["tool_name"] == "terminal"
    assert got["tool_input"] == {"command": "go test ./..."}
    assert got["session_id"] == "s1"
    assert got["extra"] == {"tool_call_id": "c1"}  # task_id: not read, not sent
    assert f.with_suffix(".argv").read_text().split() == ["hook", "pre_tool_call", "hermes"]


def test_the_wire_matches_hermess_own_shell_hooks():
    """The same keyword payload, serialised by Hermes's shell-hook code and by
    the plugin, gives the same fields for everything xscapes reads (Hermes
    adds profile, and extras the plugin keeps back)."""
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
    theirs["extra"] = {k: v for k, v in theirs["extra"].items() if k in mod._EXTRA_FIELDS}
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


def test_a_model_call_sends_only_usage_and_a_running_total(fake_xscapes):
    """post_api_request carries the response and the assistant message; only
    the usage, the window and the session's running total leave the process."""
    mod = load()
    ctx = Ctx()
    mod.register(ctx)
    for n in (1000, 2500):
        ctx.hooks["post_api_request"][0](session_id="s3", model="m", provider="p", context_length=200000,
                                         usage={"prompt_tokens": n - 100, "total_tokens": n},
                                         response={"text": "SECRET-RESPONSE"}, assistant_message="SECRET-MESSAGE")
    calls = wait_calls(fake_xscapes, 2)
    got = sorted((json.loads(f.read_text()) for f in calls), key=lambda g: g["extra"]["xscapes_total"])
    assert [g["extra"]["xscapes_total"] for g in got] == [1000, 3500]
    assert got[1]["extra"]["context_length"] == 200000
    assert got[1]["extra"]["usage"]["prompt_tokens"] == 2400
    for f in calls:
        assert "SECRET" not in f.read_text()


def test_a_question_reaches_xscapes(fake_xscapes):
    mod = load()
    ctx = Ctx()
    mod.register(ctx)
    ctx.hooks["on_human_input_request"][0](kind="clarify", request_id="r1", session_id="s4", prompt="[redacted]")
    (f,) = wait_calls(fake_xscapes, 1)
    got = json.loads(f.read_text())
    assert got["hook_event_name"] == "on_human_input_request"
    assert got["extra"]["kind"] == "clarify"


def test_a_turn_sends_one_line_never_the_conversation(fake_xscapes):
    """pre_llm_call and post_llm_call carry the whole conversation; only the
    first line of the prompt and of the reply (120 characters at most) leave."""
    mod = load()
    ctx = Ctx()
    mod.register(ctx)
    history = [{"role": "user", "content": "SECRET-HISTORY"}]
    ctx.hooks["pre_llm_call"][0](session_id="s5", user_message="fix the tests\nSECRET-SECOND-LINE",
                                 conversation_history=history, model="m", platform="cli")
    ctx.hooks["post_llm_call"][0](session_id="s5", assistant_response="x" * 300 + "\nSECRET-REST",
                                  user_message="fix the tests", conversation_history=history)
    calls = wait_calls(fake_xscapes, 2)
    got = {json.loads(f.read_text())["hook_event_name"]: json.loads(f.read_text()) for f in calls}
    assert got["pre_llm_call"]["extra"] == {"user_message": "fix the tests", "model": "m"}
    reply = got["post_llm_call"]["extra"]["assistant_response"]
    assert len(reply) == 120 and reply.endswith("\u2026")
    assert "conversation_history" not in got["post_llm_call"]["extra"]
    for f in calls:
        assert "SECRET" not in f.read_text()


def test_the_child_gets_a_minimal_environment(tmp_path, monkeypatch):
    """Hermes's provider keys never reach the xscapes process."""
    out = tmp_path / "env.txt"
    exe = tmp_path / "xscapes"
    exe.write_text(f'#!/bin/sh\nenv > "{out}.tmp" && mv "{out}.tmp" "{out}"\ncat > /dev/null\n')
    exe.chmod(0o755)
    monkeypatch.setenv("XSCAPES_BIN", str(exe))
    monkeypatch.setenv("XSCAPES_HOME", "/tmp/xs-home")
    monkeypatch.setenv("OPENROUTER_API_KEY", "SECRET-KEY")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "SECRET-KEY")
    mod = load()
    mod.send("pre_tool_call", {"tool_name": "terminal", "session_id": "s6"})
    end = time.time() + 5
    while not out.exists() and time.time() < end:
        time.sleep(0.05)
    env = dict(l.split("=", 1) for l in out.read_text().splitlines() if "=" in l)
    assert "SECRET-KEY" not in out.read_text()
    assert env.get("XSCAPES_HOME") == "/tmp/xs-home"
    assert env.get("PATH") == os.environ["PATH"]
    allowed = set(mod._ENV_KEYS) | {"PWD", "SHLVL", "_", "OLDPWD"}
    assert {k for k in env if not k.startswith("XSCAPES_")} <= allowed
