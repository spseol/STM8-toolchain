# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## O projektu

Startovací strom zdrojových kódů a `Makefile` pro výuku mikroprocesorové techniky s mikrokontroléry STM8S. Překládá se překladačem [SDCC](http://sdcc.sourceforge.net/). Standardní knihovna periférií (SPL) je spravovaná zvlášť v `../SPLSPL/`.

## Základní příkazy

```bash
make spl          # stáhne a připraví SPL knihovny (nutné spustit poprvé)
make              # zkompiluje projekt do Intel HEX (alias make ihx)
make elf          # zkompiluje s debug informacemi do ELF
make all          # zkompiluje obojí
make flash        # nahraje do chipu přes OpenOCD (Linux) nebo STVP (Windows)
make stm8flash    # nahraje přes stm8flash (alternativa)
make clean        # smaže build adresáře a compile_commands.json
make cleanall     # smaže i SPL knihovny
make rebuild      # clean + elf
make reflash      # clean + flash
make debug        # ladění jedním příkazem: build elf + nahrání + main() v cgdb (alias make cgdb)
make gdb          # totéž v stm8-gdb -q --tui
make openocd      # samostatný OpenOCD na :3333 (make debug/gdb se k němu připojí, jinak si OpenOCD spustí sám)
make switch-device # interaktivní přepnutí cílového čipu v Makefile
make lib          # interaktivní výběr (fzf) driver souborů z lib/ a přesun do src/ a inc/
make tree         # zobrazí strom projektu
```

## Konfigurace cílového zařízení

Před první kompilací nastavit v `Makefile`:

```make
DEVICE_FLASH=stm8s208rb   # cílový čip (malými písmeny)
F_CPU=16000000             # frekvence v Hz
CC_ROOT = /usr/local/stow/sdcc-4.4.0  # cesta k SDCC (nebo zakomentovat pro PATH)
```

Podporovaná zařízení: `stm8s003k3`, `stm8s103f3`, `stm8s105c6`, `stm8s208rb`.

## Struktura projektu

```
src/          # zdrojové soubory projektu (*.c)
inc/          # hlavičkové soubory projektu (*.h)
lib/          # připravené driver soubory (uart1, swi2c, swspi, …) — přesunout do src/inc/ pomocí make lib
.make/        # pomocné skripty a nástroje Makefile
  Makefile-sdcc       # výchozí varianta (pure SDCC, dead-code removal přes sekce)
  Makefile-sdcc-gas   # varianta pro SDCC-gas
  Makefile-sdccrm     # varianta s sdccrm
../SPLSPL/    # SPL knihovna (mimo repo, stažena pomocí make spl)
build-*/      # výstup kompilace (generovaný, v .gitignore)
```

Výchozí Makefile je sylink/kopie `.make/Makefile-sdcc`. Alternativní varianty jsou popsány na <https://chytrosti.marrek.cz/stm8oss.html>.

## Architektura zdrojového kódu

`src/main.c` obsahuje `init()` a `main()`. Makra pro GPIO jsou v `inc/main.h`:

```c
LOW(LED)      // GPIO_WriteLow(LED_PORT, LED_PIN)
HIGH(LED)     // GPIO_WriteHigh(LED_PORT, LED_PIN)
REVERSE(LED)  // GPIO_WriteReverse(LED_PORT, LED_PIN)
READ(LED)     // GPIO_ReadInputPin → bool
PUSH(BTN)     // aktivní LOW tlačítko → bool
```

Periférie se zapínají `#ifdef STM8S208` (resp. `103`, `105`, `003`) – `DEVICE` je definován Makefile při kompilaci.

Milis timer běží na TIM4 (viz `src/milis.c`). Printf přes UART1 se zapíná zahrnutím `uart1.h` a voláním `init_uart1()`.

`inc/stm8s_conf.h` řídí, které SPL moduly se zkompilují (podmíněné includy dle `#ifdef DEVICE`).

## IDE podpora

`compile_commands.json` se generuje automaticky při `make` (přes `.make/compile_database_generator.py`). Slouží pro clangd/ccls LSP. `.ccls` konfiguruje ccls přímo.

## Formátování kódu

`.clang-format`: styl LLVM, odsazení 4 mezery, `BreakBeforeBraces: Linux`.

## Ladění

`make debug` spustí cgdb/gdb s `-x .make/gdbinit`. Lokální `.gdbinit` se nepoužívá, protože ho gdb odmítne kvůli auto-load safe-path. `.make/stm8gdb.py` dělá tohle:
- Spustí OpenOCD přes pipe (`target extended-remote | openocd -c "gdb_port pipe"`). Když na :3333 už poslouchá OpenOCD, připojí se přes TCP.
- Definuje příkazy `flash`, `reset`, `run`/`start` (F5 v cgdb) a `vars`.
- Hlídá změnu ELF. Za běhu debugu ho nahraje do čipu a zastaví na `main()`.
- Zapisuje PID gdb do `.debug-session`. Podle něj `make flash` za běhu debugu jen přeloží ELF.
- Umí barvit hodnoty proměnných (print, display, watch, info locals) pretty-printerem `color_printer`. Výchozí `VALUE_COLOR = ""` barvení vypíná (hodnoty bíle jako dřív). Formát bere z `gdb.print_options()`. `p/x` a `display/x` jdou v gdb mimo pretty-printery, proto zůstávají bez barvy.
- Ukládá seznam `display` do `.debug-display` a v příští session ho obnoví. Obnova běží v `before_prompt` přes `gdb.execute(..., from_tty=True)`, jinak gdb nový display nevypíše. Lokální proměnné jiné funkce čekají, dokud program nezastaví v jejich funkci.

Registry periferií (SFR):
- `make debug` přes `.make/sfr_gen.py` vytvoří `build-*-elf/sfr.elf` a `sfr.json`. Vstupem je `stm8s.h` po preprocesoru s `-D$(DEVICE)`.
- `sfr.elf` obsahuje jen DWARF. Každá periferie je v něm proměnná `__at(X_BaseAddress) X_TypeDef X;` bez `main` a bez `.symtab`, aby `break main` nemělo dvě místa.
- `.make/stm8sfr.py` ho načte přes `add-symbol-file`. V gdb pak funguje `TIM4->CR1`, `TIM4.CR1` (gdb bere obojí) a doplňování.
- Číselná makra ze `sfr.json` (masky, `*_RESET_VALUE`, `*_BaseAddress`) se nadefinují přes `macro define` jako holá čísla. Cast `(uint8_t)` by selhal, protože `uint8_t` v DWARF není.
- Příkaz `sfr` vypisuje registry s rozpisem bitů. Registry, jejichž čtení maže příznaky (`READ_SIDE_EFFECT`: UARTx.DR, SPI.DR, I2C.DR/SR3, FLASH.IAPSR, AWU.CSR), v přehledu nečte.
- Pretty-printer `sfr_printer` formátuje `uint8_t` hodnoty na adresách registrů a zvýrazní změnu od minulého zastavení. Epocha roste v `gdb.events.cont`.
- `set print symbol off` v gdbinit potlačí „Internal error: pc … in read in CU“, které gdb hlásí u ukazatelů na data z DWARF SDCC.

Po `monitor reset halt` je nutné `maintenance flush register-cache`. `monitor reset run` přes gdb hlásí „Protocol error with Rcmd“, proto se používá `reset halt` + `resume`.

## Ladění ve VS Code / VSCodium

Rozšíření `spseol.stm8-toolchain` je v `.make/vscode/` (čistý JS bez npm; návrh, plán a měření spiku jsou v historii gitu, commity `0b2c908` a `02d222e`). `make vscode` ho zabalí (`pack.py`, VSIX je zip) a nainstaluje do `code` a `codium` z `PATH` (`IDES=…` vybírá). Typ ladění je `stm8`.
- `F5` spustí úlohu `stm8: build` (`make debug-files`), pak `stm8-gdb -q -i dap -x .make/gdbinit` s `STM8_UI=dap`. Mezi VS Code a gdb je proxy `src/adapter.js`: `launch` → DAP `attach {program, target}`, po `configurationDone` repl příkaz `run`, timeouty a hlášky místo zavěšení, hover nad registry s vedlejším efektem se nečte.
- `.make/vscode.mk` (načítá ho `-include` na konci `Makefile`; jen `Makefile-sdcc`, ne `-gas`/`-sdccrm`): `dap-info` (JSON s cestami, příkazem OpenOCD a `gdbTarget`), `debug-files` (v čerstvém projektu bez `../SPLSPL` nejdřív `make spl` a pak make znovu, protože první běh Makefile přečetl bez zdrojů SPL), `vscode`. `make switch-device CHIP=stm8s103f3` přepne čip bez dotazů; `.make/devices.py` nabízí jen čipy, pro které existuje `../SPLSPL/mk/<DEVICE>.mk`.
- `stm8gdb.py` v režimu `STM8_UI=dap`: žádný banner ani `display`, `set style enabled off`, `is_connected()` pozná i spojení z DAP `attach`, `reload()` při chybě vyhodí `GdbError`, hlídání ELF a `on_exit` (reset + resume) fungují stejně jako v cgdb.
- `stm8sfr.py`: příkazy `sfr-json [PERIF[.REG] …]` (jeden řádek JSON; bez argumentu struktura bez hodnot a bez čipu) a `sfr-set PERIF.REG[.POLE] HODNOTA`. Rozšíření strukturu čte offline (`stm8-gdb -batch`), hodnoty přes repl `evaluate`.
- gdb DAP za běhu programu odpovídá `notStopped`; po `attach` se chyba připojení neprojeví (kontroluje `is_connected()` v příkazu `run`). Změřeno spikem `test/dap_smoke.py`.
- Testy: `pytest .make/vscode` a `node --test .make/vscode/test/*.test.js`; `STM8_HW=1` přidá testy, které nahrávají do připojeného Nucleo.
- Ochrana před čtením registrů s vedlejším efektem: hover je v proxy odbytý textem (guard.js), tree je čte jen přes ikonu *Read*, `sfr-set` odmítne zápis pole do takového registru (read-modify-write by ho přečetl). Když se model SFR nenačte, platí pevný `DEFAULT_SIDE_EFFECTS` v `guard.js`; musí se shodovat s `READ_SIDE_EFFECT` v `stm8sfr.py` (hlídá test).
- Po neúspěšném buildu (`preLaunchTask`) rozšíření F5 zruší, aby „Debug Anyway“ nenahrál starý ELF. Preflight (gdb ≥ 15, openocd, ST-Link, `.debug-session`, ELF) běží až po buildu, v `resolveDebugConfigurationWithSubstitutedVariables`.
- Řetězec `| openocd ... 2>log` je na dvou místech, `pipe_target()` ve `stm8gdb.py` a `dap_info.py`; test hlídá, že jsou stejné. Po úpravě `.make/Makefile-sdcc` zkopíruj soubor do `Makefile` (test hlídá shodu).
- Jednotkové testy rozšíření běží bez editoru: `extension.test.js` používá falešný modul `vscode`. GUI (F5, strom, panel) se zkouší ručně.
