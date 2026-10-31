import json
import re
import shutil
import struct
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pytest

from conftest import ROOT, dap_info, load_upgrade, project_copy, run_make

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
        assert Path(name).name not in {"DESIGN.md", "PLAN.md", "SPIKE.md", "RELEASING.md", "release.py", "pack.py",
                                         "dap_info.py", "pytest.ini"}, name
    assert "extension/CHANGELOG.md" in names


def manifest_of(path):
    archive = zipfile.ZipFile(path)
    return archive, ElementTree.fromstring(archive.read("extension.vsixmanifest"))


NS = {"v": "http://schemas.microsoft.com/developer/vsx-schema/2011"}


def test_vsix_has_marketplace_assets(tmp_path):
    archive, root = manifest_of(pack(tmp_path / "x.vsix"))
    names = set(archive.namelist())
    assert archive.read("extension/LICENSE.txt") == (ROOT / "LICENSE").read_bytes()
    for name in ("extension/CHANGELOG.md", "extension/README.md", "extension/media/icon.png",
                 "extension/media/README.project.md", "extension/media/schema.png"):
        assert name in names, name
    assets = {a.get("Type"): a.get("Path") for a in root.findall("v:Assets/v:Asset", NS)}
    assert assets["Microsoft.VisualStudio.Services.Icons.Default"] == "extension/media/icon.png"
    assert assets["Microsoft.VisualStudio.Services.Content.Details"] == "extension/README.md"
    assert assets["Microsoft.VisualStudio.Services.Content.Changelog"] == "extension/CHANGELOG.md"
    assert assets["Microsoft.VisualStudio.Services.Content.License"] == "extension/LICENSE.txt"
    assert assets["Microsoft.VisualStudio.Code.Manifest"] == "extension/package.json"
    for asset in root.findall("v:Assets/v:Asset", NS):
        assert asset.get("Addressable") == "true"
        assert asset.get("Path") in names
    package = json.loads((VSCODE / "package.json").read_text())
    meta = root.find("v:Metadata", NS)
    assert meta.find("v:Categories", NS).text == "Debuggers,Education"
    assert meta.find("v:Tags", NS).text == ",".join(package["keywords"])
    props = {p.get("Id"): p.get("Value") for p in meta.findall("v:Properties/v:Property", NS)}
    repo = package["repository"]["url"].removesuffix(".git")
    assert props["Microsoft.VisualStudio.Services.Links.Source"] == repo
    assert props["Microsoft.VisualStudio.Services.Links.Getstarted"] == repo
    assert props["Microsoft.VisualStudio.Services.Links.Support"] == package["bugs"]["url"]
    assert props["Microsoft.VisualStudio.Services.Links.Learn"] == package["homepage"]
    assert "[Content_Types].xml" in names and ".txt" in archive.read("[Content_Types].xml").decode()


def test_icon_is_png_at_least_128():
    data = (VSCODE / "media" / "icon.png").read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR"
    width, height = struct.unpack(">II", data[16:24])
    assert width >= 128 and height >= 128


def test_readme_images_are_https_and_not_svg():
    text = (VSCODE / "README.md").read_text(encoding="utf-8")
    urls = re.findall(r"!\[[^\]]*\]\(([^)\s]+)", text) + re.findall(r"<img[^>]+src=[\"']([^\"']+)", text)
    for url in urls:
        assert url.startswith("https://"), url
        assert not url.split("?")[0].lower().endswith(".svg"), url


def test_package_json_marketplace_fields():
    package = json.loads((VSCODE / "package.json").read_text())
    assert (VSCODE / package["icon"]).is_file() and package["icon"].endswith(".png")
    assert package["repository"] == {"type": "git", "url": "https://github.com/spseol/STM8S-toolchain.git"}
    assert package["bugs"]["url"] == "https://github.com/spseol/STM8S-toolchain/issues"
    assert package["homepage"].startswith("https://github.com/spseol/STM8S-toolchain")
    assert {"stm8", "sdcc"} <= set(package["keywords"])
    assert package["categories"] == ["Debuggers", "Education"]
    top = re.search(r"^## (\d+\.\d+\.\d+)\b", (VSCODE / "CHANGELOG.md").read_text(encoding="utf-8"), re.M).group(1)
    assert package["version"] == top


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
    assert "workspaceContains:.make/Makefile-sdcc" in package["activationEvents"]  # offer to update old projects
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


def tasks_json_matcher():
    return json.loads((ROOT / ".vscode" / "tasks.json").read_text())["tasks"][0]["problemMatcher"]


def package_matcher():
    matchers = json.loads((VSCODE / "package.json").read_text())["contributes"]["problemMatchers"]
    return next(m for m in matchers if m["name"] == "sdcc")


def test_provider_problem_matcher_equals_tasks_json():
    """The provider's $sdcc (package.json) and the shell task in .vscode/tasks.json must stay the same matcher."""
    mine = package_matcher()
    assert mine["owner"] == "sdcc"
    theirs = tasks_json_matcher()
    assert {k: v for k, v in mine.items() if k != "name"} == theirs


