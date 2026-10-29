import json
import subprocess
import time

import pytest

from conftest import ROOT, dap_info
from dapclient import DapClient, repl, top_frame

CLI = str(ROOT / ".make" / "vscode" / "bin" / "proxy-cli.js")
MAIN_C = str(ROOT / "src" / "main.c")
pytestmark = pytest.mark.hw


def openocd_pids():
    return subprocess.run(["pgrep", "-x", "openocd"], capture_output=True, text=True).stdout.split()


def start_proxy(override=None):
    """The proxy as a DAP server on stdio, like VS Code talks to it. Returns (client, launch response)."""
    env = None
    if override:
        import os
        env = {**os.environ, "STM8_DAP_INFO_OVERRIDE": json.dumps(override)}
    client = DapClient(["node", CLI], env=env, cwd=str(ROOT))
    client.request("initialize", {"adapterID": "stm8", "linesStartAt1": True, "columnsStartAt1": True})
    client.wait_event("initialized")
    return client, client.request("launch", {"type": "stm8", "request": "launch"}, timeout=60)


def finish(client):
    if client.proc.poll() is None:
        client.request("disconnect", {"terminateDebuggee": False}, timeout=10)
        client.proc.wait(10)
    client.close()


def test_start_stops_at_main():
    client, launch = start_proxy()
    try:
        assert launch["success"], launch
        client.request("configurationDone")
        client.wait_event("stopped", timeout=40)
        assert top_frame(client, 1)["name"] == "main"
    finally:
        finish(client)


def test_threads_right_after_configuration_done():
    client, _ = start_proxy()
    try:
        client.request("configurationDone")
        reply = client.request("threads", timeout=40)  # VS Code asks before the first stop
        assert "success" in reply
        client.wait_event("stopped", timeout=40)
        assert top_frame(client, 1)["name"] == "main"
    finally:
        finish(client)


def test_six_breakpoints_verified_and_hit():
    lines = [53, 55, 57, 58, 59, 60]
    client, _ = start_proxy()
    try:
        reply = client.request("setBreakpoints", {"source": {"path": MAIN_C},
                                                   "breakpoints": [{"line": n} for n in lines]})
        assert all(bp["verified"] for bp in reply["body"]["breakpoints"]), reply
        client.request("configurationDone")
        client.wait_event("stopped", timeout=40)  # tbreak main
        client.request("continue", {"threadId": 1})
        client.wait_event("stopped", timeout=15)
        assert top_frame(client, 1)["line"] in lines
    finally:
        finish(client)


def test_disconnect_leaves_no_openocd():
    client, _ = start_proxy()
    client.request("configurationDone")
    client.wait_event("stopped", timeout=40)
    finish(client)
    time.sleep(3)
    assert openocd_pids() == []


def test_closing_stdin_leaves_no_openocd():
    """VS Code closes the session without disconnect (window closed): gdb is killed by SIGTERM."""
    client, _ = start_proxy()
    client.request("configurationDone")
    client.wait_event("stopped", timeout=40)
    client.proc.stdin.close()
    client.proc.wait(10)
    client.close()
    time.sleep(3)
    assert openocd_pids() == []


def test_leftover_openocd_on_3333_attaches_over_tcp():
    info = dap_info()
    other = subprocess.Popen(info["openocd"].split() + ["-c", "init", "-c", "reset halt"], cwd=ROOT,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # like `make openocd`
    time.sleep(3)
    client = None
    try:
        client, launch = start_proxy()
        assert launch["success"], launch
        client.request("configurationDone")
        client.wait_event("stopped", timeout=40)
        assert top_frame(client, 1)["name"] == "main"
        assert other.poll() is None  # the foreign OpenOCD keeps running
    finally:
        if client:
            finish(client)
        other.terminate()
        other.wait()


def test_unreachable_chip_message():
    client, launch = start_proxy({"openocd": "/nonexistent/openocd",
                                  "gdbTarget": "| /nonexistent/openocd 2>/dev/null"})
    try:
        start = time.monotonic()
        client.request("configurationDone")
        client.wait_event("terminated", timeout=10)
        assert time.monotonic() - start < 10
        assert "run failed" in client.output_text()
    finally:
        client.close()


def repl_text(client, expression):
    reply = repl(client, expression, timeout=40)
    return reply, (reply.get("body") or {}).get("result", "")


def test_sfr_json_via_proxy():
    client, _ = start_proxy()
    try:
        client.request("configurationDone")
        client.wait_event("stopped", timeout=40)
        reply, text = repl_text(client, "sfr-json TIM4")
        assert reply["success"], reply
        model = json.loads(next(line for line in text.splitlines() if line.startswith("{")))
        tim4 = next(p for p in model["periphs"] if p["name"] == "TIM4")
        assert isinstance(next(r for r in tim4["regs"] if r["name"] == "CR1")["value"], int)
        client.request("continue", {"threadId": 1})
        time.sleep(1)
        running, _ = repl_text(client, "sfr-json TIM4")
        assert running["success"] is False and "notStopped" in running["message"]  # the tree shows "running"
        client.request("pause", {"threadId": 1})
        client.wait_event("stopped", timeout=10)
        again, _ = repl_text(client, "sfr-json TIM4")
        assert again["success"], again
    finally:
        finish(client)


def test_hover_guard_with_real_model():
    client, _ = start_proxy()
    try:
        client.request("configurationDone")
        client.wait_event("stopped", timeout=40)
        frame = top_frame(client, 1)["id"]
        guarded = client.request("evaluate", {"expression": "UART1->DR", "context": "hover", "frameId": frame})
        assert "not read" in guarded["body"]["result"]
        harmless = client.request("evaluate", {"expression": "TIM4->CR1", "context": "hover", "frameId": frame})
        assert harmless["success"] and "not read" not in harmless["body"]["result"]
    finally:
        finish(client)
