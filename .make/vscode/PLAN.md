# STM8 VS Code Debugger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** F5 ve VS Code/VSCodium přeloží projekt, nahraje ho do STM8S a zastaví na `main()`; k tomu krokování, proměnné a strom periferií (SFR) se zápisem.

**Architecture:** Rozšíření `.make/vscode/` (čistý JS) spustí `stm8-gdb -i dap` a mezi VS Code a gdb vloží tenký DAP proxy (`launch` → `attach`, startovní sekvence, timeouty, ochrana hoveru). SFR logika zůstává v Pythonu v `.make/stm8sfr.py` a rozšíření ji volá repl příkazy `sfr-json` a `sfr-set`. Cesty a příkaz OpenOCD dodává `make dap-info`.

**Tech Stack:** stm8-gdb 15.0.50 (Python 3.13, DAP), OpenOCD, SDCC, GNU Make, VS Code API ≥ 1.80 (CommonJS), pytest, `node --test` (Node 20, jen pro vývoj; studenti Node nepotřebují).

**Spec:** `.make/vscode/DESIGN.md`. Odchylky od specifikace jsou na konci v sekci „Odchylky od návrhu“.

## Global Constraints

- UI pluginu a všechny nové hlášky (JS i Python) anglicky; existující české texty v `.make/` se nepřekládají.
- Rozšíření: čistý JavaScript (CommonJS), žádné npm závislosti, žádný build krok; VSIX je zip sestavený Pythonem (`zipfile`).
- `package.json`: publisher `spseol`, name `stm8-toolchain`, debug typ `stm8`.
- Verze 1 jen Linux, ale v JS bez `/proc` a shell triků a cesty přes `path`.
- Mění se jen `.make/Makefile-sdcc` a `Makefile` (jeho kopie, musí zůstat identická). `Makefile-sdcc-gas` a `Makefile-sdccrm` se nemění.
- Nové make cíle jsou jen v `.make/vscode.mk`, načítaném řádkem `-include .make/vscode.mk`.
- cgdb ladění (`make debug`, `make gdb`) se chová beze změny.
- Jen veřejné DAP požadavky a gdb CLI; žádné interní API `gdb.dap.server`.
- gdb běží jako `stm8-gdb -q -i dap -x .make/gdbinit` s env `STM8_UI=dap`, `STM8_OPENOCD`, `STM8_OPENOCD_LOG`, `STM8_SFR`; požadovaná verze ≥ 15.
- Nucleo ST-LINK/V2.1 (`0483:374b`) smí implementace volně programovat. GUI testy (F5, klikání, LED) dělá uživatel.
- **Nic nekomitovat** (pokyn uživatele): na konci tasku jen připomenout commit a navrhnout zprávu.

## Review Focus

Vstupy a stavy, které spec předpokládá, ale nezmiňuje. Každý má test v uvedeném tasku.

1. ST-Link obsazený: `make openocd` na :3333 se obslouží přes TCP, běžící `make debug` dá srozumitelnou hlášku v `preflight`, nedosažitelný čip hlášku do 10 s; nikde zavěšení a cizí session se nezabije (Task 8, 9).
2. Cesta projektu s mezerou a diakritikou (`~/Dokumenty/Žák Novák/lab 1`): build, `dap-info` i start fungují (Task 1, 7).
3. Čtení a zápis SFR za běhu programu: chyba „program is running“, strom ukáže „running“, žádný timeout (Task 4, 10).
4. Chybějící ELF nebo selhaný build: F5 skončí hláškou, nenahraje se starý program (Task 9).
5. Překročení limitu HW breakpointů: breakpoint je nepotvrzený s textem, ne tichý (Task 8).

---

### Task 1: `vscode.mk`, `dap-info`, `debug-files`

**Files:**
- Create: `.make/vscode.mk`, `.make/vscode/dap_info.py`, `.make/vscode/pytest.ini`, `.make/vscode/test/conftest.py`, `.make/vscode/test/test_make_targets.py`
- Modify: `.make/Makefile-sdcc` (poslední řádek `-include .make/vscode.mk`), `Makefile` (kopie)

**Interfaces:**
- Produces: `make -s --no-print-directory dap-info` vypíše jeden řádek JSON `{"device":"STM8S208","deviceFlash":"stm8s208rb","elf":ABS,"sfr":ABS,"openocd":STR,"openocdLog":ABS,"gdbTarget":STR}`. `gdbTarget` je přesně řetězec z `connect()` ve `stm8gdb.py`: `| <openocd> -c "gdb_port pipe" -c "telnet_port disabled" -c "tcl_port disabled" 2><openocdLog>`.
- Produces: `make debug-files` přeloží `$(TARGET_ELF)` a `$(SFR_ELF)`.
- Produces (conftest): fixture `project_info() -> dict` (výstup `dap-info`), `run_make(args, cwd=ROOT)`, `project_copy(tmp_path, name) -> Path` (kopie projektu bez `build-*`, s symlinkem `../SPLSPL`), marker `hw` (přeskočí se bez `STM8_HW=1`), `ROOT`.
- `dap_info.py`: `main(argv: list[str]) -> int`, argumenty `--device --device-flash --elf --sfr --openocd --log`; cesty převádí na absolutní, JSON píše `json.dumps`.

