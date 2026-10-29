# Registry periferií (SFR) v gdb: TIM4->CR1 jako v C, bitové masky ze stm8s.h
# jako makra gdb (SPI_CR2_SSM), příkaz `sfr` s rozpisem bitů a zvýraznění změn
# od minulého zastavení (sfr, print, display).
# sfr.elf a sfr.json připraví .make/sfr_gen.py (make debug) do build-*-elf/.
# Načítá se z .make/gdbinit po stm8gdb.py, používá jeho say, warn,
# target_running a NAME_COLOR.
import json
import os
import re

import gdb

CHANGE_COLOR = "1;33"  # změněná hodnota, bity a číslice
CLEARED_COLOR = "2"  # vynulovaný bit: -UIF

# Čtení těchto registrů maže příznaky, `sfr PERIFERIE` je proto nečte.
READ_SIDE_EFFECT = {
    "UART1": {"DR"},  # RXNE, s SR i OR, NF, FE, PE
    "UART2": {"DR"},
    "UART3": {"DR"},
    "UART4": {"DR"},
    "SPI": {"DR"},  # RXNE, OVR
    "I2C": {"DR", "SR3"},  # RXNE; SR1 a pak SR3 maže ADDR
    "FLASH": {"IAPSR"},  # EOP, WR_PG_DIS
    "AWU": {"CSR"},  # AWUF
}


class Reg:
    def __init__(self, periph, name, addr, bits, reset, desc):
        self.periph = periph  # jméno periferie (GPIOB)
        self.name = name  # jméno registru (ODR)
        self.addr = addr
        self.bits = bits  # [(jméno, maska, komentář)], od nejvyššího bitu
        self.reset = reset
        self.desc = desc
        self.side_effect = name in READ_SIDE_EFFECT.get(periph.prefix, ())


class Periph:
    def __init__(self, name, prefix, base, size):
        self.name = name
        self.prefix = prefix  # předpona masek: GPIOB → GPIO
        self.base = base
        self.size = size
        self.regs = []  # Reg
        self.other = []  # (jméno, adresa) položek, které nejsou uint8_t


sfr = {
    "periphs": {},  # jméno → Periph
    "regs": {},  # adresa → Reg
    "epoch": 0,  # zvýší se při každém rozběhu programu
    "seen": {},  # adresa → [epocha, hodnota, hodnota z dřívější epochy]
}


# ---------------------------------------------------------------------------
# načtení symbolů a masek
# ---------------------------------------------------------------------------


def mask_index(macros, comments):
    """{(GPIO, ODR): [(jméno, maska, komentář)]}, {(GPIO, ODR): reset}."""
    bits, resets = {}, {}
    for name, value in macros.items():
        parts = name.split("_", 2)
        if len(parts) < 3:
            continue
        key = (parts[0], parts[1])
        if parts[2] == "RESET_VALUE":
            resets[key] = value
        elif 0 < value <= 0xFF:
            bits.setdefault(key, []).append((parts[2], value, comments.get(name, "")))
    for items in bits.values():
        items.sort(key=lambda item: -item[1])
    return bits, resets


def load_sfr():
    path = os.environ.get("STM8_SFR")
    if not path:
        elf = gdb.current_progspace().filename or ""
        path = os.path.join(os.path.dirname(elf), "sfr.elf")
    try:
        with open(os.path.splitext(path)[0] + ".json") as f:
            info = json.load(f)
        gdb.execute(f'add-symbol-file "{path}"', to_string=True)
    except (OSError, ValueError, gdb.error):
        warn("Registry periferií nejsou k dispozici (chybí sfr.elf). Spusť ladění přes make debug.")
        return

    macros, comments = info["macros"], info["comments"]
    for name, value in macros.items():
        gdb.execute(f"macro define {name} {value:#x}")
    bits, resets = mask_index(macros, comments)

    for name, prefix in info["peripherals"].items():
        try:
            value = gdb.parse_and_eval(name)
            base = int(value.address)
        except gdb.error:
            continue
        kind = value.type.strip_typedefs()
        periph = Periph(name, prefix, base, kind.sizeof)
        desc = info["regdesc"].get(prefix, {})
        for field in kind.fields():
            addr = base + field.bitpos // 8
            ftype = field.type.strip_typedefs()
            if field.name.upper().startswith("RESERVED"):
                continue
            if ftype.code != gdb.TYPE_CODE_INT or ftype.sizeof != 1:
                periph.other.append((field.name, addr))
                continue
            key = (prefix, field.name)
            # obecné masky pro číslované registry: TIM1_CCMR_OCM pro CCMR1…4
            regbits = bits.get(key) or bits.get((prefix, re.sub(r"\d+$", "", field.name)), [])
            reg = Reg(periph, field.name, addr, regbits, resets.get(key), desc.get(field.name, ""))
            periph.regs.append(reg)
            sfr["regs"][addr] = reg
        sfr["periphs"][name] = periph


