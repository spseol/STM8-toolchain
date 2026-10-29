import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pytest

from conftest import ROOT, project_copy, run_make

VSCODE = ROOT / ".make" / "vscode"
sys_path = str(VSCODE)


def pack(out):
    import importlib.util

    spec = importlib.util.spec_from_file_location("pack", VSCODE / "pack.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.pack(VSCODE, out)
    return out


# --- VSIX ----------------------------------------------------------------------------------


def test_vsix_entries(tmp_path):
    names = set(zipfile.ZipFile(pack(tmp_path / "x.vsix")).namelist())
    assert {"extension.vsixmanifest", "[Content_Types].xml", "extension/package.json", "extension/extension.js"} <= names
    for source in (VSCODE / "src").glob("*.js"):
        assert f"extension/src/{source.name}" in names


def test_vsix_excludes_dev_files(tmp_path):
    names = zipfile.ZipFile(pack(tmp_path / "x.vsix")).namelist()
    for name in names:
        assert not name.startswith(("extension/test/", "extension/bin/")), name
        assert Path(name).name not in {"DESIGN.md", "PLAN.md", "SPIKE.md", "pack.py", "dap_info.py", "pytest.ini"}, name


def test_manifest_identity(tmp_path):
    archive = zipfile.ZipFile(pack(tmp_path / "x.vsix"))
    root = ElementTree.fromstring(archive.read("extension.vsixmanifest"))
    ns = {"v": "http://schemas.microsoft.com/developer/vsx-schema/2011"}
    identity = root.find("v:Metadata/v:Identity", ns)
    version = json.loads((VSCODE / "package.json").read_text())["version"]
    assert identity.get("Publisher") == "spseol"
    assert identity.get("Id") == "stm8-toolchain"
    assert identity.get("Version") == version


def test_package_json_contributes_stm8_debugger():
    package = json.loads((VSCODE / "package.json").read_text())
    assert (package["publisher"], package["name"]) == ("spseol", "stm8-toolchain")
    assert [d["type"] for d in package["contributes"]["debuggers"]] == ["stm8"]
    assert "workspaceContains:.make/gdbinit" in package["activationEvents"]
    assert "onDebugResolve:stm8" in package["activationEvents"]
    assert package["engines"]["vscode"].startswith("^1.")
    assert not package.get("dependencies")  # no npm install for students


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("codium") is None, reason="codium not installed")
def test_install_in_codium(tmp_path):
    vsix = pack(tmp_path / "x.vsix")
    dirs = ["--extensions-dir", str(tmp_path / "ext"), "--user-data-dir", str(tmp_path / "data")]
    installed = subprocess.run(["codium", *dirs, "--install-extension", str(vsix), "--force"],
                               capture_output=True, text=True, timeout=120)
    assert installed.returncode == 0, installed.stdout + installed.stderr
    listed = subprocess.run(["codium", *dirs, "--list-extensions"], capture_output=True, text=True, timeout=60)
    assert "spseol.stm8-toolchain" in listed.stdout


# --- make vscode ---------------------------------------------------------------------------


def stub_ide(directory, name):
    script = directory / name
    script.write_text(f'#!/bin/sh\necho "{name} $@" >> "{directory}/calls"\n')
    script.chmod(0o755)