- [ ] **Step 1: Write failing tests** v `test_make_targets.py`: `test_dap_info_keys` (všechny klíče, `elf` absolutní a končí `out.elf`, `gdbTarget` začíná `"| "`, obsahuje `gdb_port pipe` a `2>` + `openocdLog`), `test_makefile_copy_identical` (`Makefile` == `.make/Makefile-sdcc`), `test_debug_files_in_path_with_space_and_diacritics` (`project_copy(tmp_path, "Žák Novák/lab 1")`: `make debug-files` skončí 0, existují `out.elf` a `sfr.elf`, `dap-info` vrací `elf` uvnitř té složky).
- [ ] **Step 2: Run** `pytest .make/vscode/test/test_make_targets.py -q`. Expected: FAIL (`No rule to make target 'dap-info'`).
- [ ] **Step 3: Implement** `.make/vscode.mk` (cíle `dap-info`, `debug-files`; `dap-info` volá `$(PYTHON) .make/vscode/dap_info.py` s hodnotami proměnných Makefile) a `-include` v `.make/Makefile-sdcc`; pak `cp .make/Makefile-sdcc Makefile`. Pokud build v cestě s mezerou selže v existující části Makefile, oprava je součástí tasku (citace proměnných), ne obejití testu.
- [ ] **Step 4: Run** testy z kroku 2. Expected: PASS. Dál `make elf` a `make` v kořeni skončí 0.
- [ ] **Step 5:** Připomeň commit (`feat(vscode): make dap-info a debug-files`).

### Task 2: Spike DAP na čipu

Zjistí, jak se `stm8-gdb -i dap` chová na skutečném STM8, než se na tom postaví zbytek. Používá **nezměněné** `.make/gdbinit`.

**Files:**
- Create: `.make/vscode/test/dapclient.py`, `.make/vscode/test/dap_smoke.py`, `.make/vscode/SPIKE.md`
- Modify: `.make/vscode/DESIGN.md` (sekce Rizika podle výsledků)

**Interfaces:**
- Consumes: `project_info` z Task 1.
- Produces: `class DapClient` (stdlib, `__init__(argv: list[str], env: dict, cwd: str)`, `request(command: str, arguments: dict | None = None, timeout: float = 20) -> dict` vrací celou odpověď, `wait_event(name: str, timeout: float = 20) -> dict`, `events: list[dict]` všechny dosud přijaté, `close() -> None`). Použijí ho Task 5, 8, 10.

- [ ] **Step 1: Write `DapClient`** (framing `Content-Length`, vlákno čtoucí stdout, fronta událostí).
- [ ] **Step 2: Write `dap_smoke.py`**: `make debug-files`, spustí gdb s env jako v `GDB_ENV` v Makefile + `STM8_UI=dap`, a projde brány G1–G8. Každá vypíše `PASS Gn` nebo `FAIL Gn: důvod`; zjištěné hodnoty (časy, texty chyb) vypíše vždy.
  - **G1 start:** `initialize`, `attach {program: elf, target: gdbTarget}`, `setBreakpoints`, `configurationDone`, pak repl `evaluate` těchto příkazů po jednom: `load`, `monitor reset halt`, `maintenance flush register-cache`, `tbreak main`, `continue`. Očekává `stopped` ve funkci `main`. Zapsat přesné pořadí a co `attach` vrátí.
  - **G2 chyby:** totéž s odpojeným ST-Linkem a s ST-Linkem obsazeným jiným `openocd` (spustit ručně). Co vrátí `attach` (úspěch?) a co přijde v `output` událostech.
  - **G3 data:** `next`, `stepIn`, `stackTrace`, `scopes`, `variables` (Locals, Registers), `readMemory` na 0x5340, repl `sfr TIM4` a `p TIM4->CR1` (jsou v textu ANSI kódy?), `setExpression`.
  - **G4 pause:** `continue`, za 1 s `pause`, `stopped` s reason `pause` do 2 s.
  - **G5 disconnect:** `disconnect {terminateDebuggee: false}`; gdb skončí do 3 s, po 3 s neběží žádný `openocd`; zapsat, zda čip po odpojení běží (LED).
  - **G6 breakpointy:** 6 řádkových breakpointů v `src/main.c`; zapsat `verified` a `message` v odpovědi a co se stane po `continue`.
  - **G7 repl:** funguje `evaluate` repl před `configurationDone` a za běhu programu? Přesný text chyby.
  - **G8 výstup:** `gdb.write` ze `say()` se objeví jako `output` události?
- [ ] **Step 3: Run** `STM8_HW=1 python3 .make/vscode/test/dap_smoke.py`. Expected: G1, G3, G4, G5, G8 `PASS`; G2, G6, G7 jen informativní.
- [ ] **Step 4: Write `SPIKE.md`** (tabulka bran s pozorováním) a zapsat **rozhodnutí**: konečná startovní sekvence požadavků pro Task 5 a 7; pokud G1 selže, přepnout na záložní variantu z Rizik v DESIGN.md (gdb příkaz `stm8-dap-start`).
- [ ] **Step 5:** Připomeň commit (`test(vscode): DAP spike na čipu`).

### Task 3: Seznam čipů a neinteraktivní `switch-device`

