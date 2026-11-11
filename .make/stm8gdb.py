# Ladění STM8 v gdb: připojení k čipu přes OpenOCD, příkazy flash/reset/vars
# a automatické nahrání nového programu, když se změní ELF (make flash, make elf).
# Načítá se z .make/gdbinit (make debug, make cgdb, make gdb).
import os
import re
import shlex
import subprocess
import threading

import gdb

PROJECT_DIR = os.getcwd()
SESSION_FILE = os.path.join(PROJECT_DIR, ".debug-session")  # čte Makefile (make flash)
DISPLAY_FILE = os.path.join(PROJECT_DIR, ".debug-display")  # display mezi sezeními
GDB_PORT = 3333
POLL_INTERVAL = 0.5  # s, jak často se kontroluje změna ELF
NAME_COLOR = "36"  # jména proměnných azurově (jako `info locals` v gdb)
VALUE_COLOR = ""  # hodnoty bez barvy; třeba "35" = fialově v print, display, watch, …
HELP_COLOR = "1;35"  # příkazy a klávesy v nápovědě po startu tučně purpurově

state = {
    "connected": False,
    "elf": None,  # ELF, který gdb ladí
    "loaded": None,  # (mtime, velikost) ELF při posledním nahrání do čipu
    "busy": False,  # právě se překládá nebo nahrává
    "queued": False,  # watcher už poslal událost, ještě nezpracovanou
    "pending": False,  # čeká se na zastavení programu, pak se nahraje nový
    "autovars": True,  # vypisovat proměnné po každém zastavení
    "displays_pending": [],  # display ze souboru, které ještě nejdou vytvořit
    "displays_saved": None,  # naposledy uložený obsah DISPLAY_FILE
    "watching": False,  # běží vlákno hlídající změnu ELF
}
stop_watch = threading.Event()


def say(msg, color="1;32"):
    gdb.write(f"\033[{color}m{msg}\033[0m\n")
    gdb.flush()


def warn(msg):
    say(msg, "1;31")


def elf_stamp():
    if state["elf"] is None:  # v režimu DAP se ELF načte až příkazem attach
        state["elf"] = gdb.current_progspace().filename
    try:
        st = os.stat(state["elf"])
    except (OSError, TypeError):
        return None
    return (st.st_mtime_ns, st.st_size)


def target_running():
    thread = gdb.selected_thread()
    return thread is not None and thread.is_running()


def dap_mode():
    """gdb běží jako DAP server pro rozšíření VS Code (.make/vscode/)."""
    return os.environ.get("STM8_UI") == "dap"


def is_connected():
    """Připojení udělal connect(), nebo DAP attach (target remote)."""
    if state["connected"]:
        return True
    try:
        return gdb.selected_inferior().connection_num is not None
    except AttributeError:
        return False


# ---------------------------------------------------------------------------
# připojení k OpenOCD
# ---------------------------------------------------------------------------


def tcp_listening(port):
    """Poslouchá už na portu ručně spuštěný OpenOCD (make openocd)? Linux (/proc) a Windows."""
    if os.name == "nt":
        import socket

        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            return False
    for name in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(name) as f:
                next(f)
                for line in f:
                    fields = line.split()
                    local_port = int(fields[1].rsplit(":", 1)[1], 16)
                    if fields[3] == "0A" and local_port == port:
                        return True
        except (OSError, StopIteration, IndexError, ValueError):
            pass
    return False


def openocd_errors():
    log = os.environ.get("STM8_OPENOCD_LOG")
    try:
        with open(log, errors="replace") as f:
            lines = [line.rstrip() for line in f if "Error" in line]
    except (OSError, TypeError):
        return []
    return lines[-5:]


def write_session():
    try:
        with open(SESSION_FILE, "w") as f:
            f.write(f"{os.getpid()}\n")
    except OSError:
        pass


