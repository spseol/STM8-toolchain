# STM8 Toolchain Debugger (VS Code / VSCodium)

Debugs STM8S projects of the STM8S toolchain: press `F5`, the project is built, uploaded to the
chip and the program stops at `main()`. Breakpoints, stepping, variables, CPU registers and the
peripheral registers (SFR) of your chip.

## Install

```
make vscode
```

packages this folder into a VSIX and installs it into every `code` / `codium` found in `PATH`
(`make vscode IDES=codium` to choose). Once per computer; restart the editor afterwards. The project
tells you when it carries a newer extension than the installed one.

Needs `stm8-gdb` 15 or newer (it has the Debug Adapter Protocol built in) and `openocd` in `PATH`.
No Node.js or npm is needed.

## Use

Open the project folder and press `F5` (configuration *STM8 debug*; without a `launch.json` the
default one is used). The task `stm8: build` runs `make debug-files` first (in a new project it downloads SPL
before that); compiler errors appear in the Problems panel.

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
session with a message instead of hanging. The peripheral registers come from the same `.make/stm8sfr.py`
that serves cgdb (`sfr-json`, `sfr-set`). Design, plan and the spike measurements are in the git history
(commits `0b2c908`, `02d222e`). Tests: `pytest .make/vscode`, `node --test .make/vscode/test/*.test.js`
(`STM8_HW=1` adds the tests that flash the connected board).
