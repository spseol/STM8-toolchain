# Changelog

All notable changes to this extension are documented here.

## 0.2.0

### Added

- `STM8: New Project…` clones the STM8S toolchain into a new project folder next to your other
  projects (they share the SPL library in `../SPLSPL`) and offers to open it. The welcome view of an
  empty Explorer has a button for it. Setting `stm8.projectsFolder`.
- `STM8: Update Toolchain` brings the toolchain files of an existing project (`.make/`, `Makefile`)
  up to date without touching your sources (`make upgrade` does the same from a terminal). It is
  also offered when the project carries an older toolchain. Setting `stm8.toolchainUrl`.
- The extension provides the `stm8: build` task itself (with the SDCC problem matcher), so `F5`
  works without a `tasks.json`.
- Marketplace metadata: icon, categories, keywords, links, licence and this changelog.

### Changed

- README rewritten for people who do not know the toolchain.

## 0.1.0

### Added

- Debugging of STM8S projects with `F5`: build, upload to the chip through OpenOCD and stop in
  `main()`; breakpoints, stepping, variables and CPU registers through `stm8-gdb` and the Debug
  Adapter Protocol.
- STM8 Peripherals view: peripheral registers (SFR) of the chip with a bit-by-bit breakdown,
  highlighted changes since the last stop, and writing of registers and single bits. Registers whose
  read clears flags are never read by the view or by hover.
- Status bar buttons *Build*, *Flash*, *Debug* and the target chip.
- `make vscode` packages and installs the extension without Node.js or npm.
