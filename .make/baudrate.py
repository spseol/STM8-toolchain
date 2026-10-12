#!/usr/bin/env python3
# Popis:   Zjistí baud rate, který projekt nastavuje na UARTu.
#
#   1. V C zdrojácích prohnaných preprocesorem hledá volání UARTx_Init()
#      a vyhodnotí první argument (makra jsou rozbalená).
#   2. Když volání nenajde, hledá v *.asm z build adresáře zápisy do
#      registrů BRR1/BRR2 a baud rate dopočítá z F_CPU.
#
# Výsledek vypíše na stdout (jen číslo), komentář na stderr.
# Když nic nenajde, nevypíše na stdout nic.
############################################################################
import argparse
import ast
import bisect
import glob
import operator
import os
import re
import shlex
import shutil
import subprocess
import sys

STANDARD_RATES = (1200, 2400, 4800, 9600, 14400, 19200, 28800, 38400, 57600,
                  76800, 115200, 230400, 250000, 460800, 500000, 921600,
                  1000000)

# báze UARTů: 0x5230 = UART1, 0x5240 = UART2 (STM8S105) nebo UART3 (STM8S208)
UART_BASES = {0x5230: "UART1", 0x5240: "UART2/3"}

CAST_RE = re.compile(
    r"\(\s*(?:(?:const|volatile|unsigned|signed|long|short|int|char"
    r"|u?int(?:8|16|32)_t|u8|u16|u32)\s*)+\)")
SUFFIX_RE = re.compile(r"\b(0[xX][0-9a-fA-F]+|\d+)[uUlL]+\b")
DECL_RE = re.compile(r"^[A-Za-z_]\w*(?:\s+|\s*\*\s*)[A-Za-z_]\w*$")
LINE_MARKER_RE = re.compile(r'^#\s*(?:line\s+)?(\d+)\s+"([^"]*)"')
DEFINE_RE = re.compile(r"^\s*#\s*define\s+([A-Za-z_]\w*)[ \t]+(.+?)\s*$",
                       re.M)
INIT_RE = re.compile(r"\b(UART[1-4])_Init\s*\(")

OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.floordiv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.LShift: operator.lshift,
    ast.RShift: operator.rshift, ast.BitOr: operator.or_,
    ast.BitAnd: operator.and_, ast.BitXor: operator.xor,
    ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Invert: operator.inv,
}


def log(msg):
    print(f"baudrate: {msg}", file=sys.stderr)


