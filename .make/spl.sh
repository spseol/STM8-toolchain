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

    curl https://gitlab.com/spseol/mit-no/spl/-/archive/main/spl-main.tar.gz --output spl.tgz
    if [[ "$(uname -s)" == "Darwin" ]]; then
        COPYFILE_DISABLE=1 tar -xf spl.tgz
    else
        tar xzf spl.tgz
    fi
    mv spl.tgz ../SPL.tgz

    for dir in ${SPLS[@]}; do
        if ! [ -d ../$dir ]; then
            echo "Nahrávám $dir"
            mv spl-main/$dir ..
        fi
    done

    rm -R spl-main

else
    echo "... ${SPLS[@]} již existují."
fi
