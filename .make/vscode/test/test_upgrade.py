import hashlib
import json
import re
import shutil
import subprocess
import sys

import pytest

from conftest import ROOT, VARIANT_FILES, _with_user_lines, git, load_upgrade, old_project, toolchain_remote

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


CONFLICTED = "<<<<<<< Makefile\nF_CPU=8000000\n=======\nF_CPU=16000000\n>>>>>>> new .make/Makefile-sdcc\n"


@pytest.mark.parametrize("commit", [True, False])
@pytest.mark.parametrize("symlink", [False, True])
def test_check_project_refuses_conflict_markers(tmp_path, commit, symlink):
    project = old_project(tmp_path, symlink=symlink)
    with open(project / "Makefile", "a") as handle:
        handle.write(CONFLICTED)
    if commit:
        commit_all(project, "markers")
    with pytest.raises(upgrade.Refused, match="unresolved conflict markers") as info:
        upgrade.check_project(project)
    assert "uncommitted" not in str(info.value)


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


def test_old_project_symlink_fixture_shape(tmp_path):
    for key, name in VARIANT_FILES.items():
        project = old_project(tmp_path / key, variant=key, symlink=True)
        assert (project / "Makefile").is_symlink()
        assert git(project, "ls-files", "-s", "Makefile").startswith("120000 ")
        assert "DEVICE_FLASH=stm8s103f3" in (project / ".make" / name).read_text()
        assert "F_CPU=8000000\n" in (project / "Makefile").read_text()
        assert git(project, "status", "--porcelain") == ""


def test_toolchain_remote_fixture(tmp_path):
    remote = toolchain_remote(tmp_path)
    assert git(remote, "rev-parse", "--abbrev-ref", "HEAD").strip() == "main"
    assert (remote / ".make" / "Makefile-sdcc").is_file()
    # the old toolchain is in the history: the merge base of an old project
    old = git(remote, "show", "HEAD~1:.make/Makefile-sdcc")
    assert "vscode.mk" not in old
    assert old == (old_project(tmp_path / "p") / ".make" / "Makefile-sdcc").read_text()


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


# --- Makefile committed as a symlink, the merge base from the toolchain history --------------

def test_upgrade_sdcc_symlink_keeps_settings_and_becomes_regular_file(tmp_path):
    project = prepared(tmp_path, symlink=True)
    report = upgrade.upgrade(project, "FETCH_HEAD")
    makefile = project / "Makefile"
    assert not makefile.is_symlink()
    assert makefile.is_file()
    text = makefile.read_text()
    assert re.search(r"^DEVICE_FLASH=stm8s103f3$", text, re.M)
    assert "F_CPU=8000000" in text
    assert "-include .make/vscode.mk" in text
    assert "<<<<<<<" not in text
    assert report.makefile == "merged"
    assert "Makefile was a symlink to .make/Makefile-sdcc; it is now a regular file." in report.notes
    # .make/ is the toolchain's again, the settings live in the root Makefile only
    assert (project / ".make" / "Makefile-sdcc").read_text() == (ROOT / ".make" / "Makefile-sdcc").read_text()


def test_upgrade_symlink_idempotent(tmp_path):
    project = prepared(tmp_path, symlink=True)
    upgrade.upgrade(project, "FETCH_HEAD")
    commit_all(project, "upgraded")
    before = (project / "Makefile").read_bytes()
    report = upgrade.upgrade(project, "FETCH_HEAD")
    assert report.makefile == "unchanged"
    assert report.replaced == 0
    assert report.notes == []
    assert (project / "Makefile").read_bytes() == before
    assert git(project, "status", "--porcelain") == ""


