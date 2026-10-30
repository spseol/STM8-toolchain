import hashlib
import json
import re
import subprocess
import sys

import pytest

from conftest import ROOT, VARIANT_FILES, git, load_upgrade, old_project, toolchain_remote

upgrade = load_upgrade()


def variants():
    return {key: (ROOT / ".make" / name).read_text() for key, name in VARIANT_FILES.items()}


def test_detect_variant_picks_closest():
    for key, text in variants().items():
        edited = text.replace("DEVICE_FLASH=stm8s208rb", "DEVICE_FLASH=stm8s103f3")
        assert upgrade.detect_variant(edited, variants()) == key


def test_detect_variant_refuses_foreign_makefile():
    with pytest.raises(upgrade.Refused):
        upgrade.detect_variant("all:\n\ttrue\n", variants())


def test_detect_variant_of_old_project(tmp_path):
    for key in VARIANT_FILES:
        project = old_project(tmp_path / key, variant=key)
        assert upgrade.detect_variant((project / "Makefile").read_text(), variants()) == key


def make_no_git(tmp_path):
    project = tmp_path / "p"
    project.mkdir()
    return project


def make_no_commit(tmp_path):
    project = tmp_path / "p"
    project.mkdir()
    git(project, "init", "-q", "-b", "main")
    return project


def make_no_variant_file(tmp_path):
    project = old_project(tmp_path)
    git(project, "rm", "-q", ".make/Makefile-sdcc")
    git(project, "commit", "-q", "-m", "rm")
    return project


def make_no_makefile(tmp_path):
    project = old_project(tmp_path)
    git(project, "rm", "-q", "Makefile")
    git(project, "commit", "-q", "-m", "rm")
    return project


def make_dirty(tmp_path):
    return old_project(tmp_path, dirty=True)


def make_dirty_launch(tmp_path):
    project = old_project(tmp_path)
    (project / ".vscode" / "launch.json").write_text("{}\n")
    return project


def make_dirty_make_dir(tmp_path):
    project = old_project(tmp_path)
    (project / ".make" / "gdbinit").write_text("# edited\n")
    return project


@pytest.mark.parametrize("build, word", [
    (make_no_git, "git"),
    (make_no_commit, "commit"),
    (make_no_variant_file, "Makefile-sdcc"),
    (make_no_makefile, "Makefile"),
    (make_dirty, "uncommitted"),
    (make_dirty_launch, "uncommitted"),
    (make_dirty_make_dir, "uncommitted"),
])
def test_check_project_refuses(tmp_path, build, word):
    project = build(tmp_path)
    with pytest.raises(upgrade.Refused, match=word):
        upgrade.check_project(project)


def test_check_project_without_git_binary(tmp_path, monkeypatch):
    project = old_project(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "nowhere"))
    with pytest.raises(upgrade.Refused, match="git"):
        upgrade.check_project(project)


def test_check_project_accepts_clean_old_project(tmp_path):
    assert upgrade.check_project(old_project(tmp_path)) is None


def test_check_project_ignores_other_dirty_files(tmp_path):
    project = old_project(tmp_path)
    (project / "src" / "main.c").write_text("// edited\n")
    assert upgrade.check_project(project) is None


def test_old_project_fixture_shape(tmp_path):
    project = old_project(tmp_path)
    makefile = (project / "Makefile").read_text()
    assert "DEVICE_FLASH=stm8s103f3" in makefile
    assert "F_CPU=8000000\n" in makefile
    assert "vscode.mk" not in makefile
    assert not (project / ".make" / "vscode.mk").exists()
    assert "cppdbg" in (project / ".vscode" / "launch.json").read_text()
    assert git(project, "status", "--porcelain") == ""


def test_old_project_with_include(tmp_path):
    project = old_project(tmp_path, with_include=True)
    assert "-include .make/vscode.mk" in (project / "Makefile").read_text()
    assert "-include .make/vscode.mk" in (project / ".make" / "Makefile-sdcc").read_text()
    assert (project / ".make" / "vscode.mk").is_file()