# ---------------------------------------------------------------------------
# formátování a změny mezi zastaveními
# ---------------------------------------------------------------------------


def on_cont(event):
    sfr["epoch"] += 1


def track(addr, value):
    """Zapamatuje si hodnotu, vrátí hodnotu z minulého zastavení (nebo None)."""
    entry = sfr["seen"].get(addr)
    if entry is None:
        sfr["seen"][addr] = [sfr["epoch"], value, None]
        return None
    if entry[0] != sfr["epoch"]:
        entry[0], entry[2] = sfr["epoch"], entry[1]
    entry[1] = value
    return entry[2]


def paint(text, color):
    if not color or not gdb.parameter("style enabled"):
        return text
    return f"\033[{color}m{text}\033[0m"


def binary(value, prev, sep=""):
    """0010 0001, změněné číslice žlutě."""
    digits = []
    for bit in range(7, -1, -1):
        digit = str(value >> bit & 1)
        if prev is not None and (value ^ prev) >> bit & 1:
            digit = paint(digit, CHANGE_COLOR)
        digits.append(digit)
    if sep:
        return sep.join(digits)
    return "".join(digits[:4]) + " " + "".join(digits[4:])


def field_value(mask, value):
    return (value & mask) >> ((mask & -mask).bit_length() - 1)


def bit_names(reg, value, prev):
    """ARPE CEN PSC=7; změněné žlutě, vynulované jako -UIF."""
    out = []
    for name, mask, _ in reg.bits:
        cur = field_value(mask, value)
        changed = prev is not None and field_value(mask, prev) != cur
        color = CHANGE_COLOR if changed else ""
        if mask & (mask - 1):  # pole o více bitech
            if cur or changed:
                out.append(paint(f"{name}={cur}", color))
        elif cur:
            out.append(paint(name, color))
        elif changed:
            out.append(paint("-" + name, CLEARED_COLOR))
    return " ".join(out)


def format_reg(reg, value, prev, names=True):
    """0x21 0010 0001  ARPE CEN  (bylo 0x01)"""
    changed = prev is not None and prev != value
    text = paint(f"0x{value:02x}", CHANGE_COLOR if changed else "") + " " + binary(value, prev)
    if names:
        decoded = bit_names(reg, value, prev)
        if decoded:
            text += "  " + decoded
    if changed:
        text += f"  (bylo 0x{prev:02x})"
    return text


class SfrPrinter:
    """Registr periferie v print/display: hex, binárně, bity a změna."""

    def __init__(self, reg, value):
        self.reg = reg
        self.value = value

    def to_string(self):
        fmt = gdb.print_options().get("format")
        if fmt and fmt not in "xtz":  # p/d, p/c, … jak je zvyklý gdb
            return self.value.format_string(raw=True, format=fmt)
        value = int(self.value) & 0xFF
        return format_reg(self.reg, value, track(self.reg.addr, value))


def sfr_printer(value):
    if not sfr["regs"] or value.address is None:
        return None
    reg = sfr["regs"].get(int(value.address))
    kind = value.type.strip_typedefs()
    # struktura periferie má stejnou adresu jako její první registr
    if reg is None or kind.code != gdb.TYPE_CODE_INT or kind.sizeof != 1:
        return None
    return SfrPrinter(reg, value)


