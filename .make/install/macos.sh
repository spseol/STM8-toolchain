#!/usr/bin/env bash
# One-command installer of the STM8S toolchain tools for macOS (Apple Silicon).
#
#   curl -fsSL https://gitlab.com/spseol/mit-no/STM8S-toolchain/-/raw/main/.make/install/macos.sh | bash
#
# Installs (when missing): Command Line Tools, Homebrew, make, git, SDCC, OpenOCD, cgdb,
# ccls, stm8-gdb (STM8 binutils-gdb, prebuilt package with its own Python), VSCodium
# (only when neither VS Code nor VSCodium is found) and the editor extension.
# Run it as a normal user, not as root: it calls `sudo` only where it needs to.
# Safe to run again: what is installed already is skipped.
# Works with the old bash 3.2 that macOS ships: no bash 4 features here (arrays with
# `declare -A`, `mapfile`, `${var,,}`, `<<<`, `|&`), a test checks that.
#
# A manual installation and details: https://chytrosti.marrek.cz/stm8install.html#macos

set -euo pipefail

GITLAB_API="https://gitlab.com/api/v4/projects/spseol%2Fmit-no%2Fstm8-binutils-gdb"
PKG_NAME="stm8-binutils-gdb-macos-arm64.pkg"
EXTENSION_ID="spseol.stm8-toolchain"
BLOG="https://chytrosti.marrek.cz/stm8install.html"

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
die() { printf '\033[1;31m%s\033[0m\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = "Darwin" ] || die "This script is for macOS. See ${BLOG}"
[ "$(id -u)" -ne 0 ] || die "Do not run this script as root. Run it as your normal user."
if [ "$(uname -m)" != "arm64" ]; then
    echo "WARNING: this is not an Apple Silicon Mac. The prebuilt stm8-gdb is arm64 only;"
    echo "         build it from sources (${BLOG}#macos-stm8-binutils-gdb)." >&2
fi

# --- Command Line Tools (git, compilers; Homebrew needs them) ---
if ! xcode-select -p >/dev/null 2>&1; then
    say "Installing Command Line Tools (a dialog opens, click Install and wait)"
    xcode-select --install || true
    until xcode-select -p >/dev/null 2>&1; do sleep 5; done
fi

# --- Homebrew ---
find_brew() {
    command -v brew 2>/dev/null && return 0
    for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do
        [ -x "$b" ] && { echo "$b"; return 0; }
    done
    return 1
}
if ! BREW="$(find_brew)"; then
    say "Installing Homebrew"
    NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    BREW="$(find_brew)" || die "Homebrew installation failed."
fi
eval "$("${BREW}" shellenv)"
SHELLENV_LINE="eval \"\$(${BREW} shellenv)\""
if ! grep -qsF "${SHELLENV_LINE}" "${HOME}/.zprofile"; then
    echo "${SHELLENV_LINE}" >> "${HOME}/.zprofile"
fi

# --- Tools from Homebrew ---
say "Installing the tools with Homebrew"
brew install make git coreutils sdcc open-ocd cgdb ccls

# --- stm8-gdb ---
gdb_major() { stm8-gdb --version 2>/dev/null | head -n1 | grep -Eo '[0-9]+\.[0-9]+' | head -n1 | cut -d. -f1; }
if [ "$(gdb_major || true)" -ge 15 ] 2>/dev/null; then
    say "stm8-gdb is installed already, skipping"
elif [ "$(uname -m)" = "arm64" ]; then
    say "Installing stm8-gdb (prebuilt package; asks for your password)"
    TMP="$(mktemp -d)"
    trap 'rm -rf "${TMP}"' EXIT
    PKG_URL="$(curl -fsSL -L "${GITLAB_API}/releases/permalink/latest" \
        | python3 -c 'import json,sys
name = sys.argv[1]
for l in json.load(sys.stdin)["assets"]["links"]:
    if l["name"] == name:
        print(l.get("direct_asset_url") or l["url"])
        break' "${PKG_NAME}")"
    [ -n "${PKG_URL}" ] || die "Package ${PKG_NAME} not found in the latest release: ${GITLAB_API%/api*}"
    curl -fSL "${PKG_URL}" -o "${TMP}/${PKG_NAME}"
    sudo installer -pkg "${TMP}/${PKG_NAME}" -target /
fi
export PATH="/usr/local/bin:${PATH}"

# --- Editor and extension ---
if ! command -v code >/dev/null 2>&1 && ! command -v codium >/dev/null 2>&1 \
   && [ ! -d "/Applications/Visual Studio Code.app" ] && [ ! -d "/Applications/VSCodium.app" ]; then
    say "Installing VSCodium"
    brew install --cask vscodium
fi
for ide in code codium; do
    if command -v "${ide}" >/dev/null 2>&1; then
        say "Installing the extension ${EXTENSION_ID} into ${ide}"
        "${ide}" --install-extension "${EXTENSION_ID}" --force || echo "WARNING: installation into ${ide} failed." >&2
    fi
done

# --- Check ---
say "Checking"
SDCC_VERSION="$(sdcc -v 2>&1 | head -n1)"
echo "${SDCC_VERSION}"
case "${SDCC_VERSION}" in
    *" 4.5.0 "*) echo "WARNING: SDCC 4.5.0 is broken for STM8. Use 4.4.0, 4.6.0 or newer." >&2 ;;
esac
openocd --version 2>&1 | head -n1
if command -v stm8-gdb >/dev/null 2>&1; then
    stm8-gdb --version | head -n1
    if [ "$(stm8-gdb -batch -ex 'python print(1)' 2>&1 | tail -n1)" = "1" ]; then
        echo "stm8-gdb Python: OK"
    else
        echo "WARNING: stm8-gdb has no Python support. The debugger will not work." >&2
    fi
else
    echo "WARNING: stm8-gdb not found." >&2
fi

say "Done"
echo "Open a NEW terminal window (so that PATH is loaded) and start the editor from it:"
echo "    code .        (or: codium .)"
echo "An editor started from the Dock does not see stm8-gdb and openocd."
echo "Then run 'STM8: New Project…' from the Command Palette."
echo "Details: ${BLOG}"