def log_option(log):
    """Kam půjde stderr OpenOCD. Linux a macOS: gdb příkaz pouští přes sh, takže `2>LOG`
    (cesta v uvozovkách shellu). Windows: gdb žádný shell nepoužije, `2>LOG` by dostal
    OpenOCD jako argument a skončil; proto jeho vlastní `-l`. gdb si argumenty rozebírá
    sám (zpětné lomítko je únikový znak), proto lomítka dopředu a uvozovky."""
    if os.name == "nt":
        return '-l "' + log.replace("\\", "/") + '"'
    return "2>" + shlex.quote(log)


def pipe_target(openocd, log):
    """`target extended-remote` argument: OpenOCD on a pipe.
    .make/vscode/dap_info.py builds the same string (gdbTarget)."""
    return (
        f'| {openocd} -c "gdb_port pipe" -c "telnet_port disabled"'
        f' -c "tcl_port disabled" {log_option(log)}'
    )


def connect():
    """Připojí gdb k čipu. OpenOCD spustí sám přes pipe a skončí spolu s gdb.

    Když už OpenOCD běží (make openocd), připojí se k němu přes TCP."""
    openocd = os.environ.get("STM8_OPENOCD")
    log = os.environ.get("STM8_OPENOCD_LOG", "openocd.log")
    tcp = f"localhost:{GDB_PORT}"
    pipe = pipe_target(openocd, log)
    if tcp_listening(GDB_PORT) or not openocd:
        targets = [tcp] + ([pipe] if openocd else [])
    else:
        targets = [pipe, tcp]

    gdb.execute("set tcp auto-retry off")
    for target in targets:
        try:
            gdb.execute(f"target extended-remote {target}", to_string=True)
        except gdb.error:
            continue
        state["connected"] = True
        write_session()
        return True
    return False


def ensure_connected():
    if is_connected():
        return
    say("Connecting to the chip…", "1;36")
    if connect():
        return
    warn("Cannot connect to the chip. Is the ST-Link plugged in and the chip powered?")
    for line in openocd_errors():
        warn("  " + line)
    if not os.environ.get("STM8_OPENOCD"):
        warn("Start debugging with: make debug")
    raise gdb.GdbError("Cannot debug without a connection to the chip.")


# ---------------------------------------------------------------------------
# překlad, nahrání, reset
# ---------------------------------------------------------------------------


def build():
    say("Building (make elf)…", "1;36")
    # vnější make (make debug) by předal svůj jobserver a úroveň zanoření
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("MAKEFLAGS", "MFLAGS", "MAKELEVEL")
    }
    proc = subprocess.run(
        ["make", "elf"],
        cwd=PROJECT_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )
    gdb.write(proc.stdout)
    return proc.returncode == 0


def load():
    state["busy"] = True
    try:
        out = gdb.execute("load", to_string=True)
        state["loaded"] = elf_stamp()
    finally:
        state["busy"] = False
    size = [line for line in out.splitlines() if "load size" in line]
    say("Flashed to the chip." +(f" ({size[0].strip()})" if size else ""))


def restart():
    """Reset čipu a běh do main()."""
    gdb.execute("monitor reset halt", to_string=True)
    # gdb neví, že reset změnil registry (PC) → zahodit jeho cache
    gdb.execute("maintenance flush register-cache", to_string=True)
    gdb.execute("tbreak main", to_string=True)
    gdb.execute("continue")


def reload(reason):
    """Nahraje aktuální ELF do čipu, resetuje a zastaví na main()."""
    ensure_connected()
    if dap_mode():
        write_session()
    say(reason, "1;33")
    try:
        load()
        restart()
        if dap_mode():
            start_watcher()
    except gdb.error as e:
        warn(f"Flashing failed: {e}")
        if dap_mode():  # příkaz run v rozšíření musí selhat, ne jen varovat
            raise gdb.GdbError(f"Flashing failed: {e}")


# ---------------------------------------------------------------------------
# hlídání změny ELF (make flash / make elf v jiném terminálu)
# ---------------------------------------------------------------------------


