import re
import shlex
import shutil
import tarfile
from pathlib import Path

from conftest import COPY_IGNORE, ROOT, dap_info, git, old_project, project_copy, run_make, toolchain_remote

KEYS = {"device", "deviceFlash", "elf", "sfr", "openocd", "openocdLog", "gdbTarget"}


def makefile_chip():
    text = (ROOT / "Makefile").read_text()
    return re.search(r"^DEVICE_FLASH=(stm8\w+)\s*$", text, re.M).group(1)


def test_dap_info_keys(project_info):
    assert set(project_info) == KEYS
    assert project_info["deviceFlash"] == makefile_chip()
    assert project_info["device"] == makefile_chip().upper()[:8]
    assert Path(project_info["elf"]).is_absolute()
    assert project_info["elf"].endswith("out.elf")
    assert Path(project_info["sfr"]).name == "sfr.elf"
    assert Path(project_info["openocdLog"]).is_absolute()
    target = project_info["gdbTarget"]
    assert target.startswith("| ")
    assert project_info["openocd"] in target
    for part in ('-c "gdb_port pipe"', '-c "telnet_port disabled"', '-c "tcl_port disabled"'):
        assert part in target
    # the redirect is the last shell word; the log path may need quoting
    assert shlex.split(target[2:])[-1] == "2>" + project_info["openocdLog"]


def test_makefile_copy_identical():
    assert (ROOT / "Makefile").read_text() == (ROOT / ".make" / "Makefile-sdcc").read_text()


def test_debug_files_in_path_with_space_and_diacritics(tmp_path):
    project = project_copy(tmp_path, "Žák Novák/lab 1")
    proc = run_make(["debug-files"], cwd=project)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    info = dap_info(cwd=project)
    assert info["elf"].startswith(str(project))
    assert Path(info["elf"]).is_file()
    assert Path(info["sfr"]).is_file()
    assert shlex.split(info["gdbTarget"][2:])[-1] == "2>" + info["openocdLog"]


def test_debug_files_downloads_spl_when_missing(tmp_path):
    """Fresh project: no ../SPLSPL yet. The first `make debug-files` has to fetch it and build."""
    parent = tmp_path / "fresh"
    project = parent / "proj"
    shutil.copytree(ROOT, project, ignore=COPY_IGNORE)
    real = ROOT.parent  # ../SPL.tgz is made here, so the test needs no network

    def source_only(info):  # no libraries built from another run
        return None if info.name.endswith((".lib", ".sdcc_ver")) else info

    with tarfile.open(parent / "SPL.tgz", "w:gz") as tgz:
        for name in ("SPL", "SPLSPL"):
            tgz.add((real / name).resolve(), arcname=f"spl-main/{name}", filter=source_only)
    assert not (parent / "SPLSPL").exists()
    proc = run_make(["debug-files"], cwd=project)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (parent / "SPLSPL" / "inc" / "stm8s.h").is_file()
    info = dap_info(cwd=project)
    assert Path(info["elf"]).is_file()
    assert Path(info["sfr"]).is_file()


def test_make_upgrade_runs_script_from_fetched_ref(tmp_path):
    remote = toolchain_remote(tmp_path / "remote")
    project = old_project(tmp_path / "proj", with_include=True)
    # a stale local script must not run: only the one from the fetched commit does the upgrade
    stale = project / ".make" / "upgrade.py"
    stale.write_text('import sys\nprint("STALE")\nsys.exit(1)\n')
    git(project, "commit", "-q", "-am", "stale upgrade.py")
    proc = run_make(["upgrade", f"STM8_TOOLCHAIN_URL=file://{remote}", "UPGRADE_ARGS=--switch no"], cwd=project)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Updated .make/" in proc.stdout
    assert "STALE" not in proc.stdout
    assert stale.read_text() == (remote / ".make" / "upgrade.py").read_text()


def test_make_upgrade_ignores_python_modules_of_the_project(tmp_path):
    remote = toolchain_remote(tmp_path / "remote")
    project = old_project(tmp_path / "proj", with_include=True)
    (project / "difflib.py").write_text('raise ImportError("project difflib.py imported")\n')
    git(project, "add", "difflib.py")
    git(project, "commit", "-q", "-m", "a student module named like the standard library")
    proc = run_make(["upgrade", f"STM8_TOOLCHAIN_URL=file://{remote}", "UPGRADE_ARGS=--switch no"], cwd=project)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "project difflib.py imported" not in proc.stderr
    assert "Updated .make/" in proc.stdout


def test_make_upgrade_fails_when_remote_has_no_upgrade_script(tmp_path):
    remote = toolchain_remote(tmp_path / "remote")
    git(remote, "rm", "-q", ".make/upgrade.py")
    git(remote, "commit", "-q", "-m", "no upgrade.py")
    project = old_project(tmp_path / "proj", with_include=True)
    proc = run_make(["upgrade", f"STM8_TOOLCHAIN_URL=file://{remote}", "UPGRADE_ARGS=--switch no"], cwd=project)
    assert proc.returncode != 0
    assert "upgrade.py" in proc.stderr + proc.stdout
    assert git(project, "status", "--porcelain") == ""


def test_make_upgrade_refusal_fails_make(tmp_path):
    remote = toolchain_remote(tmp_path / "remote")
    project = old_project(tmp_path / "proj", with_include=True, dirty=True)
    proc = run_make(["upgrade", f"STM8_TOOLCHAIN_URL=file://{remote}", "UPGRADE_ARGS=--switch no"], cwd=project)
    assert proc.returncode != 0
    assert "uncommitted" in proc.stderr
    assert re.search(r"(Error|Chyba) 1", proc.stderr), proc.stderr  # make localizes its message
