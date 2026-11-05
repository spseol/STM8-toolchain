#!/usr/bin/env python3
"""Upgrade a student's project to the current STM8S toolchain.

Refreshes .make/ from the toolchain repository and merges the root Makefile.
Nothing is committed or staged. It may be run as `python3 -I -c "$(git show REF:.make/upgrade.py)"`,
so it must not depend on its own path or on other files of .make/.
"""

import argparse
import dataclasses
import difflib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

REFUSE_RATIO = 0.4  # a Makefile differing from the closest variant in more lines is not ours
GUARDED_PATHS = (".make", "Makefile", ".vscode/launch.json")
VARIANT_FILES = {"sdcc": "Makefile-sdcc", "sdcc-gas": "Makefile-sdcc-gas", "sdccrm": "Makefile-sdccrm"}
DEVICE_FLASH = re.compile(r"^[ \t]*(DEVICE_FLASH=)(stm8\w+)[ \t]*$", re.M)  # like .make/switch_device.sh
CONFLICT_MARKER = re.compile(rb"^<{7} ", re.M)
HISTORY_LIMIT = 200  # versions of .make/Makefile-sdcc in the toolchain history searched for the merge base


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
    if CONFLICT_MARKER.search((project / "Makefile").read_bytes()):
        raise Refused("The Makefile still has unresolved conflict markers (<<<<<<<) from a previous update. "
                      "Resolve them, commit, then update again.")
    changed = _git(project, "status", "--porcelain", "--", *GUARDED_PATHS).strip()
    if changed:
        raise Refused("There are uncommitted changes in .make, Makefile or .vscode/launch.json. "
                      f"Commit or discard them first:\n{changed}")


@dataclass
class Report:
    replaced: int = 0  # files of .make/ that were created or changed
    removed: int = 0  # files of .make/ that the toolchain no longer has
    makefile: str = "unchanged"  # "merged" | "conflict" | "unchanged" | "switched"
    launch: str = "unchanged"  # "replaced" | "added" | "unchanged"
    backup: str = None  # copy of an untracked .vscode/launch.json
    gitignore_added: list = field(default_factory=list)
    notes: list = field(default_factory=list)


def _git_bytes(project, *args, check=True):
    """(returncode, stdout bytes) of `git ARGS` in PROJECT; Refused when git fails and CHECK is set."""
    try:
        proc = subprocess.run(["git", *args], cwd=project, capture_output=True)
    except OSError as err:
        raise Refused(f"Cannot run git: {err}") from err
    if check and proc.returncode != 0:
        raise Refused(f"git {args[0]} failed: {proc.stderr.decode(errors='replace').strip()}")
    return proc.returncode, proc.stdout


def _tree(project, ref, path):
    """{path: (mode, blob id)} of the files under PATH in REF (symlinks and submodules left out)."""
    out = _git_bytes(project, "ls-tree", "-r", "-z", ref, "--", path)[1]
    files = {}
    for entry in filter(None, out.split(b"\0")):
        meta, name = entry.split(b"\t", 1)
        mode, kind, blob = meta.decode().split()
        if kind == "blob" and mode in ("100644", "100755"):
            files[name.decode()] = (mode, blob)
    return files


def _show(project, ref, path):
    """Content of PATH in REF as bytes, None when REF has no such file."""
    code, out = _git_bytes(project, "cat-file", "blob", f"{ref}:{path}", check=False)
    return out if code == 0 else None