@pytest.mark.parametrize("variant", ["sdcc-gas", "sdccrm"])
def test_switch_of_symlinked_variant_gives_regular_makefile_and_no_loop(tmp_path, variant):
    project = prepared(tmp_path, variant=variant, symlink=True)
    report = upgrade.upgrade(project, "FETCH_HEAD", "yes")
    makefile = project / "Makefile"
    expected = DEVICE_LINE.sub(r"\1stm8s103f3", (ROOT / ".make" / "Makefile-sdcc").read_text())
    assert not makefile.is_symlink()
    assert makefile.read_text() == expected
    assert report.makefile == "switched"
    assert any("symlink" in note for note in report.notes)
    name = VARIANT_FILES[variant]
    assert (project / ".make" / name).read_text() == (ROOT / ".make" / name).read_text()
    commit_all(project, "upgraded")
    second = upgrade.upgrade(project, "FETCH_HEAD")
    assert second.makefile == "unchanged"
    assert second.replaced == 0
    assert makefile.read_text() == expected
    assert git(project, "status", "--porcelain") == ""


def test_merge_base_found_when_student_edited_make_dir_copy(tmp_path):
    # no symlink, but the student edited .make/Makefile-sdcc as well as the Makefile
    project = prepared(tmp_path)
    shutil.copy(project / "Makefile", project / ".make" / "Makefile-sdcc")
    commit_all(project)
    report = upgrade.upgrade(project, "FETCH_HEAD")
    text = (project / "Makefile").read_text()
    assert report.makefile == "merged"
    assert re.search(r"^DEVICE_FLASH=stm8s103f3$", text, re.M) and "F_CPU=8000000" in text
    assert "-include .make/vscode.mk" in text


def test_no_usable_merge_base_gives_conflict_markers(tmp_path):
    # the project's .make/Makefile-sdcc is far from every toolchain version: no base to trust
    project = prepared(tmp_path, symlink=True)
    own = project / ".make" / "Makefile-sdcc"
    lines = own.read_text().count("\n")
    own.write_text(own.read_text() + "".join(f"MY_SETTING_{i}=1\n" for i in range(lines)))
    commit_all(project)
    report = upgrade.upgrade(project, "FETCH_HEAD")
    text = (project / "Makefile").read_text()
    assert report.makefile == "conflict"
    assert "<<<<<<< Makefile" in text
    assert "MY_SETTING_0=1" in text
    assert any("No toolchain version close" in note for note in report.notes)


def test_history_without_older_versions_is_no_merge_base(tmp_path):
    # a remote with one commit: the only version in the history is the new file itself, which
    # as the base would hide the change (`unchanged`, no -include .make/vscode.mk line)
    remote = toolchain_remote(tmp_path / "remote")
    git(remote, "checkout", "-q", "--orphan", "flat")
    git(remote, "add", "-A")
    git(remote, "commit", "-q", "-m", "flat")
    git(remote, "branch", "-q", "-D", "main")
    git(remote, "branch", "-q", "-m", "main")
    assert git(remote, "rev-list", "--count", "main").strip() == "1"
    project = old_project(tmp_path / "project")
    git(project, "fetch", "-q", str(remote), "main")
    report = upgrade.upgrade(project, "FETCH_HEAD")
    text = (project / "Makefile").read_text()
    assert report.makefile == "conflict"
    assert "<<<<<<< Makefile" in text
    assert "F_CPU=8000000" in text
    assert any("No toolchain version close" in note for note in report.notes)


def test_history_lists_commits_with_full_history(tmp_path, monkeypatch):
    seen = []
    original = upgrade._git_bytes

    def spy(project, *args, **kwargs):
        seen.append(args)
        return original(project, *args, **kwargs)

    monkeypatch.setattr(upgrade, "_git_bytes", spy)
    remote = toolchain_remote(tmp_path)
    upgrade._history(remote, "HEAD", ".make/Makefile-sdcc")
    (rev_list,) = [args for args in seen if args[0] == "rev-list"]
    assert "--full-history" in rev_list


def test_device_flash_changed_by_the_merge_is_noted(tmp_path, monkeypatch):
    project = prepared(tmp_path)
    ours = (project / "Makefile").read_bytes()
    monkeypatch.setattr(upgrade, "_merge_base", lambda *args: ours)  # base == ours: the result is theirs
    report = upgrade.upgrade(project, "FETCH_HEAD")
    assert report.makefile == "merged"
    assert any("DEVICE_FLASH" in note and "stm8s103f3" in note for note in report.notes)


