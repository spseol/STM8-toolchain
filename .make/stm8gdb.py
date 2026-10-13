# Ladění STM8 v gdb: připojení k čipu přes OpenOCD, příkazy flash/reset/vars
# a automatické nahrání nového programu, když se změní ELF (make flash, make elf).
# Načítá se z .make/gdbinit (make debug, make cgdb, make gdb).
import os
import re
import subprocess
import threading

import gdb

PROJECT_DIR = os.getcwd()
SESSION_FILE = os.path.join(PROJECT_DIR, ".debug-session")  # čte Makefile (make flash)
DISPLAY_FILE = os.path.join(PROJECT_DIR, ".debug-display")  # display mezi sezeními
GDB_PORT = 3333
POLL_INTERVAL = 0.5  # s, jak často se kontroluje změna ELF

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
}
stop_watch = threading.Event()


def say(msg, color="1;32"):
    gdb.write(f"\033[{color}m{msg}\033[0m\n")
    gdb.flush()


def warn(msg):
    say(msg, "1;31")


def elf_stamp():
    try:
        st = os.stat(state["elf"])
    except (OSError, TypeError):
        return None
    return (st.st_mtime_ns, st.st_size)


def target_running():
    thread = gdb.selected_thread()
    return thread is not None and thread.is_running()


# ---------------------------------------------------------------------------
# připojení k OpenOCD
# ---------------------------------------------------------------------------


def tcp_listening(port):
    """Poslouchá už na portu ručně spuštěný OpenOCD (make openocd)? Jen Linux."""
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


def connect():
    """Připojí gdb k čipu. OpenOCD spustí sám přes pipe a skončí spolu s gdb.

    Když už OpenOCD běží (make openocd), připojí se k němu přes TCP."""
    openocd = os.environ.get("STM8_OPENOCD")
    log = os.environ.get("STM8_OPENOCD_LOG", "openocd.log")
    tcp = f"localhost:{GDB_PORT}"
    pipe = (
        f'| {openocd} -c "gdb_port pipe" -c "telnet_port disabled"'
        f' -c "tcl_port disabled" 2>{log}'
    )
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
    if state["connected"]:
        return
    say("Připojuji se k čipu…", "1;36")
    if connect():
        return
    warn("Nepodařilo se připojit k čipu. Je ST-Link připojený a čip napájený?")
    for line in openocd_errors():
        warn("  " + line)
    if not os.environ.get("STM8_OPENOCD"):
        warn("Ladění spouštěj přes: make debug")
    raise gdb.GdbError("Bez připojení k čipu nejde ladit.")


# ---------------------------------------------------------------------------
# překlad, nahrání, reset
# ---------------------------------------------------------------------------


def build():
    say("Překládám (make elf)…", "1;36")
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
    say("Nahráno do čipu." + (f" ({size[0].strip()})" if size else ""))


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
    say(reason, "1;33")
    try:
        load()
        restart()
    except gdb.error as e:
        warn(f"Nahrání selhalo: {e}")


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


def on_elf_changed():
    state["queued"] = False
    if not state["connected"] or state["busy"]:
        return
    if elf_stamp() in (None, state["loaded"]):
        return
    if target_running():
        # program běží → zastavit, nahrání dokončí on_stop()
        state["pending"] = True
        say("\nProgram se změnil – zastavuji čip…", "1;33")
        gdb.execute("interrupt")
        return
    reload("\nProgram se změnil – nahrávám do čipu…")


def on_stop(event):
    if state["pending"]:
        state["pending"] = False
        gdb.post_event(lambda: reload("\nNahrávám nový program do čipu…"))
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
    save_displays()
    # po ukončení ladění ať program v čipu běží znovu od začátku
    # (`monitor reset run` hlásí přes gdb „Protocol error with Rcmd“ a čip stojí)
    if state["connected"]:
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
                f.write("# display pro make debug, jeden výraz na řádek (ukládá se samo)\n")
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
    options = {"pretty_structs": False, "max_elements": 8}
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
            "  " + "   ".join(f"\033[36m{n}\033[0m = {v}" for n, v in items) + "\n"
        )