def _history(project, ref, path):
    """Distinct contents (bytes) of PATH in the newest HISTORY_LIMIT commits of REF that changed it."""
    revs = _git_bytes(project, "rev-list", "--full-history", f"--max-count={HISTORY_LIMIT}", ref, "--", path)[1].split()
    query = b"".join(rev + b":" + path.encode() + b"\n" for rev in revs)
    try:
        out = subprocess.run(["git", "cat-file", "--batch"], cwd=project, input=query,
                             capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as err:
        raise Refused(f"Cannot read the toolchain history: {err}") from err
    versions, pos = {}, 0
    while pos < len(out):
        end = out.index(b"\n", pos)
        header = out[pos:end].split()
        pos = end + 1
        if len(header) == 3 and header[1] == b"blob":
            size = int(header[2])
            versions.setdefault(header[0], out[pos:pos + size])
            pos += size + 1
    return list(versions.values())


def _merge_base(project, ref, path, head, theirs):
    """The version of PATH in the history of REF closest to HEAD (the project's committed copy,
    bytes; the student may have edited it). None when there is no version close enough to trust.
    THEIRS (the new version) is no base: merging against it would never show what changed."""
    versions = _history(project, ref, path)
    if head is None or not versions:
        return None
    if head in versions:
        return head
    text = head.decode(errors="replace")
    distance, best = min(((_differences(text, data.decode(errors="replace")), index)
                          for index, data in enumerate(versions)))
    if distance > REFUSE_RATIO * len(text.splitlines()) or versions[best] == theirs:
        return None
    return versions[best]


def _merge_makefile(project, ours, base, theirs):
    """Three-way merge of OURS (the project Makefile) with the toolchain change BASE -> THEIRS
    (bytes; BASE None merges two-way: every difference is a conflict). Returns (merged bytes,
    number of conflicts)."""
    with tempfile.TemporaryDirectory() as tmp:
        mine, old, new = Path(tmp, "mine"), Path(tmp, "old"), Path(tmp, "new")
        mine.write_bytes(ours)
        old.write_bytes(base or b"")
        new.write_bytes(theirs)
        try:
            proc = subprocess.run(
                ["git", "merge-file", "-p", "-L", "Makefile", "-L", "old .make/Makefile-sdcc",
                 "-L", "new .make/Makefile-sdcc", str(mine), str(old), str(new)],
                cwd=project, capture_output=True)
        except OSError as err:
            raise Refused(f"Cannot run git: {err}") from err
    if proc.returncode < 0 or proc.returncode > 127:
        raise Refused(f"git merge-file failed: {proc.stderr.decode(errors='replace').strip()}")
    return proc.stdout, proc.returncode


def _switched_makefile(current, theirs, report):
    """New Makefile-sdcc (bytes) with the active DEVICE_FLASH of the CURRENT Makefile."""
    active = DEVICE_FLASH.search(current.decode(errors="replace"))
    if not active:
        report.notes.append("The old Makefile had no active DEVICE_FLASH line, so the default of the new "
                            "Makefile was kept. Check DEVICE_FLASH in the Makefile.")
        return theirs
    return DEVICE_FLASH.sub(lambda m: m.group(1) + active.group(2), theirs.decode(), count=1).encode()


def _write(path, data, mode=None):
    """Write DATA to PATH; True when the file was created or its content changed."""
    changed = not path.is_file() or path.read_bytes() != data
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    if mode:
        current = stat.S_IMODE(path.stat().st_mode)
        wanted = current | 0o111 if mode == "100755" else current & ~0o111
        if wanted != current:
            path.chmod(wanted)
    return changed


def prune_entries(text):
    """Entries of .make/prune.txt (TEXT): paths relative to the project, one per line, `#` comments
    and blank lines skipped. Absolute paths, backslashes, `..` segments and .git (in any case) are left out, the
    list comes from a downloaded repository. Same rules as in newproject.js and stm8newproject."""
    entries = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "/")) or "\\" in line or re.match(r"[A-Za-z]:", line):
            continue
        parts = [part for part in line.split("/") if part and part != "."]
        # a segment of dots and spaces is `..` on Windows, `.GIT` and `.git.` are .git on case-insensitive file systems
        if not parts or any(re.fullmatch(r"[. ]+", part) for part in parts) or re.sub(r"[. ]+$", "", parts[0]).lower() == ".git":
            continue
        entries.append("/".join(parts))
    return list(dict.fromkeys(entries))


def _pruned(name, entries):
    """True when NAME is one of the prune ENTRIES or below one."""
    return any(name == entry or name.startswith(entry + "/") for entry in entries)