def watch():
    last = None
    while not stop_watch.wait(POLL_INTERVAL):
        stamp = elf_stamp()
        # nová verze, která se už nemění (linker dopsal)
        if (
            stamp
            and stamp == last
            and stamp != state["loaded"]
            and not state["busy"]
            and not state["queued"]
        ):
            state["queued"] = True
            gdb.post_event(on_elf_changed)
        last = stamp


def start_watcher():
    if not state["watching"]:
        state["watching"] = True
        threading.Thread(target=watch, daemon=True).start()


def on_elf_changed():
    state["queued"] = False
    if not is_connected() or state["busy"]:
        return
    if elf_stamp() in (None, state["loaded"]):
        return
    if target_running():
        # program běží → zastavit, nahrání dokončí on_stop()
        state["pending"] = True
        say("\nProgram changed – halting the chip…", "1;33")
        gdb.execute("interrupt")
        return
    reload("\nProgram changed – flashing to the chip…")


def on_stop(event):
    if state["pending"]:
        state["pending"] = False
        gdb.post_event(lambda: reload("\nFlashing the new program to the chip…"))
        return
    if dap_mode():  # proměnné a display ukazuje VS Code
        return
    save_displays()
    if state["autovars"] and not state["busy"]:
        show_vars()


def on_prompt():
    # čekající display až tady: ve stop handleru by se nový display nevypsal
    if state["displays_pending"] and state["connected"] and not target_running():
        restore_displays()
        save_displays()


def on_exit(event):
    stop_watch.set()
    if not dap_mode():
        save_displays()
    # po ukončení ladění ať program v čipu běží znovu od začátku
    # (`monitor reset run` hlásí přes gdb „Protocol error with Rcmd“ a čip stojí)
    if is_connected():
        try:
            if not target_running():
                gdb.execute("monitor reset halt", to_string=True)
                gdb.execute("monitor resume", to_string=True)
        except gdb.error:
            pass
    try:
        with open(SESSION_FILE) as f:
            mine = f.read().strip() == str(os.getpid())
        if mine:
            os.remove(SESSION_FILE)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# display mezi sezeními (.debug-display, jeden výraz na řádek)
# ---------------------------------------------------------------------------

# řádek `info display`: "2:   y  /x sum (cannot be evaluated in the current context)"
DISPLAY_LINE = re.compile(
    r"^\d+:\s+[yn]\s+(.*?)(?: \(cannot be evaluated in the current context\))?$"
)


def current_displays():
    try:
        out = gdb.execute("info display", to_string=True)
    except gdb.error:
        return []
    return [m.group(1) for m in map(DISPLAY_LINE.match, out.splitlines()) if m]


def load_displays():
    try:
        with open(DISPLAY_FILE) as f:
            lines = [line.strip() for line in f]
    except OSError:
        return
    state["displays_pending"] = [e for e in lines if e and not e.startswith("#")]
    state["displays_saved"] = state["displays_pending"]


def restore_displays():
    """Vytvoří display ze souboru. Lokální proměnná jde vytvořit, až když
    program stojí v její funkci, do té doby zůstává čekat."""
    if not state["displays_pending"]:
        return
    existing = current_displays()
    waiting = []
    for expr in state["displays_pending"]:
        if expr in existing:
            continue
        try:
            # from_tty=True: jinak gdb nový display hned nevypíše
            gdb.execute(f"display {expr}", True)
        except gdb.error:
            waiting.append(expr)
    state["displays_pending"] = waiting


def save_displays():
    exprs = current_displays()
    exprs += [e for e in state["displays_pending"] if e not in exprs]
    if exprs == state["displays_saved"]:
        return
    try:
        if exprs:
            with open(DISPLAY_FILE, "w") as f:
                f.write("# display list for make debug, one expression per line (saved automatically)\n")
                f.write("".join(e + "\n" for e in exprs))
        elif os.path.exists(DISPLAY_FILE):
            os.remove(DISPLAY_FILE)
        state["displays_saved"] = exprs
    except OSError:
        pass


