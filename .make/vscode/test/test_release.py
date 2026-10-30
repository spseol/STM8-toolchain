"""release.py: the checks, the order of the steps and the secrecy of the token.

Everything runs in a temporary repository with two local bare remotes (origin, github). The fake
`run` executes git for real and only records (and fakes) pytest, node, pack.py, npx and xdg-open,
so nothing is ever published, and nothing leaves the temp directory.
"""

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import ROOT, git

VERSION = "1.2.3"
TAG = f"vscode-v{VERSION}"
TOKEN = "s3cr3t-t0ken/with+chars"


def load_release():
    """The module .make/vscode/release.py (it is not importable as a package, like pack.py)."""
    spec = importlib.util.spec_from_file_location("release", ROOT / ".make" / "vscode" / "release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release_py = load_release()


class Runner:
    """Stands for subprocess.run: git runs for real, everything else is recorded and answered
    by REPLIES (program name -> (returncode, stdout, stderr)). HOOKS (program name -> function)
    run before the answer."""

    def __init__(self):
        self.calls = []  # (cmd, env)
        self.replies = {}
        self.hooks = {}

    def __call__(self, cmd, cwd=None, env=None, capture_output=None, text=None, **kwargs):
        assert capture_output and text, "release.py must capture text output of every child"
        self.calls.append((list(cmd), dict(env or {})))
        if cmd[0] == "git":
            return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
        if cmd[0] in self.hooks:
            self.hooks[cmd[0]]()
        code, out, err = self.replies.get(cmd[0], (0, "", ""))
        return SimpleNamespace(returncode=code, stdout=out, stderr=err)

    def commands(self):
        return [cmd for cmd, _ in self.calls]

    def programs(self):
        """Names of the non-git programs in the order of the calls (python3 -m pytest -> pytest)."""
        names = []
        for cmd in self.commands():
            if cmd[0] == "git":
                continue
            names.append("pytest" if cmd[:3] == ["python3", "-m", "pytest"] else
                         "pack" if cmd[0] == "python3" and cmd[1].endswith("pack.py") else cmd[0])
        return names


@pytest.fixture
def setup(tmp_path):
    """(repo, origin bare, github bare, env, token file, runner): repo on main, pushed to both remotes."""
    origin, github, repo = tmp_path / "origin.git", tmp_path / "github.git", tmp_path / "repo"
    for bare in (origin, github):
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "t")
    git(repo, "config", "user.email", "t@example.com")
    extension = repo / ".make" / "vscode"
    (extension / "test").mkdir(parents=True)
    (extension / "package.json").write_text(json.dumps({"name": "x", "publisher": "p", "version": VERSION}))
    (extension / "test" / "a.test.js").write_text("")
    (extension / "test" / "b.test.js").write_text("")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "remote", "add", "github", str(github))
    git(repo, "push", "-q", "origin", "main")
    git(repo, "push", "-q", "github", "main")
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "OVSX_PAT": TOKEN}
    return SimpleNamespace(repo=repo, origin=origin, github=github, env=env,
                           token_file=tmp_path / "no-such-token", runner=Runner(), tmp=tmp_path)


def do_release(s, dry_run=False, env=None):
    return release_py.release(s.repo, dry_run=dry_run, run=s.runner,
                              env=s.env if env is None else env, token_file=s.token_file)


def tags(repo):
    return git(repo, "tag", "-l").split()


def remote_refs(bare):
    return git(bare, "for-each-ref", "--format=%(refname)").split()


def assert_refused(s, capsys, *words):
    assert do_release(s) == 1
    assert not {"pytest", "node", "pack", "npx"} & set(s.runner.programs())
    assert tags(s.repo) == []
    err = capsys.readouterr().err
    for word in words:
        assert word in err
    assert TOKEN not in err


def test_refuses_dirty_tree(setup, capsys):
    (setup.repo / "untracked.txt").write_text("x")
    assert_refused(setup, capsys, "not clean")


