import os
import re
import sys


def _enable_vt(stream):
    """Zapne na Windows zpracování ANSI sekvencí. Vrací True, když se sekvence
    mají posílat surové (konzole je umí, nebo je výstup roura a řeší je terminál
    na druhém konci, třeba mintty)."""
    if os.name != "nt":
        return True
    try:
        import ctypes
        import msvcrt

        kernel32 = ctypes.windll.kernel32
        handle = msvcrt.get_osfhandle(stream.fileno())
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            # Roura (make, mintty). Výstup nakonec skončí v konzole procesu,
            # tak jí zapneme VT přes CONOUT$. Bez konzole (mintty) se nic
            # nestane a barvy se pošlou surově.
            kernel32.CreateFileW.restype = ctypes.c_void_p
            con = kernel32.CreateFileW(
                "CONOUT$", 0xC0000000, 3, None, 3, 0, None
            )
            if con and con != ctypes.c_void_p(-1).value:
                if kernel32.GetConsoleMode(
                    ctypes.c_void_p(con), ctypes.byref(mode)
                ):
                    kernel32.SetConsoleMode(
                        ctypes.c_void_p(con), mode.value | 0x4
                    )
                kernel32.CloseHandle(ctypes.c_void_p(con))
            return True
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x4
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x4))
    except Exception:
        return False


_RAW = _enable_vt(sys.stderr)
_ANSI = re.compile(r"\033\[[0-9;]*m")


class Style:
    BRIGHT = "\033[1m"
    RESET_ALL = "\033[0m"


class Fore:
    RED = "\033[31m"
    YELLOW = "\033[33m"
    LIGHTRED_EX = "\033[91m"
    LIGHTYELLOW_EX = "\033[93m"
    LIGHTWHITE_EX = "\033[97m"


class Back:
    BLACK = "\033[40m"


def emit(text):
    if not _RAW:
        text = _ANSI.sub("", text)
    sys.stderr.write(text)
    sys.stderr.flush()


class c:
    bold = "\033[1m"
    reset = "\033[0m"
    red = "\033[31m"
    yellow = "\033[33m"
    blue = "\033[34m"
    purple = "\033[35m"


def colorized(color):
    def wrapper(match):
        word = match.group(0)
        return Style.BRIGHT + color + word + Style.RESET_ALL

    return wrapper


while line := sys.stdin.readline():
    m = re.search(r"\?ASlink-Warning-Undefined Global '_?(\w+)'", line)
    if m:
        symbol = m.group(1)
        emit(Style.BRIGHT + Fore.RED + Back.BLACK + line.rstrip() + Style.RESET_ALL + "\n")
        emit(Style.BRIGHT + Fore.YELLOW + Back.BLACK +
            f"   '{symbol}' is used but not defined —"
            f" the corresponding source file is probably missing from the project." +
            Style.RESET_ALL + "\n")
        continue
    if not re.search("/SPL(-STM8S...)?/", line, re.I):
        line = re.sub(
            r"[\w\d/-_]+(\.c|\.h)(:\d+)?",
            colorized(Fore.LIGHTWHITE_EX+Back.BLACK),
            line,
            flags=re.I,
        )
        line = re.sub(r"[^:]+error[^:]*:", colorized(Fore.LIGHTRED_EX), line, flags=re.I)
        line = re.sub(r"[^:]+warning[^:]*:", colorized(Fore.LIGHTYELLOW_EX), line, flags=re.I)
        emit(line)