# ---------------------------------------------------------------------------
# proměnné aktuální funkce
# ---------------------------------------------------------------------------


def format_value(value):
    """Hodnota na jeden řádek; uint8_t (i v poli) jako číslo, ne znak."""
    kind = value.type.strip_typedefs()
    if kind.code == gdb.TYPE_CODE_ARRAY:
        kind = kind.target().strip_typedefs()
    options = {"pretty_structs": False, "max_elements": 8, "styling": True}
    if kind.code == gdb.TYPE_CODE_INT and kind.sizeof == 1:
        options["format"] = "d" if getattr(kind, "is_signed", False) else "u"
    return value.format_string(**options)


def frame_vars():
    try:
        frame = gdb.selected_frame()
        block = frame.block()
    except (gdb.error, RuntimeError):
        return []
    items, seen = [], set()
    while block is not None:
        for sym in block:
            if (sym.is_argument or sym.is_variable) and sym.name not in seen:
                seen.add(sym.name)
                try:
                    value = format_value(sym.value(frame))
                except gdb.error as e:
                    value = f"<{e}>"
                items.append((sym.name, value))
        if block.function is not None:
            break
        block = block.superblock
    return items


def show_vars():
    items = frame_vars()
    if items:
        gdb.write(
            "  "
            + "   ".join(f"\033[{NAME_COLOR}m{n}\033[0m = {v}" for n, v in items)
            + "\n"
        )


# ---------------------------------------------------------------------------
# barevné hodnoty: print, display, watch, info locals, finish, …
# ---------------------------------------------------------------------------

# typy, jejichž hodnota se vypisuje celá najednou (ukazatele barví gdb sám)
COLOR_TYPES = (
    gdb.TYPE_CODE_INT,
    gdb.TYPE_CODE_CHAR,
    gdb.TYPE_CODE_BOOL,
    gdb.TYPE_CODE_ENUM,
    gdb.TYPE_CODE_FLT,
)


class ColorPrinter:
    """Obarví hodnotu. Formát (print/x, display/t, …) zůstává."""

    def __init__(self, value):
        self.value = value

    def to_string(self):
        options = gdb.print_options()  # včetně /x a podobných z příkazu
        options["raw"] = True  # bez pretty-printerů, jinak by se volal znovu
        try:
            text = self.value.format_string(**options)
        except gdb.MemoryError:
            raise  # gdb vypíše <error: Cannot access memory …>
        except gdb.error as e:
            text = f"<{e}>"
        return f"\033[{VALUE_COLOR}m{text}\033[0m"


def color_printer(value):
    """Struktury a pole nechá gdb, obarví se jejich prvky. Řetězce celé."""
    if not VALUE_COLOR or not gdb.parameter("style enabled"):
        return None
    kind = value.type.strip_typedefs()
    if kind.code == gdb.TYPE_CODE_ARRAY:
        item = kind.target().strip_typedefs()
        if item.code in (gdb.TYPE_CODE_INT, gdb.TYPE_CODE_CHAR) and item.sizeof == 1:
            return ColorPrinter(value)  # char[] gdb vypisuje jako "text"
        return None
    if kind.code in COLOR_TYPES:
        return ColorPrinter(value)
    return None


gdb.pretty_printers.append(color_printer)


# ---------------------------------------------------------------------------
# příkazy
# ---------------------------------------------------------------------------


class FlashCommand(gdb.Command):
    """Build the project (make elf), flash it to the chip and stop at main().
Usage: flash"""

    def __init__(self):
        super().__init__("flash", gdb.COMMAND_RUNNING)

    def invoke(self, arg, from_tty):
        self.dont_repeat()
        state["busy"] = True
        try:
            ok = build()
        finally:
            state["busy"] = False
        if not ok:
            raise gdb.GdbError("Build failed, nothing was flashed to the chip.")
        reload("Flashing to the chip…")