**Files:**
- Modify: `.make/devices.py`, `.make/switch_device.py`, `.make/switch_device.sh`, `.make/Makefile-sdcc` + `Makefile` (recept `switch-device`)
- Test: `.make/vscode/test/test_devices.py`

**Interfaces:**
- Produces v `devices.py`: `supported(chip: str, mk_dir: str = "../SPLSPL/mk") -> bool` (existuje `<mk_dir>/<prvních 8 znaků čipu velkými>.mk`, stejně jako `include ../SPLSPL/mk/$(DEVICE).mk` v Makefile) a `available(devices: dict = DEVICES, mk_dir: str = "../SPLSPL/mk") -> dict` (`DEVICES` bez čipů, které nejsou `supported`; prázdné rodiny se vypustí; když `mk_dir` neexistuje, tj. SPL není stažená, vrací `DEVICES` beze změny).
- Produces: `python3 .make/devices.py` vypíše `json.dumps(available())` (`{rodina: {čip: datasheet}}`). Interaktivní `switch_device.py` nabízí `available()`.
- Produces: `make switch-device CHIP=stm8s103f3` přepíše `DEVICE_FLASH=` bez dotazů. Neznámý čip skončí nenulově s `Unknown chip: <x>`, čip bez `.mk` s `SPL has no support for <8 znaků>` (např. `STM8S001`). Proměnná se jmenuje `CHIP`, protože `DEVICE` už Makefile používá.

