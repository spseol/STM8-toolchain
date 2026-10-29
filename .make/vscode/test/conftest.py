"""Shared helpers for the VS Code debugger tests (run from anywhere, see pytest.ini)."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]  # test -> vscode -> .make -> project root

COPY_IGNORE = shutil.ignore_patterns(
    "build-*", ".git", ".superpowers", "compile_commands.json", "__pycache__",
    "*.backup", ".debug-*", "out.ihx", "out.elf",
)


def pytest_collection_modifyitems(config, items):
    if os.environ.get("STM8_HW") == "1":
        return
    skip = pytest.mark.skip(reason="needs the Nucleo board, set STM8_HW=1")
    for item in items:
        if "hw" in item.keywords:
            item.add_marker(skip)


def run_make(args, cwd=ROOT, timeout=900):
    """`make -s --no-print-directory ARGS` in CWD; returns CompletedProcess (text)."""
    return subprocess.run(
        ["make", "-s", "--no-print-directory", *args],
        cwd=cwd, capture_output=True, text=True, timeout=timeout,
    )


def dap_info(cwd=ROOT):
    """Parsed output of `make dap-info` in CWD."""
    proc = run_make(["dap-info"], cwd=cwd)
    assert proc.returncode == 0, f"make dap-info failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def project_copy(tmp_path, name="proj", spl_without=()):
    """Copy of the project at TMP_PATH/NAME (NAME may contain subfolders, spaces and
    diacritics). ../SPLSPL next to it is a symlink to the real SPL, like in a student's tree.
    SPL_WITHOUT: family names (e.g. "STM8S007") whose mk file the copied SPL must lack."""
    dest = tmp_path / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT, dest, ignore=COPY_IGNORE)
    spl = dest.parent / "SPLSPL"
    real = (ROOT.parent / "SPLSPL").resolve()
    if spl_without:
        spl.mkdir()
        for entry in real.iterdir():
            if entry.name != "mk":
                (spl / entry.name).symlink_to(entry)
        (spl / "mk").mkdir()
        for mk in (real / "mk").iterdir():
            if mk.stem not in spl_without:
                (spl / "mk" / mk.name).symlink_to(mk)
    elif not spl.exists():
        spl.symlink_to(real)
    return dest


def gdb_env(info=None):
    """Environment `make debug` gives gdb (OpenOCD command, its log, the SFR symbols)."""
    info = info or dap_info()
    env = os.environ.copy()
    env.update(STM8_OPENOCD=info["openocd"], STM8_OPENOCD_LOG=info["openocdLog"], STM8_SFR=info["sfr"])
    return env


def gdb_batch(commands, hw=False, timeout=120):
    """stm8-gdb -batch running COMMANDS (gdb CLI). Without HW only the scripts are sourced:
    no ELF, no chip. With HW it starts like `make debug` (ELF loaded into the chip, stopped in main)."""
    info = dap_info()
    argv = ["stm8-gdb", "-q", "-batch"]
    if hw:
        argv += ["-x", ".make/gdbinit", info["elf"]]
    else:
        argv += ["-ex", "source .make/stm8gdb.py", "-ex", "source .make/stm8sfr.py"]
    for command in commands:
        argv += ["-ex", command]
    return subprocess.run(argv, cwd=ROOT, env=gdb_env(info), capture_output=True, text=True, timeout=timeout)


def gdb_init(commands, ui=None, cwd=ROOT, timeout=120):
    """stm8-gdb -batch with .make/gdbinit like `make debug` but without ELF (no chip).
    UI is the STM8_UI value ("dap" for the VS Code mode)."""
    env = gdb_env(dap_info())
    env.pop("STM8_UI", None)
    if ui:
        env["STM8_UI"] = ui
    argv = ["stm8-gdb", "-q", "-batch", "-x", ".make/gdbinit"]
    for command in commands:
        argv += ["-ex", command]
    return subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)


def start_dap(info=None):
    """DapClient on `stm8-gdb -i dap`, started like the VS Code extension does it:
    initialize, attach, configurationDone, repl `run`. Returns (client, thread_id) stopped in main()."""
    from dapclient import DapClient

    info = info or dap_info()
    env = gdb_env(info)
    env["STM8_UI"] = "dap"
    client = DapClient(["stm8-gdb", "-q", "-i", "dap", "-x", ".make/gdbinit"], env=env, cwd=str(ROOT))
    client.request("initialize", {"adapterID": "stm8", "linesStartAt1": True, "columnsStartAt1": True})
    client.wait_event("initialized")
    reply = client.request("attach", {"program": info["elf"], "target": info["gdbTarget"]}, timeout=60)
    assert reply["success"], reply
    client.request("configurationDone")
    reply = client.request("evaluate", {"expression": "run", "context": "repl"}, timeout=90)
    assert reply["success"], reply
    stop = client.wait_event("stopped", timeout=30)
    return client, stop["body"].get("threadId", 1)


def json_lines(proc):
    """Every stdout line of PROC that is a JSON object, parsed."""
    return [json.loads(line) for line in proc.stdout.splitlines() if line.startswith("{")]


@pytest.fixture
def project_info():
    return dap_info()
