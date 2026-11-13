# STM8 Toolchain Debugger

Build, flash and debug [STM8S](https://www.st.com/en/microcontrollers-microprocessors/stm8s-series.html)
microcontroller projects from VS Code or VSCodium. The extension drives the open-source
[STM8S toolchain](https://github.com/spseol/STM8-toolchain) (a `Makefile` around the
[SDCC](http://sdcc.sourceforge.net/) compiler, [OpenOCD](https://openocd.org/) and `stm8-gdb`),
which is used to teach microcontroller programming. It runs on Linux, macOS (Apple Silicon) and Windows 10/11 (x64).

Everything the extension needs (compiler, OpenOCD, `stm8-gdb`) is installed by one command, see
[Installation](#installation).

## What it does

The toolchain works without the extension: build, flash and `make debug` (cgdb) run from any editor
or terminal. The extension is a layer on top of it. It adds `F5` debugging through the Debug Adapter
Protocol, the peripherals view, the status bar buttons, and project creation and update.

- **Build and flash** the project with a click in the status bar: it runs `make` / `make flash` as a
  task in the terminal panel. When `make` ends successfully, the extension switches back (closes the
  panel and focuses the editor); see the setting `stm8.afterSuccess`. After an error the terminal stays
  in front. Compiler errors and warnings appear in the Problems panel.
- **Debug with `F5`**: the project is built, uploaded to the chip and stopped at `main()`.
  Breakpoints, stepping, variables, CPU registers and the **peripheral registers (SFR)** of your chip
  in the *STM8 Peripherals* view, with a bit-by-bit breakdown and writing of single bits.
- **Status bar buttons** for *Build*, *Flash*, *Debug* and the target chip.
- **New projects**: `STM8: New Project…` clones the toolchain into a new project folder and opens it.
- **Toolchain updates**: `STM8: Update Toolchain` brings an existing project up to date.

## Installation

The extension needs a few tools (compiler, OpenOCD, a special `stm8-gdb`). One command per system
installs them all and then the extension itself. Run it in a terminal, once per computer.

### Linux (one-line install)

Debian, Ubuntu, Mint and other Debian-based distributions (amd64).

```sh
curl -fsSL https://raw.githubusercontent.com/spseol/STM8-toolchain/main/.make/install/linux.sh | bash
```

### macOS (Apple Silicon, one-line install)

Installs Homebrew first if you do not have it.

```sh
curl -fsSL https://raw.githubusercontent.com/spseol/STM8-toolchain/main/.make/install/macos.sh | bash
```

### Windows 10/11 (one-line install)

Open *PowerShell* and run one of the two commands below (they do the same, choose the package manager
you prefer). The script asks for administrator rights once.

#### Option 1: Chocolatey

Uses [Chocolatey](https://chocolatey.org). It is installed too when you do not have it:

```powershell
irm https://raw.githubusercontent.com/spseol/STM8-toolchain/main/.make/install/windows.ps1 | iex
```

#### Option 2: winget

Uses winget, which is already in Windows 10/11:

```powershell
irm https://raw.githubusercontent.com/spseol/STM8-toolchain/main/.make/install/windows-winget.ps1 | iex
```

#### The ST-Link driver

The ST-Link driver for Windows is not installed by the script
(ST publishes it after registration): if the board is not found, install
[STSW-LINK009](https://www.st.com/en/development-tools/stsw-link009.html).

### About the scripts

The scripts install the tools with the package manager of the system: `apt` on Linux, Homebrew on macOS,
Chocolatey or winget on Windows. A package manager knows only what it installed itself. If you already have
a tool (for example Git or Python) installed in another way, for example by an installer from a web page,
the script probably installs it a second time next to the first one. If you want more control, do not run
the script and install each tool by hand, see [Requirements](#requirements) and
[Manual installation](#manual-installation-and-building-from-sources).

The scripts are short and readable, [take a look](https://github.com/spseol/STM8-toolchain/tree/main/.make/install) before you run them. Run them again any time:
what is installed already is skipped.

### Next step

Open VS Code or VSCodium and run **`STM8: New Project…`**. On macOS start the editor from a
terminal (`code .`), see [Requirements](#requirements).

### Manual installation and building from sources

Other Linux distributions, a manual installation and building the tools from sources are described at
<https://chytrosti.marrek.cz/stm8install-en.html> (the original is in Czech: <https://chytrosti.marrek.cz/stm8install.html>).

## Requirements

Linux, macOS (Apple Silicon) and Windows 10/11 (x64) are supported. The [installation scripts](#installation)
set all of this up; the list is for those who install the tools by hand:

- `make`, `python3` (on Windows `python`) and `git` (on Windows Git for Windows, which brings `bash`)
- [SDCC](http://sdcc.sourceforge.net/) (the compiler), **not version 4.5.0**: it is broken for STM8
- `openocd`
- `stm8-gdb` **15 or newer**, built with Python and Debug Adapter Protocol support. It is not part of
  the extension. It comes from the STM8 binutils-gdb build: <https://github.com/spseol/STM8-binutils-GDB>
  (a Debian package, an installer for macOS Apple Silicon and one for Windows; release `v15.0.50-stm8.2`
  or newer)
- an ST-Link (for example the one on a Nucleo-STM8S board, or a standalone ST-Link V2)

`stm8-gdb` and `openocd` must be in the `PATH` of the program that starts the editor. On macOS start
VS Code / VSCodium from a terminal (`code .`), not from the Dock. There is no `lsusb` on macOS, so the
ST-Link check is skipped there and OpenOCD reports a missing board instead.

No Node.js or npm is needed.

## Getting started

1. Run **`STM8: New Project…`** from the Command Palette (or use the button in the empty Explorer).
   The toolchain is cloned into a new folder in your projects folder (the `stm8.projectsFolder`
   setting; the first time you choose it), because all projects share the SPL library in `../SPLSPL`.
   The project is opened (in a new window if a folder is already open). It is a git repository on
   the branch `main` with one commit; the toolchain's own history stays on the branch `upstream`.
2. The first build downloads the SPL library (it needs an internet connection once).
3. Pick your chip in the status bar (it changes `DEVICE_FLASH` in the `Makefile`).
4. Connect the board and press **`F5`**.

## Existing projects

Open a project that was cloned from the toolchain and run **`STM8: Update Toolchain`**. The project
must be a git repository with at least one commit, and `.make`, `Makefile` and `.vscode/launch.json`
must have no uncommitted changes; otherwise the update refuses and changes nothing.

It downloads the current toolchain and replaces the toolchain files: `.make/` and
`.vscode/launch.json` (an untracked original is saved as a `.bak`), and appends the missing lines to
`.gitignore`. It never touches your sources (`src/`, `inc/`) or your `README`. Your `Makefile` is
merged, so your settings (chip, frequency, compiler path) stay and the new parts come from the
toolchain. If your edits and the new ones collide, the `Makefile` is left with conflict markers
(`<<<<<<<`) that you resolve by hand; the project does not build until they are gone. If the project
uses `Makefile-sdcc-gas` or `Makefile-sdccrm`, the update offers a switch to the default
`Makefile-sdcc`, the only variant the debugger supports. The switch carries over only the chip
(`DEVICE_FLASH`), not other edits of the `Makefile`; if you decline, nothing is changed.
Nothing is committed or staged, so you can review the result with `git diff`.

The extension also offers the update when it opens a project with an older toolchain.

## Settings

| setting | default | meaning |
|:--- |:--- |:- |
| `stm8.toolchainUrl` | `https://gitlab.com/spseol/mit-no/STM8S-toolchain.git` | Git repository that *Update Toolchain* downloads the toolchain from. It can only be set in your user settings; a project's `.vscode/settings.json` cannot change it, because the downloaded `upgrade.py` is run. |
| `stm8.checkToolchainUpdates` | `true` | When a project is opened, the extension compares the version of the extension sources in the project (`.make/vscode/package.json`) with the installed extension. It offers *Update Toolchain* when the project is older and tells you to update the extension when the project is newer. No network is used. Set it to `false` (user settings or the project's `.vscode/settings.json`) to switch both messages off; *Update Toolchain* and `make upgrade` still work. |
| `stm8.afterSuccess` | `hidePanel` | What *Build* and *Flash* in the status bar do when `make` ends with exit code 0: `hidePanel` (close the panel, focus the editor), `editor` (focus the editor, keep the panel), `previousTerminal` (show the terminal that was active before, otherwise the editor) or `stay` (keep the terminal in front). After an error the terminal always stays in front. VS Code cannot tell which tab of the panel (Problems, Output, …) was active, so it cannot return to that. |
| `stm8.projectsFolder` | *(empty)* | Folder where *New Project* creates your projects. Keep all projects in one folder: they share the SPL library in `../SPLSPL`. Like `stm8.toolchainUrl`, it can only be set in your user settings. |

## Using it

Open the project folder and press `F5` (configuration *STM8 debug*; without a `launch.json` the
default one is used). The task `stm8: build` runs `make debug-files` first (in a new project it downloads SPL
before that); compiler errors appear in the Problems panel. The same task is *Terminal > Run Task > stm8: build*.

**STM8 Peripherals** (Run and Debug sidebar) lists the peripherals of the chip set in the `Makefile`.
Expand one to read its registers at every stop. Changes since the previous stop are yellow.

| action | |
|:--- |:- |
| tick a single-bit field | writes that bit (the other bits stay) |
| GPIO `ODR`, `DDR`, `CR1`, `CR2` | `stm8s.h` has no bit names for them, so the fields `PIN0` … `PIN7` are made up; `IDR` is read-only |
| pencil on a register / multi-bit field | asks for a value (decimal, `0x…` or `0b…`) |
| open icon on a register | tab with all bits, descriptions and the reset value |
| *Read* icon (`UART1.DR`, `SPI.DR`, `I2C.DR`, …) | reads a register whose read clears flags; the tree and a hover in the code never read it, but a Watch expression, the Debug Console and `p UART1` do, because you typed them |

Single bits of registers whose read clears flags (`AWU.CSR`, `I2C.SR3`, `FLASH.IAPSR`, …) cannot be changed from
the tree or the detail tab: the write would read the register first. Write the whole register with the pencil.

Writing to a status register with write-0-to-clear flags (e.g. `TIM4.SR1`) can clear flags other
than the one you meant: the bits are written back as a whole byte.

The Debug Console accepts gdb commands, including `sfr`, `sfr TIM4.CR1`, `p TIM4->CR1`,
`set var GPIOD->ODR |= 0x10`. The status bar has *Build* (`make` as a task), *Flash* (while debugging it restarts the
session, otherwise `make flash` as a task), *Debug* and the target chip (click to switch, only while not debugging).

## When something goes wrong

| message | what to do |
|:--- |:- |
| `Old toolchain – run STM8: Update Toolchain …` | the project has no `.make/vscode.mk`: run *STM8: Update Toolchain* (or copy `.make/` from a current toolchain by hand and add `-include .make/vscode.mk` as the last line of `Makefile`) |
| `stm8-gdb 15 or newer is required` / `not found in PATH` | run the [installation](#installation) script again, or install the STM8 binutils-gdb build with Python and DAP support by hand; on Windows open a new editor window after the installation, on macOS also start VS Code / VSCodium from a terminal (`code .`), a program started from the Dock does not see the `PATH` of your shell |
| `No ST-Link found on USB` | connect the board; on Linux check the udev rules, on Windows install the ST-Link driver ([STSW-LINK009](https://www.st.com/en/development-tools/stsw-link009.html)) |
| `make debug is running (PID …)` | close the cgdb session, one debugger at a time |
| `ST-Link may be in use by another OpenOCD …` | stop the other OpenOCD (`make openocd`, another editor window) |
| `… timed out after 30 s` | the chip does not answer; check the cable and power, the OpenOCD log is `build-*-elf/openocd.log` |

The output of gdb is in the *STM8 debug* output channel.

## How it works

`F5` starts `stm8-gdb -i dap -x .make/gdbinit` and the extension talks the Debug Adapter Protocol to
it through a small proxy (`src/adapter.js`): it attaches gdb to the chip through OpenOCD, loads the
program with the `run` command, answers hovers over registers whose read clears flags, and ends the
session with a message instead of hanging. The peripheral registers come from the same
`.make/stm8sfr.py` that serves `cgdb`.

## Links

- Toolchain: <https://gitlab.com/spseol/mit-no/STM8S-toolchain>
  (public mirror on GitHub: <https://github.com/spseol/STM8-toolchain>)
- Documentation: <https://chytrosti.marrek.cz/stm8oss-en.html> (the original is in Czech: <https://chytrosti.marrek.cz/stm8oss.html>)
- Issues: <https://github.com/spseol/STM8-toolchain/issues>

## License

GPL-3.0-or-later, see the `LICENSE.txt` of the package.

## Installing from a toolchain checkout (`make vscode`)

Developers and users of the toolchain can install the extension without a marketplace:

```
make vscode
```

packages `.make/vscode` into a VSIX (a zip, written by `pack.py`) and installs it into every `code` /
`codium` found in `PATH` (`make vscode IDES=codium` to choose). Once per computer; restart the editor
afterwards. A project tells you when it carries a newer extension than the installed one.

Tests: `pytest .make/vscode`, `node --test .make/vscode/test/*.test.js` (`STM8_HW=1` adds the tests
that flash the connected board).
