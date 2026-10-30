# STM8 Toolchain Debugger

Build, flash and debug [STM8S](https://www.st.com/en/microcontrollers-microprocessors/stm8s-series.html)
microcontroller projects from VS Code or VSCodium. The extension drives the open-source
[STM8S toolchain](https://github.com/spseol/STM8S-toolchain) (a `Makefile` around the
[SDCC](http://sdcc.sourceforge.net/) compiler, [OpenOCD](https://openocd.org/) and `stm8-gdb`),
which is used to teach microcontroller programming.

## What it does

- **Build and flash** the project with a click in the status bar: it runs `make` / `make flash` in
  a terminal. Compiler errors and warnings appear in the Problems panel when the build is run by
  `F5` or by the `stm8: build` task (*Terminal > Run Task*).
- **Debug with `F5`**: the project is built, uploaded to the chip and stopped at `main()`.
  Breakpoints, stepping, variables, CPU registers and the **peripheral registers (SFR)** of your chip
  in the *STM8 Peripherals* view, with a bit-by-bit breakdown and writing of single bits.
- **Status bar buttons** for *Build*, *Flash*, *Debug* and the target chip.
- **New projects**: `STM8: New Project…` clones the toolchain into a new project folder and opens it.
- **Toolchain updates**: `STM8: Update Toolchain` brings an existing project up to date.

## Requirements

Linux only: the extension relies on `lsusb`, `pgrep` and a pipe to OpenOCD; Windows and macOS are not
supported or tested. You need:

- `make`, `python3` and `git`
- [SDCC](http://sdcc.sourceforge.net/) (the compiler)
- `openocd`
- `stm8-gdb` **15 or newer**, built with Python and Debug Adapter Protocol support. It comes from the
  STM8 binutils-gdb build: <https://stm8-binutils-gdb.sourceforge.io>
- an ST-Link (for example the one on a Nucleo-STM8S board, or a standalone ST-Link V2)

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
| `stm8.toolchainUrl` | `https://gitlab.com/spseol/mit-no/STM8S-toolchain.git` | Git repository that *Update Toolchain* downloads the toolchain from. It cannot be set by a project (`.vscode/settings.json`), because the downloaded `upgrade.py` is run. |
| `stm8.projectsFolder` | *(empty)* | Folder where *New Project* creates your projects. Keep all projects in one folder: they share the SPL library in `../SPLSPL`. |

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
`set var GPIOD->ODR |= 0x10`. The status bar has *Build* (`make` in a terminal), *Flash* (while debugging it restarts the
session, otherwise `make flash` in the same terminal), *Debug* and the target chip (click to switch, only while not debugging).

## When something goes wrong

| message | what to do |
|:--- |:- |
| `Old toolchain – run STM8: Update Toolchain …` | the project has no `.make/vscode.mk`: run *STM8: Update Toolchain* (or copy `.make/` from a current toolchain by hand and add `-include .make/vscode.mk` as the last line of `Makefile`) |
| `stm8-gdb 15 or newer is required` / `not found in PATH` | install the STM8 binutils-gdb build with Python and DAP support |
| `No ST-Link found on USB` | connect the board; on Linux check the udev rules |
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

- Toolchain: <https://github.com/spseol/STM8S-toolchain>
  (mirror: <https://gitlab.com/spseol/mit-no/STM8S-toolchain>)
- Documentation in Czech: <https://chytrosti.marrek.cz/stm8oss.html>
- Issues: <https://github.com/spseol/STM8S-toolchain/issues>

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
