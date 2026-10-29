import re
import shlex
from pathlib import Path

from conftest import ROOT, dap_info, project_copy, run_make

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