def test_package_json_declares_task_definition():
    package = json.loads((VSCODE / "package.json").read_text())
    assert "stm8" in {d["type"] for d in package["contributes"]["taskDefinitions"]}
    # the provider is the only place that makes the task, and it refers to the matcher declared above
    assert "$sdcc" in (VSCODE / "src" / "tasks.js").read_text()


@pytest.mark.parametrize("source", ["package.json", "tasks.json"])
def test_problem_matcher_matches_real_build_output(tmp_path, source):
    """The SDCC messages the build prints (colored by recolor.py) must produce problems."""
    pattern = (package_matcher() if source == "package.json" else tasks_json_matcher())["pattern"]
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


def test_package_json_declares_update_toolchain():
    package = json.loads((VSCODE / "package.json").read_text())
    commands = {c["command"]: c for c in package["contributes"]["commands"]}
    assert commands["stm8.updateToolchain"]["title"] == "STM8: Update Toolchain"
    hidden = {m["command"] for m in package["contributes"]["menus"]["commandPalette"]}
    assert "stm8.updateToolchain" not in hidden  # must be visible in the palette
    setting = package["contributes"]["configuration"]["properties"]["stm8.toolchainUrl"]
    assert setting["type"] == "string"
    assert setting["default"] == "https://gitlab.com/spseol/mit-no/STM8S-toolchain.git"
    assert setting["description"]
    # a cloned project's .vscode/settings.json must not redirect the updater (it runs the downloaded upgrade.py);
    # "machine-overridable" would still let workspace/folder settings override it, only "machine" ignores them
    assert setting["scope"] == "machine", 'scope must be "machine" (user settings only), not "machine-overridable"'



def test_fallback_side_effects_match_python():
    """guard.js falls back to a fixed list when the model cannot be loaded: it must equal READ_SIDE_EFFECT."""
    from conftest import gdb_batch

    js = subprocess.run(["node", "-e", "console.log(JSON.stringify(require('./.make/vscode/src/guard').DEFAULT_SIDE_EFFECTS))"],
                        cwd=ROOT, capture_output=True, text=True, check=True).stdout
    py = gdb_batch(["python import json; print(json.dumps({k: sorted(v) for k, v in READ_SIDE_EFFECT.items()}))"]).stdout
    normalize = lambda text: {k: sorted(v) for k, v in json.loads(text.strip().splitlines()[-1]).items()}  # noqa: E731
    assert normalize(js) == normalize(py)


def test_new_project_command_and_settings_are_declared():
    package = json.loads((VSCODE / "package.json").read_text())
    commands = {c["command"]: c for c in package["contributes"]["commands"]}
    assert commands["stm8.newProject"]["title"] == "STM8: New Project…"
    assert "stm8.newProject" not in {m["command"] for m in package["contributes"]["menus"]["commandPalette"]}
    setting = package["contributes"]["configuration"]["properties"]["stm8.projectsFolder"]
    assert (setting["type"], setting["default"], setting["scope"]) == ("string", "", "machine")
    assert "../SPLSPL" in setting["description"]
    welcome = package["contributes"]["viewsWelcome"]
    assert any(w["view"] == "explorer" and w["when"] == "workbenchState == empty" and "command:stm8.newProject" in w["contents"] for w in welcome)


def test_new_project_media_are_in_the_vsix(tmp_path):
    template = (VSCODE / "media" / "README.project.md").read_text(encoding="utf-8")
    assert template.startswith("# {{TITLE}}\n")
    png = (VSCODE / "media" / "schema.png").read_bytes()
    assert png.startswith(b"\x89PNG\r\n\x1a\n") and len(png) > 10_000
    archive = zipfile.ZipFile(pack(tmp_path / "x.vsix"))
    assert archive.read("extension/media/README.project.md").decode("utf-8") == template
    assert archive.read("extension/media/schema.png") == png


# --- logo ----------------------------------------------------------------------------------


def _png_header(path):
    data = path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR", path
    width, height = struct.unpack(">II", data[16:24])
    return width, height, data[25], len(data)


def test_logo_files_exist():
    media = VSCODE / "media"
    for name in ("icon.svg", "banner.svg"):
        ElementTree.parse(media / name)
    assert _png_header(media / "icon.png")[:2] == (256, 256)
    width, height, _, _ = _png_header(media / "banner.png")
    assert 400 <= width <= 1000 and height > 0


def test_icon_png_is_not_the_placeholder():
    _, _, colour_type, size = _png_header(VSCODE / "media" / "icon.png")
    assert colour_type == 6  # RGBA, průhledné pozadí
    assert size > 2000


