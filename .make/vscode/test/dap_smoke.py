#!/usr/bin/env python3
"""Spike: how does `stm8-gdb -i dap` behave on the real chip? Uses the unmodified .make/gdbinit.

Run with the Nucleo connected:  STM8_HW=1 python3 .make/vscode/test/dap_smoke.py
Prints PASS/FAIL/INFO per gate (G1..G10: start sequence, errors, data, pause, disconnect, breakpoints, repl, output) and the observed values.
"""
import base64
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from conftest import ROOT, dap_info, run_make  # noqa: E402
from dapclient import DapClient  # noqa: E402

GDB = ["stm8-gdb", "-q", "-i", "dap", "-x", ".make/gdbinit"]
STARTUP = ["load", "monitor reset halt", "maintenance flush register-cache", "tbreak main", "continue"]
MAIN_C = str(ROOT / "src" / "main.c")
failed = []


def report(kind, gate, text):
    print(f"{kind} {gate}: {text}", flush=True)
    if kind == "FAIL":
        failed.append(gate)


def gdb_env(info):
    env = os.environ.copy()
    env.update(STM8_UI="dap", STM8_OPENOCD=info["openocd"],
               STM8_OPENOCD_LOG=info["openocdLog"], STM8_SFR=info["sfr"])
    return env


def repl(c, expression, timeout=30):
    return c.request("evaluate", {"expression": expression, "context": "repl"}, timeout=timeout)


def brief(response):
    body = response.get("body") or {}
    return (body.get("result") if response.get("success") else response.get("message", "")).strip()[:200]


def top_frame(c, thread_id):
    frames = c.request("stackTrace", {"threadId": thread_id})["body"]["stackFrames"]
    return frames[0] if frames else None


def addr_of(c, lvalue):
    """Address of a C lvalue, asked from gdb (register addresses differ between STM8S families)."""
    text = brief(repl(c, f"p/x &{lvalue}"))
    return int(re.search(r"0x[0-9a-f]+", text.split("=", 1)[1]).group(0), 16)


def read_byte(c, address):
    body = c.request("readMemory", {"memoryReference": hex(address), "count": 1})["body"]
    return base64.b64decode(body["data"])[0]


def main_session(info):
    c = DapClient(GDB, env=gdb_env(info), cwd=str(ROOT))
    try:
        run_gates(c, info)
    finally:
        report("INFO", "G9", f"stray stdout before DAP framing: {c.junk[:5]}")
        report("INFO", "stderr", f"{c.stderr[-5:]}")
        c.close()


