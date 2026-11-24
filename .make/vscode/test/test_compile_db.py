"""compile_database_generator.py: compile_commands.json and .ccls made from the Makefile variables."""
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ROOT, git

GENERATOR = ROOT / ".make" / "compile_database_generator.py"


def make_project(tmp_path, sdcc_version="4.4.0"):
    """Project dir with src/, a fake ../SPLSPL/mk and ../SPL/src, and a fake sdcc in CC_ROOT."""
    base = tmp_path / "base"
    project = base / "proj"
    (project / "src").mkdir(parents=True)
    for name in ("main.c", "delay.c"):
        (project / "src" / name).write_text("int x;\n")
    (base / "SPLSPL" / "mk").mkdir(parents=True)
    (base / "SPLSPL" / "mk" / "STM8S208.mk").write_text(
        "SPL_SOURCE_PREFIX = stm8s_gpio \\\n   stm8s_clk # comment stm8s_nope\n")
    cc_root = base / "sdcc root"  # a space on purpose
    (cc_root / "bin").mkdir(parents=True)
    (cc_root / "share" / "sdcc" / "include").mkdir(parents=True)
    fake = cc_root / "bin" / "sdcc"
    fake.write_text(f"#!/bin/sh\necho 'SDCC : stm8 {sdcc_version} #14620 (Linux)'\n")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    return project, cc_root


def generate(project, *args):
    return subprocess.run([sys.executable, str(GENERATOR), *args], cwd=project, capture_output=True, text=True)


def entries(project):
    return {Path(e["file"]).name: e for e in json.loads((project / "compile_commands.json").read_text())}


@pytest.mark.skipif(sys.platform == "win32", reason="fake sdcc is a shell script")
def test_every_entry_has_the_makefile_flags(tmp_path):
    project, cc_root = make_project(tmp_path)
    proc = generate(project, "STM8S208", str(cc_root), "--flag=-DF_CPU=16000000", "--flag=-DSKIP_TRAPS=1")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    found = entries(project)
    assert set(found) == {"main.c", "delay.c", "stm8s_gpio.c", "stm8s_clk.c"}
    for entry in found.values():
        args = entry["arguments"]
        assert entry["directory"] == str(project)
        for flag in ("-std=c2x", "-Iinc", "-I../SPL/inc", "-DSTM8S208", "-D__CLANG", "-D__SDCC",
                     "-DF_CPU=16000000", "-DSKIP_TRAPS=1", "-D__naked=", "-D__trap=",
                     f"-I{cc_root}/share/sdcc/include",
                     "-D__SDCC_VERSION_MAJOR=4", "-D__SDCC_VERSION_MINOR=4", "-D__SDCC_VERSION_PATCH=0"):
            assert flag in args, (entry["file"], flag)
        assert args[-1] == entry["file"]
        assert "-D_SDCC_" not in args  # stm8s.h defines it, with SDCC_VERSION, from __SDCC
    assert found["stm8s_gpio.c"]["file"] == "../SPL/src/stm8s_gpio.c"
    assert found["main.c"]["file"] == "src/main.c"


@pytest.mark.skipif(sys.platform == "win32", reason="fake sdcc is a shell script")
def test_ccls_has_the_same_flags_as_the_database(tmp_path):
    project, cc_root = make_project(tmp_path)
    assert generate(project, "STM8S208", str(cc_root), "--flag=-DF_CPU=8000000").returncode == 0
    lines = (project / ".ccls").read_text().splitlines()
    assert lines[0] == "clang"
    args = entries(project)["main.c"]["arguments"]
    assert lines[1:] == args[2:-1]  # without "clang -c" and the file name


def test_positional_arguments_still_work_and_empty_cc_root_means_path(tmp_path):
    """Old Makefile variants call `generator DEVICE CC_ROOT`; the new one passes "" when CC_ROOT is unset."""
    project, _ = make_project(tmp_path)
    assert generate(project, "208", "").returncode == 0
    assert "-DSTM8S208" in entries(project)["main.c"]["arguments"]
    assert generate(project, "STM8S208").returncode == 0


def test_unknown_sdcc_gets_a_default_version(tmp_path):
    project, _ = make_project(tmp_path)
    env_path = tmp_path / "empty"
    env_path.mkdir()
    proc = subprocess.run([sys.executable, str(GENERATOR), "STM8S208", ""], cwd=project, capture_output=True,
                          text=True, env={**os.environ, "PATH": str(env_path)})
    assert proc.returncode == 0, proc.stderr
    assert "-D__SDCC_VERSION_MAJOR=4" in entries(project)["main.c"]["arguments"]


