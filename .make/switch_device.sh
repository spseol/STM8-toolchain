#!/bin/bash

# usage: [PYTHON=python3] switch_device.sh [CHIP]   (make passes its PYTHON)
PYTHON=${PYTHON:-python}
# Without CHIP the chip is picked interactively, with CHIP (e.g. stm8s103f3) nothing is asked.
if [ -n "$1" ]; then
    device=$("$PYTHON" .make/devices.py --check "$1") || exit 1
else
    # pick/curses needs stdout to be a real TTY; $() would make it a pipe and
    # break the interactive UI — so the result is passed via a temp file instead
    file=$(mktemp)
    "$PYTHON" .make/switch_device.py $file || { rm -f $file; exit 1; }
    device=$(cat $file)
    rm $file
fi

sed -i.backup -E -e "s/^\s*(DEVICE_FLASH\=)stm8\w+\s*\$/\1${device}/" Makefile
echo Switched to $device.