def test_root_readmes_show_the_banner():
    banner = ".make/vscode/media/banner.png"
    assert (ROOT / banner).is_file()
    for name in ("README.md", "README.cs.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert f'src="{banner}"' in text, name
        assert "https://" not in re.search(r"<img[^>]+banner\.png[^>]*>", text).group(0)


def test_icon_in_the_vsix_equals_the_file(tmp_path):
    archive = zipfile.ZipFile(pack(tmp_path / "x.vsix"))
    assert archive.read("extension/media/icon.png") == (VSCODE / "media" / "icon.png").read_bytes()
    assert "extension/media/icon.svg" in archive.namelist()


# --- repository cleanup --------------------------------------------------------------------


def test_todo_is_gone_and_exclude_reference_lives_in_make():
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
    assert "TODO.md" not in tracked
    assert not (ROOT / "TODO.md").exists()
    assert not (ROOT / "exclude_reference").exists()
    assert ".make/exclude_reference" in tracked


def test_sdccrm_scripts_use_exclude_reference_in_make():
    # exclude_reference is only ever named with its .make/ prefix
    for name in ("Makefile-sdccrm", "asm2obj", "reference2exclude"):
        text = (ROOT / ".make" / name).read_text()
        assert "exclude_reference" in text, name
        assert not re.search(r"(?<!\.make/)exclude_reference", text), name


# --- .make/prune.txt: what a new project does not get --------------------------------------

# may be missing in a checkout: generated, or notes that are not committed
OPTIONAL_PRUNED = {".make/vscode/.pytest_cache", ".make/vscode/__pycache__", ".make/vscode/SPIKE.md",
                   ".make/vscode/PLAN.md", ".make/vscode/DESIGN.md"}
MUST_STAY = [".make/prune.txt", ".make/upgrade.py", ".make/vscode.mk", ".make/vscode/pack.py", ".make/vscode/dap_info.py",
             ".make/vscode/package.json", ".make/vscode/extension.js", ".make/vscode/src/newproject.js",
             ".make/vscode/src/adapter.js", ".make/vscode/media/icon.png", ".make/vscode/README.md",
             ".make/vscode/CHANGELOG.md", "CLAUDE.md", "Makefile", "README.md", ".vscode/launch.json", "src/main.c"]


def prune_lines():
    """The lines of the real .make/prune.txt that are entries."""
    return [line.strip() for line in (ROOT / ".make" / "prune.txt").read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")]


def pruned_by(name, entries):
    return any(name == entry or name.startswith(entry + "/") for entry in entries)


def test_prune_txt_entries_are_safe_and_exist():
    entries = prune_lines()
    assert entries
    assert load_upgrade().prune_entries((ROOT / ".make" / "prune.txt").read_text()) == entries  # none is dropped as unsafe
    for entry in entries:
        assert (ROOT / entry).exists() or entry in OPTIONAL_PRUNED, f"{entry} does not exist (typo?)"


def test_prune_txt_never_matches_what_must_stay():
    entries = prune_lines()
    for name in MUST_STAY:
        assert (ROOT / name).exists(), name
        assert not pruned_by(name, entries), name
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
    stays = [name for name in tracked if name.startswith(".make/vscode/") and not pruned_by(name, entries)]
    # what is left of the extension folder is what the VSIX is made of, plus its docs
    assert {name.split("/")[2] for name in stays} <= {"CHANGELOG.md", "README.md", "dap_info.py", "extension.js", "media",
                                                        "pack.py", "package.json", "src"}, stays


@pytest.fixture(scope="module")
def pruned_copy(tmp_path_factory):
    """Copy of the project with the prune.txt entries deleted, like a new project has it."""
    project = project_copy(tmp_path_factory.mktemp("pruned"))
    for entry in prune_lines():
        target = project / entry
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    return project


def test_pruned_copy_is_really_pruned(pruned_copy):
    assert not (pruned_copy / ".make" / "vscode" / "test").exists()
    assert not (pruned_copy / ".make" / "vscode" / "release.py").exists()
    assert (pruned_copy / ".make" / "vscode" / "pack.py").is_file()


def test_make_vscode_works_in_a_pruned_project(pruned_copy):
    proc = run_make(["vscode", "IDES=none-such"], cwd=pruned_copy)
    assert proc.returncode != 0
    assert "None of 'none-such' found in PATH" in proc.stdout + proc.stderr
    names = zipfile.ZipFile(pruned_copy / ".make" / "vscode" / "stm8-toolchain.vsix").namelist()
    for name in ("extension/extension.js", "extension/package.json", "extension/media/icon.png"):
        assert name in names, name


def test_dap_info_works_in_a_pruned_project(pruned_copy):
    assert dap_info(cwd=pruned_copy)["deviceFlash"].startswith("stm8s")


def test_vsix_of_a_pruned_project_equals_the_full_one(pruned_copy, tmp_path):
    out = tmp_path / "pruned.vsix"
    subprocess.run(["python3", str(pruned_copy / ".make" / "vscode" / "pack.py"), str(out)], check=True)
    full = zipfile.ZipFile(pack(tmp_path / "full.vsix")).namelist()
    assert zipfile.ZipFile(out).namelist() == full