- [ ] **Step 1: Write failing tests:** `test_no_duplicate_keys` (AST: v žádném dict literálu v `devices.py` se neopakuje klíč), `test_chips_present` (`STM8S003F3`, `STM8S105C4`, `STM8S105C6`, `STM8S105K4`, `STM8S105K6`, `STM8S105S4`, `STM8S105S6`, `STM8S903F3`, `STM8S903K3`), `test_every_chip_has_mk` (každý čip v `DEVICES` je `supported`; přeskočí se, když `../SPLSPL/mk` neexistuje), `test_available_filters_chips_without_mk` (dočasný `mk_dir` jen s `STM8S103.mk` → zůstanou jen čipy `STM8S103*`), `test_available_unfiltered_without_spl` (neexistující `mk_dir` → celý `DEVICES`), `test_cli_prints_json`, `test_switch_device_noninteractive` (na `project_copy`: po `CHIP=stm8s103f3` je v Makefile `DEVICE_FLASH=stm8s103f3` a `dap-info` vrací `"device": "STM8S103"`), `test_switch_device_unknown_chip` (nenulový kód, text na stderr), `test_switch_device_chip_without_mk` (`CHIP=stm8s007c8` s `mk_dir` bez `STM8S007.mk` → nenulový kód, `SPL has no support for STM8S007`).
- [ ] **Step 2: Run** `pytest .make/vscode/test/test_devices.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - Druhý duplicitní `STM8S003K3` je `STM8S003F3`.
  - Čipy 105 patří do skupiny „Access line (103/105)“ s datasheetem `stm8s105c4`; čipy 903 (`STM8S903F3`, `STM8S903K3`, datasheet `stm8s903k3`) tam přibudou také a skupina se přejmenuje na „Access line (103/105/903)“ (moje volba).
  - Zjisti, zda `make -n` s `DEVICE_FLASH=stm8s001j3` skutečně padá na chybějícím `STM8S001.mk`. Pokud ano, `STM8S001J3` se z `DEVICES` odstraní.
  - `switch_device.sh` s argumentem přeskočí `pick` a kontroluje čip přes `devices.py` (`Unknown chip`, `SPL has no support for …`). Ostatní chování a `sed -i.backup` zůstává.
  - `Makefile` znovu zkopírovat z `.make/Makefile-sdcc`.
- [ ] **Step 4: Run** testy. Expected: PASS. Interaktivní `make switch-device` se nesmí rozbít (ověří uživatel jednou ručně).
- [ ] **Step 5:** Připomeň commit (`fix(devices): duplicitní klíč, STM8S105, switch-device CHIP=`).

### Task 4: Příkazy `sfr-json` a `sfr-set`

**Files:**
- Modify: `.make/stm8sfr.py`
- Test: `.make/vscode/test/test_sfr_cmds.py`

**Interfaces:**
- Produces: gdb příkaz `sfr-json [TOKEN …]` (TOKEN = `TIM4` nebo `TIM4.CR1`, jako `find()`). Výstup je jeden řádek JSON:
  `{"running":bool,"periphs":[{"name","base","regs":[{"name","addr","reset","desc","sideEffect","value","prev","bits":[{"name","mask","desc"}]}],"other":[{"name","addr"}]}]}`
  - Bez argumentu jsou všechna `value` a `prev` `null` a příkaz nepotřebuje čip.
  - S `TIM4` se čtou registry této periferie kromě `sideEffect`. `prev` je výsledek `track()`.
  - S `UART1.DR` se tento registr přečte výslovně.
  - Za běhu programu: `gdb.GdbError("Program is running, pause it first.")`.
- Produces: `sfr-set PERIF.REG VALUE` a `sfr-set PERIF.REG.POLE VALUE` (VALUE přes `int(x, 0)`); vypíše novou hodnotu registru jako desítkové číslo. Pole se zapisuje read-modify-write přes `merge_field(old: int, mask: int, value: int) -> int`; hodnota mimo rozsah pole: `GdbError("Value 9 does not fit field SPI.CR1.BR (3 bits)")`. Za běhu programu stejná chyba jako výše.

- [ ] **Step 1: Write failing tests (bez čipu)** přes `stm8-gdb -q -batch -ex 'source .make/stm8gdb.py' -ex 'source .make/stm8sfr.py' -ex '…'` s `STM8_SFR=<sfr z dap-info>` (po `make debug-files`): `test_static_lists_all_periphs` (TIM4 `base` 21312, `CR1` má bit `CEN` s maskou 1, `UART1.DR.sideEffect` je true, `running` false, všechna `value` null), `test_unknown_periph_errors`, `test_merge_field` (`merge_field(0x01, 0x08, 1) == 0x09`, `merge_field(0xFF, 0x70, 0x2) == 0x8F`), `test_set_rejects_oversized_field`.
- [ ] **Step 2: Write failing tests (hw)**: `test_values_on_chip` (`TIM4` hodnoty jsou čísla; `UART1` má `DR` null), `test_explicit_read_of_side_effect_reg` (`sfr-json UART1.DR` vrátí číslo), `test_set_roundtrip_tim4_arr` (zapsat `TIM4.ARR 0x55`, přečíst 85, vrátit původní), `test_running_errors` (`continue` na pozadí, pak `sfr-json TIM4` i `sfr-set` skončí chybou „running“).
- [ ] **Step 3: Implement** `sfr-json`, `sfr-set` a `merge_field` v `.make/stm8sfr.py`; formátování sdílet s `sfr`, ne duplikovat.
- [ ] **Step 4: Run** `pytest .make/vscode/test/test_sfr_cmds.py -q` a s `STM8_HW=1`. Expected: PASS. Ruční kontrola: `sfr TIM4` v `make debug` vypadá jako dřív.
- [ ] **Step 5:** Připomeň commit (`feat(sfr): sfr-json a sfr-set`).

### Task 5: Režim DAP ve `stm8gdb.py`

**Files:**
- Modify: `.make/stm8gdb.py`
- Test: `.make/vscode/test/test_gdb_dap_mode.py`

**Interfaces:**
- Consumes: `DapClient` (Task 2), startovní sekvence ze `SPIKE.md`.
- Produces: `dap_mode() -> bool` (`os.environ.get("STM8_UI") == "dap"`); `is_connected() -> bool` (`state["connected"]` nebo `gdb.selected_inferior().connection_num is not None`); `ensure_connected()` místo `state["connected"]` volá `is_connected()`; `elf_stamp()` si při `state["elf"] is None` vezme `gdb.current_progspace().filename`; `start_watcher() -> None` (idempotentní, volá se z `reload()` při prvním úspěchu v DAP režimu).
- `stm8_start()` v DAP režimu: `set style enabled off`, připojí události `stop` a `gdb_exiting`, nespouští banner, `reload()` ani obnovu `display`. `on_stop` v DAP režimu nevolá `show_vars()` ani `save_displays()`. `reload()` po úspěšném připojení volá `write_session()`.

- [ ] **Step 1: Write failing tests (bez čipu):** `test_dap_mode_quiet_start` (`STM8_UI=dap`, výstup neobsahuje banner „STM8 debug“, `show style enabled` je off), `test_color_printer_off_in_dap` (`p 1` neobsahuje `\033`), `test_cgdb_mode_unchanged_without_elf` (bez `STM8_UI` stále „gdb nemá ELF“).
- [ ] **Step 2: Write failing tests (hw)** s `DapClient`: `test_run_after_attach` (attach, configurationDone, repl `run` → `stopped` ve `main` do 30 s), `test_elf_change_reloads` (`touch src/main.c; make elf` → do 15 s nový `stopped` ve `main` a `output` s textem o změně programu), `test_session_file` (`.debug-session` obsahuje PID gdb během session a po `disconnect` zmizí), `test_make_flash_during_session_only_builds`, `test_cgdb_regression` (batch s `GDB_ENV` jako v `make debug`: `sfr TIM4`, `p TIM4->CR1` fungují).
- [ ] **Step 3: Implement** podle rozhraní výše. Pokud `test_elf_change_reloads` ukáže, že Python watcher v DAP režimu nefunguje (rozhodne Task 2/SPIKE.md), watcher se vypustí a hlídání ELF přebírá Task 9 (krok „elfwatch“).
- [ ] **Step 4: Run** `pytest .make/vscode/test/test_gdb_dap_mode.py -q` a s `STM8_HW=1`. Expected: PASS.
- [ ] **Step 5:** Připomeň commit (`feat(gdb): režim STM8_UI=dap`).

### Task 6: Čisté JS moduly `dapframe` a `guard`

**Files:**
- Create: `.make/vscode/src/dapframe.js`, `.make/vscode/src/guard.js`, `.make/vscode/test/dapframe.test.js`, `.make/vscode/test/guard.test.js`

**Interfaces:**
- Produces: `encode(msg: object): Buffer`; `createParser(onMessage: (msg: object) => void): { push(chunk: Buffer): void }`.
- Produces: `guardsHover(expression: string, sideEffects: {[periph: string]: string[]}): string | null` vrací jméno čteného registru/periferie (`"UART1.DR"`, `"UART1"`) nebo `null`.

- [ ] **Step 1: Write failing tests** (`node:test`). dapframe: `test_split_in_three_chunks`, `test_utf8_char_split_across_chunks` (zpráva s „ž“ rozříznutá uprostřed bajtů), `test_two_messages_in_one_chunk`, `test_content_length_counts_bytes`. guard s `{UART1: ["DR"], SPI: ["DR"]}`: `UART1->DR` a `UART1.DR` → `"UART1.DR"`; `UART1` → `"UART1"`; `x + UART1->DR` → `"UART1.DR"`; `UART1->SR`, `GPIOA->ODR`, `&UART1->DR`, `UART1_SR_TXE` → `null`.
- [ ] **Step 2: Run** `node --test .make/vscode/test/dapframe.test.js .make/vscode/test/guard.test.js`. Expected: FAIL (modul neexistuje).
- [ ] **Step 3: Implement** obě funkce. `guard` hledá celá slova (`\b`), rozlišuje velikost písmen a výraz s předcházejícím `&` nevyhodnocuje jako čtení.
- [ ] **Step 4: Run** testy. Expected: PASS.
- [ ] **Step 5:** Připomeň commit (`feat(vscode): dapframe a guard`).

### Task 7: DAP proxy `GdbProxy`

**Files:**
- Create: `.make/vscode/src/adapter.js`, `.make/vscode/test/fake-gdb.js`, `.make/vscode/test/adapter.test.js`

**Interfaces:**
- Consumes: `encode`, `createParser`, `guardsHover` (Task 6); startovní sekvence ze `SPIKE.md`.
- Produces: `class GdbProxy` s konstruktorem `({ project, spawn, send, sideEffects, stepTimeoutMs = 30000, openocdTail, log })`: `project` je výstup `dap-info`, `spawn(): ChildProcess`, `send(msg: object)` posílá zprávy do VS Code, `openocdTail(): string[]`. Metody `handleMessage(msg: object): void`, `dispose(): void`.
- Chování:
  - `launch` od klienta se nepřepošle; proxy pošle gdb `attach {program: project.elf, target: project.gdbTarget}` a na `launch` odpoví klientovi odpovědí na `attach` (přepsané `command` a `request_seq`).
  - Po odpovědi na `configurationDone` proxy provede zbytek startovní sekvence ze `SPIKE.md` přes repl `evaluate`.
  - Chyba nebo timeout kteréhokoli kroku: proxy pošle `output` (category `stderr`) s textem chyby a posledními řádky `openocdTail()` a pak `terminated`, a zabije gdb.
  - Chyba kroku (podle SPIKE.md nejde busy ST-Link poznat z logu OpenOCD): pokud `otherOpenocd()` (nový parametr konstruktoru, `() => Promise<boolean>`, v produkci `pgrep -x openocd`) vrátí true, přidá řádek `ST-Link may be in use by another OpenOCD or debug session (make debug / make openocd).`
  - `evaluate` s `context: "hover"`, pro který `guardsHover` vrátí jméno: odpoví lokálně `not read – reading clears flags; use Watch or sfr`, gdb ho nevidí.
  - Ukončení procesu gdb: `terminated` s textem. `dispose()` pošle SIGTERM a po 2 s SIGKILL.

- [ ] **Step 1: Write `fake-gdb.js`**: Node skript mluvící DAP po stdio, chování podle env `FAKE` (`ok`, `hang-attach`, `error-run`, `exit-early`), zapisuje přijaté příkazy do souboru z `FAKE_LOG`.
- [ ] **Step 2: Write failing tests** v `adapter.test.js`: `test_launch_becomes_attach` (fake dostane `attach` s `program` a `target` beze změny; klient vidí úspěšnou odpověď na `launch`), `test_start_sequence_after_configuration_done`, `test_step_timeout_terminates` (`stepTimeoutMs: 200`, výstup obsahuje „timed out“, přijde `terminated`, fake je zabit), `test_error_shows_openocd_tail_and_busy_hint`, `test_hover_guard_local_answer`, `test_hover_other_forwarded`, `test_gdb_exit_terminates`, `test_dispose_kills_gdb`, `test_path_with_space_and_diacritics` (`project.elf` = `/tmp/Žák Novák/lab 1/out.elf` dorazí do `attach` beze změny).
- [ ] **Step 3: Run** `node --test .make/vscode/test/adapter.test.js`. Expected: FAIL.
- [ ] **Step 4: Implement** `GdbProxy`. Každý krok startu má vlastní časovač; zprávy od gdb se parsují přes `createParser`.
- [ ] **Step 5: Run** testy. Expected: PASS.
- [ ] **Step 6:** Připomeň commit (`feat(vscode): DAP proxy`).

### Task 8: Proxy na skutečném čipu

**Files:**
- Create: `.make/vscode/bin/proxy-cli.js`, `.make/vscode/test/test_proxy_hw.py`

**Interfaces:**
- Produces: `node .make/vscode/bin/proxy-cli.js` čte DAP ze stdin, píše na stdout; vezme `project` z `make dap-info` a spustí `GdbProxy` se skutečným `stm8-gdb`. Slouží jen testům, VS Code ho nepoužívá.

- [ ] **Step 1: Write failing tests (hw)** s `DapClient` proti `proxy-cli.js`: `test_start_stops_at_main` (`initialize`, `launch`, `configurationDone` → `stopped` ve `main` do 30 s), `test_disconnect_no_orphans` (po `disconnect` do 3 s žádný `pgrep -x openocd`), `test_leftover_openocd_on_3333_attaches_over_tcp` (ručně spuštěný `openocd` jako `make openocd` drží ST-Link na :3333; `launch` přesto skončí `stopped` ve `main` přes TCP, cizí `openocd` zůstane běžet), `test_unreachable_chip_message` (`gdbTarget` s neexistujícím příkazem; do 10 s přijde `output` s chybou a `terminated`, žádné zavěšení), `test_six_breakpoints_verified_and_hit` (6 řádkových breakpointů jsou `verified`, `continue` se zastaví na prvním; viz SPIKE.md G6), `test_threads_right_after_configuration_done` (VS Code posílá `threads`/`stackTrace` hned po `configurationDone`: proxy nesmí spadnout ani zablokovat start).
- [ ] **Step 2: Run** `STM8_HW=1 pytest .make/vscode/test/test_proxy_hw.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `proxy-cli.js`; chyby podle výsledků opravit v `adapter.js` (a doplnit unit test do `adapter.test.js`).
- [ ] **Step 4: Run** testy. Expected: PASS.
- [ ] **Step 5:** Připomeň commit (`test(vscode): proxy na čipu`).

