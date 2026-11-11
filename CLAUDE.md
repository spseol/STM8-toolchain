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
make upgrade      # aktualizuje .make/ a Makefile projektu podle main toolchainu (viz „Ladění ve VS Code“)
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
  Makefile-sdccrm     # varianta s sdccrm (seznam vyloučených symbolů je v .make/exclude_reference)
  prune.txt           # soubory, které nový studentský projekt nedostane (viz VS Code níže)
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
- `set host-charset UTF-8` na začátku gdbinit: bez `LANG` (locale C) by gdb kódoval ne-ASCII znaky ve výpisech skriptů (`…`, `–`, `─`) do ASCII a `stm8gdb.py` by spadl na `UnicodeEncodeError` (nahlášeno z macOS, reprodukovatelné i na Linuxu přes `env -i`).
- `set print symbol off` v gdbinit potlačí „Internal error: pc … in read in CU“, které gdb hlásí u ukazatelů na data z DWARF SDCC.

Po `monitor reset halt` je nutné `maintenance flush register-cache`. `monitor reset run` přes gdb hlásí „Protocol error with Rcmd“, proto se používá `reset halt` + `resume`.

Windows: `make debug` a `make gdb` (TUI) v Git Bash (mintty, `tty` = `/dev/pty*`) hlásí `Cannot enable the TUI when output is not a terminal`, protože nativní `stm8-gdb.exe` dostane od MSYS roru místo terminálu. Makefile proto v tom případě před `stm8-gdb` přidá `winpty` (proměnná `WINPTY`, je v Git for Windows). V PowerShellu, cmd a Windows Terminalu (`/dev/cons*`) a na Linuxu a macOS se nepřidává nic. Zkouší se v mintty bez okna: `mintty -w hide -e bash -l skript.sh`.

## Ladění ve VS Code / VSCodium

