#!/usr/bin/env python3
"""Print the paths and the OpenOCD command for the VS Code extension as one JSON line.

Called by `make dap-info` (.make/vscode.mk) with values taken from the Makefile.
"""
import argparse
import json
import os
import shlex


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("device", "device-flash", "elf", "sfr", "openocd", "log"):
        parser.add_argument("--" + option, required=True)
    args = parser.parse_args(argv)

    log = os.path.abspath(args.log)
    # same command as pipe_target() in stm8gdb.py. Linux, macOS: gdb runs it through sh, so the log
    # path is quoted for sh. Windows: no shell, so `2>` would reach OpenOCD as an argument; its own
    # `-l` is used instead, and gdb splits the arguments itself (backslash escapes), hence `/`.
    if os.name == "nt":
        redirect = '-l "' + log.replace("\\", "/") + '"'
    else:
        redirect = "2>" + shlex.quote(log)
    target = (
        f'| {args.openocd} -c "gdb_port pipe" -c "telnet_port disabled"'
        f' -c "tcl_port disabled" {redirect}'
    )
    info = {
        "device": args.device,
        "deviceFlash": args.device_flash,
        "elf": os.path.abspath(args.elf),
        "sfr": os.path.abspath(args.sfr),
        "openocd": args.openocd,
        "openocdLog": log,
        "gdbTarget": target,
    }
    print(json.dumps(info, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
