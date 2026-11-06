import shutil
import subprocess
import time

import pytest

from conftest import ROOT, dap_info, gdb_batch, gdb_init, project_copy, run_make, start_dap
from dapclient import repl, top_frame


def test_dap_mode_quiet_start():
    proc = gdb_init(["show style enabled"], ui="dap")
    text = proc.stdout + proc.stderr
    assert "styling is disabled" in text
    assert "STM8 debug" not in text  # banner
    assert "nemá ELF" not in text


def test_cgdb_mode_unchanged_without_elf():
    proc = gdb_init([], ui=None)
    assert "gdb nemá ELF" in proc.stdout + proc.stderr


def dollar_line(proc):
    return next(line for line in proc.stdout.splitlines() if line.startswith("$1"))


def test_color_printer_off_in_dap():
    colored = dollar_line(gdb_init(["python VALUE_COLOR = '35'", "p 1"], ui=None))
    assert "\x1b" in colored  # control: the printer does color in the cgdb mode
    assert "\x1b" not in dollar_line(gdb_init(["python VALUE_COLOR = '35'", "p 1"], ui="dap"))


def test_dap_mode_leaves_display_file_alone(tmp_path):
    project = project_copy(tmp_path)
    display = project / ".debug-display"
    display.write_text("# kept\ntime\n")
    gdb_init([], ui="dap", cwd=project)
    assert display.read_text() == "# kept\ntime\n"


def test_is_connected_false_without_target():
    proc = gdb_batch(["python print(is_connected(), dap_mode())"])
    # without build-*-elf/sfr.elf (make clean, fresh checkout) gdb warns on stdout first; the printed values come last
    assert proc.stdout.split()[-2:] == ["False", "False"]


@pytest.mark.hw
def test_run_after_attach():
    client, thread = start_dap()
    try:
        assert top_frame(client, thread)["name"] == "main"
    finally:
        client.close()


@pytest.mark.hw
def test_session_file():
    session = ROOT / ".debug-session"
    assert not session.exists(), "close any running make debug first"
    client, _ = start_dap()
    try:
        assert session.read_text().strip() == str(client.proc.pid)
        make = run_make(["flash"])
        assert make.returncode == 0, make.stdout + make.stderr
        assert "make debug" in make.stdout + make.stderr  # only builds, the debugger loads
    finally:
        client.request("disconnect", {"terminateDebuggee": False}, timeout=10)
        client.proc.wait(5)
        client.close()
    assert not session.exists()


@pytest.mark.hw
def test_elf_change_reloads():
    client, thread = start_dap()
    try:
        main_c = ROOT / "src" / "main.c"
        main_c.touch()
        make = run_make(["elf"])
        assert make.returncode == 0, make.stdout + make.stderr
        client.wait_event("stopped", timeout=20)  # the watcher reloaded the chip and ran to main()
        assert top_frame(client, thread)["name"] == "main"
        assert "změnil" in client.output_text()
    finally:
        client.close()


def chip_runs(info, counter):
    """Do two reads of the timer counter at COUNTER differ (the chip runs)?"""
    probe = subprocess.run(
        info["openocd"].split() + ["-c", "init", "-c", f"mdb {counter:#x} 1", "-c", "sleep 30",
                                   "-c", f"mdb {counter:#x} 1", "-c", "shutdown"],
        cwd=ROOT, capture_output=True, text=True, timeout=30)
    reads = [line.split(":")[1].strip() for line in (probe.stdout + probe.stderr).splitlines()
             if line.startswith("0x0000")]
    return len(reads) == 2 and reads[0] != reads[1]


@pytest.mark.hw
def test_disconnect_leaves_chip_running():
    info = dap_info()
    client, thread = start_dap(info)
    try:
        frame = repl(client, "p/x &TIM4->CNTR")
        counter = int(frame["body"]["result"].split("=")[1].strip(), 16)
        client.request("next", {"threadId": thread})  # past the start of main()
        client.wait_event("stopped", timeout=10)
        client.request("disconnect", {"terminateDebuggee": False}, timeout=10)
        client.proc.wait(5)
    finally:
        client.close()
    time.sleep(1)
    assert chip_runs(info, counter)


@pytest.mark.hw
def test_cgdb_regression():
    proc = gdb_batch(["sfr TIM4.CR1", "p TIM4->CR1", "flash"], hw=True)
    text = proc.stdout + proc.stderr
    assert "ARPE" in text  # sfr: bit by bit with descriptions
    assert "$1 = 0x00 0000 0000" in text  # print: pretty-printed register
    assert "Nahráno do čipu" in text  # flash: build, load, run to main


def test_connect_string_quotes_the_log_path():
    """The fallback connect() of the DAP mode gets an absolute log path; it must stay one word.
    Linux, macOS: the shell sees `2>LOG`. Windows: no shell, OpenOCD gets `-l "LOG"` with slashes."""
    import os
    import shlex

    log = "C:\\Users\\Žák Novák\\o.log" if os.name == "nt" else "/tmp/Žák Novák/o.log"
    proc = gdb_batch([f"python print(pipe_target('openocd -f x', {log!r}))"])
    target = proc.stdout.strip().splitlines()[-1]
    assert target.startswith("| openocd -f x ")
    if os.name == "nt":
        assert target.endswith(' -l "C:/Users/Žák Novák/o.log"')
        assert "2>" not in target
    else:
        assert shlex.split(target[2:])[-1] == "2>/tmp/Žák Novák/o.log"


def test_connect_string_equals_dap_info_target():
    """dap_info.py builds the same pipe string as connect() (one rule, two places)."""
    info = dap_info()
    proc = gdb_batch([f"python print(pipe_target({info['openocd']!r}, {info['openocdLog']!r}))"])
    assert proc.stdout.strip().splitlines()[-1] == info["gdbTarget"]
