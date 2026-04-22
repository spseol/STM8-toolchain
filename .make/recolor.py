import re
import sys
from colorama import Fore, Back, Style, just_fix_windows_console

just_fix_windows_console()


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
        sys.stderr.write(Style.BRIGHT + Fore.RED + Back.BLACK + line.rstrip() + Style.RESET_ALL + "\n")
        sys.stderr.write(Style.BRIGHT + Fore.YELLOW + Back.BLACK +
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
        sys.stderr.write(line)