def run_gates(c, info):
    # --- G1: start sequence ------------------------------------------------------
    init = c.request("initialize", {"adapterID": "stm8", "linesStartAt1": True,
                                    "columnsStartAt1": True, "pathFormat": "path"})
    c.wait_event("initialized")
    t0 = time.monotonic()
    attach = c.request("attach", {"program": info["elf"], "target": info["gdbTarget"]}, timeout=60)
    report("INFO", "G1", f"attach success={attach['success']} in {time.monotonic() - t0:.1f}s "
                         f"message={attach.get('message')!r}")
    if not attach["success"]:
        report("FAIL", "G1", "attach failed")
        return

    before = repl(c, "p 1+1")  # G7: repl between attach and configurationDone
    report("INFO", "G7", f"repl before configurationDone: success={before['success']} {brief(before)!r}")
    done = c.request("configurationDone")
    report("INFO", "G1", f"configurationDone success={done['success']}")
    for command in STARTUP:
        t0 = time.monotonic()
        r = repl(c, command, timeout=90)
        report("INFO", "G1", f"repl {command!r}: success={r['success']} {time.monotonic() - t0:.1f}s {brief(r)!r}")
        if not r["success"] and command != "maintenance flush register-cache":
            report("FAIL", "G1", f"{command!r} failed")
            return
    stop = c.wait_event("stopped", timeout=30)
    thread_id = stop["body"].get("threadId", 1)
    frame = top_frame(c, thread_id)
    if frame and frame["name"] == "main":
        report("PASS", "G1", f"stopped in main, line {frame.get('line')}, reason {stop['body'].get('reason')}")
    else:
        report("FAIL", "G1", f"stopped at {frame}")
        return

    # --- G10/G3: symbols after `file`, data access -------------------------------------
    for expression in ("p TIM4->CR1", "sfr TIM4"):
        r = repl(c, expression)
        text = (r.get("body") or {}).get("result", r.get("message", ""))
        report("INFO", "G3", f"repl {expression!r}: success={r['success']} ansi={chr(27) in text} {text.strip()[:160]!r}")
    report("PASS" if repl(c, "p TIM4->CR1")["success"] else "FAIL", "G10", "TIM4 symbols usable after attach")

    step_log = []
    for command in ("next", "stepIn", "stepOut"):
        r = c.request(command, {"threadId": thread_id})
        try:
            c.wait_event("stopped", timeout=15)
            f = top_frame(c, thread_id)
            step_log.append(f"{command}->{f['name']}:{f.get('line')}")
        except TimeoutError:
            step_log.append(f"{command}->no stop (success={r['success']})")
    report("INFO", "G3", "stepping: " + ", ".join(step_log))

    frame = top_frame(c, thread_id)
    scopes = c.request("scopes", {"frameId": frame["id"]})["body"]["scopes"]
    summary = []
    for scope in scopes:
        variables = c.request("variables", {"variablesReference": scope["variablesReference"]})["body"]["variables"]
        summary.append(f"{scope['name']}[{len(variables)}]: " + ", ".join(v["name"] for v in variables[:6]))
    report("INFO", "G3", "scopes: " + " | ".join(summary))

    arr, cntr = addr_of(c, "TIM4->ARR"), addr_of(c, "TIM4->CNTR")
    original = read_byte(c, arr)
    set_ok = c.request("setExpression", {"expression": "TIM4->ARR", "value": "85", "frameId": frame["id"]})
    after_set = read_byte(c, arr)
    write_ok = c.request("writeMemory", {"memoryReference": hex(arr),
                                         "data": base64.b64encode(bytes([original])).decode()})
    restored = read_byte(c, arr)
    ok = after_set == 85 and restored == original
    report("PASS" if ok else "FAIL", "G3", f"readMemory/setExpression/writeMemory at {arr:#x}: ARR {original} -> {after_set} "
           f"(setExpression success={set_ok['success']}) -> {restored} (writeMemory success={write_ok['success']})")

    # --- G6: breakpoint limit -------------------------------------------------------
    lines = [53, 55, 57, 58, 59, 60]
    bps = c.request("setBreakpoints", {"source": {"path": MAIN_C},
                                       "breakpoints": [{"line": n} for n in lines]})
    for n, bp in zip(lines, bps["body"]["breakpoints"]):
        report("INFO", "G6", f"line {n}: verified={bp.get('verified')} line={bp.get('line')} message={bp.get('message')!r}")
    c.request("continue", {"threadId": thread_id})
    try:
        hit = c.wait_event("stopped", timeout=10)
        f = top_frame(c, thread_id)
        report("INFO", "G6", f"continue stopped: reason={hit['body'].get('reason')} at {f['name']}:{f.get('line')}")
    except TimeoutError:
        report("INFO", "G6", "continue: no stop within 10 s")
    c.request("setBreakpoints", {"source": {"path": MAIN_C}, "breakpoints": []})

    # --- G4/G7: pause and repl while running ------------------------------------------
    c.request("continue", {"threadId": thread_id})
    time.sleep(1.0)
    running = repl(c, "p 1+1")
    report("INFO", "G7", f"repl while running: success={running['success']} {brief(running)!r}")
    t0 = time.monotonic()
    c.request("pause", {"threadId": thread_id})
    try:
        paused = c.wait_event("stopped", timeout=5)
        report("PASS", "G4", f"pause -> stopped reason={paused['body'].get('reason')} in {time.monotonic() - t0:.1f}s")
    except TimeoutError:
        report("FAIL", "G4", "no stopped event 5 s after pause")
        return

    # --- G8: gdb.write reaches the client ---------------------------------------------
    marker = repl(c, 'python gdb.write("G8-MARKER\\n")')
    seen = "G8-MARKER" in c.output_text() or "G8-MARKER" in (marker.get("body") or {}).get("result", "")
    report("PASS" if seen else "FAIL", "G8", f"gdb.write visible to client: output events={'G8-MARKER' in c.output_text()} "
           f"repl result={'G8-MARKER' in (marker.get('body') or {}).get('result', '')}")

    # --- G5: disconnect -------------------------------------------------------------------
    repl(c, "monitor reset halt")
    repl(c, "monitor resume")
    t0 = time.monotonic()
    c.request("disconnect", {"terminateDebuggee": False}, timeout=10)
    try:
        c.proc.wait(3)
        gdb_gone = f"gdb exited in {time.monotonic() - t0:.1f}s"
    except subprocess.TimeoutExpired:
        gdb_gone = "gdb still running 3 s after disconnect"
    time.sleep(1.0)
    orphans = subprocess.run(["pgrep", "-x", "openocd"], capture_output=True, text=True).stdout.split()
    report("PASS" if "exited" in gdb_gone and not orphans else "FAIL", "G5", f"{gdb_gone}; openocd processes left: {orphans}")
    probe = subprocess.run(
        info["openocd"].split() + ["-c", "init", "-c", f"mdb {cntr:#x} 1", "-c", "sleep 30",
                                   "-c", f"mdb {cntr:#x} 1", "-c", "shutdown"],
        cwd=ROOT, capture_output=True, text=True, timeout=30)
    reads = [line for line in (probe.stdout + probe.stderr).splitlines() if line.startswith(f"{cntr:#010x}") or line.startswith(f"{cntr:#x}")]
    report("INFO", "G5", f"TIM4 CNTR reads after disconnect (differ = chip runs): {reads or (probe.stdout + probe.stderr)[-300:]!r}")


