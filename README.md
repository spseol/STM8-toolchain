<p align="center"><img src=".make/vscode/media/banner.png" alt="STM8S toolchain" width="480"></p>

# Open-Source STM8S Toolchain (SDCC + Makefile)

[🇨🇿 Česká verze](README.cs.md) | **🇬🇧 English**

Open-source build system for STM8 microcontrollers (tested and used with STM8S).
Supports Linux, Windows, and macOS.

**Includes** / **Supports** / **Can do**:

* *build* using the free [SDCC](http://sdcc.sourceforge.net/) compiler
* *flash* via [OpenOCD](https://openocd.org/) or [stm8flash](https://github.com/vdudouyt/stm8flash)
* *debug* with [STM8 GDB](https://gitlab.com/spseol/mit-no/stm8-binutils-gdb) (`stm8-gdb`) and `cgdb`, or in VS Code / VSCodium
* SPL integration and VS Code / clangd support via `compile_commands.json`

## How does it work?

* It is essentially "just" a starter source code tree and `Makefile` (not only) for teaching
  Microprocessor Technology
  with [STM8S](https://www.st.com/en/microcontrollers-microprocessors/stm8s-series.html).
* Designed for the [SDCC](http://sdcc.sourceforge.net/) compiler (or
  [SDCC-gas](https://github.com/XaviDCR92/sdcc-gas)).
* The Standard Peripheral Library [SPL](https://www.st.com/content/st_com/en/products/embedded-software/mcu-mpu-embedded-software/stm8-embedded-software/stsw-stm8069.html)
  *should* (for licensing reasons) be downloaded separately from the manufacturer's website and use the
  [patch](https://github.com/gicking/STM8-SPL_SDCC_patch). But I think if you run
  `make spl` it won't be a sin. The first `make` runs it by itself, so it needs an internet connection.
* Competition and inspiration:
  * <https://gitlab.com/wykys/stm8-tools>
  * <https://github.com/matejkrenek/stm8-toolchain>


## Usage

First, you need to configure the microprocessor and its frequency in the `Makefile`;
optionally the path to SDCC installation.

```make
#DEVICE_FLASH=stm8s103f3
DEVICE_FLASH=stm8s208rb

F_CPU=16000000

ifeq ($(OS),Windows_NT)
	CC_ROOT = "/c/Program Files/SDCC"
	STVP_ROOT = "/c/Program Files (x86)/STMicroelectronics/st_toolset/stvp"
else
	CC_ROOT = /usr
endif
```

... and then just tinker, program and run `make`.

| Command&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;||
|:---------- |:--------------------------- |
| `make spl` | downloads and prepares SPL libraries |
| `make spl-renew` | re-downloads SPL libraries |
| `make` | compiles the project (alias for `make ihx`) |
| `make ihx` | compiles to Intel HEX format |
| `make elf` | compiles to ELF format (with debug info) |
| `make all` | compiles both (ihx and elf) |
| `make clean` | deletes build output |
| `make clean-spl-objects` | deletes SPL object files (library stays) |
| `make clean-spl` | deletes SPL library (forces full SPL rebuild) |
| `make cleanall` | deletes everything including SPL libraries |
| `make rebuild` | cleans everything and recompiles (elf) |
| `make reflash` | cleans everything and flashes again |
| `make flash` | uploads ihx to the chip — [OpenOCD](https://openocd.org/); on Windows [STVP](https://www.st.com/en/development-tools/stvp-stm8.html) if it is installed, otherwise OpenOCD too; while `make debug` is running it only builds the elf and the debugger uploads it |
| `make flash-elf` | uploads elf to the chip via OpenOCD |
| `make flash-ihex` | converts elf to ihex and uploads via OpenOCD |
| `make stm8flash` | alternative flash method (uses [stm8flash](https://github.com/vdudouyt/stm8flash)) |
| `make stm8flash-unlock` | removes read protection via stm8flash |
| `make debug` | one-command debugging: builds the elf, uploads it, stops at `main()` and opens [cgdb](https://cgdb.github.io/) (gdb TUI without cgdb), see [Debugging](#debugging) |
| `make cgdb` | same as `make debug` |
| `make upgrade` | updates `.make/` and the `Makefile` of an existing project to the current toolchain, see [Updating the toolchain](#updating-the-toolchain) |
| `make vscode` | installs the debugger extension into VS Code / VSCodium (once per computer), see [VS Code](#vs-code--vscodium) |
| `make gdb` | same, but in STM8-gdb TUI mode |
| `make openocd` | starts a standalone OpenOCD on port 3333 (for manual connection; `make debug` does not need it) |
| `make miniterm` | starts serial terminal (pyserial-miniterm) on the first `/dev/ttyUSB*`/`/dev/ttyACM*`, speed detected from the project (`UARTx_Init()` or BRR register writes), override with `BAUD=`, default 115200; alias `make pyserial`. Works reliably only on Linux (on macOS the ports have other names, use `pyserial-miniterm` by hand) |
| `make baudrate` | prints the baud rate detected from the project and where it was found |
| `make switch-device` | interactively switches target device in Makefile |
| `make lib` | interactively selects drivers from `lib/` and moves them to `src/` and `inc/` |
| `make docs-download` | downloads datasheet/reference manual for the current device |
| `make tree` | displays the project tree |


## Debugging

Debugging needs `stm8-gdb`: [STM8 binutils-gdb](https://gitlab.com/spseol/mit-no/stm8-binutils-gdb), a fork of GNU binutils-gdb
with STM8 support, version 15 or newer, with Python and Debug Adapter Protocol (DAP) support (the DAP is needed
for VS Code). It is not part of this toolchain: install it first. The repository has a Debian package
(APT) and the build instructions for Linux and macOS (Apple Silicon). For macOS (Apple Silicon) there is a
prebuilt package with Python bundled in its [releases](https://gitlab.com/spseol/mit-no/stm8-binutils-gdb/-/releases)
(`v15.0.50-stm8.2` or newer; the older `v15.0.50-stm8.1` has no Python).

`make debug` does everything at once: it builds the project with debug info,
starts OpenOCD (it runs only while debugging), uploads the program to the chip
and stops at the beginning of `main()`. No second terminal and no manual
OpenOCD start are needed. After you quit the debugger (`quit`), the program
in the chip runs again from the start.

cgdb shows the source window at the top and the gdb window at the bottom.
`Esc` switches to the source window, `i` back to gdb. In the source window:

| key | |
|:--- |:- |
| `space` | breakpoint on the line under the cursor |
| `F8` / `F10` | next line / step into function |
| `F7` / `F6` | finish function / continue |
| `F5` | restart from the beginning of `main()` |

The gdb window accepts the usual commands (`n`, `s`, `c`, `finish`, `b 42`,
`p x`, `display x`, `Ctrl-C` stops the running program) plus:

| command | |
|:------- |:- |
| `flash` | builds (`make elf`), uploads to the chip and stops at `main()` |
| `reset`, `r` | resets the chip and runs the program to `main()` |
| `vars` | prints local variables; they are printed automatically after every stop (`vars off` / `vars on`) |
| `display x` | prints the variable `x` after every stop; the list is saved to `.debug-display` and the next `make debug` restores it (locals of another function once the program stops there) |

**Peripheral registers (SFR):** gdb knows the peripherals from `stm8s.h`
under the same names as in C, with Tab completion. `p TIM4->CR1`,
`display GPIOB->ODR`, `p GPIOB` (the whole peripheral) and
`set var GPIOD->ODR |= 0x10` work, and so do bit masks from `stm8s.h`:
`p/t SPI->CR2 & SPI_CR2_SSM`. A register is printed in hex, in binary and
with the names of the set bits. What changed since the previous stop is
shown in yellow with the old value, e.g. `0x21 0010 0001  (bylo 0x01)`.
`display/x` and `p/x` skip this, so use `display GPIOB->ODR`.

| command | |
|:------- |:- |
| `sfr` | lists the chip's peripherals |
| `sfr TIM4 [GPIOB …]` | registers of a peripheral and their set bits; a cleared bit is shown as `-UIF` |
| `sfr TIM4.CR1` | one register bit by bit, with descriptions and the reset value |

Reading some registers clears flags (`UART1->DR` clears RXNE, …). `sfr TIM4`
skips such registers, but `p UART1` or `display UART1` reads them.

**New code while debugging:** edit the source and run `make flash` in another
terminal (or from your editor). The debugger detects the change, stops the
program, uploads the new one and stops at `main()`. The `flash` command in gdb
does the same.

The configuration is in `.make/gdbinit`, `.make/stm8gdb.py` and
`.make/stm8sfr.py`; the OpenOCD log is in `build-*-elf/openocd.log`. The `.debug-display` file (one expression
per line) can be edited by hand, e.g. to ship watched variables with an example.


### VS Code / VSCodium

The same debugging works in VS Code (or VSCodium) with the extension from `.make/vscode/`:

1. Install the extension (once per computer) from the extension marketplace of your editor: search for
   *STM8 Toolchain Debugger* (publisher `spseol`) on [Open VSX](https://open-vsx.org/extension/spseol/stm8-toolchain)
   (VSCodium) or in the
   [Visual Studio Marketplace](https://marketplace.visualstudio.com/items?itemName=spseol.stm8-toolchain) (VS Code).
   Without a marketplace, and for development, `make vscode` packages the extension from `.make/vscode/` and
   installs it (`code` or `codium` must be in `PATH`).
2. Restart the editor. Create a project with **`STM8: New Project…`** (Command Palette; it clones the toolchain
   into a new folder, see `stm8.projectsFolder`), or open the folder of an existing project.
3. Press `F5`. The project is built, uploaded to the chip and the program stops at `main()`.

Breakpoints, stepping, variables and CPU registers work as usual. The **STM8 Peripherals** view
in *Run and Debug* shows the peripherals of your chip: tick a bit to change it, the pencil writes a
whole register, the open icon shows one register in detail with descriptions. What changed since
the previous stop is yellow. The tree does not read `UART1->DR` and similar registers (reading clears flags)
until you click *Read*, and a hover over them in the code does not read them either;
a Watch expression, the Debug Console and `p UART1` do, because you asked for it.
Single bits of such registers cannot be changed (the write would read the register first), write the whole register. The status bar
has *Build*, *Flash*, *Debug* and the target chip (click it to switch). Details and troubleshooting:
[`.make/vscode/README.md`](.make/vscode/README.md).

It needs [`stm8-gdb`](https://gitlab.com/spseol/mit-no/stm8-binutils-gdb) 15 or newer (it is not part of the extension, install it first) and `openocd`
in `PATH`, as `make debug` does. The extension is tested on Linux. On macOS (Apple Silicon) it has been verified with a
Nucleo-STM8S208RB: `make`, `make flash`, `make cgdb` and debugging in the extension (`stm8-gdb` from the prebuilt package,
OpenOCD and SDCC from Homebrew). `stm8-gdb` and `openocd` must be in the `PATH` of the program that starts the
editor: start VS Code / VSCodium from a terminal (`code .`), not from the Dock, which does not see the `PATH` of your shell.

#### Updating the toolchain

A project created earlier has an older `.make/`. In VS Code run **`STM8: Update Toolchain`** (the extension offers
it by itself when it finds an older project); without the editor run `make upgrade`, or, if your project
does not have that target yet:

```bash
git fetch https://gitlab.com/spseol/mit-no/STM8S-toolchain.git main
python3 -I -c "$(git show FETCH_HEAD:.make/upgrade.py)" FETCH_HEAD
```

Windows has no `python3` (the one in `WindowsApps` is only a stub for the Microsoft Store): use `python` instead. The same goes for a Linux or macOS machine that has only one of the two.

It refreshes `.make/` and `.vscode/launch.json` and merges the toolchain changes into your `Makefile`
(your chip, frequency and paths stay; if the changes collide, conflict markers `<<<<<<<` are left in the `Makefile`
for you to resolve). It never touches `src/`, `inc/` or your README and commits nothing, so review the result with
`git diff` and commit it yourself. Commit your own changes in `.make/`, `Makefile` and `.vscode/launch.json` first.


## Dependencies

* [GNU Make](https://www.gnu.org/software/make/)
* [GNU Bash](https://www.gnu.org/software/bash/) -- on Windows
  it can be installed together with [Git](https://git-scm.com/download/win).
* [SDCC](http://sdcc.sourceforge.net/)
  or [SDCC-gas](https://github.com/XaviDCR92/sdcc-gas)
* [STM8 binutils-gdb](https://gitlab.com/spseol/mit-no/stm8-binutils-gdb) -- a fork of GNU binutils-gdb with STM8 support
  (`stm8-gdb`, `stm8-ld`); `stm8-gdb` 15 or newer with Python and DAP for debugging
* [OpenOCD](https://openocd.org/) for `flash` and `debug`
* [cgdb](https://cgdb.github.io/) for `make debug` (gdb TUI is used without it)
* [STVP](https://www.st.com/en/development-tools/stvp-stm8.html) -- Windows only and optional:
  `make flash` uses it when it is installed, otherwise OpenOCD.
* ([stm8flash](https://github.com/vdudouyt/stm8flash) for `flash2`)

### On Windows

One command in PowerShell installs everything needed (details in the
[extension README](.make/vscode/README.md#installation)):

```powershell
irm https://gitlab.com/spseol/mit-no/STM8S-toolchain/-/raw/main/.make/install/windows.ps1 | iex          # Chocolatey
irm https://gitlab.com/spseol/mit-no/STM8S-toolchain/-/raw/main/.make/install/windows-winget.ps1 | iex   # or winget
```

## Three Makefiles

There are three `Makefile` variants available in the `.make` directory. This is because the
`SDCC` compiler cannot remove dead code. There are three solutions. The first one is
the most optimal, the other two are kept just in case. **By default the Makefile is set
to the first and most optimal solution `sdcc`.**
For more details, see <https://chytrosti.marrek.cz/stm8oss.html>.

```
$ ls .make/Makefile*
.make/Makefile-sdcc
.make/Makefile-sdcc-gas
.make/Makefile-sdccrm
```
