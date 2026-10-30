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
