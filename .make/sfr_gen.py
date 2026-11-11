#!/usr/bin/env python3
# Popis:   Připraví registry periferií (SFR) pro gdb (make debug).
#
#   Z stm8s.h vygeneruje sfr.c, kde je každá periferie proměnná na své
#   adrese: `__at(TIM4_BaseAddress) TIM4_TypeDef TIM4;`. SDCC z něj udělá
#   sfr.elf jen s ladicími informacemi (bez kódu). gdb ho načte přes
#   add-symbol-file a pak zná `TIM4->CR1` jako v C, i s doplňováním.
#
#   Vedle vznikne sfr.json: seznam periferií, číselná makra (bitové masky,
#   reset hodnoty) a jejich komentáře ze stm8s.h. Masky z něj
#   .make/stm8sfr.py nadefinuje jako makra gdb a podle nich rozepíše bity.
#
# Když se něco nepovede, vypíše varování a skončí s 0, ať ladění jde
# spustit i bez registrů.
############################################################################
import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

# `#define TIM4 ((TIM4_TypeDef *) TIM4_BaseAddress)`
PERIPH_RE = re.compile(
    r"^#define\s+(\w+)\s+\(\(\s*(\w+)_TypeDef\s*\*\s*\)\s*(\w+)\s*\)\s*$", re.M)
# `#define TIM4_CR1_CEN ((uint8_t)0x01)`, `#define GPIOA_BaseAddress 0x5000`
NUMBER_RE = re.compile(
    r"^#define\s+([A-Z]\w*)\s+(?:\(\(\s*uint(?:8|16|32)_t\s*\)\s*"
    r"(0[xX][0-9a-fA-F]+|\d+)\s*\)|(0[xX][0-9a-fA-F]+))\s*$", re.M)
TYPEDEF_RE = re.compile(r"\}\s*(\w+)_TypeDef\s*;")
# komentáře v originálním stm8s.h
COMMENT_RE = re.compile(
    r"^\s*#\s*define\s+(\w+)\s+.*?/\*!<\s*(.*?)\s*\*/", re.M)
STRUCT_RE = re.compile(r"typedef\s+struct\s*\w*\s*\{", re.M)
FIELD_RE = re.compile(r"\b(\w+)\s*;\s*/\*!<\s*(.*?)\s*\*/")

PROBE = '#define STM8S_IT_H  /* bez deklarací přerušení */\n#include "stm8s.h"\n'


def warn(msg):
    print(f"\033[1;33msfr_gen: {msg}\033[0m", file=sys.stderr)


def native_command(cmd):
    """Windows: Makefile předává `CC` jako cestu pro MSYS bash, `/c/Program\\ Files/SDCC/bin/sdcc`.
    python.exe (není z MSYS) ji nespustí (WinError 2), potřebuje `C:/Program Files/SDCC/bin/sdcc`.
    MSYS bash při předání argumentu nativnímu programu cestu ještě změní na
    `C:/Program/ Files/SDCC/bin/sdcc` (`\\ ` se stane `/ `), proto se obě podoby opraví.
    Jinde a u příkazů z PATH (`sdcc`, `stm8-objcopy`) se nic nemění."""
    if os.name != "nt":
        return cmd
    path = cmd.replace("\\ ", " ").replace("/ ", " ")
    m = re.match(r"^/([A-Za-z])/(.*)$", path)
    if m:
        path = f"{m.group(1).upper()}:/{m.group(2)}"
    # shutil.which() příponu .exe u cesty se složkou doplňuje až od Pythonu 3.12
    for candidate in (path, path + ".exe"):
        if os.path.isfile(candidate):
            return candidate
    return cmd


def run(cmd, **kw):
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, errors="replace", **kw)
    if proc.returncode:
        raise RuntimeError(f"{' '.join(cmd)}\n{proc.stderr.strip()}")
    return proc.stdout


def find_header(cflags):
    """stm8s.h, který najde překladač (stejné pořadí -I)."""
    dirs = [f[2:] for f in cflags if f.startswith("-I") and len(f) > 2]
    for d in dirs:
        path = os.path.join(d, "stm8s.h")
        if os.path.isfile(path):
            return path
    raise RuntimeError("stm8s.h nenalezen v " + " ".join(dirs))


