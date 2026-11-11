#!/bin/bash

SPLS=(SPL SPLSPL)

#####################################################################################

any_dir_not_exists() {
    for dir in $@; do
        if ! [ -d ../$dir ]; then
            return 0
        fi
    done
    return 1
}

#####################################################################################


if any_dir_not_exists ${SPLS[@]} ; then

    # git clone: anonymní Git přes HTTPS GitLab nepočítá do limitu 60 požadavků/h na IP
    git clone --depth 1 --quiet https://gitlab.com/spseol/mit-no/spl.git spl-main
    for dir in ${SPLS[@]}; do
        if ! [ -d ../$dir ]; then
            echo "Nahrávám $dir"
            mv spl-main/$dir ..
        fi
    done

    rm -rf spl-main

else
    echo "... ${SPLS[@]} již existují."
fi
