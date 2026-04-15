#!/usr/bin/env bash

if ! command -v fzf &> /dev/null; then
    echo "fzf not found"
    echo "install fzf: https://github.com/junegunn/fzf"
    echo "             $ sudo apt install fzf"
    echo "             % brew install fzf"
    exit 1
fi

cd "$(dirname "$0")/.." >/dev/null

cd lib >/dev/null || { echo "lib dir not found"; exit 1; }
libs=( $(ls *.c *.h 2>/dev/null) )
if [ ${#libs[@]} -eq 0 ]; then
    echo "lib dir is empty"
    exit 1
fi

if BAT=$(command -v batcat 2>/dev/null || command -v bat 2>/dev/null); then
    BAT=( "$BAT" -fS --style=full )
else
    BAT=( cat )
fi

targets=( $( printf '%s\n' "${libs[@]}" \
    | sed -e 's/\.c$//' -e 's/\.h$//' \
    | sort -u \
    | fzf -m --layout=default --preview-window=right \
--preview "{  ls {}.h; ls {}.c } 2>/dev/null | tr '\n' '  '; echo; ${BAT[*]} {}.h {}.c 2>/dev/null" ) )

cd - >/dev/null

for target in "${targets[@]}"; do
    if [ -f lib/${target}.c ]; then
        mv -v lib/${target}.c src
    fi
    if [ -f lib/${target}.h ]; then
        mv -v lib/${target}.h inc
    fi
done