def test_refuses_other_branch(setup, capsys):
    git(setup.repo, "checkout", "-q", "-b", "work")
    assert_refused(setup, capsys, "main", "work")


def test_refuses_when_behind_origin(setup, capsys):
    clone = setup.tmp / "clone"
    git(setup.tmp, "clone", "-q", str(setup.origin), str(clone))
    (clone / "new.txt").write_text("x")
    git(clone, "add", "-A")
    git(clone, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "other")
    git(clone, "push", "-q", "origin", "main")
    assert_refused(setup, capsys, "behind")


def test_refuses_missing_remote(setup, capsys):
    git(setup.repo, "remote", "remove", "github")
    assert_refused(setup, capsys, "github")


def test_refuses_existing_tag(setup, capsys):
    git(setup.repo, "tag", TAG)
    assert do_release(setup) == 1
    assert "npx" not in setup.runner.programs()
    assert tags(setup.repo) == [TAG]
    assert TAG in capsys.readouterr().err


def test_refuses_without_token(setup, capsys):
    setup.env.pop("OVSX_PAT")
    assert_refused(setup, capsys, "OVSX_PAT", str(setup.token_file))


def test_refuses_when_tests_fail(setup, capsys):
    setup.runner.replies["node"] = (1, "", "boom")
    assert do_release(setup) == 1
    assert "npx" not in setup.runner.programs()
    assert tags(setup.repo) == []
    assert "boom" in capsys.readouterr().err


def test_dry_run_publishes_nothing(setup, capsys):
    setup.env.pop("OVSX_PAT")  # a dry run needs no token
    before = (remote_refs(setup.origin), remote_refs(setup.github))
    assert do_release(setup, dry_run=True) == 0
    assert setup.runner.programs() == ["pytest", "node", "pack"]
    assert tags(setup.repo) == []
    assert (remote_refs(setup.origin), remote_refs(setup.github)) == before
    assert "Dry run: nothing was published or tagged." in capsys.readouterr().out
    assert not any(cmd[:2] in (["git", "push"], ["git", "tag"]) for cmd in setup.runner.commands())


def test_test_commands(setup):
    assert do_release(setup, dry_run=True) == 0
    commands = setup.runner.commands()
    assert ["python3", "-m", "pytest", ".make/vscode"] in commands
    assert ["node", "--test", ".make/vscode/test/a.test.js", ".make/vscode/test/b.test.js"] in commands
    pack = next(cmd for cmd in commands if cmd[0] == "python3" and cmd[1].endswith("pack.py"))
    assert pack[1:] == [".make/vscode/pack.py", ".make/vscode/stm8-toolchain.vsix"]


def test_full_release_order(setup, capsys):
    assert do_release(setup) == 0
    # tests -> pack -> publish -> tag -> push origin -> push github -> open the Marketplace page
    commands = setup.runner.commands()
    ordered = [cmd for cmd in commands if cmd[0] != "git" or cmd[1] in ("tag", "push")]
    assert [cmd[0] if cmd[0] != "git" else " ".join(cmd[:3]) for cmd in ordered] == [
        "python3", "node", "python3", "npx", f"git tag -a", "git push origin", "git push github", "xdg-open"]
    assert ["python3", "-m", "pytest", ".make/vscode"] == ordered[0]
    assert ordered[3] == ["npx", "ovsx", "publish", ".make/vscode/stm8-toolchain.vsix"]
    assert ordered[4][:4] == ["git", "tag", "-a", TAG]
    assert ordered[5] == ["git", "push", "origin", "main", TAG]
    assert ordered[6] == ["git", "push", "github", "main", TAG]
    assert ordered[7] == ["xdg-open", "https://marketplace.visualstudio.com/manage/publishers/spseol"]
    # the tag is annotated and in both remotes together with main
    assert git(setup.repo, "cat-file", "-t", TAG).strip() == "tag"
    for bare in (setup.origin, setup.github):
        assert sorted(remote_refs(bare)) == ["refs/heads/main", f"refs/tags/{TAG}"]
    # the token only in the environment of the ovsx call, never in argv, never printed
    for cmd, env in setup.runner.calls:
        assert not any(TOKEN in part for part in cmd)
        assert (env.get("OVSX_PAT") == TOKEN) == (cmd[0] == "npx")
    captured = capsys.readouterr()
    assert TOKEN not in captured.out + captured.err
    assert "stm8-toolchain.vsix" in captured.out
    assert "2026-12-01" in captured.out


