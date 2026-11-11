# Changelog

All notable changes to this extension are documented here.

## 1.0.1 11-11-2026

### Changed

- The installation scripts and the `stm8-gdb` and `ccls` installers are downloaded from GitHub
  (`spseol/STM8-toolchain`, `spseol/STM8-binutils-GDB`, `spseol/ccls`) instead of GitLab, because
  GitLab.com limits anonymous web and API requests to 60 per hour per IP address (a school network shares
  one address). The installers use fixed file names, no API call is needed.
- `make spl` downloads the SPL libraries with `git clone` (anonymous Git over HTTPS is not limited) instead
  of a `curl` of an archive. Use *Update Toolchain* to get the new `Makefile` in an existing project.
- README: new commands and links for the installation.

## 1.0.0 10-11-2026

First stable release: the extension works on Linux, macOS (Apple Silicon) and Windows 10/11.

### Added

- Installation with one command per system (`.make/install/linux.sh`, `.make/install/macos.sh`,
  `.make/install/windows.ps1` with Chocolatey, `.make/install/windows-winget.ps1` with winget). The scripts install the compiler,
  OpenOCD, `stm8-gdb` and the extension, and install Homebrew (macOS) or Chocolatey (Windows) when missing.
  See the README.

### Changed

- Windows: `make flash` (the *Flash* button) uses STVP when it is installed and OpenOCD otherwise, so
  STVP is no longer needed. Use *Update Toolchain* to get the new `Makefile` in an existing project.
- README: Windows is supported (the notes that it is not were removed), new *Installation* section.

## 0.3.4 09-11-2026

### Fixed

- Windows: `make` typed in the integrated terminal of VSCodium (PowerShell, cmd) works. The terminal inherits
  `PATH` of the editor started from the Start menu, which has only `<Git>\cmd`, so `make` did not find
  `bash`, `tr` and `nproc` ("CreateProcess ... failed", "No rule to make target '../SPLSPL/mk/.mk'"). The
  extension now puts `<Git>\usr\bin` first in `PATH` of terminals opened after it is activated, not only of
  its own tasks. Terminals that are already open must be reopened.

## 0.3.3 06-11-2026

### Fixed

- Windows: the extension runs `python`, not `python3`. The `python3.exe` in `WindowsApps` is only a stub for
  the Microsoft Store and exits with code 9009, which Update Toolchain reported as "failed (code 9009)".
  An exit code of `upgrade.py` other than 0 to 3 is now an error with an explanation, not a success.
- Windows: `make` is run with `<Git>\usr\bin` first in `PATH` (build tasks, project info, chip switch, New
  Project), so that an editor started from the Start menu finds `bash` of Git for Windows. Without it
  `make` complains about `No rule to make target '../SPLSPL/mk/.mk'`.
- Windows: the peripheral registers load in the Debug Console session. `add-symbol-file` got a path with
  backslashes, which gdb takes as escapes ("Registry periferií nejsou k dispozici"), and `sfr_gen.py` passed a
  source path with backslashes to SDCC, which damages the debug information of `sfr.elf` ("Dwarf Error: Could
  not find abbrev number"). Both paths use `/` now.
- Windows: Czech letters in the Debug Console ("periferiĂ­" instead of "periferií"): gdb runs with
  `PYTHONUTF8=1`.
- "Old toolchain" is reported only when the target `dap-info` is missing. Another "No rule to make target"
  is shown as an error of make (with a hint when bash is missing), so Update Toolchain is no longer offered
  for a problem it cannot fix.

### Changed

- The Python of the toolchain is chosen by what is installed: the first of `python3` and `python` found in
  `PATH` (macOS has only `python3`, Linux usually both), `python3` when neither is found. Windows stays on
  `python`, because `python3.exe` there is the Microsoft Store stub. The Makefiles and the helper scripts
  (`switch_device.sh`, `pyserial.auto`, `lib-mv.sh`) use the same order.

## 0.3.1 04-11-2026

### Changed

- README: macOS (Apple Silicon) is supported. The release `v15.0.50-stm8.2` of STM8 binutils-gdb has a
  prebuilt macOS package of `stm8-gdb` with Python and DAP bundled. A complete session (build, flash,
  debugging in the extension) is verified on a Mac with a Nucleo-STM8S208RB; the editor has to be started
  from a terminal so that it sees `stm8-gdb` and `openocd` in `PATH`.

### Fixed

- `stm8-gdb` started without `LANG` (locale C, for example by a program started from the macOS GUI)
  stopped with `UnicodeEncodeError` while loading `.make/stm8gdb.py`. `.make/gdbinit` now sets
  `host-charset` to UTF-8. The fix is in the toolchain, not in the extension: a project gets it with
  `STM8: Update Toolchain`.

## 0.3.0 03-11-2026

### Added

- Setting `stm8.afterSuccess`: when `make` started by *Build* or *Flash* in the status bar ends with
  exit code 0, the extension closes the panel and focuses the editor (`hidePanel`, the default),
  only focuses the editor (`editor`), shows the previously active terminal (`previousTerminal`), or
  does nothing (`stay`). After an error the terminal stays in front.

### Changed

- *Build* and *Flash* in the status bar run `make` / `make flash` as VS Code tasks (`stm8: make`,
  `stm8: make flash`) instead of typing the command into a terminal; the exit code is needed for
  `stm8.afterSuccess`. Compiler errors and warnings now appear in the Problems panel for them too.

## 0.2.1 01-11-2026

### Changed

- README: the first paragraph says that `stm8-gdb` (the *STM8 binutils-gdb* build of GDB) is not part
  of the extension, has to be installed first, and links to where to get it.
- README: the extension is tested on Linux; everything except STM8 binutils-gdb is also tested on
  macOS, so it should work there once `stm8-gdb` does.

## 0.2.0 31-10-2026

### Added

- `STM8: New Project…` clones the STM8S toolchain into a new project folder next to your other
  projects (they share the SPL library in `../SPLSPL`) and opens it. The welcome view of an
  empty Explorer has a button for it. Setting `stm8.projectsFolder`.
- `STM8: Update Toolchain` brings the toolchain files of an existing project (`.make/`, `Makefile`)
  up to date without touching your sources (`make upgrade` does the same from a terminal). It is
  also offered when the project carries an older toolchain. Setting `stm8.toolchainUrl`.
- The extension provides the `stm8: build` task itself (with the SDCC problem matcher), so `F5`
  works without a `tasks.json`.
- Marketplace metadata: icon, categories, keywords, links, licence and this changelog.

### Changed

- README rewritten for people who do not know the toolchain.

## 0.1.0 30-10-2026

### Added

- Debugging of STM8S projects with `F5`: build, upload to the chip through OpenOCD and stop in
  `main()`; breakpoints, stepping, variables and CPU registers through `stm8-gdb` and the Debug
  Adapter Protocol.
- STM8 Peripherals view: peripheral registers (SFR) of the chip with a bit-by-bit breakdown,
  highlighted changes since the last stop, and writing of registers and single bits. Registers whose
  read clears flags are never read by the view or by hover.
- Status bar buttons *Build*, *Flash*, *Debug* and the target chip.
- `make vscode` packages and installs the extension without Node.js or npm.