def _refresh_make_dir(project, ref, new_files, report):
    """Replace the files of .make/ by those of REF and delete the tracked ones REF lacks.
    What REF:.make/prune.txt lists is neither created nor replaced (students do not have it),
    a copy that already exists is left as it is."""
    old_files = _tree(project, "HEAD", ".make")
    pruned = prune_entries((_show(project, ref, ".make/prune.txt") or b"").decode(errors="replace"))
    for name, (mode, blob) in new_files.items():
        if _pruned(name, pruned):
            continue
        data = _git_bytes(project, "cat-file", "blob", blob)[1]
        if _write(project / name, data, mode):
            report.replaced += 1
    for name in old_files:
        path = project / name
        if name not in new_files and path.is_file():
            path.unlink()
            report.removed += 1
            for parent in path.parents:
                if parent == project / ".make" or any(parent.iterdir()):
                    break
                parent.rmdir()


def _update_gitignore(project, ref, report):
    """Append the lines of REF:.gitignore that the project .gitignore does not have yet."""
    wanted = (_show(project, ref, ".gitignore") or b"").decode().splitlines()
    path = project / ".gitignore"
    text = path.read_text() if path.is_file() else ""
    have = set(text.splitlines())
    for line in wanted:
        if line.strip() and line not in have:
            have.add(line)
            report.gitignore_added.append(line)
    if report.gitignore_added:
        prefix = "" if not text or text.endswith("\n") else "\n"
        path.write_text(text + prefix + "\n".join(report.gitignore_added) + "\n")


def _save_backup(path):
    """Copy PATH to PATH.bak, PATH.bak.1, ... without overwriting anything; the first
    existing backup with the same content is reused. Returns the backup path."""
    data = path.read_bytes()
    index = 0
    while True:
        backup = path.with_name(path.name + (".bak" if index == 0 else f".bak.{index}"))
        if not backup.exists():
            backup.write_bytes(data)
            return backup
        if backup.is_file() and backup.read_bytes() == data:
            return backup
        index += 1


def _update_launch(project, ref, report):
    """Replace .vscode/launch.json by the toolchain one; save an untracked original as .bak."""
    new = _show(project, ref, ".vscode/launch.json")
    if new is None:
        return
    path = project / ".vscode" / "launch.json"
    if path.is_file() and path.read_bytes() == new:
        return
    if path.is_file():
        tracked = _git_bytes(project, "ls-files", "--error-unmatch", ".vscode/launch.json", check=False)[0] == 0
        if not tracked:
            report.backup = str(_save_backup(path))
    report.launch = "replaced" if path.is_file() else "added"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(new)


def upgrade(project, ref, switch=None):
    """Upgrade PROJECT to the toolchain in the git ref REF (already fetched into the project
    repository). SWITCH answers the question whether to move from another Makefile variant to
    Makefile-sdcc ("yes"/"no"). Nothing is committed or staged."""
    project = Path(project)
    check_project(project)
    new_files = _tree(project, ref, ".make")
    if ".make/Makefile-sdcc" not in new_files:
        raise Refused(f"{ref} does not contain .make/Makefile-sdcc, it is not the STM8S toolchain.")
    variants = {}
    for key, name in VARIANT_FILES.items():
        data = _show(project, "HEAD", f".make/{name}")
        if data is not None:
            variants[key] = data.decode(errors="replace")
    makefile = project / "Makefile"
    link = os.readlink(makefile) if makefile.is_symlink() else None
    current = makefile.read_bytes()  # through a symlink: the student's .make/Makefile-<variant>, read before .make/ is refreshed
    variant = detect_variant(current.decode(errors="replace"), variants)
    if variant != "sdcc":
        if switch is None:
            raise NeedsSwitch(variant)
        if switch != "yes":
            raise Refused("Update cancelled, nothing was changed.")
    theirs = _show(project, ref, ".make/Makefile-sdcc")

    report = Report()
    if variant == "sdcc":
        path = ".make/Makefile-sdcc"
        base = _merge_base(project, ref, path, _show(project, "HEAD", path), theirs)
        result, conflicts = _merge_makefile(project, current, base, theirs)
        if base is None:
            report.notes.append("No toolchain version close to the project's .make/Makefile-sdcc was found, so every "
                                "difference from the new Makefile is marked as a conflict.")
        report.makefile = "conflict" if conflicts else ("unchanged" if result == current else "merged")
        before, after = (DEVICE_FLASH.search(text.decode(errors="replace")) for text in (current, result))
        if not conflicts and (before and before.group(2)) != (after and after.group(2)):
            report.notes.append(f"DEVICE_FLASH changed from {before and before.group(2)} to "
                                f"{after and after.group(2)} in the merge. Check DEVICE_FLASH in the Makefile.")
    else:
        result = _switched_makefile(current, theirs, report)
        report.makefile = "switched"

    _refresh_make_dir(project, ref, new_files, report)
    if link is not None:  # never write through it: it points into the refreshed .make/
        makefile.unlink()
        makefile.write_bytes(result)
        report.notes.append(f"Makefile was a symlink to {link}; it is now a regular file.")
    elif result != current:
        makefile.write_bytes(result)
    _update_gitignore(project, ref, report)
    _update_launch(project, ref, report)
    return report