def test_make_vscode_installs_into_every_ide_found(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub_ide(bin_dir, "code")
    stub_ide(bin_dir, "codium")
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin"}
    proc = subprocess.run(["make", "-s", "--no-print-directory", "vscode"], cwd=ROOT, env=env,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    calls = (bin_dir / "calls").read_text().splitlines()
    assert len(calls) == 2
    assert all("--install-extension .make/vscode/stm8-toolchain.vsix --force" in call for call in calls)


def test_make_vscode_without_ide_explains(tmp_path):
    proc = run_make(["vscode", "IDES=no-such-ide"])
    assert proc.returncode != 0
    assert "Install .make/vscode/stm8-toolchain.vsix by hand" in proc.stdout + proc.stderr


# --- .vscode -------------------------------------------------------------------------------


def test_write_icon_is_hidden_for_read_only_registers():
    menus = json.loads((VSCODE / "package.json").read_text())["contributes"]["menus"]["view/item/context"]
    (write,) = [m for m in menus if m["command"] == "stm8.sfr.writeRegister"]
    pattern = re.search(r"viewItem =~ /(.*)/", write["when"]).group(1)
    assert re.match(pattern, "stm8.reg") and re.match(pattern, "stm8.reg.sideEffect")
    assert not re.match(pattern, "stm8.reg.readOnly")


def test_launch_json_is_one_stm8_configuration():
    launch = json.loads((ROOT / ".vscode" / "launch.json").read_text())
    assert launch["configurations"] == [
        {"name": "STM8 debug", "type": "stm8", "request": "launch", "preLaunchTask": "stm8: build"}]


def test_tasks_json_builds_debug_files():
    tasks = json.loads((ROOT / ".vscode" / "tasks.json").read_text())["tasks"]
    (build,) = [t for t in tasks if t["label"] == "stm8: build"]
    assert build["command"] == "make debug-files"


def test_tracked_vscode_files_are_not_ignored():
    for name in ("tasks.json", "launch.json"):
        ignored = subprocess.run(["git", "check-ignore", "-q", f".vscode/{name}"], cwd=ROOT)
        assert ignored.returncode == 1, f".vscode/{name} is git-ignored"
    assert subprocess.run(["git", "check-ignore", "-q", ".make/vscode/stm8-toolchain.vsix"], cwd=ROOT).returncode == 0


def test_problem_matcher_matches_real_build_output(tmp_path):
    """The SDCC messages the build prints (colored by recolor.py) must produce problems."""
    tasks = json.loads((ROOT / ".vscode" / "tasks.json").read_text())["tasks"]
    pattern = tasks[0]["problemMatcher"]["pattern"]
    regexp = re.compile(pattern["regexp"])
    project = project_copy(tmp_path)
    with open(project / "src" / "main.c", "a") as f:
        f.write("\nvoid broken(void) { int unused; undefined_name = 1; }\n")
    proc = run_make(["debug-files"], cwd=project)
    assert proc.returncode != 0
    problems = []
    for line in (proc.stdout + proc.stderr).splitlines():
        match = regexp.match(line)
        if match:
            problems.append((match.group(pattern["file"]), match.group(pattern["severity"]), match.group(pattern["message"])))
    assert any(f.endswith("src/main.c") and s == "error" and "undefined_name" in m for f, s, m in problems), problems
    assert any(s == "warning" for _, s, _ in problems), problems


def test_package_json_matches_extension_code():
    package = json.loads((VSCODE / "package.json").read_text())
    code = "\n".join(p.read_text() for p in [VSCODE / "extension.js", *(VSCODE / "src").glob("*.js")])
    declared = {c["command"] for c in package["contributes"]["commands"]}
    registered = set(re.findall(r"registerCommand\('([^']+)'", code))
    assert declared == registered
    # tree-item commands need a node argument, so they stay out of the command palette
    assert {m["command"] for m in package["contributes"]["menus"]["commandPalette"]} == {c for c in declared if c.startswith("stm8.sfr.")}
    views = [v["id"] for v in package["contributes"]["views"]["debug"]]
    assert views == re.findall(r"createTreeView\('([^']+)'", code) == ["stm8Peripherals"]


def test_fallback_side_effects_match_python():
    """guard.js falls back to a fixed list when the model cannot be loaded: it must equal READ_SIDE_EFFECT."""
    from conftest import gdb_batch

    js = subprocess.run(["node", "-e", "console.log(JSON.stringify(require('./.make/vscode/src/guard').DEFAULT_SIDE_EFFECTS))"],
                        cwd=ROOT, capture_output=True, text=True, check=True).stdout
    py = gdb_batch(["python import json; print(json.dumps({k: sorted(v) for k, v in READ_SIDE_EFFECT.items()}))"]).stdout
    normalize = lambda text: {k: sorted(v) for k, v in json.loads(text.strip().splitlines()[-1]).items()}  # noqa: E731
    assert normalize(js) == normalize(py)