### Task 9: Sestavení rozšíření a F5

**Files:**
- Create: `.make/vscode/package.json`, `.make/vscode/extension.js`, `.make/vscode/src/project.js`, `.make/vscode/pack.py`, `.make/vscode/test/project.test.js`, `.make/vscode/test/test_pack.py`, `.vscode/tasks.json`
- Modify: `.make/vscode.mk` (cíl `vscode`), `.vscode/launch.json`, `.vscode/.gitignore` (přidat `!tasks.json`), `.gitignore` (přidat `.make/vscode/*.vsix`)

**Interfaces:**
- Consumes: `GdbProxy` (Task 7), `dap-info` (Task 1).
- Produces v `project.js`: `readProjectInfo(cwd: string, deps?: { exec }): Promise<ProjectInfo>` (spustí `make -s --no-print-directory dap-info`; při „No rule to make target“ vyhodí `ToolchainError` s textem `Old toolchain – update .make/ and add the line -include .make/vscode.mk to Makefile`), `preflight(info: ProjectInfo, cwd: string): Promise<string[]>` (seznam problémů; viz kroky), `openocdTail(logPath: string, n = 5): string[]` (poslední řádky obsahující `Error`), `versionNotice(installed: string, projectDir: string): string | null`.
- Produces: `pack.py`: `pack(src_dir: str, out_path: str) -> None`; VSIX obsahuje `extension.vsixmanifest`, `[Content_Types].xml`, `extension/package.json`, `extension/extension.js`, `extension/src/*.js`, `extension/media/*`; bez `test/`, `bin/`, `DESIGN.md`, `PLAN.md`, `SPIKE.md`, `pack.py`.
- `package.json`: debug typ `stm8` (`languages: ["c"]`, `configurationAttributes` prázdné, `initialConfigurations` s jednou konfigurací), aktivace `workspaceContains:.make/gdbinit` a `onDebugResolve:stm8`, `engines.vscode: ^1.80.0`.
- `.vscode/launch.json`: jediná konfigurace `{"type":"stm8","request":"launch","name":"STM8 debug","preLaunchTask":"stm8: build"}`. `.vscode/tasks.json`: úloha `stm8: build` = `make debug-files`, problem matcher regexp `^(.+?):(\d+):\s+(warning|error)\s+(\d+):\s+(.*)$` (soubor, řádek, závažnost, kód, zpráva).

