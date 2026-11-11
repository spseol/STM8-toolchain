#!/bin/bash
#
# https://www.st.com/content/ccc/resource/technical/document/reference_manual/9a/1b/85/07/ca/eb/4f/dd/CD00190271.pdf/files/CD00190271.pdf/jcr:content/translations/en.CD00190271.pdf
# https://www.st.com/resource/en/datasheet/stm8s103f2.pdf
# https://www.st.com/resource/en/datasheet/stm8s105c4.pdf
# https://www.st.com/resource/en/datasheet/stm8s207mb.pdf

DEVICE="${1^^}"

RM_URL="https://www.st.com/content/ccc/resource/technical/document/reference_manual/9a/1b/85/07/ca/eb/4f/dd/CD00190271.pdf/files/CD00190271.pdf/jcr:content/translations/en.CD00190271.pdf"
DS_BASE="https://www.st.com/resource/en/datasheet"

case "$DEVICE" in
    *001*) DS="stm8s001j3" ;;
    *003*) DS="stm8s003f3" ;;
    *005*) DS="stm8s005c6" ;;
    *007*) DS="stm8s007c8" ;;
    *103*) DS="stm8s103f2" ;;
    *105*) DS="stm8s105c4" ;;
    *207*|*208*) DS="stm8s207mb" ;;
    *)
        echo "Unknown device: $DEVICE"
        exit 1
        ;;
esac

if [ -t 1 ]; then
    B=$'\e[1m'; G=$'\e[32m'; Y=$'\e[33m'; C=$'\e[36m'; N=$'\e[0m'
else
    B=""; G=""; Y=""; C=""; N=""
fi

mkdir -p docs

# dvojice "soubor|URL"
DOCS=(
    "RM0016-STM8S-reference-manual.pdf|$RM_URL"
    "${DS}-datasheet.pdf|${DS_BASE}/${DS}.pdf"
)

MIN_SIZE=50000  # menší soubor je chybová stránka nebo zástupný prázdný soubor

# platné PDF: dost velké a začíná "%PDF"
is_ok() {
    [ -s "$1" ] && [ "$(stat -c %s "$1")" -ge "$MIN_SIZE" ] && [ "$(head -c 4 "$1")" = "%PDF" ]
}

missing=()
for d in "${DOCS[@]}"; do
    f="docs/${d%%|*}"
    if is_ok "$f"; then
        echo "${G}✔${N} $f ($(du -h "$f" | cut -f1))"
    else
        missing+=("$d")
        # prázdný zástupný soubor; neúplný nebo vadný soubor se přepíše také
        : > "$f"
    fi
done

[ ${#missing[@]} -eq 0 ] && exit 0

echo
echo "${Y}${B}The documentation must be downloaded manually.${N}"
echo "ST blocks downloads by script (bot protection),"
echo "so nothing is downloaded automatically. The ${B}docs/${N} folder contains empty"
echo "placeholder files. Steps:"
echo
echo "  1. Open the link in a browser (in the terminal Ctrl+click the URL)."
echo "  2. If ST shows a consent or verification prompt, confirm it."
echo "  3. Save the PDF over the placeholder file ${B}$PWD/docs/…${N} and confirm the overwrite."
echo "  4. Run ${B}make docs-download${N} again, it checks that the files are downloaded."
echo
n=0
for d in "${missing[@]}"; do
    n=$((n + 1))
    echo "${B}File $n of ${#missing[@]}:${N} ${C}docs/${d%%|*}${N}"
    echo "  ${d#*|}"
    echo
done
exit 1