class ResetCommand(gdb.Command):
    """Reset the chip and let the program run to main().
Usage: reset"""

    def __init__(self):
        super().__init__("reset", gdb.COMMAND_RUNNING)

    def invoke(self, arg, from_tty):
        self.dont_repeat()
        ensure_connected()
        restart()


class RunCommand(gdb.Command):
    """Restart the program from the beginning and stop at main().
If the ELF is newer than the program in the chip, flash it first.
Replaces the original run/start, which do not work with OpenOCD (F5 in cgdb)."""

    def __init__(self, name):
        super().__init__(name, gdb.COMMAND_RUNNING)

    def invoke(self, arg, from_tty):
        self.dont_repeat()
        if not is_connected() or elf_stamp() != state["loaded"]:
            reload("Flashing to the chip…")
        else:
            restart()


class VarsCommand(gdb.Command):
    """Print the arguments and local variables of the current function.
Usage: vars       print now
       vars on    print after every stop (default)
       vars off   do not print automatically
Global variables: display name"""

    def __init__(self):
        super().__init__("vars", gdb.COMMAND_DATA)

    def invoke(self, arg, from_tty):
        arg = arg.strip()
        if arg in ("on", "off"):
            state["autovars"] = arg == "on"
            say(f"Automatic variable printing: {arg}")
        elif arg:
            raise gdb.GdbError("Usage: vars [on|off]")
        else:
            show_vars()


FlashCommand()
ResetCommand()
RunCommand("run")
RunCommand("start")
VarsCommand()


def banner():
    """Help shown after start; commands and keys are in backticks."""
    ui = os.environ.get("STM8_UI")
    lines = []
    if ui == "cgdb":
        lines += [
            "cgdb  `Esc` = source window, `i` = back to gdb",
            "      in the source: `Space` = breakpoint, `F5` restart from main(),"
            " `F6` continue, `F7` finish, `F8` next, `F10` step",
        ]
    elif ui == "tui":
        lines += [
            "TUI   `Ctrl-x s` = single-key mode (`n s f c r v`, `q` = quit),"
            " `Ctrl-x a` = TUI off/on",
        ]
    lines += [
        "gdb   `n` = next line, `s` = step into, `finish` = step out,"
        " `c` = continue, `Ctrl-C` = stop",
        "      `b 42` = breakpoint at line 42, `p x` = print x,"
        " `display x` = print x after every step (remembered for next time)",
        "STM8  `flash` = build + flash + main(), `reset` / `r` = restart from main(),"
        " `vars [on|off]` = variables",
        "      `make flash` in another terminal flashes the new program by itself",
        "SFR   `sfr` = peripherals, `sfr TIM4` = registers, `sfr TIM4.CR1` = bits,"
        " `display GPIOB->ODR`, `set var GPIOD->ODR |= 0x10`",
    ]
    say("─" * 30 + " STM8 debug " + "─" * 30, "1;36")
    for line in lines:
        gdb.write(re.sub(r"`([^`]+)`", rf"\033[{HELP_COLOR}m\1\033[0m", line) + "\n")


def stm8_start():
    """Volá .make/gdbinit: připojení, nahrání, main(), hlídání ELF."""
    gdb.events.stop.connect(on_stop)
    gdb.events.gdb_exiting.connect(on_exit)
    if dap_mode():  # start řídí rozšíření: attach, pak příkaz run
        gdb.execute("set style enabled off")
        return
    gdb.events.before_prompt.connect(on_prompt)
    load_displays()
    state["elf"] = gdb.current_progspace().filename
    if not state["elf"]:
        warn("gdb has no ELF. Start debugging with: make debug")
        return
    start_watcher()
    try:
        reload("Flashing to the chip…")
    except gdb.GdbError as e:
        warn(str(e))
    banner()
