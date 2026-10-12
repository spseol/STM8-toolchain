#!/usr/bin/env bash

cd "$(dirname "$0")/.." >/dev/null

cd lib >/dev/null || { echo "lib dir not found"; exit 1; }
libs=( $(ls *.c *.h 2>/dev/null) )
if [ ${#libs[@]} -eq 0 ]; then
    echo "lib dir is empty"
    exit 1
fi
cd - >/dev/null

if command -v fzf &> /dev/null; then
    if BAT=$(command -v batcat 2>/dev/null || command -v bat 2>/dev/null); then
        BAT=( "$BAT" -fS --style=full )
    else
        BAT=( cat )
    fi

    targets=( $( cd lib && printf '%s\n' "${libs[@]}" \
        | sed -e 's/\.c$//' -e 's/\.h$//' \
        | sort -u \
        | fzf -m --layout=default --preview-window=right \
    --preview "{  ls {}.h; ls {}.c } 2>/dev/null | tr '\n' '  '; echo; ${BAT[*]} {}.h {}.c 2>/dev/null" ) )
else
    echo "Install fzf for better experience:"
    echo "  \$ sudo apt install fzf"
    echo "  % brew install fzf"
    if [ "$OS" = "Windows_NT" ]; then
        PYTHON=python
    else
        PYTHON=python3
    fi
    file=$(mktemp)
    "$PYTHON" .make/lib_mv.py "$file"
    targets=()
    # while read instead of mapfile: macOS ships bash 3.2 without mapfile
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line%$'\r'}
        [ -n "$line" ] && targets+=( "$line" )
    done < "$file"
    rm -f "$file"
fi

for target in "${targets[@]}"; do
    if [ -f lib/${target}.c ]; then
        mv -v lib/${target}.c src
    fi
    if [ -f lib/${target}.h ]; then
        mv -v lib/${target}.h inc
    fi
done