# ---------------------------------------------------------------------------
# příkaz sfr
# ---------------------------------------------------------------------------


def read_regs(regs):
    """{adresa: hodnota}; souvislé registry čte jedním přenosem."""
    inferior = gdb.selected_inferior()
    values, run = {}, []
    for reg in regs + [None]:
        if reg is not None and run and reg.addr == run[-1].addr + 1:
            run.append(reg)
            continue
        if run:
            data = bytes(inferior.read_memory(run[0].addr, len(run)))
            values.update((r.addr, b) for r, b in zip(run, data))
        run = [reg] if reg is not None else []
    return values


def find(token):
    """TIM4, TIM4.CR1, tim4->cr1 → (Periph, Reg nebo None)."""
    name, _, regname = re.sub(r"->", ".", token.upper()).partition(".")
    periph = sfr["periphs"].get(name)
    if periph is None:
        raise gdb.GdbError(f"Periferie {name} neexistuje. Seznam: sfr")
    if not regname:
        return periph, None
    for reg in periph.regs:
        if reg.name == regname:
            return periph, reg
    for field, _ in periph.other:
        if field.upper() == regname:
            raise gdb.GdbError(f"{name}.{field} není jeden registr, použij: p/x {name}.{field}")
    raise gdb.GdbError(f"{name} nemá registr {regname}: " + " ".join(r.name for r in periph.regs))


def show_list():
    periphs = sorted(sfr["periphs"].values(), key=lambda p: p.base)
    say("Periferie čipu:", "1;36")
    cells = [f"{paint(f'{p.name:<6}', NAME_COLOR)} 0x{p.base:04x}" for p in periphs]
    for i in range(0, len(cells), 5):
        gdb.write("  " + "   ".join(cells[i:i + 5]) + "\n")
    gdb.write("sfr TIM4 = registry, sfr TIM4.CR1 = bity, help sfr = víc\n")


def show_periph(periph):
    values = read_regs([r for r in periph.regs if not r.side_effect])
    gdb.write(paint(periph.name, "1;36") + f"  0x{periph.base:04x}\n")
    high = None  # (jméno bez H, hodnota) předchozího registru xxxH
    for reg in periph.regs:
        line = f"  {paint(f'{reg.name:<6}', NAME_COLOR)} 0x{reg.addr:04x}  "
        if reg.addr not in values:
            line += paint(f"nečteno, čtení maže příznaky; přečti: sfr {periph.name}.{reg.name}", "2")
            high = None
        else:
            value = values[reg.addr]
            line += format_reg(reg, value, track(reg.addr, value))
            if high and reg.name == high[0] + "L" and (high[1] or value):
                both = high[1] << 8 | value
                line += f"   {high[0]}=0x{both:04x} ({both})"
            high = (reg.name[:-1], value) if reg.name.endswith("H") else None
        gdb.write(line + "\n")
    for field, addr in periph.other:
        gdb.write(f"  {paint(f'{field:<6}', NAME_COLOR)} 0x{addr:04x}  p/x {periph.name}.{field}\n")


def show_reg(periph, reg):
    value = read_regs([reg])[reg.addr]
    prev = track(reg.addr, value)
    head = f"{paint(f'{periph.name}->{reg.name}', '1;36')}  0x{reg.addr:04x}"
    if reg.desc:
        head += f"  {reg.desc}"
    if reg.reset is not None:
        head += f"  (po resetu 0x{reg.reset:02x})"
    gdb.write(head + "\n")
    gdb.write("  = " + format_reg(reg, value, prev, names=False) + "\n")
    gdb.write("  bit  7 6 5 4 3 2 1 0\n")
    gdb.write("       " + binary(value, prev, sep=" ") + "\n")
    for name, mask, comment in reg.bits:
        low = (mask & -mask).bit_length() - 1
        high = mask.bit_length() - 1
        pos = f"{high}:{low}" if high != low else f"{low}"
        cur = field_value(mask, value)
        changed = prev is not None and field_value(mask, prev) != cur
        text = paint(f"{name:<8} {cur}", CHANGE_COLOR if changed else "")
        gdb.write(f"  {pos:<5} {text}  {comment}\n")
    if reg.side_effect:
        say(f"  Čtení {periph.name}->{reg.name} smazalo příznaky (viz datasheet).", "2")