def test_toolchain_remote_fixture(tmp_path):
    remote = toolchain_remote(tmp_path)
    assert git(remote, "rev-parse", "--abbrev-ref", "HEAD").strip() == "main"
    assert (remote / ".make" / "Makefile-sdcc").is_file()


# --- upgrade() and main() ----------------------------------------------------------------------

UPGRADE_PY = ROOT / ".make" / "upgrade.py"
DEVICE_LINE = re.compile(r"^[ \t]*(DEVICE_FLASH=)stm8\w+[ \t]*$", re.M)


def prepared(tmp_path, **kwargs):
    """Old project with the toolchain fetched into FETCH_HEAD, like `git fetch URL main`."""
    remote = toolchain_remote(tmp_path / "remote")
    project = old_project(tmp_path / "project", **kwargs)
    git(project, "fetch", "-q", str(remote), "main")
    return project


def commit_all(project, message="change"):
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", message)


def tree_hashes(project, *names):
    result = {}
    for name in names:
        base = project / name
        files = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file())
        for path in files:
            result[str(path.relative_to(project))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def test_upgrade_sdcc_clean_merge(tmp_path):
    project = prepared(tmp_path)
    report = upgrade.upgrade(project, "FETCH_HEAD")
    makefile = (project / "Makefile").read_text()
    assert "-include .make/vscode.mk" in makefile
    assert "DEVICE_FLASH=stm8s103f3" in makefile
    assert "F_CPU=8000000" in makefile
    assert "<<<<<<<" not in makefile
    assert (project / ".make" / "vscode.mk").is_file()
    assert report.makefile == "merged"
    assert report.replaced > 0


def test_upgrade_conflict_keeps_markers(tmp_path):
    project = prepared(tmp_path)
    with open(project / "Makefile", "a") as handle:
        handle.write("MY_OWN_LINE=1\n")
    commit_all(project)
    report = upgrade.upgrade(project, "FETCH_HEAD")
    makefile = (project / "Makefile").read_text()
    assert report.makefile == "conflict"
    assert "<<<<<<< Makefile" in makefile
    assert ">>>>>>> new .make/Makefile-sdcc" in makefile
    assert "MY_OWN_LINE=1" in makefile


def test_upgrade_does_not_touch_user_files(tmp_path):
    project = prepared(tmp_path)
    (project / "lib").mkdir()
    (project / "lib" / "x.c").write_text("// lib\n")
    (project / "README.md").write_text("# mine\n")
    commit_all(project)
    names = ("src", "inc", "lib", "README.md")
    before = tree_hashes(project, *names)
    head = git(project, "rev-parse", "HEAD")
    upgrade.upgrade(project, "FETCH_HEAD")
    assert tree_hashes(project, *names) == before
    assert git(project, "diff", "--cached", "--name-only") == ""
    assert git(project, "rev-parse", "HEAD") == head
    assert not (project / ".vscode" / "tasks.json").exists()


def test_upgrade_removes_files_gone_from_toolchain(tmp_path):
    project = prepared(tmp_path)
    (project / ".make" / "obsolete.sh").write_text("echo old\n")
    (project / ".gitignore").write_text(".make/linker_output\n")
    commit_all(project)
    (project / ".make" / "linker_output").mkdir()
    (project / ".make" / "linker_output" / "x").write_text("build artefact\n")
    report = upgrade.upgrade(project, "FETCH_HEAD")
    assert not (project / ".make" / "obsolete.sh").exists()
    assert (project / ".make" / "linker_output" / "x").is_file()
    assert report.removed == 1


def launch_configs(project):
    return json.loads((project / ".vscode" / "launch.json").read_text())["configurations"]


def test_upgrade_replaces_tracked_launch_json(tmp_path):
    project = prepared(tmp_path)
    report = upgrade.upgrade(project, "FETCH_HEAD")
    assert [c["name"] for c in launch_configs(project)] == ["STM8 debug"]
    assert report.launch == "replaced"
    assert report.backup is None
    assert not (project / ".vscode" / "launch.json.bak").exists()


def test_upgrade_untracked_launch_json_gets_bak(tmp_path):
    project = prepared(tmp_path)
    (project / ".vscode" / ".gitignore").write_text("*\n")
    git(project, "rm", "-q", "--cached", ".vscode/launch.json")
    git(project, "add", "-f", ".vscode/.gitignore")
    git(project, "commit", "-q", "-m", "untrack launch.json")
    report = upgrade.upgrade(project, "FETCH_HEAD")
    assert [c["name"] for c in launch_configs(project)] == ["STM8 debug"]
    backup = project / ".vscode" / "launch.json.bak"
    assert "cppdbg" in backup.read_text()
    assert report.launch == "replaced"
    assert report.backup == str(backup)


def test_upgrade_never_overwrites_existing_launch_backup(tmp_path):
    project = prepared(tmp_path)
    (project / ".vscode" / ".gitignore").write_text("*\n")
    git(project, "rm", "-q", "--cached", ".vscode/launch.json")
    git(project, "add", "-f", ".vscode/.gitignore")
    git(project, "commit", "-q", "-m", "untrack launch.json")
    first = upgrade.upgrade(project, "FETCH_HEAD")
    commit_all(project, "upgraded")
    # a later toolchain release changes launch.json
    remote = tmp_path / "remote" / "toolchain-remote"
    launch = remote / ".vscode" / "launch.json"
    launch.write_text(launch.read_text().replace("STM8 debug", "STM8 debug v2"))
    git(remote, "commit", "-q", "-am", "launch v2")
    git(project, "fetch", "-q", str(remote), "main")
    second = upgrade.upgrade(project, "FETCH_HEAD")
    first_bak = project / ".vscode" / "launch.json.bak"
    assert first.backup == str(first_bak)
    assert "cppdbg" in first_bak.read_text()
    assert second.backup == str(project / ".vscode" / "launch.json.bak.1")
    assert "STM8 debug" in (project / ".vscode" / "launch.json.bak.1").read_text()
    assert [c["name"] for c in launch_configs(project)] == ["STM8 debug v2"]


def test_upgrade_adds_launch_json_when_missing(tmp_path):
    project = prepared(tmp_path)
    git(project, "rm", "-q", ".vscode/launch.json")
    git(project, "commit", "-q", "-m", "no launch")
    report = upgrade.upgrade(project, "FETCH_HEAD")
    assert report.launch == "added"
    assert [c["name"] for c in launch_configs(project)] == ["STM8 debug"]


def test_upgrade_gitignore_adds_missing_lines_only(tmp_path):
    project = prepared(tmp_path)
    (project / ".gitignore").write_text("my-private-file\nbuild-*\n.cache")
    commit_all(project)
    report = upgrade.upgrade(project, "FETCH_HEAD")
    wanted = [line for line in git(project, "show", "FETCH_HEAD:.gitignore").splitlines() if line]
    lines = (project / ".gitignore").read_text().splitlines()
    assert lines[:3] == ["my-private-file", "build-*", ".cache"]
    assert sorted(lines[3:]) == sorted(set(wanted) - {"build-*", ".cache"})
    assert len(lines) == len(set(lines))
    assert report.gitignore_added == lines[3:]


def test_upgrade_idempotent(tmp_path):
    project = prepared(tmp_path)
    upgrade.upgrade(project, "FETCH_HEAD")
    commit_all(project, "upgraded")
    report = upgrade.upgrade(project, "FETCH_HEAD")
    assert report.replaced == 0
    assert report.removed == 0
    assert report.makefile == "unchanged"
    assert report.launch == "unchanged"
    assert report.gitignore_added == []
    assert git(project, "status", "--porcelain") == ""


def test_variant_needs_switch(tmp_path):
    project = prepared(tmp_path, variant="sdcc-gas")
    with pytest.raises(upgrade.NeedsSwitch) as info:
        upgrade.upgrade(project, "FETCH_HEAD", None)
    assert info.value.variant == "sdcc-gas"
    with pytest.raises(upgrade.Refused, match="nothing was changed"):
        upgrade.upgrade(project, "FETCH_HEAD", "no")
    assert git(project, "status", "--porcelain") == ""
    report = upgrade.upgrade(project, "FETCH_HEAD", "yes")
    expected = DEVICE_LINE.sub(r"\1stm8s103f3", (ROOT / ".make" / "Makefile-sdcc").read_text())
    assert (project / "Makefile").read_text() == expected
    assert report.makefile == "switched"
    assert report.notes == []


def test_switch_without_active_device_flash(tmp_path):
    project = prepared(tmp_path, variant="sdccrm")
    makefile = project / "Makefile"
    makefile.write_text(makefile.read_text().replace("\nDEVICE_FLASH=stm8s103f3", "\n#DEVICE_FLASH=stm8s103f3"))
    commit_all(project)
    report = upgrade.upgrade(project, "FETCH_HEAD", "yes")
    expected = (ROOT / ".make" / "Makefile-sdcc").read_text()
    assert makefile.read_text() == expected
    assert report.makefile == "switched"
    assert any("DEVICE_FLASH" in note for note in report.notes)


def test_upgrade_refuses_unknown_ref(tmp_path):
    project = prepared(tmp_path)
    with pytest.raises(upgrade.Refused):
        upgrade.upgrade(project, "no-such-ref")
    assert git(project, "status", "--porcelain") == ""


def run_main(project, monkeypatch, capsys, *argv):
    monkeypatch.chdir(project)
    code = upgrade.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_main_exit_codes_and_json(tmp_path, monkeypatch, capsys):
    ok = prepared(tmp_path / "ok")
    code, out, _ = run_main(ok, monkeypatch, capsys, "FETCH_HEAD", "--json")
    assert code == 0
    data = json.loads(out.splitlines()[-1])
    assert data["makefile"] == "merged"
    assert data["launch"] == "replaced"
    assert set(data) == {"replaced", "removed", "makefile", "launch", "backup", "gitignore_added", "notes"}

    dirty = prepared(tmp_path / "dirty", dirty=True)
    code, out, err = run_main(dirty, monkeypatch, capsys, "FETCH_HEAD")
    assert code == 1
    assert "uncommitted" in err

    conflict = prepared(tmp_path / "conflict")
    with open(conflict / "Makefile", "a") as handle:
        handle.write("MY_OWN_LINE=1\n")
    commit_all(conflict)
    code, out, _ = run_main(conflict, monkeypatch, capsys, "FETCH_HEAD", "--json")
    assert code == 2
    assert json.loads(out.splitlines()[-1])["makefile"] == "conflict"

    gas = prepared(tmp_path / "gas", variant="sdcc-gas")
    code, out, _ = run_main(gas, monkeypatch, capsys, "FETCH_HEAD")
    assert code == 3
    assert json.loads(out.splitlines()[-1]) == {"needsSwitch": "sdcc-gas"}
    assert git(gas, "status", "--porcelain") == ""
    code, _, err = run_main(gas, monkeypatch, capsys, "FETCH_HEAD", "--switch", "no")
    assert code == 1
    assert "nothing was changed" in err
    code, out, _ = run_main(gas, monkeypatch, capsys, "FETCH_HEAD", "--switch", "yes", "--json")
    assert code == 0
    assert json.loads(out.splitlines()[-1])["makefile"] == "switched"


def test_main_asks_on_tty(tmp_path, monkeypatch, capsys):
    gas = prepared(tmp_path, variant="sdcc-gas")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "yes")
    code, out, _ = run_main(gas, monkeypatch, capsys, "FETCH_HEAD")
    assert code == 0
    assert "Makefile" in out


def test_upgrade_runs_via_python_dash_c(tmp_path):
    project = prepared(tmp_path)
    proc = subprocess.run(["python3", "-c", UPGRADE_PY.read_text(), "FETCH_HEAD", "--json"],
                          cwd=project, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.splitlines()[-1])["makefile"] == "merged"
    assert "-include .make/vscode.mk" in (project / "Makefile").read_text()


def test_upgrade_script_is_self_contained():
    source = UPGRADE_PY.read_text()
    assert "__file__" not in source
    assert len(source.encode()) < 100_000