def test_xdg_open_failure_is_only_a_warning(setup, capsys):
    setup.runner.replies["xdg-open"] = (3, "", "no browser")
    assert do_release(setup) == 0
    assert "Warning" in capsys.readouterr().err


def test_failed_publish_creates_no_tag_and_hides_token(setup, capsys):
    setup.runner.replies["npx"] = (1, f"uploading with {TOKEN}", f"401 bad token {TOKEN}; quoted s3cr3t-t0ken%2Fwith%2Bchars")
    assert do_release(setup) == 1
    assert tags(setup.repo) == []
    assert remote_refs(setup.origin) == ["refs/heads/main"]
    assert not any(cmd[:2] == ["git", "push"] for cmd in setup.runner.commands())
    captured = capsys.readouterr()
    assert TOKEN not in captured.out + captured.err
    assert "s3cr3t-t0ken%2Fwith%2Bchars" not in captured.out + captured.err
    assert "***" in captured.err


def test_push_failure_says_which_remote_and_how_to_retry(setup, capsys):
    # the publish succeeds, then the github remote disappears
    setup.runner.hooks["npx"] = lambda: shutil.rmtree(setup.github)
    assert do_release(setup) == 1
    assert tags(setup.repo) == [TAG]
    assert sorted(remote_refs(setup.origin)) == ["refs/heads/main", f"refs/tags/{TAG}"]
    err = capsys.readouterr().err
    assert "PUBLISHED" in err
    assert f"git push github main {TAG}" in err
    assert f"git push origin main {TAG}" not in err
    assert TOKEN not in err


def test_token_from_file(setup):
    setup.env.pop("OVSX_PAT")
    setup.token_file.write_text(f"  {TOKEN}\n")
    assert do_release(setup) == 0
    npx_env = next(env for cmd, env in setup.runner.calls if cmd[0] == "npx")
    assert npx_env["OVSX_PAT"] == TOKEN


def test_env_token_is_not_leaked_to_other_children(setup):
    assert do_release(setup) == 0
    assert all("OVSX_PAT" not in env for cmd, env in setup.runner.calls if cmd[0] != "npx")


def test_load_token_prefers_env(tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("from-file\n")
    assert release_py.load_token({"OVSX_PAT": "from-env"}, token_file) == "from-env"
    assert release_py.load_token({}, token_file) == "from-file"


def test_load_token_missing_or_empty(tmp_path):
    token_file = tmp_path / "token"
    assert release_py.load_token({}, token_file) is None
    token_file.write_text(" \n")
    assert release_py.load_token({}, token_file) is None
    assert release_py.load_token({"OVSX_PAT": "  "}, token_file) is None


def test_redact():
    assert release_py.redact("a TOK b TOK", "TOK") == "a *** b ***"
    assert release_py.redact("x%2Fy and x/y", "x/y") == "*** and ***"
    assert release_py.redact("nothing", "") == "nothing"
    assert release_py.redact("nothing", None) == "nothing"


def test_main_parses_dry_run(monkeypatch):
    seen = []
    monkeypatch.setattr(release_py, "release", lambda root, **kwargs: seen.append((root, kwargs)) or 0)
    assert release_py.main(["--dry-run"]) == 0
    assert release_py.main([]) == 0
    assert seen[0][0] == ROOT
    assert seen[0][1] == {"dry_run": True}
    assert seen[1][1] == {"dry_run": False}