def c_eval(expr):
    """Vyhodnotí konstantní C výraz; při neúspěchu vrátí None."""
    expr = CAST_RE.sub("", expr)
    expr = SUFFIX_RE.sub(r"\1", expr)

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value,
                                                         (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            return OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
            return OPS[type(node.op)](ev(node.operand))
        raise ValueError(expr)

    try:
        return int(ev(ast.parse(expr.strip(), mode="eval")))
    except (SyntaxError, ValueError, TypeError, ZeroDivisionError):
        return None


def first_argument(text, start):
    """Vrátí text prvního argumentu volání; start ukazuje za '('."""
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                return text[start:i]
            depth -= 1
        elif ch == "," and depth == 0:
            return text[start:i]
    return None


def preprocess(cc, cpp_flags, source):
    """Vrátí (text, [(soubor, řádek)] pro každý řádek) nebo None."""
    if not cc:
        return None
    try:
        res = subprocess.run([cc, "-E", *cpp_flags, source],
                             capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
    except OSError:
        return None
    if res.returncode != 0:
        return None
    lines, where = [], []
    fname, lineno = source, 1
    for line in res.stdout.splitlines():
        m = LINE_MARKER_RE.match(line)
        if m:
            lineno, fname = int(m.group(1)), m.group(2)
            line = ""
        elif line.startswith("#"):
            line = ""
        lines.append(line)
        where.append((fname, lineno))
        if not m:
            lineno += 1
    return lines, where


def raw_source(source, defines):
    """Záložní varianta bez preprocesoru: jen jednoduchá makra."""
    with open(source, encoding="utf-8", errors="replace") as f:
        text = f.read()
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group().count("\n"),
                  text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    for _ in range(5):
        new = re.sub(r"\b[A-Za-z_]\w*\b",
                     lambda m: defines.get(m.group(), m.group()), text)
        if new == text:
            break
        text = new
    lines = text.splitlines()
    return lines, [(source, i + 1) for i in range(len(lines))]


def collect_defines(paths, cpp_flags):
    defines = {}
    flags = iter(cpp_flags)
    for flag in flags:
        if flag.startswith("-D"):
            name, _, value = (flag[2:] or next(flags, "")).partition("=")
            defines[name] = value or "1"
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as f:
            for name, value in DEFINE_RE.findall(f.read()):
                defines.setdefault(name, re.sub(r"//.*|/\*.*", "", value))
    return defines


def from_c(sources, cc, cpp_flags, inc_dir):
    results = []
    defines = None
    for source in sources:
        pre = preprocess(cc, cpp_flags, source)
        if pre is None:
            if defines is None:
                defines = collect_defines(
                    sources + glob.glob(os.path.join(inc_dir, "*.h")),
                    cpp_flags)
            pre = raw_source(source, defines)
        lines, where = pre
        text = "\n".join(lines)
        starts = [0]
        for line in lines:
            starts.append(starts[-1] + len(line) + 1)
        for m in INIT_RE.finditer(text):
            arg = first_argument(text, m.end())
            if arg is None:
                continue
            arg = " ".join(arg.split())
            fname, lineno = where[bisect.bisect_right(starts, m.start()) - 1]
            baud = c_eval(arg)
            if baud is None:
                if not DECL_RE.match(arg):  # prototyp funkce není chyba
                    log(f"{fname}:{lineno}: {m.group(1)}_Init({arg}, …) "
                        "nelze vyhodnotit")
                continue
            results.append((m.group(1), baud,
                            f"{fname}:{lineno}, {m.group(1)}_Init"))
    return results


def snap(baud):
    for rate in STANDARD_RATES:
        if abs(baud - rate) <= rate * 0.025:
            return rate
    return round(baud)


def from_asm(asm_dir, f_cpu):
    """Hledá zápisy do BRR1 (base+2) a BRR2 (base+3)."""
    imm = r"#(0x[0-9a-fA-F]+|\d+)"
    reg = r"0x([0-9a-fA-F]{4})(?:\+0)?"
    mov_re = re.compile(rf"^\s*mov\s+{reg}\s*,\s*(\S+)")
    clr_re = re.compile(rf"^\s*clr\s+{reg}\s*$")
    st_a_re = re.compile(rf"^\s*ld\s+{reg}\s*,\s*a\s*$")
    ld_a_re = re.compile(rf"^\s*ld\s+a\s*,\s*{imm}")
    src_re = re.compile(r"^;\s+(\S+\.c):\s+(\d+):")
    a_dest_re = re.compile(r"^\s*[a-z]+\s+a\b|^\S+:|^\s*call\b")

    results = []
    for path in sorted(glob.glob(os.path.join(asm_dir, "*.asm"))):
        brr2 = {base: 0 for base in UART_BASES}
        a = None
        where = path
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = src_re.match(line)
                if m:
                    where = f"{m.group(1)}:{m.group(2)}"
                    continue
                if line.lstrip().startswith(";"):
                    continue
                addr = value = None
                if m := mov_re.match(line):
                    addr, value = int(m.group(1), 16), None
                    if m2 := re.fullmatch(imm, m.group(2)):
                        value = int(m2.group(1), 0)
                elif m := clr_re.match(line):
                    addr, value = int(m.group(1), 16), 0
                elif m := st_a_re.match(line):
                    addr, value = int(m.group(1), 16), a
                elif m := ld_a_re.match(line):
                    a = int(m.group(1), 0)
                    continue
                elif re.match(r"^\s*clr\s+a\s*$", line):
                    a = 0
                    continue
                elif a_dest_re.match(line):
                    a = None
                    continue
                if addr is None or addr - (addr & ~0xf) not in (2, 3):
                    continue
                base = addr & ~0xf
                if base not in UART_BASES:
                    continue
                if value is None:
                    log(f"{where}: zápis do BRR nelze vyhodnotit")
                    continue
                if addr - base == 3:
                    brr2[base] = value
                    continue
                # zápis do BRR1 nastaví dělič (BRR2 se zapisuje před BRR1)
                div = ((brr2[base] & 0xf0) << 8) | (value << 4) \
                    | (brr2[base] & 0x0f)
                if div < 16:
                    continue
                baud = snap(f_cpu / div)
                results.append((UART_BASES[base], baud,
                                f"{where}, BRR1=0x{value:02x} "
                                f"BRR2=0x{brr2[base]:02x}, "
                                f"F_CPU={f_cpu}"))
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cc", default="sdcc", help="překladač (sdcc)")
    p.add_argument("--cpp", default="", help="flagy pro preprocesor")
    p.add_argument("--fcpu", type=int, default=16000000)
    p.add_argument("--asm", default=None, help="adresář s *.asm")
    p.add_argument("--inc", default="inc", help="adresář s *.h projektu")
    p.add_argument("sources", nargs="*")
    args = p.parse_args()

    cc = args.cc if os.access(args.cc, os.X_OK) else shutil.which(args.cc)
    cc = cc or shutil.which("sdcc")
    sources = [s for s in args.sources if os.path.isfile(s)]

    results = from_c(sources, cc, shlex.split(args.cpp), args.inc)
    if not results and args.asm:
        results = from_asm(args.asm, args.fcpu)
    if not results:
        log("v projektu jsem baud rate nenašel")
        return

    uart1 = [r for r in results if r[0] == "UART1"]
    chosen = (uart1 or results)[0]
    others = {r[1] for r in results if r[0] == chosen[0]} - {chosen[1]}
    if others:
        log(f"pozor, {chosen[0]} se nastavuje i na "
            + ", ".join(map(str, sorted(others))))
    log(f"{chosen[1]} ({chosen[2]})")
    print(chosen[1])


if __name__ == "__main__":
    main()
