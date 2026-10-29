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
    # same command as connect() in stm8gdb.py; gdb runs it through sh, so the log path is quoted
    target = (
        f'| {args.openocd} -c "gdb_port pipe" -c "telnet_port disabled"'
        f' -c "tcl_port disabled" 2>{shlex.quote(log)}'
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
