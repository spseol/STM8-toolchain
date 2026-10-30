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


# --- upgrade.py fixtures ----------------------------------------------------------------------

VARIANT_FILES = {"sdcc": "Makefile-sdcc", "sdcc-gas": "Makefile-sdcc-gas", "sdccrm": "Makefile-sdccrm"}
INCLUDE_COMMENT = "# VS Code extension: dap-info, debug-files (see .make/vscode/)"
INCLUDE_LINE = "-include .make/vscode.mk"


def load_upgrade():
    """The module .make/upgrade.py (it is not importable as a package, like pack.py)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("upgrade", ROOT / ".make" / "upgrade.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(cwd, *args):
    """`git ARGS` in CWD with a fixed identity; returns stdout, raises on failure."""
    env = os.environ.copy()
    env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True,
                          capture_output=True, text=True).stdout


def _strip_include(text):
    """TEXT without the `-include .make/vscode.mk` line and the comment line before it."""
    lines = text.split("\n")
    out = []
    for line in lines:
        if line == INCLUDE_LINE:
            if out and out[-1] == INCLUDE_COMMENT:
                out.pop()
            continue
        out.append(line)
    return "\n".join(out)


def _with_user_lines(text):
    """TEXT with DEVICE_FLASH=stm8s103f3 and a user line F_CPU=8000000 in the middle."""
    lines = []
    for line in text.split("\n"):
        lines.append("DEVICE_FLASH=stm8s103f3" if line.startswith("DEVICE_FLASH=") else line)
    middle = next(i for i in range(len(lines) // 2, len(lines)) if lines[i] == "")
    lines.insert(middle, "F_CPU=8000000")
    return "\n".join(lines)


def toolchain_remote(tmp_path):
    """Git repo (branch main) with the working-tree content of every file that ROOT tracks.
    Stands for the toolchain repository an upgrade fetches from. Its history has two commits:
    the old toolchain (Makefiles without `-include .make/vscode.mk`, as old_project has them),
    then the current one, so the upgrade finds the old Makefile-sdcc as the merge base."""
    remote = tmp_path / "toolchain-remote"
    remote.mkdir(parents=True)
    for name in git(ROOT, "ls-files", "-z").split("\0"):
        source = ROOT / name
        if not name or not source.is_file():
            continue
        target = remote / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target, follow_symlinks=False)
    git(remote, "init", "-q", "-b", "main")
    makefiles = [remote / "Makefile", *(remote / ".make" / name for name in VARIANT_FILES.values())]
    current = {path: path.read_text() for path in makefiles}
    for path, text in current.items():
        path.write_text(_strip_include(text))
    git(remote, "add", "-A")
    git(remote, "commit", "-q", "-m", "old toolchain")
    for path, text in current.items():
        path.write_text(text)
    git(remote, "commit", "-q", "-am", "toolchain")
    return remote


def old_project(tmp_path, variant="sdcc", dirty=False, with_include=False, symlink=False):
    """Git repo (single commit on main) as a student has it from an old toolchain: stale .make/,
    root Makefile copied from a variant, own src/main.c, .vscode/launch.json.
    DIRTY leaves an uncommitted change in Makefile; WITH_INCLUDE keeps `-include .make/vscode.mk`.
    SYMLINK commits the Makefile as a symlink to .make/Makefile-<variant>, and the student's
    settings are edited inside that file (as most real student projects have it)."""
    project = tmp_path / "old-project"
    project.mkdir(parents=True)
    make_dir = project / ".make"
    make_dir.mkdir()
    skip = {".make/vscode/", ".make/__pycache__/"}
    for name in git(ROOT, "ls-files", "-z", ".make").split("\0"):
        if not name or any(name.startswith(prefix) for prefix in skip):
            continue
        if not with_include and name in (".make/vscode.mk", ".make/upgrade.py"):
            continue
        source = ROOT / name
        if not source.is_file():
            continue
        (project / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, project / name, follow_symlinks=False)
    if not with_include:
        for name in VARIANT_FILES.values():
            path = make_dir / name
            path.write_text(_strip_include(path.read_text()))
    variant_file = make_dir / VARIANT_FILES[variant]
    if symlink:
        variant_file.write_text(_with_user_lines(variant_file.read_text()))
        (project / "Makefile").symlink_to(f".make/{VARIANT_FILES[variant]}")
    else:
        (project / "Makefile").write_text(_with_user_lines(variant_file.read_text()))
    (project / "src").mkdir()
    (project / "src" / "main.c").write_text("/* my own program */\nint main(void) { return 42; }\n")
    (project / "inc").mkdir()
    (project / "inc" / "main.h").write_text("#pragma once\n")
    (project / ".vscode").mkdir()
    (project / ".vscode" / "launch.json").write_text(json.dumps(
        {"version": "0.2.0", "configurations": [{"name": "Debug", "type": "cppdbg", "request": "launch"}]},
        indent=4) + "\n")
    git(project, "init", "-q", "-b", "main")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "init")
    if dirty:
        with open(project / "Makefile", "a") as handle:
            handle.write("# uncommitted\n")
    return project
