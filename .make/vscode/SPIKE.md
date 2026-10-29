# Spike: `stm8-gdb -i dap` na skutečném čipu

Měřeno 2026-10-29 na Nucleo (STM8S208RB, ST-LINK/V2.1), gdb 15.0.50, OpenOCD 0.12.0, s **nezměněným** `.make/gdbinit`.
Skript: `STM8_HW=1 python3 .make/vscode/test/dap_smoke.py` (všechny povinné brány PASS).

## Brány

| Brána | Výsledek | Pozorování |
|---|---|---|
| G1 start | PASS | `attach {program, target: gdbTarget}` trvá 0,1 s. `configurationDone` nic nespouští. Pak repl `evaluate` příkazů `load` (1,2 s), `monitor reset halt`, `maintenance flush register-cache`, `tbreak main`, `continue` dá `stopped` (reason `breakpoint`) ve `main`. Repl `continue` se vrátí až po zastavení. |
| G2 obsazený ST-Link | INFO | S jiným OpenOCD na :3333 vrací `attach` **úspěch** za 0,0 s, bez `output` události a bez řádku `Error` v logu OpenOCD (log končí řádkem „telnet server disabled“). Chybu prozradí až další příkaz: `"monitor" command not supported by this target.`; `info target` ukáže jen lokální ELF. Odpojený ST-Link nešel vyzkoušet. |
| G3 data | PASS | `next`/`stepIn`/`stepOut` (`main:55` → `init:41` → `main:58`), `scopes` = Locals + Registers (pc, a, x, y, sp, cc), `readMemory`, `writeMemory`, `setExpression` fungují. Repl `p TIM4->CR1` je bez ANSI, `sfr TIM4` s ANSI. Adresy registrů se liší mezi rodinami (S208: CNTR 0x5344, ARR 0x5346, S103: 0x5346/0x5348), proto se berou z gdb (`p/x &TIM4->ARR`). |
| G4 pause | PASS | `continue`, po 1 s `pause` → `stopped` (reason `pause`) okamžitě. |
| G5 disconnect | PASS | `disconnect {terminateDebuggee: false}`: gdb skončí do 0,1 s, žádný `openocd` nezůstane. Bez předchozího `monitor reset halt` + `monitor resume` zůstane čip **zastavený**; po nich běží (TIM4 CNTR roste). Stávající `on_exit` v `stm8gdb.py` to dělá, ale jen když `state["connected"]`, což `attach` nenastaví. |
| G6 breakpointy | INFO | 6 řádkových breakpointů v `main.c`: všech 6 `verified: true` bez `message`, `continue` se zastaví na prvním (`main:58`). Limit se nedosáhl; OpenOCD zřejmě vkládá softwarové breakpointy. Breakpointy nastavené před `configurationDone` (jak to dělá VS Code) fungují: po `tbreak main` se zastaví i na nich. |
| G7 repl | INFO | Repl `evaluate` funguje mezi `attach` a `configurationDone`. **Za běhu programu** gdb odpoví `success=false`, `message: "notStopped"` (nehodí se čekat na vlastní hlášku z Pythonu). |
| G8 výstup | PASS | Text z `gdb.write` uvnitř repl příkazu je v `result` té odpovědi, ne v `output` událostech. Text z doby načítání `gdbinit` (např. „gdb nemá ELF“) přijde jako `output` událost. |
| G9 stdout | PASS | Před prvním DAP záhlavím nic navíc, `gdbinit` DAP protokol nekazí. |
| G10 symboly | PASS | Symboly z `sfr.elf` (`add-symbol-file` v `gdbinit`) přežijí pozdější `file` z `attach`; `p TIM4->CR1` i `sfr` fungují. |

## Rozhodnutí

1. **Startovní sekvence** (proxy, Task 7): `initialize` → `attach {program: elf, target: gdbTarget}` → požadavky klienta (`setBreakpoints`, …) → `configurationDone` → repl `run`. Po Tasku 5 je repl `run` jeden příkaz (`RunCommand`: `load`, `monitor reset halt`, `maintenance flush register-cache`, `tbreak main`, `continue`), jeho `ensure_connected()` se postará o připojení. Záložní varianta `stm8-dap-start` **není potřeba**.
2. **Selhání `attach` se nepozná** z odpovědi ani z logu OpenOCD. Poznat ho musí `is_connected()` v Tasku 5 (`connection_num is not None`); `run` pak zkusí stávající `connect()` (pipe a TCP :3333) a selže `GdbError` s řádky `Error` z logu. Důsledek: **ST-Link držený `make openocd` (naslouchá na :3333) se obslouží přes TCP a F5 funguje**, jako v cgdb. Skutečně obsazený ST-Link (běžící `make debug`, cizí program) vyžaduje předběžnou kontrolu v rozšíření (`.debug-session`, `pgrep -x openocd`), ne hledání `BUSY`/`libusb` v logu.
3. **Za běhu programu** vrací gdb `notStopped`. Strom SFR to bere jako stav „running“ (Task 10), `sfr-json` a `sfr-set` si „program is running“ hlídají sami pro CLI (cgdb).
4. **Konec session:** `disconnect` čip nechá zastavený. V DAP režimu proto musí `on_exit` (Task 5) udělat `monitor reset halt` + `monitor resume` podle `is_connected()`.
5. **Limit breakpointů** se v testu nedosáhl. Test v Tasku 8 ověří, že 6 breakpointů je `verified` a první se zastaví; nepotvrzený breakpoint bez `message` není scénář, který by šlo vyvolat.
6. **Nezodpovězeno, ověří Task 8:** co VS Code posílá hned po `configurationDone` (`threads`, `stackTrace`) před prvním zastavením, a zda to gdb zvládne.