class SfrCommand(gdb.Command):
    """Registry periferií (SFR) se jmény ze stm8s.h.
Použití: sfr                  seznam periferií
         sfr TIM4 [GPIOB …]   registry periferie a nastavené bity
         sfr TIM4.CR1         jeden registr bit po bitu s popisem
Změny od minulého zastavení jsou žlutě, vynulovaný bit jako -UIF.
Tabulátor doplňuje periferie i registry (sfr TIM4.<Tab>).

Registry jdou psát i jako v C, s maskami ze stm8s.h:
  p TIM4->CR1           display GPIOB->ODR      p GPIOB (celá periferie)
  set var GPIOD->ODR |= 0x10      p/t SPI->CR2 & SPI_CR2_SSM
display/x a p/x rozpis bitů a zvýraznění vynechají, display GPIOB->ODR ne.
Pozor: p UART1 i display UART1 přečtou UART1->DR, a tím smažou RXNE."""

    def __init__(self):
        super().__init__("sfr", gdb.COMMAND_DATA)

    def invoke(self, arg, from_tty):
        self.dont_repeat()
        if not sfr["periphs"]:
            raise gdb.GdbError("Registry periferií nejsou načtené. Spusť ladění přes make debug.")
        tokens = arg.split()
        if not tokens:
            show_list()
            return
        targets = [find(token) for token in tokens]
        if target_running():
            raise gdb.GdbError("Program běží, zastav ho (Ctrl-C).")
        try:
            for periph, reg in targets:
                if reg is None:
                    show_periph(periph)
                else:
                    show_reg(periph, reg)
        except gdb.MemoryError as e:
            raise gdb.GdbError(f"Z čipu nejde číst: {e}")

    def complete(self, text, word):
        token = "" if not text or text[-1].isspace() else text.split()[-1]
        name, dot, regname = re.sub(r"->", ".", token).partition(".")
        if not dot:
            return [n for n in sorted(sfr["periphs"]) if n.startswith(name.upper())]
        periph = sfr["periphs"].get(name.upper())
        if periph is None:
            return []
        names = [r.name for r in periph.regs] + [f for f, _ in periph.other]
        return [n for n in names if n.startswith(regname.upper())]


# ---------------------------------------------------------------------------
# příkazy pro rozšíření VS Code: sfr-json, sfr-set
# ---------------------------------------------------------------------------


def reg_json(reg, value, prev):
    return {
        "name": reg.name,
        "addr": reg.addr,
        "reset": reg.reset,
        "desc": reg.desc,
        "sideEffect": reg.side_effect,
        "value": value,
        "prev": prev,
        "bits": [{"name": n, "mask": m, "desc": c} for n, m, c in reg.bits],
    }


def sfr_json(tokens):
    """All peripherals as JSON; values only for what TOKENS name."""
    if not sfr["periphs"]:
        raise gdb.GdbError("Peripheral registers are not loaded. Start debugging with make debug.")
    targets = [find(token) for token in tokens]
    running = target_running()
    if targets and running:
        raise gdb.GdbError("Program is running, pause it first.")
    reads = []
    for periph, reg in targets:
        reads += [r for r in periph.regs if not r.side_effect] if reg is None else [reg]
    try:
        values = read_regs(reads)
    except gdb.MemoryError as e:
        raise gdb.GdbError(f"Cannot read from the chip: {e}")
    periphs = []
    for periph in sorted(sfr["periphs"].values(), key=lambda p: p.base):
        regs = []
        for reg in periph.regs:
            value = values.get(reg.addr)
            regs.append(reg_json(reg, value, None if value is None else track(reg.addr, value)))
        other = [{"name": name, "addr": addr} for name, addr in periph.other]
        periphs.append({"name": periph.name, "base": periph.base, "regs": regs, "other": other})
    return json.dumps({"running": running, "periphs": periphs}, separators=(",", ":"))


