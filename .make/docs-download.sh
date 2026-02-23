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

download() {
    local url="$1"
    local out="$2"
    if [ -f "$out" ]; then
        echo "Already exists: $out"
    else
        echo "Downloading: $out"
        curl -L --fail --http1.1 --progress-bar -o "$out" "$url" || { rm -f "$out"; exit 1; }
    fi
}

print_url() {
    local url="$1"
    local out="$2"
    if [ -f "docs/$out" ]; then
        echo "Already exists: docs/$out"
    else
        echo "Save as docs/$out:"
        echo "  $url"
    fi
}

mkdir -p docs
print_url "$RM_URL" "RM0016-STM8S-reference-manual.pdf"
print_url "${DS_BASE}/${DS}.pdf" "${DS}-datasheet.pdf"
