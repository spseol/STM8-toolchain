#!/usr/bin/env python3
"""Release the VS Code extension: tests, VSIX, publish to Open VSX, tag, push, prepare Microsoft.

Usage: release.py [--dry-run]   (or `make vscode-release [DRY_RUN=1]`)

The Open VSX token comes from $OVSX_PAT or ~/.config/stm8-toolchain/ovsx-token. It is passed to
`ovsx` only through the environment of that one child process: never in argv (visible in `ps`),
never printed and never stored in the repository.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

BRANCH = "main"
REMOTES = ("origin", "github")
TOKEN_VAR = "OVSX_PAT"
# pinned: the token is handed to whatever npx resolves, so a new ovsx is adopted on purpose
# (how: .make/vscode/RELEASING.md)
OVSX_VERSION = "1.3.0"
TOKEN_FILE = Path.home() / ".config" / "stm8-toolchain" / "ovsx-token"
EXTENSION_DIR = Path(".make") / "vscode"  # relative to the repository root
VSIX = EXTENSION_DIR / "stm8-toolchain.vsix"
MARKETPLACE_URL = "https://marketplace.visualstudio.com/manage/publishers/spseol"


class Refused(Exception):
    """The release cannot proceed; the message is shown to the user as it is."""


def load_token(env, token_file):
    """The Open VSX token: $OVSX_PAT, else the stripped content of TOKEN_FILE; None when there is none."""
    token = env.get(TOKEN_VAR, "").strip()
    if token:
        return token
    try:
        return Path(token_file).read_text().strip() or None
    except OSError:
        return None


def redact(text, token):
    """TEXT with every occurrence of TOKEN (also in its URL-quoted form) replaced by ***."""
    if not token:
        return text
    for secret in {token, quote(token, safe="")}:
        text = text.replace(secret, "***")
    return text


class Releaser:
    """State of one release run; every external command goes through RUN (the subprocess.run contract)."""

    def __init__(self, root, run, env, token_file):
        self.root = Path(root)
        self.run = run
        self.token_file = token_file
        self.token = load_token(env, token_file)
        # the token reaches only the ovsx child, see publish()
        self.env = {key: value for key, value in env.items() if key != TOKEN_VAR}

    def call(self, cmd, env=None):
        """Run CMD in the repository root; a command that cannot even start gives returncode 127."""
        try:
            return self.run(cmd, cwd=self.root, env=self.env if env is None else env,
                            capture_output=True, text=True)
        except OSError as error:
            return SimpleNamespace(returncode=127, stdout="", stderr=f"{cmd[0]}: {error}")

    def show(self, result):
        """Print the output of a child process (never with the token)."""
        for stream, target in ((result.stdout, sys.stdout), (result.stderr, sys.stderr)):
            if stream and stream.strip():
                print(redact(stream.rstrip("\n"), self.token), file=target)

    def git(self, *args):
        return self.call(["git", *args])

    # --- step 1 and 2: the repository -----------------------------------------------------------

    def check_repository(self):
        status = self.git("status", "--porcelain")
        if status.returncode != 0:
            raise Refused("`git status` failed, is this a git repository?")
        if status.stdout.strip():
            raise Refused("The working tree is not clean, commit or stash your changes first.")
        branch = self.git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        if branch != BRANCH:
            raise Refused(f"Release only from the branch '{BRANCH}' (now on '{branch}'), merge the work first.")
        remotes = self.git("remote").stdout.split()
        for remote in REMOTES:
            if remote not in remotes:
                raise Refused(f"The git remote '{remote}' does not exist.")
        fetch = self.git("fetch", "origin")
        if fetch.returncode != 0:
            self.show(fetch)
            raise Refused("`git fetch origin` failed.")
        behind = self.git("rev-list", "--count", f"{BRANCH}..origin/{BRANCH}")
        if behind.returncode != 0:
            raise Refused(f"origin/{BRANCH} was not found.")
        if int(behind.stdout.strip() or 0) > 0:
            raise Refused(f"'{BRANCH}' is behind origin/{BRANCH}, run `git pull` first.")

    def check_version(self):
        package = json.loads((self.root / EXTENSION_DIR / "package.json").read_text())
        version = package["version"]
        tag = f"vscode-v{version}"
        if self.git("rev-parse", "-q", "--verify", f"refs/tags/{tag}").returncode == 0:
            raise Refused(f"The tag {tag} already exists, bump 'version' in {EXTENSION_DIR / 'package.json'}.")
        changelog = self.root / EXTENSION_DIR / "CHANGELOG.md"
        try:
            text = changelog.read_text(encoding="utf-8")
        except OSError:
            text = ""
        if not re.search(rf"^## {re.escape(version)}(?=\s|$)", text, re.M):
            raise Refused(f"{EXTENSION_DIR / 'CHANGELOG.md'} has no heading '## {version}', describe the release there first.")
        return version, tag

    # --- step 3 to 5: token, tests, VSIX --------------------------------------------------------

    def check_token(self):
        if not self.token:
            raise Refused(f"No Open VSX token. Set ${TOKEN_VAR} or put the token into {self.token_file} "
                          "(see .make/vscode/RELEASING.md).")

    def run_tests(self):
        node_tests = sorted((self.root / EXTENSION_DIR / "test").glob("*.test.js"))
        commands = [[sys.executable, "-m", "pytest", EXTENSION_DIR.as_posix()],
                    ["node", "--test", *(path.relative_to(self.root).as_posix() for path in node_tests)]]
        for cmd in commands:
            print("+", " ".join(cmd))
            result = self.call(cmd)
            if result.returncode != 0:
                self.show(result)
                raise Refused(f"Tests failed ({cmd[0]}), nothing was published.")

    def pack(self):
        cmd = [sys.executable, (EXTENSION_DIR / "pack.py").as_posix(), VSIX.as_posix()]
        print("+", " ".join(cmd))
        result = self.call(cmd)
        if result.returncode != 0:
            self.show(result)
            raise Refused("Packing the VSIX failed.")

    # --- step 6 to 8: publish, tag, push, Microsoft ---------------------------------------------

    def publish(self):
        cmd = ["npx", "--yes", f"ovsx@{OVSX_VERSION}", "publish", VSIX.as_posix()]
        print("+", " ".join(cmd))
        env = dict(self.env)
        env[TOKEN_VAR] = self.token  # the only place where the token leaves this process
        result = self.call(cmd, env=env)
        self.show(result)
        if result.returncode != 0:
            raise Refused("Publishing to Open VSX failed. No tag was created and nothing was pushed.")

    @staticmethod
    def finish_by_hand(version, tag, remotes, with_tag=False):
        """The commands that complete a release whose publish already happened."""
        lines = [f"  git tag -a {tag} -m 'STM8 Toolchain extension {version}'"] if with_tag else []
        lines += [f"  git push {remote} {BRANCH} {tag}" for remote in remotes]
        return "\n".join(lines)

    def tag_and_push(self, version, tag):
        result = self.git("tag", "-a", tag, "-m", f"STM8 Toolchain extension {version}")
        if result.returncode != 0:
            self.show(result)
            raise Refused(f"The extension is already PUBLISHED on Open VSX, but creating the tag {tag} failed. "
                          f"Finish by hand:\n{self.finish_by_hand(version, tag, REMOTES, with_tag=True)}")
        failed = []
        for remote in REMOTES:
            result = self.git("push", remote, BRANCH, tag)
            if result.returncode != 0:
                self.show(result)
                failed.append(remote)
        if failed:
            raise Refused(f"The extension is already PUBLISHED on Open VSX and tagged, but the push to "
                          f"{' and '.join(failed)} failed. Retry:\n{self.finish_by_hand(version, tag, failed)}")

    def finish(self):
        print(f"VSIX: {(self.root / VSIX).resolve()}")
        result = self.call(["xdg-open", MARKETPLACE_URL])
        if result.returncode != 0:
            print(f"Warning: could not open {MARKETPLACE_URL}, open it by hand.", file=sys.stderr)
        print("Upload the VSIX to the Microsoft Marketplace by hand (publishers page, ... > Update). "
              "Microsoft retires PATs on 2026-12-01, so there is no automatic upload.")


def release(root, *, dry_run=False, run=subprocess.run, env=os.environ, token_file=None):
    """Run the whole release in ROOT (the repository root); 0 on success, 1 with a message otherwise."""
    releaser = Releaser(root, run, env, TOKEN_FILE if token_file is None else token_file)
    try:
        releaser.check_repository()
        version, tag = releaser.check_version()
        if not dry_run:
            releaser.check_token()
        releaser.run_tests()
        releaser.pack()
        if dry_run:
            print(f"VSIX: {(releaser.root / VSIX).resolve()}")
            print("Dry run: nothing was published or tagged.")
            return 0
        releaser.publish()
        try:
            releaser.tag_and_push(version, tag)
            releaser.finish()
        except Refused:
            raise
        except BaseException as error:  # KeyboardInterrupt, a decoding error, ...
            print(redact(f"Stopped by {type(error).__name__}: {error}\nThe extension is already PUBLISHED on "
                         f"Open VSX. Finish by hand (skip the tag command when the tag exists):\n"
                         f"{releaser.finish_by_hand(version, tag, REMOTES, with_tag=True)}", releaser.token),
                  file=sys.stderr)
            return 1
    except Refused as refusal:
        print(redact(str(refusal), releaser.token), file=sys.stderr)
        return 1
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Release the VS Code extension to Open VSX.")
    parser.add_argument("--dry-run", action="store_true", help="run the checks, tests and packing only")
    args = parser.parse_args(argv)
    return release(Path(__file__).resolve().parents[2], dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
