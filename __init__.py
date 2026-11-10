"""xscapes for Hermes: the agent's lifecycle, forwarded to the xscapes scene.

Every hook below hands the event to ``xscapes hook <event> hermes`` on stdin,
as the same JSON Hermes's own shell hooks send (``hook_event_name``,
``tool_name``, ``tool_input``, ``session_id``, ``cwd``, ``extra``), so the
xscapes side reads a plugin and a shell hook alike. Nothing is returned:
the plugin never blocks, edits or approves anything. The child is started
and left to finish on its own (``xscapes hook`` exits within a quarter of a
second whatever happens), so a hook never waits on it.

Without the xscapes binary on PATH (or at ``XSCAPES_BIN``) every hook is a
no-op, with one warning in the log.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# The events xscapes reads (the same list `xscapes install hermes` writes as
# shell hooks).
EVENTS = (
    "on_session_start",
    "on_session_reset",
    "on_session_end",
    "on_session_finalize",
    "pre_llm_call",
    "post_llm_call",
    "pre_tool_call",
    "post_tool_call",
    "pre_approval_request",
    "post_approval_response",
    "subagent_start",
    "subagent_stop",
    # Hermes waits on the person (a clarify question, a password prompt, an
    # approval) and when that wait ends: the ask balloon and its sound.
    "on_human_input_request",
    "on_human_input_resolved",
    # After each model call: the context in use and the window (the moon),
    # and the tokens the call processed (the running count).
    "post_api_request",
)

# post_api_request also carries the model's response and message; the scene
# needs only these, so nothing else leaves the process.
_API_FIELDS = ("session_id", "model", "provider", "usage", "context_length")

_totals_lock = threading.Lock()
_totals: dict[str, int] = {}


def slim_api_request(kwargs: dict[str, Any]) -> dict[str, Any]:
    """The few post_api_request fields xscapes reads, plus the session's
    running token total (Hermes reports each call on its own)."""
    out = {k: kwargs.get(k) for k in _API_FIELDS if k in kwargs}
    usage = kwargs.get("usage") if isinstance(kwargs.get("usage"), dict) else {}
    try:
        n = int(usage.get("total_tokens") or 0)
    except (TypeError, ValueError):
        n = 0
    sid = str(kwargs.get("session_id") or "")
    with _totals_lock:
        _totals[sid] = _totals.get(sid, 0) + max(n, 0)
        out["xscapes_total"] = _totals[sid]
    return out

# kwargs that the shell-hook wire puts at the top level; everything else
# goes under "extra".
_TOP_LEVEL = {"tool_name", "args", "session_id", "parent_session_id"}

_bin_lock = threading.Lock()
_bin: Optional[str] = None
_bin_looked = False


def find_xscapes() -> Optional[str]:
    """The xscapes binary: XSCAPES_BIN, then PATH, then ~/.local/bin (where
    the install line puts it, and which a GUI-launched Hermes may not have
    on PATH)."""
    global _bin, _bin_looked
    with _bin_lock:
        if _bin_looked:
            return _bin
        _bin_looked = True
        for cand in (os.environ.get("XSCAPES_BIN"), shutil.which("xscapes"),
                     str(Path.home() / ".local" / "bin" / "xscapes")):
            if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
                _bin = cand
                break
        if _bin is None:
            logger.warning("xscapes: no xscapes binary found (PATH, ~/.local/bin, XSCAPES_BIN); "
                           "the scene will not follow Hermes. Install it from https://donlucasx.github.io/xscapes/")
        return _bin


def payload(event: str, kwargs: dict[str, Any]) -> str:
    """The shell-hook wire format, built from a hook's keyword payload."""
    try:
        cwd = str(Path.cwd())
    except OSError:
        cwd = ""
    args = kwargs.get("args")
    return json.dumps({
        "hook_event_name": event,
        "tool_name": kwargs.get("tool_name"),
        "tool_input": args if isinstance(args, dict) else None,
        "session_id": kwargs.get("session_id") or kwargs.get("parent_session_id") or "",
        "cwd": cwd,
        "extra": {k: v for k, v in kwargs.items() if k not in _TOP_LEVEL},
    }, ensure_ascii=False, default=str)


def _reap(proc: subprocess.Popen) -> None:
    try:
        proc.wait(timeout=10)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def send(event: str, kwargs: dict[str, Any]) -> None:
    """Hand one event to `xscapes hook`, without waiting for it."""
    exe = find_xscapes()
    if exe is None:
        return
    try:
        data = payload(event, kwargs).encode("utf-8")
        proc = subprocess.Popen(
            [exe, "hook", event, "hermes"],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True, close_fds=True,
        )
        try:
            proc.stdin.write(data)
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        threading.Thread(target=_reap, args=(proc,), daemon=True).start()
    except Exception as exc:  # a scene must never break the agent
        logger.debug("xscapes: %s not delivered: %s", event, exc)


def _hook(event: str) -> Callable[..., None]:
    def callback(**kwargs: Any) -> None:
        if event == "post_api_request":
            kwargs = slim_api_request(kwargs)
        send(event, kwargs)
        return None

    callback.__name__ = callback.__qualname__ = f"xscapes_{event}"
    return callback


def shell_hooks_installed() -> bool:
    """Whether `xscapes install hermes` wrote its shell hooks into Hermes's
    config too: then every event would reach the scene twice."""
    home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
    try:
        return "# xscapes:v1" in (home / "config.yaml").read_text(errors="ignore")
    except OSError:
        return False


def register(ctx) -> None:
    if shell_hooks_installed():
        logger.warning("xscapes: the shell hooks from `xscapes install hermes` are in config.yaml as "
                       "well as this plugin, so every event reaches the scene twice. "
                       "Run `xscapes uninstall hermes` to keep the plugin only.")
    for event in EVENTS:
        ctx.register_hook(event, _hook(event))
