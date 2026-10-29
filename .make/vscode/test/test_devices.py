import ast
import json
import subprocess
import sys

import pytest

from conftest import ROOT, dap_info, project_copy, run_make

sys.path.insert(0, str(ROOT / ".make"))
import devices  # noqa: E402

SPL_MK = ROOT.parent / "SPLSPL" / "mk"


def all_chips():
    return {chip for family in devices.DEVICES.values() for chip in family}


def test_no_duplicate_keys():
    tree = ast.parse((ROOT / ".make" / "devices.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
            assert len(keys) == len(set(keys)), f"duplicate keys: {sorted(k for k in keys if keys.count(k) > 1)}"


def test_chips_present():
    wanted = {"STM8S003F3", "STM8S105C4", "STM8S105C6", "STM8S105K4", "STM8S105K6",
              "STM8S105S4", "STM8S105S6", "STM8S903F3", "STM8S903K3"}
    assert wanted <= all_chips()


@pytest.mark.skipif(not SPL_MK.is_dir(), reason="../SPLSPL/mk not downloaded")
def test_every_chip_has_mk():
    missing = sorted(chip for chip in all_chips() if not devices.supported(chip, mk_dir=SPL_MK))
    assert missing == []


def test_available_filters_chips_without_mk(tmp_path):
    (tmp_path / "STM8S103.mk").write_text("")
    chips = {c for family in devices.available(mk_dir=tmp_path).values() for c in family}
    assert chips == {c for c in all_chips() if c.startswith("STM8S103")}


def test_available_unfiltered_without_spl(tmp_path):
    assert devices.available(mk_dir=tmp_path / "nope") == devices.DEVICES


def test_cli_prints_json():
    out = subprocess.run([sys.executable, ".make/devices.py"], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    listed = {c for family in json.loads(out.stdout).values() for c in family}
    assert listed and listed <= all_chips()


def test_switch_device_noninteractive(tmp_path):
    project = project_copy(tmp_path)
    proc = run_make(["switch-device", "CHIP=stm8s103f3"], cwd=project)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "DEVICE_FLASH=stm8s103f3\n" in (project / "Makefile").read_text()
    assert dap_info(cwd=project)["device"] == "STM8S103"


def test_switch_device_unknown_chip(tmp_path):
    proc = run_make(["switch-device", "CHIP=foo"], cwd=project_copy(tmp_path))
    assert proc.returncode != 0
    assert "Unknown chip: foo" in proc.stderr


def test_switch_device_chip_without_mk(tmp_path):
    project = project_copy(tmp_path, spl_without=["STM8S007"])
    proc = run_make(["switch-device", "CHIP=stm8s007c8"], cwd=project)
    assert proc.returncode != 0
    assert "SPL has no support for STM8S007" in proc.stderr
    assert "DEVICE_FLASH=stm8s208rb\n" in (project / "Makefile").read_text()


def test_switch_device_uses_the_makefile_python(tmp_path):
    """The Makefile picks python3 on Linux; the script must not depend on a `python` command."""
    project = project_copy(tmp_path)
    proc = run_make(["switch-device", "CHIP=stm8s103f3", "PYTHON=/nonexistent/python"], cwd=project)
    assert proc.returncode != 0
    assert "DEVICE_FLASH=stm8s208rb\n" in (project / "Makefile").read_text()
