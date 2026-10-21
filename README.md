# Open-Source STM8S Toolchain (SDCC + Makefile)

[🇨🇿 Česká verze](README.cs.md) | **🇬🇧 English**

Open-source build system for STM8 microcontrollers (tested and used with STM8S).
Supports Linux, Windows, and macOS.

**Includes** / **Supports** / **Can do**:

* *build* using the free [SDCC](http://sdcc.sourceforge.net/) compiler
* *flash* via [OpenOCD](https://openocd.org/) or [stm8flash](https://github.com/vdudouyt/stm8flash)
* *debug* with GDB and `cgdb`
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
  `make spl` it won't be a sin.
* Competition and inspiration:
  * <https://gitlab.com/wykys/stm8-tools>
  * <https://github.com/matejkrenek/stm8-toolchain>


## Usage

First, you need to configure the microprocessor and its frequency in the `Makefile`;
optionally the path to SDCC installation, or
[STVP](https://www.st.com/en/development-tools/stvp-stm8.html).

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
| `make flash` | uploads ihx to the chip — [OpenOCD](https://openocd.org/) on Linux, [STVP](https://www.st.com/en/development-tools/stvp-stm8.html) on Windows; while `make debug` is running it only builds the elf and the debugger uploads it |
| `make flash-elf` | uploads elf to the chip via OpenOCD |
| `make flash-ihex` | converts elf to ihex and uploads via OpenOCD |
| `make stm8flash` | alternative flash method (uses [stm8flash](https://github.com/vdudouyt/stm8flash)) |
| `make stm8flash-unlock` | removes read protection via stm8flash |
| `make debug` | one-command debugging: builds the elf, uploads it, stops at `main()` and opens [cgdb](https://cgdb.github.io/) (gdb TUI without cgdb), see [Debugging](#debugging) |
| `make cgdb` | same as `make debug` |
| `make gdb` | same, but in STM8-gdb TUI mode |
| `make openocd` | starts a standalone OpenOCD on port 3333 (for manual connection; `make debug` does not need it) |
| `make miniterm` | starts serial terminal (pyserial-miniterm) on the first `/dev/ttyUSB*`/`/dev/ttyACM*`, speed detected from the project (`UARTx_Init()` or BRR register writes), override with `BAUD=`, default 115200; alias `make pyserial` |
| `make baudrate` | prints the baud rate detected from the project and where it was found |
| `make switch-device` | interactively switches target device in Makefile |
| `make lib` | interactively selects drivers from `lib/` and moves them to `src/` and `inc/` |
| `make docs-download` | downloads datasheet/reference manual for the current device |
| `make tree` | displays the project tree |


## Debugging

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


## Dependencies

* [GNU Make](https://www.gnu.org/software/make/)
* [GNU Bash](https://www.gnu.org/software/bash/) -- on Windows
  it can be installed together with [Git](https://git-scm.com/download/win).
* [SDCC](http://sdcc.sourceforge.net/)
  or [SDCC-gas](https://github.com/XaviDCR92/sdcc-gas)
* [STM8 binutils](https://stm8-binutils-gdb.sourceforge.io) (`stm8-gdb`, `stm8-ld`)
* [OpenOCD](https://openocd.org/) for `flash` and `debug`
* [cgdb](https://cgdb.github.io/) for `make debug` (gdb TUI is used without it)
  or [STVP](https://www.st.com/en/development-tools/stvp-stm8.html)
  for `flash` on Windows.
* ([stm8flash](https://github.com/vdudouyt/stm8flash) for `flash2`)

### On Windows

[`choco`](https://chocolatey.org/)` install git make vscode mingw`

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