- [ ] **Step 1: Write failing tests:** node `project.test.js`: `test_old_toolchain_message`, `test_parse_dap_info`, `test_preflight_old_gdb` (`stm8-gdb` verze 14 → problém obsahuje „stm8-gdb 15“), `test_preflight_missing_openocd`, `test_preflight_live_debug_session` (`.debug-session` s `process.pid` → problém „make debug is running“; mrtvý PID se ignoruje), `test_preflight_missing_elf` (problém s cestou a „Build failed?“), `test_openocd_tail_last_five_errors`, `test_version_notice`. Python `test_pack.py`: `test_vsix_entries`, `test_vsix_excludes_dev_files`, `test_manifest_identity` (`Publisher="spseol"`, `Id="stm8-toolchain"`, verze z `package.json`), `test_install_in_codium` (slow: `codium --install-extension … --force` exit 0 a `codium --list-extensions` obsahuje `spseol.stm8-toolchain`).
- [ ] **Step 2: Run** `node --test .make/vscode/test/project.test.js` a `pytest .make/vscode/test/test_pack.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** `project.js`, `pack.py`, cíl `vscode` v `vscode.mk` (balí a instaluje do `code` a/nebo `codium` nalezených v PATH; žádný nenalezen → chyba s návodem), `package.json`, `.vscode/*`.
- [ ] **Step 4: Implement `extension.js`:** `DebugConfigurationProvider` pro `stm8` (prázdná konfigurace → výchozí; `readProjectInfo` + `preflight`, při problémech modální chyba a zrušení F5), `DebugAdapterDescriptorFactory` vracející `DebugAdapterInlineImplementation` s `GdbProxy` (`spawn`: `stm8-gdb -q -i dap -x .make/gdbinit` s cwd projektu a env podle Global Constraints; `sideEffects` zatím `{}`), při aktivaci `versionNotice`. **Pokud SPIKE.md/Task 5 určil, že Python watcher v DAP režimu nejde:** přidat `src/elfwatch.js` (`FileSystemWatcher` na `info.elf`, při změně `workbench.action.debug.restart`).
- [ ] **Step 5: Run** všechny testy z kroku 2 a `make vscode`. Expected: PASS a `codium --list-extensions` ukáže `spseol.stm8-toolchain`.
- [ ] **Step 6: Milník pro uživatele (GUI):** `make vscode`, restart VSCodium, otevřít projekt, F5. Zastaví na `main`, breakpoint v `src/main.c` funguje, step over/into/out, Locals a Registers; odpojený ST-Link dá hlášku do 10 s; čip po „Stop“ běží (LED bliká).
- [ ] **Step 7:** Připomeň commit (`feat(vscode): rozšíření, make vscode, F5`).

### Task 10: Strom SFR

**Files:**
- Create: `.make/vscode/src/sfrmodel.js`, `.make/vscode/src/sfrtree.js`, `.make/vscode/test/sfrmodel.test.js`
- Modify: `.make/vscode/package.json` (view `stm8Peripherals` v kontejneru `debug`, `when: debugType == 'stm8'`, příkazy, menu), `.make/vscode/extension.js`, `.make/vscode/src/project.js`, `.make/vscode/test/test_proxy_hw.py`

**Interfaces:**
- Consumes: JSON ze `sfr-json` (Task 4).
- Produces v `project.js`: `loadSfrModel(info: ProjectInfo): Promise<SfrModel>` (offline `stm8-gdb -q -batch` s `source` obou skriptů a `sfr-json`, `STM8_SFR=info.sfr`).
- Produces v `sfrmodel.js`: `parse(text: string): { periphs: Periph[], sideEffects: {[periph: string]: string[]} }`; `regLabel(reg): string` (`"0x81  1000 0001  ARPE CEN"`, vícebitové pole jako `PSC=5`); `changedBits(reg): number` (maska bitů, kde se `value` liší od `prev`); `fieldValue(bit, value): number`; `withField(old: number, bit, v: number): number`.
- Produces v `sfrtree.js`: `class SfrTree` (TreeDataProvider) s `refresh(): void` a `setRunning(running: boolean): void`. Uzly periferie → registr → bit. Jednobitová pole mají `checkboxState`. Změněné registry mají žlutou ikonu `circle-filled`. Registr s `sideEffect` ukazuje popis „not read (reading clears flags)“ a ikonu „Read“, která volá `sfr-json PERIF.REG`. Za běhu programu popisek „running“. Zápis přes `session.customRequest("evaluate", {expression: "sfr-set …", context: "repl"})`. Čtou se jen rozbalené periferie. Tracker `registerDebugAdapterTrackerFactory("stm8")`: `stopped` → `refresh`, `continued` → `setRunning(true)`, `terminated` → vyčistit.

- [ ] **Step 1: Write failing tests** `sfrmodel.test.js`: `test_reg_label` (bity ARPE `0x80`, OPM `0x08`, CEN `0x01`, hodnota `0x81` → `0x81  1000 0001  ARPE CEN`), `test_reg_label_multibit` (pole `PSC` maska `0x07`, hodnota 5 → obsahuje `PSC=5`), `test_changed_bits` (value `0x81`, prev `0x01` → `0x80`), `test_with_field`, `test_parse_collects_side_effects`.
- [ ] **Step 2: Write failing hw test** `test_sfr_json_via_proxy`: repl `sfr-json TIM4` přes `proxy-cli.js` vrátí JSON s neprázdnou hodnotou `CR1`; za běhu programu (`continue`) vrátí chybu „running“.
- [ ] **Step 3: Run** `node --test .make/vscode/test/sfrmodel.test.js` a hw test. Expected: FAIL.
- [ ] **Step 4: Implement** `sfrmodel.js`, `loadSfrModel`, `sfrtree.js`, zapojení do `extension.js` včetně předání `model.sideEffects` do `GdbProxy`.
- [ ] **Step 5: Run** testy. Expected: PASS.
- [ ] **Step 6: Milník pro uživatele (GUI):** strom ukazuje periferie čipu; `TIM4.CNTR` se mezi zastaveními mění a je zvýrazněný; zaškrtnutí bitu `GPIOx.ODR` rozsvítí LED; `UART1.DR` se samo nečte; hover nad `UART1->DR` nic nesmaže.
- [ ] **Step 7:** Připomeň commit (`feat(vscode): strom SFR`).

### Task 11: Detail registru

**Files:**
- Create: `.make/vscode/src/regview.js`, `.make/vscode/test/regview.test.js`
- Modify: `.make/vscode/package.json` (příkaz `stm8.sfr.openRegister`, inline ikona na registru), `.make/vscode/extension.js`

**Interfaces:**
- Produces: `renderRegisterHtml(periph: Periph, reg: Reg, nonce: string): string`. Čisté HTML bez externích zdrojů, s CSP `default-src 'none'; style-src 'nonce-…'; script-src 'nonce-…'`: záhlaví `TIM4->CR1  0x5340`, popis, hodnota po resetu (`0x00`), tabulka bitů (pozice `7` nebo `3:1`, jméno, hodnota, popis ze `stm8s.h`). Klik na buňku bitu pošle `{type: "setBit", name}`. Příkaz otevře `WebviewPanel` a zápis jde přes `sfr-set`.

- [ ] **Step 1: Write failing tests:** `test_escapes_html_in_desc` (popis `<script>x</script>` se nevypíše jako značka), `test_shows_reset_value`, `test_multibit_position` (`3:1`), `test_csp_without_external_resources` (žádné `http`).
- [ ] **Step 2: Run** `node --test .make/vscode/test/regview.test.js`. Expected: FAIL.
- [ ] **Step 3: Implement** `regview.js` a panel v `extension.js`. Panel se po `stopped` obnoví.
- [ ] **Step 4: Run** test. Expected: PASS.
- [ ] **Step 5:** Připomeň commit (`feat(vscode): detail registru`).

### Task 12: Stavový řádek a výběr čipu

**Files:**
- Create: `.make/vscode/src/statusbar.js`, `.make/vscode/test/statusbar.test.js`
- Modify: `.make/vscode/package.json` (příkazy `stm8.build`, `stm8.flash`, `stm8.debug`, `stm8.pickChip`), `.make/vscode/extension.js`

**Interfaces:**
- Produces: `chipItems(devices: {[family: string]: {[chip: string]: string}}, current: string): { label: string, description: string, picked: boolean }[]` (čisté, seskupené podle rodiny, aktuální čip `picked`).
- Příkazy: `stm8.build` spustí úlohu `stm8: build`; `stm8.flash` za běhu ladění vyvolá `workbench.action.debug.restart`, jinak spustí `make flash` v terminálu; `stm8.debug` spustí `workbench.action.debug.start`; `stm8.pickChip` načte `python3 .make/devices.py`, ukáže QuickPick a spustí `make switch-device CHIP=<čip>`, pak znovu načte `dap-info` a SFR model.

- [ ] **Step 1: Write failing test** `test_chip_items_groups_and_marks_current`.
- [ ] **Step 2: Run** `node --test .make/vscode/test/statusbar.test.js`. Expected: FAIL.
- [ ] **Step 3: Implement** `statusbar.js` a zapojení.
- [ ] **Step 4: Run** test. Expected: PASS.
- [ ] **Step 5: Milník pro uživatele (GUI):** tlačítka Build, Flash, Debug fungují; přepnutí na `stm8s103f3` změní seznam periferií po dalším F5; za běhu ladění Flash ladění restartuje.
- [ ] **Step 6:** Připomeň commit (`feat(vscode): stavový řádek a výběr čipu`).

### Task 13: Dokumentace a závěrečné ověření

**Files:**
- Create: `.make/vscode/README.md` (anglicky: instalace `make vscode`, F5, strom SFR, řešení potíží)
- Modify: `CLAUDE.md` (sekce Ladění a IDE podpora: rozšíření, `make vscode`, `dap-info`, `sfr-json`/`sfr-set`, `STM8_UI=dap`), `README.md` a `README.cs.md` (krátká sekce VS Code), `.make/vscode/DESIGN.md` (odchylky)

- [ ] **Step 1: Write docs** podle seznamu výše.
- [ ] **Step 2: Run** celou sadu: `pytest .make/vscode -q`, `STM8_HW=1 pytest .make/vscode -q`, `node --test .make/vscode/test/*.test.js`. Expected: vše PASS.
- [ ] **Step 3: Ověření cgdb:** `make debug` se připojí, zastaví na `main`, `sfr TIM4` a `p TIM4->CR1` fungují, `flash` v gdb a hlídání ELF fungují (uživatel ručně).
- [ ] **Step 4: E2E v čistém klonu (uživatel):** devět bodů z DESIGN.md, sekce Ověření, a navíc `UART1.DR` hover.
- [ ] **Step 5:** Připomeň commit (`docs(vscode): dokumentace rozšíření`).

---

## Odchylky od návrhu

- Neinteraktivní přepnutí čipu je `make switch-device CHIP=…`, ne `DEVICE=…`, protože `DEVICE` už Makefile používá a příkazový řádek by přepsal jeho hodnotu (Task 3).
- Detail registru se neotvírá dvojklikem, protože TreeView API dvojklik nemá. Otevírá ho inline ikona na řádku registru (Task 11).
- Statický model SFR (periferie, bity, `sideEffects`) čte rozšíření offline samostatným `stm8-gdb -batch`, ne z běžící session, aby ochrana hoveru a strom nezáležely na stavu DAP (Task 10).
- Seznam čipů pro přepínání (interaktivní, `CHIP=` i výběr ve VS Code) se filtruje podle `../SPLSPL/mk/*.mk`, tedy podle toho, co build opravdu umí přeložit. `devices.py` zůstává katalogem čipů (Task 3).
- Pořadí fází se změnilo: `dap-info` (Task 1) je před spikem, protože spike potřebuje `gdbTarget`.