def test_latin2_byte_in_makefile_is_merged_without_fake_conflicts(tmp_path):
    remote = toolchain_remote(tmp_path / "remote")
    path = remote / ".make" / "Makefile-sdcc"
    current = path.read_bytes()
    old = git(remote, "show", "HEAD~1:.make/Makefile-sdcc").encode()
    head, rest = old.split(b"\n", 1)
    latin2 = head + b"\n# \xe8ip a frekvence (Latin-2)\n" + rest
    path.write_bytes(latin2)
    git(remote, "commit", "-q", "-am", "old toolchain in Latin-2")
    path.write_bytes(current)
    git(remote, "commit", "-q", "-am", "toolchain again")
    project = old_project(tmp_path / "project")
    (project / ".make" / "Makefile-sdcc").write_bytes(latin2)
    (project / "Makefile").write_bytes(_with_user_lines(latin2.decode("latin-1")).encode("latin-1"))
    commit_all(project)
    git(project, "fetch", "-q", str(remote), "main")
    report = upgrade.upgrade(project, "FETCH_HEAD")
    text = (project / "Makefile").read_bytes()
    assert report.makefile == "merged"
    assert b"<<<<<<<" not in text
    assert b"F_CPU=8000000" in text and re.search(rb"^DEVICE_FLASH=stm8s103f3$", text, re.M)
    assert b"-include .make/vscode.mk" in text


def test_main_reports_unexpected_failure(tmp_path, monkeypatch, capsys):
    project = prepared(tmp_path)

    def broken(*args):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(upgrade, "_refresh_make_dir", broken)
    code, out, err = run_main(project, monkeypatch, capsys, "FETCH_HEAD", "--json")
    assert code == 1
    assert "Update failed:" in err
    assert "No space left on device" in err
    assert "git checkout .make Makefile .vscode/launch.json" in err
    assert "Traceback" not in err


def test_main_refuses_committed_conflict_markers(tmp_path, monkeypatch, capsys):
    project = prepared(tmp_path)
    with open(project / "Makefile", "a") as handle:
        handle.write(CONFLICTED)
    commit_all(project)
    code, _, err = run_main(project, monkeypatch, capsys, "FETCH_HEAD", "--json")
    assert code == 1
    assert "unresolved conflict markers" in err


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


SHADOWING = 'raise ImportError("the project difflib.py was imported instead of the standard library")\n'


def test_upgrade_runs_via_python_dash_c(tmp_path):
    project = prepared(tmp_path)
    # with -c the current folder (the project) would come first in sys.path; -I leaves it out
    (project / "difflib.py").write_text(SHADOWING)
    (project / "json.py").write_text(SHADOWING)
    proc = subprocess.run(["python3", "-I", "-c", UPGRADE_PY.read_text(), "FETCH_HEAD", "--json"],
                          cwd=project, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.splitlines()[-1])["makefile"] == "merged"
    assert "-include .make/vscode.mk" in (project / "Makefile").read_text()


@pytest.mark.parametrize("name", ["README.md", "README.cs.md", "CLAUDE.md"])
def test_documented_commands_run_python_isolated(name):
    text = (ROOT / name).read_text(encoding="utf-8")
    assert 'python3 -I -c "$(git show FETCH_HEAD:.make/upgrade.py)" FETCH_HEAD' in text
    assert "python3 -c" not in text


def test_make_upgrade_runs_python_isolated():
    assert re.search(r"\$\(PYTHON\) -I -c ", (ROOT / ".make" / "vscode.mk").read_text())


def test_upgrade_script_is_self_contained():
    source = UPGRADE_PY.read_text()
    assert "__file__" not in source
    assert len(source.encode()) < 100_000


# --- .make/prune.txt ----------------------------------------------------------------------------

PRUNED_FILES = (".make/dev/a.js", ".make/dev/sub/b.js", ".make/dev-release.py")


