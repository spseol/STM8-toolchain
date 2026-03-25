#!/usr/bin/env python3
# Soubor:  genru.py
# Datum:   29.02.2024 14:29
# Autor:   Marek Nožka, marek <@t> tlapicka <d.t> net
# Licence: GNU/GPL
# Popis:
############################################################################
import json
import re
from sys import argv
import os
import glob
import shutil

try:
    from pick import pick
except ImportError:
    from winpick import pick

############################################################################
DEFS = "-D_SDCC -D_SDCC_ -D__SDCC -D__SDCC__ -DSDCC_VERSION=40000".split()
DEVICES = "STM8S003 STM8S005 STM8S007 STM8S103 STM8S105 STM8S207 STM8S208 STM8S903"
PATH = "../SPLSPL/mk/{device}.mk"


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


def get_spl_files(path):
    pattern = re.compile(r"stm8s_[\d\w]+")
    spl_files = []
    with open(path, "r") as file:
        for line in file:
            line = line.split("#")[0]
            spl_files += re.findall(pattern, line)
    return list(map(lambda x: f"../SPL/src/{x}.c", spl_files))


if __name__ == "__main__":
    cc_root = argv[2] if len(argv) > 2 else None
    sdcc_inc = get_sdcc_include(cc_root)

    if len(argv) == 1:
        device, index = pick(DEVICES.split(), "Vyber cílové zařízení:")
        path = PATH.format(device=device)
    else:
        try:
            device = argv[1].upper()
            device = re.findall(rf"[\w\d]*{device}[\d\w]*", DEVICES)[0]
            path = PATH.format(device=device)
        except IndexError:
            path = "tento soubor prostě a jednoduše nemůže existovat!!!!!!!!!"

    if not os.path.isfile(path):
        print("Zadej existující mikrokontroler:")
        print(DEVICES)
        exit(1)

    print(device, path)

    spl_files = get_spl_files(path)
    src_files = glob.glob("src/*.c")

    compilel_commands = []
    for file in src_files + spl_files:
        record = {}
        record["directory"] = os.getcwd()
        record["file"] = file
        record["arguments"] = []
        record["arguments"] += ["sdcc", "-c"]
        if file in src_files:
            record["arguments"] += ["-Iinc"]
        record["arguments"] += ["-I../SPL/inc"]
        if sdcc_inc:
            record["arguments"] += [f"-I{sdcc_inc}"]
        record["arguments"] += [f"-D{device}"]
        record["arguments"] += DEFS
        record["arguments"] += [file]
        compilel_commands.append(record)

    with open("compile_commands.json", "w") as f:
        json.dump(compilel_commands, f, indent=True)