def test_unknown_device_is_refused(tmp_path):
    project, _ = make_project(tmp_path)
    proc = generate(project, "STM8S999")
    assert proc.returncode == 1
    assert not (project / "compile_commands.json").exists()


def test_tracked_ccls_is_left_alone(tmp_path):
    project, cc_root = make_project(tmp_path)
    git(project, "init", "-q", "-b", "main")
    (project / ".ccls").write_text("sdcc\nmine\n")
    git(project, "add", ".ccls")
    proc = generate(project, "STM8S208", str(cc_root))
    assert proc.returncode == 0
    assert (project / ".ccls").read_text() == "sdcc\nmine\n"
    assert "git rm --cached .ccls" in proc.stdout
    assert (project / "compile_commands.json").is_file()


def test_untracked_ccls_is_regenerated(tmp_path):
    project, cc_root = make_project(tmp_path)
    git(project, "init", "-q", "-b", "main")
    (project / ".ccls").write_text("old\n")
    assert generate(project, "STM8S208", str(cc_root)).returncode == 0
    assert (project / ".ccls").read_text().startswith("clang\n")


def test_no_temporary_files_are_left(tmp_path):
    project, cc_root = make_project(tmp_path)
    assert generate(project, "STM8S208", str(cc_root)).returncode == 0
    assert sorted(p.name for p in project.iterdir()) == [".ccls", "compile_commands.json", "src"]


def test_makefile_passes_the_flags():
    text = (ROOT / ".make" / "Makefile-sdcc").read_text()
    assert '--flag=-DF_CPU=$(F_CPU)' in text
    assert '--flag=-DSKIP_TRAPS=$(SKIP_TRAPS)' in text
    assert '"$(CC_ROOT)"' in text  # a Windows path may have spaces
    assert "rm -f .ccls" in text


CCLS = shutil.which("ccls")


@pytest.mark.skipif(not CCLS or not (ROOT.parent / "SPL" / "inc" / "stm8s.h").is_file(),
                    reason="needs ccls and ../SPL")
@pytest.mark.parametrize("name", ["src/main.c", "src/delay.c", "src/stm8s_it.c", "inc/main.h", "inc/stm8s_it.h"])
def test_ccls_finds_everything(tmp_path, name):
    """ccls starts from the generated files and has no diagnostics for the toolchain's own sources."""
    project = tmp_path / "proj"
    shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns(".git", "build-*", ".ccls*", ".cache", ".make"))
    link = tmp_path / "SPL"
    link.symlink_to((ROOT.parent / "SPL").resolve())
    (tmp_path / "SPLSPL").symlink_to((ROOT.parent / "SPLSPL").resolve())
    assert generate(project, "STM8S208", "", "--flag=-DF_CPU=16000000", "--flag=-DSKIP_TRAPS=1").returncode == 0
    messages = lsp_diagnostics(project, name, tmp_path / "cache")
    assert messages == []


def lsp_diagnostics(root, name, cache):
    """Diagnostics that ccls publishes for the file NAME (relative to ROOT)."""
    import json as _json
    import time
    proc = subprocess.Popen([CCLS, _json.dumps({"cache": {"directory": str(cache)}}).join(["-init=", ""])],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=root)

    def send(message):
        body = _json.dumps(message).encode()
        proc.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
        proc.stdin.flush()

    def receive():
        header = b""
        while not header.endswith(b"\r\n\r\n"):
            header += proc.stdout.read(1)
        length = int([h for h in header.split(b"\r\n") if h.lower().startswith(b"content-length")][0].split(b":")[1])
        return _json.loads(proc.stdout.read(length))

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"processId": None, "rootUri": root.as_uri(), "capabilities": {}}})
        receive()
        send({"jsonrpc": "2.0", "method": "initialized", "params": {}})
        path = root / name
        send({"jsonrpc": "2.0", "method": "textDocument/didOpen", "params": {"textDocument": {
            "uri": path.as_uri(), "languageId": "c", "version": 1, "text": path.read_text(errors="replace")}}})
        deadline = time.time() + 60
        while time.time() < deadline:
            message = receive()
            if message.get("method") == "textDocument/publishDiagnostics":
                return [d["message"] for d in message["params"]["diagnostics"]]
        raise AssertionError("ccls published no diagnostics")
    finally:
        proc.kill()