def prunable_remote(tmp_path, prune_text):
    """toolchain_remote plus dev-only files and, when PRUNE_TEXT is not None, .make/prune.txt."""
    remote = toolchain_remote(tmp_path / "remote")
    for name in (*PRUNED_FILES, ".make/vscode/pack.py", ".make/y.sh", ".make/y2.sh"):
        (remote / name).parent.mkdir(parents=True, exist_ok=True)
        (remote / name).write_text(f"# {name}\n")
    if prune_text is not None:
        (remote / ".make" / "prune.txt").write_text(prune_text)
    commit_all(remote, "dev files")
    return remote


def fetched(tmp_path, prune_text):
    remote = prunable_remote(tmp_path, prune_text)
    project = old_project(tmp_path / "project")
    git(project, "fetch", "-q", str(remote), "main")
    return project


PRUNE_TEXT = "# dev-only\n\n.make/dev\n.make/dev-release.py\n.make/missing.md\n"


def test_prune_entries():
    assert upgrade.prune_entries(
        "# c\n\n  \n a/b \nc/d/\n./e\nf//g\n/abs\n\\win\nC:/x\n../up\na/../b\n..\n.\n.git\n.git/hooks\nx\nx\n") == [
        "a/b", "c/d", "e", "f/g", "x"]
    assert upgrade.prune_entries("") == []
    # .git in any spelling a case-insensitive or Windows file system maps to it, and dot-only segments
    assert upgrade.prune_entries(
        ".GIT\n.Git/hooks\n.git.\n.git \n.git. .\n...\na/.../b\na/.. /b\na/.git\na/.gitignore\n.gitignore\n") == [
        "a/.git", "a/.gitignore", ".gitignore"]


def test_upgrade_does_not_bring_pruned_paths(tmp_path):
    project = fetched(tmp_path / "pruned", PRUNE_TEXT)
    control = fetched(tmp_path / "control", "# nothing pruned\n")
    report = upgrade.upgrade(project, "FETCH_HEAD")
    full = upgrade.upgrade(control, "FETCH_HEAD")
    for name in PRUNED_FILES:
        assert not (project / name).exists(), name
        assert (control / name).is_file(), name
    for name in (".make/prune.txt", ".make/vscode/pack.py", ".make/y.sh"):
        assert (project / name).is_file(), name
    assert full.replaced - report.replaced == len(PRUNED_FILES)


def test_upgrade_leaves_existing_pruned_files_alone(tmp_path):
    project = fetched(tmp_path, PRUNE_TEXT)
    (project / ".make" / "dev").mkdir()
    (project / ".make" / "dev-release.py").write_text("# my copy\n")
    (project / ".make" / "dev" / "a.js").write_text("// my copy\n")
    commit_all(project)
    report = upgrade.upgrade(project, "FETCH_HEAD")
    assert (project / ".make" / "dev-release.py").read_text() == "# my copy\n"
    assert (project / ".make" / "dev" / "a.js").read_text() == "// my copy\n"
    assert not (project / ".make" / "dev" / "sub").exists()
    assert report.removed == 0


def test_upgrade_ignores_unsafe_prune_entries(tmp_path):
    project = fetched(tmp_path, "# unsafe\n.make/x/../y.sh\n/.make/y2.sh\n../project\n.make/..\n")
    upgrade.upgrade(project, "FETCH_HEAD")
    assert (project / ".make" / "y.sh").is_file()
    assert (project / ".make" / "y2.sh").is_file()
    assert (project / ".make" / "dev-release.py").is_file()


def test_upgrade_without_prune_txt_in_ref_brings_everything(tmp_path):
    project = fetched(tmp_path, None)
    upgrade.upgrade(project, "FETCH_HEAD")
    for name in PRUNED_FILES:
        assert (project / name).is_file(), name


def test_upgrade_with_pruned_paths_is_idempotent(tmp_path):
    project = fetched(tmp_path, PRUNE_TEXT)
    upgrade.upgrade(project, "FETCH_HEAD")
    commit_all(project, "upgraded")
    second = upgrade.upgrade(project, "FETCH_HEAD")
    assert second.makefile == "unchanged"
    assert second.replaced == 0
    assert second.removed == 0
    assert git(project, "status", "--porcelain") == ""
