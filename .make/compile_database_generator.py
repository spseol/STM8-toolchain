#!/usr/bin/env python3
# Soubor:  compile_database_generator.py
# Datum:   29.02.2024 14:29
# Autor:   Marek Nožka, marek <@t> tlapicka <d.t> net
# Licence: GNU/GPL
# Popis:   Vytvoří compile_commands.json a .ccls pro language servery (ccls, clangd).
#          Flagy odpovídají tomu, co dělá Makefile (čip, F_CPU, -Iinc, SPL, verze SDCC).
#
#   compile_database_generator.py [DEVICE [CC_ROOT]] [--flag=FLAG ...]
#
#   DEVICE   čip (např. STM8S208); bez něj se zeptá.
#   CC_ROOT  kořen SDCC (bin/sdcc, share/sdcc/include); prázdný = sdcc z PATH.
#   --flag=FLAG  další flag pro každý soubor (např. --flag=-DF_CPU=16000000), lze víckrát
#            (se znakem = , jinak by argparse bral FLAG jako vlastní přepínač).
############################################################################
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

try:
    from pick import pick
except ImportError:
    from winpick import pick

############################################################################
DEVICES = "STM8S003 STM8S005 STM8S007 STM8S103 STM8S105 STM8S207 STM8S208 STM8S903"
MK_PATH = "../SPLSPL/mk/{device}.mk"
SPL_SRC = "../SPL/src"
SPL_INC = "../SPL/inc"
DEFAULT_SDCC_VERSION = (4, 0, 0)
# SDCC je v kódu rozpoznán podle __SDCC (stm8s.h si pak sám odvodí _SDCC_ a SDCC_VERSION);
# __CLANG zapíná v stm8s.h náhradu INTERRUPT_HANDLER, které clang nerozumí.
BASE_DEFS = ["-D__SDCC", "-D__SDCC_stm8", "-D__CLANG"]
# Funkční klíčová slova SDCC, kterým clang nerozumí; pro language server stačí, když zmizí.
SDCC_KEYWORDS = ["-D__naked=", "-D__trap="]
STD = "-std=c2x"
############################################################################


def sdcc_binary(cc_root=None):
    """Path of the sdcc executable: CC_ROOT/bin/sdcc if it exists, otherwise sdcc from PATH."""
    if cc_root:
        for name in ("sdcc", "sdcc.exe"):
            candidate = os.path.join(cc_root, "bin", name)
            if os.path.isfile(candidate):
                return candidate
    return shutil.which("sdcc")


def get_sdcc_include(cc_root=None):
    if cc_root:
        inc = os.path.join(cc_root, 'share', 'sdcc', 'include')
        if os.path.isdir(inc):
            return inc
    sdcc_path = shutil.which('sdcc')
    if sdcc_path:
        real_path = os.path.realpath(sdcc_path)
        sdcc_root = os.path.dirname(os.path.dirname(real_path))
        inc = os.path.join(sdcc_root, 'share', 'sdcc', 'include')
        if os.path.isdir(inc):
            return inc
    return None


def get_sdcc_version(binary):
    """(major, minor, patch) from `sdcc --version` ("... 4.4.0 #14620 ..."); DEFAULT_SDCC_VERSION on failure."""
    if not binary:
        return DEFAULT_SDCC_VERSION
    try:
        out = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return DEFAULT_SDCC_VERSION
    found = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", out)
    return tuple(int(x) for x in found.groups()) if found else DEFAULT_SDCC_VERSION


def get_spl_files(path):
    pattern = re.compile(r"stm8s_[\d\w]+")
    spl_files = []
    with open(path, "r") as file:
        for line in file:
            line = line.split("#")[0]
            spl_files += re.findall(pattern, line)
    return [f"{SPL_SRC}/{x}.c" for x in spl_files]


def common_flags(device, sdcc_inc, version, extra):
    """Flags that every file has, the project's and the SPL's."""
    flags = [STD, "-Iinc", f"-I{SPL_INC}"]
    if sdcc_inc:
        flags.append(f"-I{sdcc_inc}")
    flags.append(f"-D{device}")
    flags += BASE_DEFS + SDCC_KEYWORDS
    flags += [f"-D__SDCC_VERSION_{name}={value}" for name, value in zip(("MAJOR", "MINOR", "PATCH"), version)]
    return flags + list(extra)


def build_database(files, flags, directory):
    return [{"directory": directory, "file": file, "arguments": ["clang", "-c", *flags, file]}
            for file in files]


def tracked_in_git(path):
    """True when PATH is tracked by git (False also when git is missing or this is no repository)."""
    try:
        return subprocess.run(["git", "ls-files", "--error-unmatch", path], capture_output=True).returncode == 0
    except OSError:
        return False


def write_atomic(path, text):
    """Replace PATH in one step so that a language server never reads a half-written file."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), prefix=os.path.basename(path) + ".")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def ccls_text(flags):
    """The .ccls file: the compiler on the first line, then one flag per line."""
    return "\n".join(["clang", *flags]) + "\n"


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Generate compile_commands.json and .ccls")
    parser.add_argument("device", nargs="?")
    parser.add_argument("cc_root", nargs="?", default=None)
    parser.add_argument("--flag", action="append", default=[], metavar="FLAG")
    return parser.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    cc_root = args.cc_root or None

    if args.device is None:
        device, _index = pick(DEVICES.split(), "Select the target device:")
        path = MK_PATH.format(device=device)
    else:
        try:
            device = args.device.upper()
            device = re.findall(rf"[\w\d]*{device}[\d\w]*", DEVICES)[0]
            path = MK_PATH.format(device=device)
        except IndexError:
            path = "tento soubor prostě a jednoduše nemůže existovat!!!!!!!!!"

    if not os.path.isfile(path):
        print("Enter an existing microcontroller:")
        print(DEVICES)
        return 1

    print(device, path)

    spl_files = get_spl_files(path)
    src_files = sorted(glob.glob("src/*.c"))
    flags = common_flags(device, get_sdcc_include(cc_root), get_sdcc_version(sdcc_binary(cc_root)), args.flag)

    database = build_database(src_files + spl_files, flags, os.getcwd())
    write_atomic("compile_commands.json", json.dumps(database, indent=True) + "\n")

    if os.path.exists(".ccls") and tracked_in_git(".ccls"):
        print(".ccls is tracked by git and was left alone. To generate it: git rm --cached .ccls")
    else:
        write_atomic(".ccls", ccls_text(flags))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
