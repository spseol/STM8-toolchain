#!/bin/bash

# pick/curses needs stdout to be a real TTY; $() would make it a pipe and
# break the interactive UI — so the result is passed via a temp file instead
file=$(mktemp)
python .make/switch_device.py $file
device=$(cat $file)
rm $file

sed -i.backup -E -e "s/^\s*(DEVICE_FLASH\=)stm8\w+\s*\$/\1${device}/" Makefile
echo Switched to $device.