class SfrJsonCommand(gdb.Command):
    """Peripheral registers as one line of JSON (for the VS Code extension).
Usage: sfr-json                 all peripherals and bits, no values (needs no chip)
       sfr-json TIM4 [GPIOB …]  plus values; registers whose read clears flags are skipped
       sfr-json UART1.DR        reads exactly that register"""

    def __init__(self):
        super().__init__("sfr-json", gdb.COMMAND_DATA)

    def invoke(self, arg, from_tty):
        self.dont_repeat()
        gdb.write(sfr_json(arg.split()) + "\n")


def merge_field(old, mask, value):
    """OLD with the bits under MASK replaced by VALUE (counted from the lowest bit of the field)."""
    low = (mask & -mask).bit_length() - 1
    return (old & ~mask & 0xFF) | (value << low & mask)


def parse_target(token):
    """TIM4.CR1 or TIM4.CR1.CEN → (Periph, Reg, (name, mask, comment) or None)."""
    name, _, rest = re.sub(r"->", ".", token.upper()).partition(".")
    regname, _, bitname = rest.partition(".")
    periph, reg = find(f"{name}.{regname}")
    if reg is None:
        raise gdb.GdbError(f"Use PERIPH.REG[.FIELD], got {token}")
    if not bitname:
        return periph, reg, None
    for bit in reg.bits:
        if bit[0] == bitname:
            return periph, reg, bit
    raise gdb.GdbError(f"{periph.name}.{reg.name} has no field {bitname}: " + " ".join(b[0] for b in reg.bits))


class SfrSetCommand(gdb.Command):
    """Write a peripheral register or one of its fields (the other bits stay).
Usage: sfr-set TIM4.CR1 0x21     whole register
       sfr-set TIM4.CR1.CEN 1    one field
Prints the value written to the register."""

    def __init__(self):
        super().__init__("sfr-set", gdb.COMMAND_DATA)

    def invoke(self, arg, from_tty):
        self.dont_repeat()
        tokens = arg.split()
        if len(tokens) != 2:
            raise gdb.GdbError("Usage: sfr-set PERIPH.REG[.FIELD] VALUE")
        periph, reg, bit = parse_target(tokens[0])
        where = f"{periph.name}.{reg.name}"
        if bit is not None and reg.side_effect:  # a field write reads the register first
            raise gdb.GdbError(
                f"{where} cannot be changed field by field: reading it clears flags. "
                f"Write the whole register: sfr-set {where} VALUE"
            )
        try:
            value = int(tokens[1], 0)
        except ValueError:
            raise gdb.GdbError(f"Not a number: {tokens[1]}")
        if bit is None:
            if not 0 <= value <= 0xFF:
                raise gdb.GdbError(f"Value {value} does not fit register {where} (8 bits)")
        else:
            width = (bit[1] >> ((bit[1] & -bit[1]).bit_length() - 1)).bit_length()
            if not 0 <= value < 1 << width:
                raise gdb.GdbError(
                    f"Value {value} does not fit field {where}.{bit[0]} ({width} bit{'s' * (width > 1)})"
                )
        if target_running():
            raise gdb.GdbError("Program is running, pause it first.")
        inferior = gdb.selected_inferior()
        try:
            if bit is not None:
                value = merge_field(bytes(inferior.read_memory(reg.addr, 1))[0], bit[1], value)
            inferior.write_memory(reg.addr, bytes([value]))
        except gdb.MemoryError as e:
            raise gdb.GdbError(f"Cannot write to the chip: {e}")
        gdb.write(f"{value}\n")


SfrCommand()
SfrJsonCommand()
SfrSetCommand()
gdb.pretty_printers.insert(0, sfr_printer)
gdb.events.cont.connect(on_cont)
load_sfr()