def struct_comments(text):
    """{"TIM4": {"CR1": "control register 1", ...}} z typedef struct."""
    result = {}
    for m in STRUCT_RE.finditer(text):
        depth, i = 1, m.end()
        while depth and i < len(text):
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        name = TYPEDEF_RE.match(text, i - 1)
        if not name:
            continue
        fields = result.setdefault(name.group(1), {})
        for field, comment in FIELD_RE.findall(text[m.end():i]):
            fields.setdefault(field, comment)
    return result


def generate(cc, cflags, objcopy, out_elf):
    header = find_header(cflags)
    with tempfile.TemporaryDirectory() as tmp:
        probe = os.path.join(tmp, "probe.c")
        with open(probe, "w") as f:
            f.write(PROBE)
        macros = run([cc, *cflags, "-E", "-dM", probe])
        typedefs = set(TYPEDEF_RE.findall(run([cc, *cflags, "-E", probe])))

        # periferie, které čip má (DM má makro, ale ne DM_TypeDef)
        periphs = [(name, typ, base) for name, typ, base in PERIPH_RE.findall(macros)
                   if typ in typedefs]
        if not periphs:
            raise RuntimeError("no peripherals found in stm8s.h")

        # jen jména s podtržítkem (TIM4_CR1_CEN), ne obecná (AREA)
        numbers = {name: int(value or plain, 0)
                   for name, value, plain in NUMBER_RE.findall(macros) if "_" in name}
        periphs.sort(key=lambda p: numbers.get(p[2], 0))

        src = os.path.join(tmp, "sfr.c")
        with open(src, "w") as f:
            f.write("/* vygeneroval .make/sfr_gen.py */\n" + PROBE)
            for name, typ, base in periphs:
                f.write(f"#undef {name}\n__at({base}) {typ}_TypeDef {name};\n")
        rel = os.path.join(tmp, "sfr.rel")
        elf = os.path.join(tmp, "sfr.elf")
        # Windows: cesta ke zdroji po zpětných lomítkách (C:\Users\...\Temp\tmpXXXX\sfr.c) se zapíše do
        # ladicích informací SDCC a poškodí je (gdb: "Dwarf Error: Could not find abbrev number");
        # s lomítky dopředu je ELF v pořádku
        src_arg, rel_arg, elf_arg = (p.replace("\\", "/") if os.name == "nt" else p
                                     for p in (src, rel, elf))
        run([cc, *cflags, "--debug", "--out-fmt-elf", "-c", src_arg, "-o", rel_arg])
        # bez main a bez knihoven: v ELF jsou jen ladicí informace
        run([cc, "-mstm8", "--debug", "--out-fmt-elf", "--nostdlib", rel_arg, "-o", elf_arg])
        if not os.path.isfile(elf):
            raise RuntimeError("SDCC did not create sfr.elf")
        # symboly ELF jsou na adresách SFR typu FUNC, gdb stačí DWARF
        if objcopy and shutil.which(objcopy):
            run([objcopy, "-R", ".symtab", "-R", ".strtab", elf])

        with open(header, errors="replace") as f:
            text = f.read()
        info = {
            "peripherals": {name: typ for name, typ, _ in periphs},
            "macros": numbers,
            "comments": {n: c for n, c in COMMENT_RE.findall(text) if n in numbers},
            "regdesc": struct_comments(text),
        }
        out_json = os.path.splitext(out_elf)[0] + ".json"
        with open(out_json, "w") as f:
            json.dump(info, f, indent=1, sort_keys=True)
        # ELF až nakonec: je to cíl pro make
        shutil.copyfile(elf, out_elf)
    return len(periphs)


def main():
    # Windows: výstup do roury/konzole v 8bitovém kódování bez `→` by spadl na UnicodeEncodeError
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(
        description="Prepare peripheral registers (sfr.elf, sfr.json) for gdb.")
    parser.add_argument("--cc", default="sdcc")
    parser.add_argument("--cflags", default="-mstm8",
                        help="e.g. \"-mstm8 -DSTM8S208 -I inc -I ../SPLSPL/inc\"")
    parser.add_argument("--objcopy", default="stm8-objcopy")
    parser.add_argument("-o", "--output", required=True, help="output sfr.elf")
    args = parser.parse_args()
    try:
        count = generate(native_command(args.cc), shlex.split(args.cflags),
                         args.objcopy, args.output)
    except (OSError, RuntimeError) as e:
        warn(f"could not prepare peripheral registers for gdb:\n{e}")
        return 0
    print(f"sfr_gen: {count} peripherals → {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
