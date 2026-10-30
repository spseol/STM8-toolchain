#!/usr/bin/env python3
"""Upgrade a student's project to the current STM8S toolchain.

Refreshes .make/ from the toolchain repository and merges the root Makefile.
Nothing is committed or staged. It may be run as `python3 -c "$(git show REF:.make/upgrade.py)"`,
so it must not depend on __file__ or on other files of .make/.
"""

import difflib
import subprocess
from pathlib import Path

REFUSE_RATIO = 0.4  # a Makefile differing from the closest variant in more lines is not ours
GUARDED_PATHS = (".make", "Makefile", ".vscode/launch.json")


class Refused(Exception):
    """The upgrade cannot proceed; the message is shown to the user as it is."""


class NeedsSwitch(Exception):
    """The project must first be switched to another toolchain version (attribute `variant`)."""

    def __init__(self, variant):
        super().__init__(variant)
        self.variant = variant


def _differences(a, b):
    """Number of lines in which the texts A and B differ (added plus removed)."""
    diff = difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=0)
    return sum(1 for line in diff if line[:1] in "+-" and not line.startswith(("+++", "---")))


def detect_variant(makefile, variants):
    """Key of the VARIANTS text closest to MAKEFILE; Refused when none is close enough."""
    if not variants:
        raise Refused("No Makefile variants to compare with.")
    best = min(variants, key=lambda key: _differences(makefile, variants[key]))
    lines = len(makefile.splitlines())
    if _differences(makefile, variants[best]) > REFUSE_RATIO * lines:
        raise Refused("The Makefile does not look like any of the toolchain Makefiles "
                      "(Makefile-sdcc, Makefile-sdcc-gas, Makefile-sdccrm), it will not be changed.")
    return best


def _git(project, *args):
    """Stdout of `git ARGS` in PROJECT; Refused with a plain message when git fails."""
    try:
        proc = subprocess.run(["git", *args], cwd=project, capture_output=True, text=True)
    except OSError as err:
        raise Refused(f"Cannot run git: {err}") from err
    if proc.returncode != 0:
        raise Refused(f"git {args[0]} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout


def check_project(project):
    """Refused unless PROJECT is a git repository with a commit, with a Makefile and
    .make/Makefile-sdcc, and without uncommitted changes in .make, Makefile and .vscode/launch.json."""
    project = Path(project)
    try:
        top = _git(project, "rev-parse", "--show-toplevel").strip()
    except Refused as err:
        raise Refused(f"{project} is not a git repository ({err}). Run the upgrade in the project folder.") from err
    if Path(top).resolve() != project.resolve():
        raise Refused(f"{project} is not the top folder of a git repository (that is {top}).")
    try:
        _git(project, "rev-parse", "--verify", "-q", "HEAD")
    except Refused as err:
        raise Refused("The git repository has no commit yet. Commit your work first.") from err
    if not (project / ".make" / "Makefile-sdcc").is_file():
        raise Refused("The project has no .make/Makefile-sdcc, it does not look like an STM8S toolchain project.")
    if not (project / "Makefile").is_file():
        raise Refused("The project has no Makefile.")
    changed = _git(project, "status", "--porcelain", "--", *GUARDED_PATHS).strip()
    if changed:
        raise Refused("There are uncommitted changes in .make, Makefile or .vscode/launch.json. "
                      f"Commit or discard them first:\n{changed}")
