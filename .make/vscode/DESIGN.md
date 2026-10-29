# VS Code debugger pro STM8 toolchain — návrh

## Kontext

Ladění přes cgdb (`make debug`) funguje dobře: krokování, breakpointy, proměnné a SFR periferie. Ke SFR patří příkaz `sfr`, výrazy `TIM4->CR1`, zvýraznění změn a zápis přes `set var`. Teď chceme stejné možnosti ve VS Code, protože žáci píšou kód tam.

Existující rozšíření [github0null/stm8-debug](https://github.com/github0null/stm8-debug) nestačí:
- Start je nespolehlivý. Vlastní DAP vrstva nad gdb na chybových cestách neodpovídá, nemá timeouty a souběh při startu obchází čekáním `setTimeout(100)`.
- SFR má jen ručně psaný JSON pro 3 čipy (S003F3, S103F3, S105K4) a registry umí jen číst.
- Je jen pro Windows. Na Linuxu ho uživatel musel ručně upravit.

Klíčový nález: nainstalovaný `stm8-gdb` je GDB 15.0.50 (`/opt/stm8-binutils-gdb`) a má zabudovaný DAP server (`stm8-gdb -i dap`). Ověřeno požadavkem `initialize`. Server umí `readMemory` a `writeMemory`, `setExpression`, `disassemble`, instrukční breakpointy a scope Registers. Python 3.13 v něm běží, takže stávající `.make/stm8gdb.py` a `.make/stm8sfr.py` jdou použít přímo. Vlastní DAP vrstvu proto nepíšeme. Rozšíření jen spustí gdb a postaví nad ním UI.

Výsledek: student otevře projekt ve VS Code a stiskne F5. Projekt se přeloží, nahraje do čipu a zastaví na `main()`. Periferie jsou vidět ve stromu a dají se měnit.

## Rozhodnutí uživatele

- Plugin žije **v toolchainu**, ne v samostatném repu. Nebude v Marketplace a instaluje se příkazem `make vscode`.
- Hlavní verze Python logiky zůstává v `.make/`. Plugin ji smí použít přímo, nemusí mít vlastní kopii.
- Verze 1 jen Linux. Windows později a návrh ho nesmí zablokovat: žádné `/proc` a shell triky v JS, cesty přes `path`.
- SFR pro všechny čipy STM8S, které pokrývá `stm8s.h` ve SPL. Data generuje `.make/sfr_gen.py` jako teď.
- Pohled SFR: strom v panelu Run and Debug (periferie, registry, bity) a k tomu detail registru po dvojkliku.
- Rozsah: debugger a tlačítka ve stavovém řádku (Build, Flash, Debug, výběr čipu). Sériový terminál ne.
- Cgdb ladění (`make debug`, `make gdb`) musí fungovat beze změny chování.
- **UI pluginu anglicky.** Celý toolchain se postupně přepíše do angličtiny. Nový kód (JS i nové Python příkazy a hlášky) je anglicky. Stávající české texty v `.make/` se teď nepřekládají.
- Varianty `Makefile-sdcc-gas` a `Makefile-sdccrm` jsou historie a neupravují se. Mění se jen `.make/Makefile-sdcc` (a `Makefile`, jeho kopie).
- Staré projekty žáků (bez nových cílů a příkazů) nemusí F5 podporovat. Plugin je pozná a napíše, co aktualizovat.
- Rozšíření na školních PC mezi přihlášeními zůstávají. Stačí jednou `make vscode`. Plugin upozorní, když je v projektu novější verze, než je nainstalovaná.
- Během implementace se smí volně nahrávat do připojeného Nucleo (ST-LINK/V2.1, `0483:374b`) a krokovat na něm. GUI testy (F5, klikání, LED) dělá uživatel.

## Cíle / ne-cíle / anti-cíle

**Cíle:** F5 bez úprav konfigurace. Spolehlivé připojení napoprvé. Krokování, breakpointy, Variables a Watch. Registry CPU, paměť a disassembly. SFR strom s rozpisem bitů, zvýrazněním změn a zápisem. `sfr …` a `p TIM4->CR1` fungují v Debug Console.

**Ne-cíle:** Marketplace a Open VSX. STM8L/AL. Windows ve verzi 1. Sériový terminál. Podpora projektů mimo tento toolchain.

**Anti-cíle (selhání, i když „to funguje“):**
- Student musí upravovat `launch.json`.
- Start občas visí nebo potichu selže bez srozumitelné hlášky.
- Instalace vyžaduje Node.js nebo npm u studenta.
- Rozbije se cgdb workflow.

## Architektura

```
VS Code ──DAP (stdio)──► stm8-gdb -q -i dap -x .make/gdbinit     (env STM8_UI=dap, STM8_OPENOCD, STM8_SFR, …)
   │                          │  Python: stm8gdb.py (start, reload), stm8sfr.py (sfr, sfr-json)
   │                          └──pipe──► openocd -c "gdb_port pipe" …  ──► ST-Link ──► STM8
   └── rozšíření .make/vscode/ (čistý JS): debug typ "stm8", SFR strom, detail registru, stavový řádek
```

### 1. Rozšíření `.make/vscode/` (moje volba umístění)

- Čistý JavaScript (CommonJS), **žádné npm závislosti a žádný build krok**. VSIX je zip (`extension.vsixmanifest`, `[Content_Types].xml`, `extension/…`), takže ho `make vscode` sestaví `zip`em a nainstaluje přes `code --install-extension`, případně `codium`.
- `package.json`: publisher `spseol`, name `stm8-toolchain`, debug typ **`stm8`** (moje volba). Typ `stm8-debug` patří github0null a dva stejné typy by kolidovaly.
- Aktivace: `workspaceContains:.make/gdbinit` a `onDebugResolve:stm8`.
- UI texty anglicky (příkazy, hlášky, popisky stromu, webview).
- Části:
  - **`DebugConfigurationProvider`**: doplní prázdnou nebo minimální konfiguraci. Spustí `make -s --no-print-directory dap-info` a z JSON vezme cestu k ELF, `sfr.elf`, příkaz OpenOCD a cestu k logu.
  - **`DebugAdapterDescriptorFactory`** vrátí `DebugAdapterInlineImplementation` (moje volba): tenký proxy v JS. Spustí `stm8-gdb -q -i dap -x .make/gdbinit` (cwd projektu, env jako dnešní `GDB_ENV` v Makefile a navíc `STM8_UI=dap`) a DAP zprávy přeposílá oběma směry. Framing `Content-Length` zabere asi 50 řádků. Proxy umí to, co čistý `DebugAdapterExecutable` ne:
    - timeouty startovních kroků a srozumitelné chyby místo visení,
    - startovní sekvenci (níž),
    - ochranu hoveru (níž),
    - úklid procesu gdb a OpenOCD při chybě.
  - **Startovní sekvence (řídí proxy):** VS Code pošle `launch` s konfigurací `stm8`. Proxy ho nepřepošle a místo něj pošle gdb `attach` s `program` (ELF) a `target` (pipe na OpenOCD, stejný řetězec jako dnes staví `connect()` ve `stm8gdb.py`).
    - Proč `attach`: v režimu `launch` gdb 15 v `configurationDone` volá `run`, a to na vzdáleném cíli nejde. Při `attach` gdb potlačí počáteční stop, takže prvním stop eventem je až zastavení na `main`.
    - Gdb v `attach` chyby `target remote` spolkne: `exec_and_log` chytá `gdb.error`, ověřeno ve `startup.py`. Úspěšná odpověď na `attach` tedy nic neznamená.
    - Proto po `configurationDone` proxy pošle repl `evaluate` s příkazem `run` (dnešní `RunCommand`: load, reset halt, flush register-cache, tbreak main, continue). `ensure_connected()` při chybějícím spojení zkusí `connect()` znovu a selže `GdbError` s chybami z logu OpenOCD. Repl evaluate tak vrátí chybu a proxy ji ukáže uživateli a session ukončí.
    - **Ověřit ve fázi 0.**
  - **Ochrana hoveru (moje volba):** hover nad `UART1->DR` by tiše přečetl DR a smazal RXNE. To rozbije typický UART program žáka. Proxy u `evaluate` s `context: "hover"` porovná výraz se seznamem registrů s vedlejším efektem (`READ_SIDE_EFFECT` přes `sfr-json`). Platí i pro celou periferii, která takový registr obsahuje (`UART1`). Místo čtení vrátí text „not read – reading clears flags; use Watch or sfr“. Watch, Variables a Debug Console čtou normálně, protože tam si čtení žák řekl sám (stejně jako `p UART1` v cgdb).
  - **Kontrola před startem** se srozumitelnými hláškami: existuje `stm8-gdb` a je to verze ≥ 15? Existuje `openocd`? Je připojený ST-Link (lsusb VID 0483)? Když spojení selže, rozšíření ukáže posledních 5 řádků `Error` z logu OpenOCD, jako dnes `openocd_errors()`. Každý DAP krok startu má timeout, po vypršení přijde hláška, nikdy tiché čekání.
  - **SFR strom** (`TreeDataProvider` ve view containeru `debug`): periferie (jméno, base adresa), pod nimi registry (`0x01  0000 0001  CEN`), pod nimi bity. Jednobitová pole jako `checkboxState` (VS Code ≥ 1.72). Vícebitová pole a celý registr přepíše akce „Zapsat hodnotu…“ přes InputBox. Data se načtou při `stopped` eventu (`DebugAdapterTracker`), jen pro rozbalené periferie. Za běhu programu je strom zašedlý s textem „running“.
  - **Detail registru** (webview po dvojkliku): obsah jako `sfr TIM4.CR1`, tedy bity 7…0, jména polí, popisy ze `stm8s.h` a hodnota po resetu. Klik na bit ho přepne.
  - **Stavový řádek:** Build (task `stm8: build`), Flash (`make flash` v terminálu; za běhu ladicí session místo toho restart session), Debug (`workbench.action.debug.start`), čip (QuickPick ze `.make/devices.py`, pak neinteraktivní `make switch-device DEVICE=…`).

### 2. Úpravy Python skriptů v `.make/`

- **`stm8gdb.py`**, režim `STM8_UI=dap`:
  - Žádný banner a žádný `reload()` ve `stm8_start()`. Start řídí rozšíření.
  - `ensure_connected()` pozná spojení navázané DAP `attach`em. Například přes `gdb.selected_inferior().connection`, místo příznaku `state["connected"]`, který nastavuje jen `connect()`.
  - `on_stop` nevolá `show_vars()`, to dělá panel Variables.
  - Zapsat `.debug-session`, aby `make flash` za běhu ladění jen přeložil ELF.
  - Hlídač ELF: cílem je stejné chování jako v cgdb (změna ELF za běhu ladění znamená nahrát a zastavit na `main`). Fáze 0 ověří, jestli Python watcher v DAP režimu funguje. Když ne, ELF hlídá rozšíření (`FileSystemWatcher`) a restartuje session.
  - Barvy: `say()` smí dál psát ANSI (Debug Console je zobrazí). `ColorPrinter` musí v DAP režimu zůstat vypnutý, ANSI kódy nesmí dostat hodnoty proměnných.
- **`stm8sfr.py`**:
  - Nový příkaz `sfr-json [PERIFERIE[.REG] …]`. Bez argumentu vypíše seznam periferií a registrů s bity. S argumenty vypíše hodnoty, předchozí hodnoty (`track()`) a příznak `side_effect`. Formátovací logika se sdílí se `sfr`.
  - Nový příkaz `sfr-set PERIFERIE.REG HODNOTA` nebo `PERIFERIE.REG.POLE HODNOTA` (read-modify-write).
  - `SfrPrinter` v DAP režimu vrací hodnotu bez ANSI (`paint` už respektuje `style enabled`, DAP režim nastaví `set style enabled off`).
  - Rozšíření volá oba příkazy přes `session.customRequest("evaluate", {context: "repl"})`. Výstup se vrací v `result` a do Debug Console nejde. Používají se jen veřejné DAP požadavky a CLI gdb, žádné interní API `gdb.dap.server`.

### 3. Makefile (jen `.make/Makefile-sdcc`, varianty `-gas` a `rm` ne)

Nové cíle jsou v **`.make/vscode.mk`**, které Makefile načte řádkem `-include .make/vscode.mk`. Pozdější změny cílů pro VS Code tak nevyžadují zásah do Makefile, který si žák upravil.
- Když `make dap-info` selže (starý projekt bez `vscode.mk`), plugin napíše „Old toolchain – update .make/ and add the line -include .make/vscode.mk to Makefile“.
- Plugin porovná svou verzi s `version` v `.make/vscode/package.json` projektu. Když je projekt novější, nabídne spuštění `make vscode`.

- `debug-files: $(TARGET_ELF) $(SFR_ELF)`, cíl pro build task.
- `dap-info`: vypíše JSON `{"elf", "sfr", "openocd", "openocdLog", "device"}` bez buildu. Jediný zdroj pravdy o cestách `build-$(DEVICE)-elf`.
- `vscode`: zabalí `.make/vscode/` do VSIX a nainstaluje ho.
- `switch-device`: přijme `DEVICE=…` neinteraktivně (`switch_device.sh` s argumentem přeskočí `pick`).
- `.make/devices.py` (moje volba, oprava chyby): duplicitní klíč `STM8S003K3` (kvůli němu chybí S003F3) a chybějící STM8S105. Stejný seznam používá výběr čipu v pluginu i interaktivní `make switch-device`.
- `make vscode` instaluje do toho z `code` a `codium`, který je v PATH, případně do obou. Na tomto PC je jen `codium` 1.143.

### 4. `.vscode/` v toolchainu

- `launch.json`: jediná konfigurace `{"type": "stm8", "request": "launch", "name": "STM8 debug", "preLaunchTask": "stm8: build"}`. Staré konfigurace (`gdb`, `stm8-debug`) se smažou.
- `tasks.json`: `stm8: build` = `make debug-files` s problem matcherem pro SDCC (`soubor:řádek: error N: text`, případně `warning`).
- `extensions.json` se nemění, plugin v Marketplace nebude.

## Fáze implementace

Po schválení: tento návrh se uloží do `.make/vscode/DESIGN.md` (moje volba místo `docs/`, aby startovací strom pro žáky nedostal novou složku). Pak z něj vznikne podrobný implementační plán (superpowers:writing-plans).

0. **Spike na čipu (zahodit nebo ponechat jen ověřený kus):** ručně (skript v Pythonu, který mluví DAP) ověřit `stm8-gdb -i dap -x .make/gdbinit`: `initialize`, `attach` s pipe na OpenOCD, repl `run`, stop na `main`, `setBreakpoints`, `next`, `stepIn`, `variables` (Locals, Registers), `readMemory`, repl `sfr TIM4`. Dál `disconnect` (čip po ukončení běží), Python watcher ELF v DAP režimu a restart session v VS Code včetně opakovaného `preLaunchTask`. Výsledky rozhodnou o otevřených bodech výše.
1. Python: DAP režim ve `stm8gdb.py`, `sfr-json` a `sfr-set` ve `stm8sfr.py`. Ověřit, že `make debug` (cgdb) funguje dál.
2. Makefile: `debug-files`, `dap-info`, `vscode`, neinteraktivní `switch-device`.
3. Rozšíření: debug typ, start, kontroly a hlášky, `.vscode/launch.json` a `tasks.json`. Milník: F5 zastaví na `main`, krokování funguje.
4. SFR strom a zápis bitů a registrů.
5. Detail registru (webview).
6. Stavový řádek.
7. Dokumentace: README toolchainu a `CLAUDE.md` (sekce Ladění a IDE podpora).

## Rizika

- **Zvláštnosti DAP v gdb 15:** ověřeno spikem (`SPIKE.md`). `attach` + repl `load`/`monitor reset halt`/`tbreak main`/`continue` funguje, záložní příkaz `stm8-dap-start` není potřeba. Zbývá: `attach` hlásí úspěch i když se k čipu nepřipojil (hlídá `is_connected()`), `disconnect` nechá čip zastavený (řeší `on_exit`), za běhu programu vrací gdb `notStopped`.
- **Hardwarové breakpointy STM8:** spike s 6 breakpointy limit nenašel (OpenOCD zřejmě vkládá softwarové). Pokud se limit někdy projeví, ukázat srozumitelnou hlášku, ne tichý neověřený breakpoint.
- **Read-modify-write bitů ve status registrech** (rc_w0, třeba TIM SR1) může smazat i jiné příznaky. Zdokumentovat v detailu registru. Registry z `READ_SIDE_EFFECT` se ve stromu nečtou automaticky.

## Ponecháno builderovi

Vzhled ikon a stromu, přesné texty hlášek, struktura JS modulů, formát JSON z `sfr-json` a `dap-info`, implementace problem matcheru, zda VSIX sestavit `zip`em nebo Pythonem (`zipfile`).

## Ověření

- **Fáze 0:** DAP skript projde všechny kroky na reálném STM8S208 (Nucleo) přes ST-Link.
- **Cgdb regrese:** `make debug` se připojí, zastaví na `main`, `sfr TIM4`, `p TIM4->CR1`, `flash` a hlídání ELF fungují jako dřív.
- **VS Code end-to-end** (`make vscode`, pak F5 v čistém klonu toolchainu):
  1. Zastaví na `main`.
  2. Breakpoint v `milis.c` se zastaví.
  3. Step over, into a out fungují.
  4. Locals, Registers a Watch `TIM4->CR1` ukazují hodnoty.
  5. SFR strom: TIM4.CNTR se mezi zastaveními mění a je zvýrazněný.
  6. Zaškrtnutí ODR bitu rozsvítí LED.
  7. UART1.DR se nečte automaticky.
  8. Úprava kódu a Restart nahraje nový program.
  9. Odpojený ST-Link dá srozumitelnou hlášku do 10 s.
- **Výběr čipu:** přepnout na stm8s103f3, F5 má jiný seznam periferií.
- **VSCodium:** `make vscode` nainstaluje rozšíření i do `codium`.

## Odchylky při implementaci (2026-10-29)

Plán, výsledky spiku a rulings jsou v `PLAN.md` a `SPIKE.md`. Hlavní odchylky od tohoto návrhu:

- Neinteraktivní přepnutí čipu je `make switch-device CHIP=…`, ne `DEVICE=…` (proměnná `DEVICE` už Makefile používá). Seznam čipů se filtruje podle `../SPLSPL/mk/*.mk`; z `devices.py` zmizel `STM8S001J3` (bez `.mk` nejde přeložit) a přibyly čipy STM8S105 a STM8S903.
- Detail registru se neotvírá dvojklikem (TreeView API ho nemá), ale ikonou na řádku registru.
- Strukturu SFR (periferie, bity, registry s vedlejším efektem) čte rozšíření offline samostatným `stm8-gdb -batch`, ne z běžící session.
- Záložní příkaz `stm8-dap-start` ani JS hlídání ELF nebyly potřeba: `attach` + repl `run` a Python watcher fungují v DAP režimu.
- Selhání `attach` (obsazený nebo nedostupný ST-Link) se z odpovědi ani z logu OpenOCD nepozná. Hlídá ho `run` (`is_connected()`), obsazený `make openocd` na :3333 se obslouží přes TCP.
- Limit hardwarových breakpointů se při 6 breakpointech neprojevil (OpenOCD vkládá softwarové).
- Text hoveru nad registrem s vedlejším efektem radí ikonu *Read* ve stromu, ne Watch (Watch registr čte při každém zastavení). Zápis jednotlivého pole do takového registru (`AWU.CSR`, `I2C.SR3`, `FLASH.IAPSR`) je odmítnutý, protože read-modify-write by registr přečetl; zapisuje se celý registr.
- Když se model SFR nenačte, hover guard používá pevný seznam `DEFAULT_SIDE_EFFECTS` (shodný s `READ_SIDE_EFFECT`, hlídá to test).
- Po neúspěšném buildu (`preLaunchTask`) rozšíření F5 zruší, aby „Debug Anyway“ nenahrálo starý program.
