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
| `make flash` | uploads ihx to the chip — [OpenOCD](https://openocd.org/) on Linux, [STVP](https://www.st.com/en/development-tools/stvp-stm8.html) on Windows |
| `make flash-elf` | uploads elf to the chip via OpenOCD |
| `make flash-ihex` | converts elf to ihex and uploads via OpenOCD |
| `make stm8flash` | alternative flash method (uses [stm8flash](https://github.com/vdudouyt/stm8flash)) |
| `make stm8flash-unlock` | removes read protection via stm8flash |
| `make openocd` | starts OpenOCD for debugging (keeps running, then use `make gdb`) |
| `make gdb` | starts STM8-gdb in TUI mode |
| `make cgdb` | starts cgdb with STM8-gdb |
| `make switch-device` | interactively switches target device in Makefile |
| `make lib` | interactively selects drivers from `lib/` and moves them to `src/` and `inc/` |
| `make docs-download` | downloads datasheet/reference manual for the current device |
| `make tree` | displays the project tree |


## Dependencies

* [GNU Make](https://www.gnu.org/software/make/)
* [GNU Bash](https://www.gnu.org/software/bash/) -- on Windows
  it can be installed together with [Git](https://git-scm.com/download/win).
* [SDCC](http://sdcc.sourceforge.net/)
  or [SDCC-gas](https://github.com/XaviDCR92/sdcc-gas)
* [STM8 binutils](https://stm8-binutils-gdb.sourceforge.io) (`stm8-gdb`, `stm8-ld`)
* [OpenOCD](https://openocd.org/) for `flash` and `debug`
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
