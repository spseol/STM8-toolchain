#!/usr/bin/env bash
# One-command installer of the STM8S toolchain tools for Debian, Ubuntu, Mint and
# other Debian-based Linux distributions (amd64).
#
#   curl -fsSL https://raw.githubusercontent.com/spseol/STM8-toolchain/main/.make/install/linux.sh | bash
#
# Installs: make, git, python3, SDCC, OpenOCD, stm8-gdb (STM8 binutils-gdb), stm8flash,
# cgdb, ccls and the VS Code / VSCodium extension (when `code` or `codium` is found).
# The tools come from apt, so a tool you have installed in another way (from sources, pip) is probably
# installed again next to it. For more control, install each tool by hand.
# Run it as a normal user, not as root: it calls `sudo` only where it needs to.
# Safe to run again: what is installed already is skipped by apt.
#
# Other systems and a manual installation: https://chytrosti.marrek.cz/stm8install.html

set -euo pipefail

REPO_URL="https://mamut.spseol.cz/debian"
KEYRING="/etc/apt/keyrings/mamut-archive-keyring.gpg"
LIST="/etc/apt/sources.list.d/mamut.list"
EXTENSION_ID="spseol.stm8-toolchain"
BLOG="https://chytrosti.marrek.cz/stm8install.html"

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
die() { printf '\033[1;31m%s\033[0m\n' "$*" >&2; exit 1; }

if [ "$(id -u)" -eq 0 ]; then
    die "Do not run this script as root. Run it as your normal user; it uses sudo itself."
fi

if [ ! -f /etc/debian_version ] || ! command -v apt >/dev/null 2>&1; then
    die "This script supports Debian-based distributions only. See ${BLOG}#linux"
fi
if [ "$(dpkg --print-architecture)" != "amd64" ]; then
    die "Prebuilt packages exist for amd64 only. Build the tools from sources: ${BLOG}#linux"
fi

say "Adding the package repository ${REPO_URL}"
sudo apt-get install -y curl ca-certificates
sudo mkdir -p /etc/apt/keyrings
sudo curl -fsSL "${REPO_URL}/mamut-archive-keyring.gpg" -o "${KEYRING}"
if [ ! -f "${LIST}" ]; then
    echo "deb [arch=amd64 signed-by=${KEYRING}] ${REPO_URL} mamut main" | sudo tee "${LIST}" >/dev/null
fi
sudo apt-get update

say "Installing the tools"
sudo apt-get install -y make git python3 python3-serial openocd cgdb ccls fzf
sudo apt-get install -y -t mamut sdcc sdcc-libraries stm8-binutils-gdb stm8flash stm8newproject

# Serial port access (UART) needs the group dialout.
if ! id -nG "${USER}" | tr ' ' '\n' | grep -qx dialout; then
    say "Adding ${USER} to the group dialout (serial ports)"
    sudo usermod -aG dialout "${USER}"
    NEED_RELOGIN=1
fi

say "Checking"
SDCC_VERSION="$(sdcc -v 2>&1 | head -n1)"
echo "${SDCC_VERSION}"
case "${SDCC_VERSION}" in
    *" 4.5.0 "*) echo "WARNING: SDCC 4.5.0 is broken for STM8. Use 4.4.0, 4.6.0 or newer." >&2 ;;
esac
openocd --version 2>&1 | head -n1
stm8-gdb --version | head -n1
if [ "$(stm8-gdb -batch -ex 'python print(1)' 2>&1 | tail -n1)" = "1" ]; then
    echo "stm8-gdb Python: OK"
else
    echo "WARNING: stm8-gdb has no Python support. The debugger will not work." >&2
fi

installed_ide=0
for ide in code codium; do
    if command -v "${ide}" >/dev/null 2>&1; then
        say "Installing the extension ${EXTENSION_ID} into ${ide}"
        "${ide}" --install-extension "${EXTENSION_ID}" --force || echo "WARNING: installation into ${ide} failed." >&2
        installed_ide=1
    fi
done
if [ "${installed_ide}" -eq 0 ]; then
    echo
    echo "No VS Code or VSCodium found. Install one of them (https://vscodium.com), then"
    echo "install the extension '${EXTENSION_ID}' from its Extensions view."
fi

say "Done"
if [ "${NEED_RELOGIN:-0}" -eq 1 ]; then
    echo "Log out and log in again so that the group change takes effect."
fi
echo "Next: in the editor run 'STM8: New Project…' from the Command Palette."
echo "Details: ${BLOG}"