def busy_session(info):
    """G2: ST-Link held by another OpenOCD (what a leftover `make openocd` does)."""
    other = subprocess.Popen(info["openocd"].split() + ["-c", "init", "-c", "reset halt"],
                             cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    c = DapClient(GDB, env=gdb_env(info), cwd=str(ROOT))
    try:
        c.request("initialize", {"adapterID": "stm8", "linesStartAt1": True, "columnsStartAt1": True})
        c.wait_event("initialized")
        t0 = time.monotonic()
        attach = c.request("attach", {"program": info["elf"], "target": info["gdbTarget"]}, timeout=60)
        report("INFO", "G2", f"busy ST-Link: attach success={attach['success']} in {time.monotonic() - t0:.1f}s "
                             f"message={attach.get('message')!r}")
        c.request("configurationDone")
        r = repl(c, "monitor reset halt")
        report("INFO", "G2", f"repl 'monitor reset halt': success={r['success']} {brief(r)!r}")
        report("INFO", "G2", f"output events: {c.output_text().strip()[-300:]!r}")
        log = Path(info["openocdLog"])
        tail = [line for line in log.read_text(errors="replace").splitlines() if "Error" in line][-3:] if log.exists() else []
        report("INFO", "G2", f"openocd log errors: {tail}")
    finally:
        c.close()
        other.terminate()
        other.wait()


if __name__ == "__main__":
    if os.environ.get("STM8_HW") != "1":
        sys.exit("Set STM8_HW=1 (this flashes the connected board).")
    build = run_make(["debug-files"])
    if build.returncode:
        sys.exit(build.stdout + build.stderr)
    project = dap_info()
    main_session(project)
    time.sleep(2)
    busy_session(project)
    print("failed gates:", failed or "none")
    sys.exit(1 if failed else 0)