Rozšíření `spseol.stm8-toolchain` je v `.make/vscode/` (čistý JS bez npm; návrh, plán a měření spiku jsou v historii gitu, commity `0b2c908` a `02d222e`). `make vscode` ho zabalí (`pack.py`, VSIX je zip) a nainstaluje do `code` a `codium` z `PATH` (`IDES=…` vybírá). Určeným kanálem pro studenty je ale marketplace (Open VSX pro VSCodium, Visual Studio Marketplace pro VS Code), viz `release.py` níže; `make vscode` zůstává pro vývoj a pro stroje bez marketplace. Typ ladění je `stm8`.
- `F5` spustí úlohu `stm8: build` (`make debug-files`), pak `stm8-gdb -q -i dap -x .make/gdbinit` s `STM8_UI=dap`. Mezi VS Code a gdb je proxy `src/adapter.js`: `launch` → DAP `attach {program, target}`, po `configurationDone` repl příkaz `run`, timeouty a hlášky místo zavěšení, hover nad registry s vedlejším efektem se nečte.
- Tlačítka *Build* a *Flash* ve stavovém řádku (`src/statusbar.js`) spouští `make` / `make flash` jako task `stm8: make` / `stm8: make flash` (`onDidEndTaskProcess` dá `exitCode`, terminál přes `sendText()` ho nedá). Při kódu 0 přepne nastavení `stm8.afterSuccess` (`hidePanel` výchozí, `editor`, `previousTerminal`, `stay`) zpět; aktivní záložku panelu (Problems, Output) VS Code API zjistit neumí. Posluchač konce tasku se zakládá jen na dobu běhu tasku.
- `.make/vscode.mk` (načítá ho `-include` na konci `Makefile`; jen `Makefile-sdcc`, ne `-gas`/`-sdccrm`): `dap-info` (JSON s cestami, příkazem OpenOCD a `gdbTarget`), `debug-files` (v čerstvém projektu bez `../SPLSPL` nejdřív `make spl` a pak make znovu, protože první běh Makefile přečetl bez zdrojů SPL), `vscode`. `make switch-device CHIP=stm8s103f3` přepne čip bez dotazů; `.make/devices.py` nabízí jen čipy, pro které existuje `../SPLSPL/mk/<DEVICE>.mk`.
- `stm8gdb.py` v režimu `STM8_UI=dap`: žádný banner ani `display`, `set style enabled off`, `is_connected()` pozná i spojení z DAP `attach`, `reload()` při chybě vyhodí `GdbError`, hlídání ELF a `on_exit` (reset + resume) fungují stejně jako v cgdb.
- `stm8sfr.py`: příkazy `sfr-json [PERIF[.REG] …]` (jeden řádek JSON; bez argumentu struktura bez hodnot a bez čipu) a `sfr-set PERIF.REG[.POLE] HODNOTA`. Rozšíření strukturu čte offline (`stm8-gdb -batch`), hodnoty přes repl `evaluate`.
- gdb DAP za běhu programu odpovídá `notStopped`; po `attach` se chyba připojení neprojeví (kontroluje `is_connected()` v příkazu `run`). Změřeno spikem `test/dap_smoke.py`.
- Testy: `pytest .make/vscode` a `node --test .make/vscode/test/*.test.js` (dále `test_upgrade.py`, `test_release.py`, `upgrade.test.js`, `newproject.test.js`, `tasks.test.js`); `STM8_HW=1` přidá testy, které nahrávají do připojeného Nucleo.
- Ochrana před čtením registrů s vedlejším efektem: hover je v proxy odbytý textem (guard.js), tree je čte jen přes ikonu *Read*, `sfr-set` odmítne zápis pole do takového registru (read-modify-write by ho přečetl). Když se model SFR nenačte, platí pevný `DEFAULT_SIDE_EFFECTS` v `guard.js`; musí se shodovat s `READ_SIDE_EFFECT` v `stm8sfr.py` (hlídá test).
- Po neúspěšném buildu (`preLaunchTask`) rozšíření F5 zruší, aby „Debug Anyway“ nenahrál starý ELF. Preflight (gdb ≥ 15, openocd, ST-Link, `.debug-session`, ELF) běží až po buildu, v `resolveDebugConfigurationWithSubstitutedVariables`.
- Řetězec `| openocd ... 2>log` je na dvou místech, `pipe_target()` ve `stm8gdb.py` a `dap_info.py`; test hlídá, že jsou stejné. Na Windows gdb příkaz za `|` žádným shellem nepouští (OpenOCD by dostal `2>log` jako argument a skončil), proto je tam místo přesměrování `-l "cesta"` s lomítky dopředu (gdb si argumenty rozebírá sám a zpětné lomítko bere jako únikový znak); na Linuxu a macOS zůstává `2>log`. `tcp_listening()` má na Windows vlastní kontrolu přes socket (bez `/proc`). Po úpravě `.make/Makefile-sdcc` zkopíruj soubor do `Makefile` (test hlídá shodu).
- `.make/upgrade.py` + `make upgrade` (proměnné `STM8_TOOLCHAIN_URL`, `UPGRADE_ARGS`): obnoví `.make/` podle `main` toolchainu, kořenový `Makefile` slije tříčestně (`git merge-file`; základem je verze `.make/Makefile-sdcc` z historie staženého toolchainu nejbližší té v `HEAD` projektu, protože ji student mohl upravit; nová verze sama základem není, jinak by slití nic neukázalo, takže bez starší verze v historii vznikne konflikt; při střetu nebo bez použitelného základu nechá značky konfliktu; `Makefile` jako symlink do `.make/` nahradí obyčejným souborem, nikdy nepíše skrz něj), `Makefile-sdcc-gas`/`-sdccrm` nabídne přepnout na `Makefile-sdcc` (přenese jen `DEVICE_FLASH`), `.vscode/launch.json` nahradí (nesledovaný původní uloží jako `.bak`, existující `.bak` nikdy nepřepíše), do `.gitignore` doplní chybějící řádky. Nic necommituje ani nestaguje; odmítne projekt se značkami konfliktu v `Makefile`, bez commitu nebo s necommitnutými změnami v `.make`, `Makefile` a `.vscode/launch.json`. Návratové kódy: 0 hotovo, 1 odmítnuto, 2 konflikt v `Makefile`, 3 je třeba rozhodnout o přepnutí varianty (JSON `{"needsSwitch": …}` na stdout; `--json` vypíše zprávu jako JSON, `--switch` rozhodnutí předá).
- Skript se spouští z právě stažené verze: `python3 -I -c "$(git show FETCH_HEAD:.make/upgrade.py)" FETCH_HEAD`, takže starý projekt žádnou kopii nepotřebuje a vždy platí nejnovější logika. `upgrade.py` proto nesmí záviset na vlastní cestě ani na jiných souborech v `.make/`. `make upgrade` (`git fetch` + totéž) existuje až v novém `.make/vscode.mk`; starý projekt použije příkaz výše nebo `STM8: Update Toolchain`. Testy: `test/test_upgrade.py`, `test/upgrade.test.js`.
- `STM8: New Project…` (`src/newproject.js`) dělá totéž co starý skript `stm8newproject`: `git clone` toolchainu do `stm8.projectsFolder/NAZEV`, větev i remote `upstream`, osiřelá větev `main` s českým studentským README (`media/README.project.md`, `{{TITLE}}`) a `docs/schema.png`, první commit. Selhání `make compile_commands.json` a commitu je jen varování. Testy: `test/newproject.test.js`.
- `.make/prune.txt`: seznam cest (jedna na řádek, relativně ke kořeni projektu, bez zástupných znaků, `#` komentáře; položka platí i pro vše pod ní) vývojářských souborů, které student nepotřebuje: testy rozšíření (`.make/vscode/test`, `bin`, `pytest.ini`), `release.py`, `RELEASING.md`, návrhy. Čte ho `STM8: New Project…` i skript `stm8newproject` (smažou položky z čerstvého klonu před prvním commitem osiřelé větve `main`; větev `upstream` zůstává úplná; selhání je jen varování) a `upgrade.py` (položky z `ref` nezakládá ani nepřepisuje, existující kopii nechá být). Řádky se ořežou; ignorují se (stejně ve všech třech implementacích) absolutní cesty, tvar disku (`C:x`), cesty s opačným lomítkem, položky s libovolným segmentem `..` nebo jen z teček a mezer a položky, jejichž první segment je po odříznutí koncových teček a mezer a převodu na malá písmena přesně `.git` (tedy `.GIT`, `.git.`, `.Git/hooks`, ale ne `.gitignore`, `.github` ani `a/.git`; seznam pochází ze staženého repozitáře). Samotný segment `.` se zahodí (`./x` i `x/.` znamenají `x`). `pack.py`, `dap_info.py`, `package.json`, `extension.js`, `src/`, `media/` a dokumentace rozšíření v seznamu nejsou, takže `make vscode` funguje i v ořezaném projektu; `release.py` tam není (vydává se jen z plného checkoutu). Test: `test_vscode_files.py` (typo guard, nic z povinných souborů, ořezaná kopie projektu).
- `STM8: Update Toolchain` (`src/upgrade.js`) udělá `git fetch` z `stm8.toolchainUrl` a spustí stažený `upgrade.py` (`--json`, případně `--switch`) s `GIT_TERMINAL_PROMPT=0`; kódy 0–3 ukáže uživateli (2 = rozřešit konflikt v `Makefile`, 3 = zeptat se na přepnutí varianty). Rozšíření ji samo nabídne u projektu, jehož `.make/` je starší než nainstalované rozšíření (`upgradeOffer` v `src/project.js`; „Don't ask again“ se pamatuje ve `workspaceState`; nastavení `stm8.checkToolchainUpdates`, scope `resource`, výchozí `true`, vypne při aktivaci nabídku i hlášku `versionNotice`, ruční příkaz a F5 zůstávají) a při F5 u starého projektu bez `dap-info` (`ToolchainError` s `fix: 'updateToolchain'`). `readProjectInfo` předem hledá v `Makefile` značky konfliktu `<<<<<<<` a vyhodí srozumitelnou chybu, ať `make` nehlásí nesmysly.
- Nastavení: `stm8.toolchainUrl` (výchozí GitLab SPŠE) a `stm8.projectsFolder` (prázdné = zeptá se při prvním použití); obě mají scope `machine`, takže jdou nastavit jen v uživatelských nastaveních a `.vscode/settings.json` projektu je ignoruje (`machine-overridable` by nestačilo, to workspace nastavení povoluje přebít). Stažený `upgrade.py` se spouští, takže `toolchainUrl` musí být důvěryhodné.
- Úloha `stm8: build` už nemusí být v `.vscode/tasks.json`: rozšíření ji poskytuje samo (`src/tasks.js`, `registerTaskProvider('stm8')`, `make debug-files`, problem matcher `$sdcc` deklarovaný v `package.json`). Testy: `test/tasks.test.js`.
- Zpětná kompatibilita: rozšíření musí fungovat i se starým `.make/` v projektech studentů, hlavně s jejich `make dap-info` (kontrakt: JSON na jednom řádku, viz `dap_info.py`). Starý projekt bez `dap-info` rozšíření pozná (`No rule to make target`) a nabídne Update Toolchain. Při změně `dap-info` nebo `.make/vscode.mk` proto nerozbíjej starší výstup.
- Marketplace: `pack.py` zapisuje do VSIX metadata (ikona, licence, changelog, tagy z `keywords`, odkazy repository/bugs/homepage, `README.md` jako popis); soubory logo/banner (`icon.svg/png`, `banner.svg/png`), `README.project.md` a `schema.png` jsou v `media/`. `python3 .make/vscode/release.py [--dry-run]` (postup a jednorázové nastavení v `.make/vscode/RELEASING.md`): kontroly (čistý strom, větev `main`, remoty `origin` a `github`, tag `vscode-v<verze>` ještě neexistuje) → testy → `pack.py` (VSIX pro Open VSX) → `npx --yes @vscode/vsce@<VSCE_VERSION> package` z čisté kopie souborů (VSIX pro Microsoft, ručně vyrobený manifest z `pack.py` Marketplace odmítl) → `npx --yes ovsx@<OVSX_VERSION> publish` (token jen z prostředí `OVSX_PAT` nebo `~/.config/stm8-toolchain/ovsx-token`, nikdy na příkazové řádce) → anotovaný tag `vscode-v<verze>` → push `main` a tagu do `origin` i `github` → otevře stránku vydavatele Microsoftu pro ruční nahrání `stm8-toolchain-marketplace.vsix` (PAT Azure DevOps končí 2026-12-01). Verze se zvedá v `package.json` a `CHANGELOG.md`. `--dry-run` skončí po zabalení. Skript nikdy nespouštěj bez vlastníka. Testy: `test/test_release.py`.
- Limit GitLab.com (od 2026-10-19): nepřihlášený web a API provoz je 60 požadavků/h na IP (třída za NATem sdílí IP). Anonymní Git přes HTTPS je z limitu vyňatý. Proto instalační skripty `.make/install/` a binárky (stm8-gdb: `spseol/STM8-binutils-GDB`, ccls: `spseol/ccls`) jsou na GitHubu, stahují se přes `releases/latest/download/<pevné jméno>` bez API, a SPL (`make spl`, `spl.sh`) jde přes `git clone --depth 1` místo `curl` archivu. Nepoužívej `gitlab.com/api`, `/-/raw/`, `/-/archive/` ani `/-/releases/` (hlídá `test_install_scripts.py`). Po změně `.make/install/` pushni i do remotu `github`, jinak studenti stáhnou starou verzi. Nové vydání stm8-gdb/ccls na GitHubu musí mít assety s pevnými jmény (ccls navíc kopii `ccls-windows-x64-setup.exe`).
- Python (`PYTHON`): na Windows `python` (`python3.exe` ve WindowsApps je jen zástupce pro Microsoft Store); jinde první dostupný z `python3` a `python`, jinak `python3` (macOS má jen `python3`, Linux obvykle oba). Stejné pořadí je na třech místech: `Makefile-sdcc*` (`$(shell command -v …)`), shell skripty `switch_device.sh`, `pyserial.auto`, `lib-mv.sh` (když `PYTHON` nepředá make) a `detectPython()` v `src/platform.js`.
- Windows (`src/platform.js`): Python je `python`, ne `python3` (`PYTHON`, stejně jako v Makefile; `python3.exe` ve WindowsApps je jen zástupce pro Microsoft Store a končí kódem 9009). VSCodium spuštěný z nabídky Start má v PATH jen `<Git>\cmd`, bez `bash` a `nproc` (ty přidává až Git Bash) a Windows `make` pak místo chyby napíše „No rule to make target '../SPLSPL/mk/.mk'“. `toolEnv()` (volání make, `make compile_commands.json`) a `taskEnv()` (`ShellExecution` v `tasks.js` a `statusbar.js`) proto dají na začátek PATH `<Git>\usr\bin`. Hláška „Old toolchain“ platí jen pro chybějící cíl `dap-info`; jiná chyba „No rule to make target“ se hlásí jako chyba make (a při chybějícím bashi s návodem). Návratový kód `upgrade.py` jiný než 0–3 je chyba, ne úspěch.
- Jednotkové testy rozšíření běží bez editoru: `extension.test.js` používá falešný modul `vscode`. GUI (F5, strom, panel) se zkouší ručně.