def _ask_switch(variant):
    """Ask on the terminal whether to switch from VARIANT to Makefile-sdcc; "yes" or "no"."""
    print(f"The project uses the older toolchain variant {variant}. The update replaces its Makefile "
          "with the current Makefile-sdcc (only DEVICE_FLASH is kept; the old one stays in git history).")
    while True:
        try:
            answer = input("Switch to Makefile-sdcc? [yes/no] ").strip().lower()
        except EOFError:
            return "no"
        if answer in ("y", "yes"):
            return "yes"
        if answer in ("n", "no"):
            return "no"


def _summary(report):
    lines = [f"Updated .make/: {report.replaced} files replaced, {report.removed} removed.",
             f"Makefile: {report.makefile}."]
    if report.makefile == "conflict":
        lines.append("The Makefile has conflict markers (<<<<<<<); resolve them by hand.")
    lines.append(f"launch.json: {report.launch}" + (f" (original saved as {report.backup})." if report.backup else "."))
    if report.gitignore_added:
        lines.append("Added to .gitignore: " + ", ".join(report.gitignore_added))
    lines += report.notes
    lines.append("Nothing was committed. Review the changes with `git status` and `git diff`.")
    return lines


def _use_color():
    """Color in a terminal. stdin is checked as well as stderr: `make -Otarget -jN` (the toolchain
    Makefile sets it) makes stderr a pipe even in a terminal, but stdin stays the terminal. Under the
    VS Code extension both are pipes, so its messages stay plain."""
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    return sys.stderr.isatty() or sys.stdin.isatty()


def _error(text):
    """Print TEXT as an error on stderr, red in a terminal."""
    print(f"\033[1;31m{text}\033[0m" if _use_color() else text, file=sys.stderr)


def main(argv):
    parser = argparse.ArgumentParser(description="Upgrade the project to the current STM8S toolchain.")
    parser.add_argument("ref", help="git ref with the fetched toolchain, e.g. FETCH_HEAD")
    parser.add_argument("--switch", choices=("yes", "no"), help="answer to the Makefile variant switch question")
    parser.add_argument("--json", action="store_true", help="print the report as JSON on the last line")
    args = parser.parse_args(argv)
    project = Path(os.getcwd())
    switch = args.switch
    try:
        try:
            report = upgrade(project, args.ref, switch)
        except NeedsSwitch as need:
            if switch is not None or not sys.stdin.isatty():
                print(json.dumps({"needsSwitch": need.variant}))
                return 3
            report = upgrade(project, args.ref, _ask_switch(need.variant))
    except Refused as err:
        _error(str(err))
        return 1
    except Exception as err:  # OSError, UnicodeError, ...: say what to do instead of a traceback
        _error(f"Update failed: {err}. .make/ may be partly updated; `git status` shows what changed and "
               "`git checkout .make Makefile .vscode/launch.json` restores it.")
        return 1
    print("\n".join(_summary(report)))
    if args.json:
        print(json.dumps(dataclasses.asdict(report)))
    return 2 if report.makefile == "conflict" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
