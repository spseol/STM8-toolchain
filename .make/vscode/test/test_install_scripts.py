"""The one-command installation scripts in install/ and the links to them."""
import re
import shutil
import subprocess

import pytest

from conftest import ROOT

INSTALL = ROOT / "install"
README = ROOT / ".make" / "vscode" / "README.md"
RAW = "https://gitlab.com/spseol/mit-no/STM8S-toolchain/-/raw/main/install/"


def test_install_dir_is_not_given_to_students():
    entries = [line.strip() for line in (ROOT / ".make" / "prune.txt").read_text().splitlines()]
    assert "install" in entries


def test_readme_links_point_to_existing_scripts():
    names = re.findall(re.escape(RAW) + r"([\w.-]+)", README.read_text())
    assert {"linux.sh", "macos.sh", "windows.ps1", "windows-winget.ps1"} <= set(names)
    for name in names:
        assert (INSTALL / name).is_file(), f"README links to install/{name}, which does not exist"


def test_scripts_use_the_same_base_url():
    for name in ("linux.sh", "macos.sh", "windows.ps1", "windows-winget.ps1"):
        text = (INSTALL / name).read_text()
        assert RAW[:-1] in text, name


@pytest.mark.parametrize("name", ["linux.sh", "macos.sh"])
def test_shell_scripts_parse(name):
    subprocess.run(["bash", "-n", str(INSTALL / name)], check=True)


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck not installed")
@pytest.mark.parametrize("name", ["linux.sh", "macos.sh"])
def test_shell_scripts_shellcheck(name):
    subprocess.run(["shellcheck", "-S", "warning", str(INSTALL / name)], check=True)


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="pwsh not installed")
@pytest.mark.parametrize("name", ["windows.ps1", "windows-winget.ps1"])
def test_powershell_scripts_parse(name):
    code = ("$e=$null; [System.Management.Automation.Language.Parser]::ParseFile("
            f"'{INSTALL / name}',[ref]$null,[ref]$e) | Out-Null; if ($e) {{ $e; exit 1 }}")
    subprocess.run(["pwsh", "-NoProfile", "-Command", code], check=True)


def test_windows_script_installs_sdcc_where_makefile_expects_it():
    # Makefile-sdcc has the SDCC folder hard-coded for Windows
    makefile = (ROOT / ".make" / "Makefile-sdcc").read_text()
    assert "/c/Program Files/SDCC" in makefile
    assert "$env:ProgramFiles\\SDCC" in (INSTALL / "windows.ps1").read_text()


def test_flash_on_windows_falls_back_to_openocd():
    makefile = (ROOT / ".make" / "Makefile-sdcc").read_text()
    recipe = makefile[makefile.index("\nflash:"):makefile.index("\nflash-elf:")]
    windows = recipe[recipe.index("ifeq ($(OS),Windows_NT)"):recipe.index("\nelse\n")]
    assert "if [ -f $(STVP) ]" in windows and "$(OPENOCD)" in windows