# ---------------------------------------------------------------------------
# příkazy
# ---------------------------------------------------------------------------


class FlashCommand(gdb.Command):
    """Přeloží projekt (make elf), nahraje ho do čipu a zastaví na main().
Použití: flash"""

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
            raise gdb.GdbError("Překlad selhal, do čipu se nic nenahrálo.")
        reload("Nahrávám do čipu…")


class ResetCommand(gdb.Command):
    """Resetuje čip a nechá program doběhnout na main().
Použití: reset"""

    def __init__(self):
        super().__init__("reset", gdb.COMMAND_RUNNING)

    def invoke(self, arg, from_tty):
        self.dont_repeat()
        ensure_connected()
        restart()


class RunCommand(gdb.Command):
    """Spustí program znovu od začátku a zastaví na main().
Když je ELF novější než program v čipu, nejdřív ho nahraje.
Nahrazuje původní run/start, které s OpenOCD nefungují (F5 v cgdb)."""

    def __init__(self, name):
        super().__init__(name, gdb.COMMAND_RUNNING)

    def invoke(self, arg, from_tty):
        self.dont_repeat()
        if not state["connected"] or elf_stamp() != state["loaded"]:
            reload("Nahrávám do čipu…")
        else:
            restart()


class VarsCommand(gdb.Command):
    """Vypíše argumenty a lokální proměnné aktuální funkce.
Použití: vars       vypiš teď
         vars on    vypisuj po každém zastavení (výchozí)
         vars off   nevypisuj automaticky
Globální proměnné: display jméno"""

    def __init__(self):
        super().__init__("vars", gdb.COMMAND_DATA)

    def invoke(self, arg, from_tty):
        arg = arg.strip()
        if arg in ("on", "off"):
            state["autovars"] = arg == "on"
            say(f"Automatický výpis proměnných: {arg}")
        elif arg:
            raise gdb.GdbError("Použití: vars [on|off]")
        else:
            show_vars()


FlashCommand()
ResetCommand()
RunCommand("run")
RunCommand("start")
VarsCommand()


def banner():
    ui = os.environ.get("STM8_UI")
    lines = []
    if ui == "cgdb":
        lines += [
            "cgdb  Esc = okno se zdrojákem, i = zpět do gdb",
            "      ve zdrojáku: mezerník = breakpoint, F8 next, F10 step,"
            " F7 finish, F6 continue, F5 znovu od main()",
        ]
    elif ui == "tui":
        lines += [
            "TUI   Ctrl-x s = režim jedné klávesy (n s f c r v, q = konec),"
            " Ctrl-x a = TUI vyp/zap",
        ]
    lines += [
        "gdb   n = další řádek, s = do funkce, finish = z funkce, c = pokračuj,"
        " Ctrl-C = zastav",
        "      b 42 = breakpoint na řádku 42, p x = vypiš x,"
        " display x = vypisuj x po každém kroku (pamatuje se i pro příště)",
        "STM8  flash = přelož + nahraj + main(), reset / r = znovu od main(),"
        " vars [on|off] = proměnné",
        "      make flash v jiném terminálu nový program do čipu nahraje sám",
    ]
    say("─" * 30 + " STM8 debug " + "─" * 30, "1;36")
    for line in lines:
        gdb.write(line + "\n")


def stm8_start():
    """Volá .make/gdbinit: připojení, nahrání, main(), hlídání ELF."""
    gdb.events.stop.connect(on_stop)
    gdb.events.gdb_exiting.connect(on_exit)
    gdb.events.before_prompt.connect(on_prompt)
    load_displays()
    state["elf"] = gdb.current_progspace().filename
    if not state["elf"]:
        warn("gdb nemá ELF. Spusť ladění přes: make debug")
        return
    threading.Thread(target=watch, daemon=True).start()
    try:
        reload("Nahrávám do čipu…")
    except gdb.GdbError as e:
        warn(str(e))
    banner()
