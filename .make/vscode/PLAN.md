# Marketplace, New Project a Update Toolchain — plán implementace

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vydat plugin na Open VSX a Microsoft Marketplace, přidat příkaz `STM8: New Project` a `STM8: Update Toolchain` / `make upgrade` a dát projektu logo (papírový dráček).

**Architecture:** Plugin zůstává v `.make/vscode/` bez npm závislostí. Logika upgradu je v Pythonu (`.make/upgrade.py`) a spouští se z nově staženého commitu toolchainu, takže ji plugin i `make upgrade` sdílejí a stará verze v projektu nevadí. Zakládání projektu a vydání jsou samostatné moduly (`src/newproject.js`, `release.py`) s vložitelným `exec`/`run`, aby se daly testovat bez sítě a bez editoru.

**Tech Stack:** Node.js (jen `node:` moduly, `node --test`), Python 3 + pytest, GNU Make, git, `rsvg-convert`, `npx ovsx` (jen při vydání).

**Spec:** `.make/vscode/DESIGN.md`

## Global Constraints

- Plugin bez npm závislostí, čisté JS; student nepotřebuje Node.js.
- UI pluginu, nový kód a hlášky jsou anglicky. Výjimka: česká šablona README nového projektu.
- Kořenový `Makefile` uživatele se nepřepisuje bez jeho souhlasu: tříčestný `git merge-file`, konflikt nechá značky `<<<<<<<`. Přechod z `Makefile-sdcc-gas`/`-sdccrm` na `Makefile-sdcc` jen po souhlasu.
- Upgrade nesahá na `src/`, `inc/`, `lib/`, README, `tasks.json`, `.vscode/.gitignore`; nic necommituje ani nestaguje.
- `.vscode/launch.json` se nahradí verzí z toolchainu; nesledovaný se nejdřív uloží jako `.vscode/launch.json.bak`.
- Toolchain se stahuje z `main` na `stm8.toolchainUrl` (výchozí `https://gitlab.com/spseol/mit-no/STM8S-toolchain.git`; `make upgrade` čte `STM8_TOOLCHAIN_URL`), ne z remote `upstream`.
- `make dap-info` (JSON) zůstává zpětně kompatibilní.
- Po úpravě `.make/Makefile-sdcc` zkopírovat do `Makefile` (hlídá `test_makefile_copy_identical`). Tento plán mění jen `.make/vscode.mk`.
- Token Open VSX se nikdy nevypíše ani neuloží do repa.
- Logo nekopíruje logo STMicroelectronics; ikona je PNG ≥ 128×128, README obrázky jen `https` a ne SVG.
- Práce na větvi `vscode-marketplace`. Po dokončení smazat `DESIGN.md` a `PLAN.md` (konvence repa).
- Testy: `pytest .make/vscode` a `node --test .make/vscode/test/*.test.js` musí procházet po každém tasku.

## Review Focus

- Jméno projektu s mezerou, diakritikou, lomítkem nebo tečkou na začátku → `createProject` projde nebo srozumitelně odmítne, nikdy nezapíše mimo `parent`. (Task 5)
- `Makefile` bez aktivního řádku `DEVICE_FLASH=` nebo jen s `#DEVICE_FLASH=` → přechod variant nespadne, `Makefile` dostane výchozí řádek nové verze a report to řekne. (Task 2)
- Opakovaný upgrade (po commitu, nebo s nevyřešeným konfliktem) → podruhé nic nemění, resp. odmítne s „unresolved conflicts“. (Task 2, 4)
- Repo bez jediného commitu nebo bez gitu → srozumitelná hláška, žádný stack trace. (Task 1)
- Release s chybějícím tokenem, selhaným `ovsx publish` nebo existujícím tagem → nevznikne tag ani push, token není ve výstupu. (Task 9)

---

### Task 1: `upgrade.py` — poznání varianty a ochrany

**Files:**
- Create: `.make/upgrade.py`
- Create: `.make/vscode/test/test_upgrade.py`
- Modify: `.make/vscode/test/conftest.py` (fixtures)

**Interfaces:**
- Produces:
  - `class Refused(Exception)` — zpráva se ukáže uživateli tak, jak je.
  - `class NeedsSwitch(Exception)` — atribut `variant: str` (`"sdcc-gas"` nebo `"sdccrm"`).
  - `detect_variant(makefile: str, variants: dict[str, str]) -> str` — klíč s nejmenším počtem rozdílných řádků; `Refused`, když nejlepší rozdíl přesahuje 40 % řádků `makefile`.
  - `check_project(project: Path) -> None` — `Refused`, když to není git repo, repo nemá commit, chybí `.make/Makefile-sdcc` nebo `Makefile`, nebo jsou v `.make`, `Makefile`, `.vscode/launch.json` necommitnuté změny (`git status --porcelain -- …`).
- conftest fixtures: `toolchain_remote(tmp_path) -> Path` (git repo se sledovanými soubory z `ROOT`, commit na `main`) a `old_project(tmp_path, variant="sdcc", dirty=False, with_include=False) -> Path` (`with_include=True` ponechá `-include .make/vscode.mk` v `Makefile` i v `.make/Makefile-sdcc`; git repo s orphan `main`, `.make/` a `Makefile` z `ROOT` ve starém stavu: bez řádků `-include .make/vscode.mk` a jejich komentáře, `DEVICE_FLASH=stm8s103f3`, jeden uživatelský řádek `F_CPU=8000000` v `Makefile`, `src/main.c` s vlastním obsahem, `.vscode/launch.json` s konfigurací `cppdbg`; `variant` vezme `Makefile` z `Makefile-sdcc-gas` nebo `-sdccrm`).

- [ ] **Step 1: Write the failing tests** in `test_upgrade.py`: `test_detect_variant_picks_closest` (tři varianty z `ROOT/.make`, `Makefile` = každá s upraveným `DEVICE_FLASH` → vrátí správný klíč), `test_detect_variant_refuses_foreign_makefile` (`"all:\n\ttrue\n"` → `Refused`), `test_check_project_refuses` parametrizovaně: bez gitu, repo bez commitu, bez `.make/Makefile-sdcc`, `dirty=True` (změna v `Makefile`) — každá zpráva obsahuje slovo, které řekne důvod (`git`, `commit`, `Makefile-sdcc`, `uncommitted`); `test_check_project_accepts_clean_old_project`.
- [ ] **Step 2: Run** `pytest .make/vscode/test/test_upgrade.py -v` → FAIL (`ModuleNotFoundError: upgrade`). Test modul načítá `.make/upgrade.py` přes `importlib.util.spec_from_file_location`, jako `pack()` v `test_vscode_files.py`.
- [ ] **Step 3: Implement** `Refused`, `NeedsSwitch`, `detect_variant` (`difflib` na řádcích), `check_project` (volá `git` přes `subprocess.run`, bez stack trace — chyby git → `Refused`). Fixtures do conftestu.
- [ ] **Step 4: Run** testy → PASS.
- [ ] **Step 5: Commit** `vscode: upgrade.py rozpozná variantu Makefile a odmítne špinavý projekt`.

### Task 2: `upgrade.py` — provedení upgradu a CLI

**Files:**
- Modify: `.make/upgrade.py`
- Modify: `.make/vscode/test/test_upgrade.py`

**Interfaces:**
- Consumes: Task 1 (`Refused`, `NeedsSwitch`, `detect_variant`, `check_project`, fixtures).
- Produces:
  - `@dataclass Report`: `replaced: int`, `removed: int`, `makefile: str` (`"merged"|"conflict"|"unchanged"|"switched"`), `launch: str` (`"replaced"|"added"|"unchanged"`), `backup: str | None`, `gitignore_added: list[str]`, `notes: list[str]`.
  - `upgrade(project: Path, ref: str, switch: str | None = None) -> Report` — `ref` je git ref v repu projektu (po `git fetch`). `switch` je `"yes"|"no"|None`; varianta ≠ `sdcc` a `switch is None` → `NeedsSwitch`; `"no"` → `Refused("Update cancelled, nothing was changed.")`.
  - `main(argv: list[str]) -> int` — `REF [--switch yes|no] [--json]`; návratové kódy: `0` hotovo, `1` `Refused`, `2` konflikt v `Makefile`, `3` potřeba rozhodnutí o přechodu (JSON `{"needsSwitch": "<variant>"}` na stdout). Bez `--switch` a s TTY se zeptá přes `input()`. S `--json` je poslední řádek stdout `json.dumps(asdict(report))`. Skript nesmí používat `__file__` (spouští se přes `python3 -c`) a musí zůstat pod 100 kB.

- [ ] **Step 1: Write the failing tests:**
  - `test_upgrade_sdcc_clean_merge`: po `upgrade(old, "FETCH_HEAD")` (po `git fetch toolchain_remote main`) obsahuje `Makefile` `-include .make/vscode.mk` **a** `DEVICE_FLASH=stm8s103f3` **a** `F_CPU=8000000`; `.make/vscode.mk` existuje; `report.makefile == "merged"`.
  - `test_upgrade_conflict_keeps_markers`: uživatel přidal řádek na konec `Makefile` (commitnutý) → `report.makefile == "conflict"`, `main()` vrací `2`, `Makefile` obsahuje `<<<<<<< Makefile` a `>>>>>>> new .make/Makefile-sdcc`.
  - `test_upgrade_does_not_touch_user_files`: SHA-256 všech souborů v `src/` (a `inc/`, `lib/`, `README.md`) před a po stejné; `git diff --cached --quiet` (nic nestagováno) a `git rev-parse HEAD` stejné.
  - `test_upgrade_removes_files_gone_from_toolchain`: soubor sledovaný ve starém `.make/` a chybějící v novém zmizí; nesledovaný `.make/linker_output/x` zůstane.
  - `test_upgrade_replaces_tracked_launch_json` a `test_upgrade_untracked_launch_json_gets_bak` (`.vscode/.gitignore` = `*`): `launch.json` má jedinou konfiguraci `STM8 debug`; `.bak` obsahuje původní `cppdbg`.
  - `test_upgrade_gitignore_adds_missing_lines_only`.
  - `test_upgrade_idempotent`: po commitu výsledku druhé volání → `replaced == 0`, `makefile == "unchanged"`.
  - `test_variant_needs_switch` (`old_project(variant="sdcc-gas")`): `upgrade(..., None)` → `NeedsSwitch`; `"no"` → `Refused` a `git status --porcelain` prázdný; `"yes"` → `Makefile` shodný s novým `Makefile-sdcc` až na řádek `DEVICE_FLASH=stm8s103f3`.
  - `test_switch_without_active_device_flash`: starý `Makefile` má jen `#DEVICE_FLASH=…` → výsledek má výchozí řádek nové verze a `report.notes` to zmiňuje.
  - `test_main_exit_codes_and_json`: `main([...])` vrací `0/1/2/3` v příslušných situacích; `--json` poslední řádek parsuje.
- [ ] **Step 2: Run** `pytest .make/vscode/test/test_upgrade.py -v` → FAIL.
- [ ] **Step 3: Implement** `upgrade()` a `main()`. Soubory z `ref` číst přes `git ls-tree -r -z ref -- .make` a `git show ref:cesta` v bytech (binární `sdccrm.exe`, `.x`); zachovat exec bit z módu `ls-tree`. Starý `Makefile-sdcc` pro merge vzít z `HEAD` před přepsáním `.make/`. Merge: `git merge-file -p -L Makefile -L "old .make/Makefile-sdcc" -L "new .make/Makefile-sdcc" Makefile old new` (návratový kód = počet konfliktů). Přechod: nový `Makefile-sdcc` + `DEVICE_FLASH` přes regex `^\s*(DEVICE_FLASH=)stm8\w+\s*$` (stejný jako `.make/switch_device.sh`). Chybějící řádky `.gitignore` = řádky z `ref:.gitignore`, které v souboru nejsou.
- [ ] **Step 4: Run** testy → PASS; potom celé `pytest .make/vscode`.
- [ ] **Step 5: Commit** `vscode: upgrade.py provede upgrade .make/ s tříčestným mergem Makefile`.

### Task 3: `make upgrade`

**Files:**
- Modify: `.make/vscode.mk`
- Modify: `.make/vscode/test/test_make_targets.py`

**Interfaces:**
- Consumes: `upgrade.py main()` z Tasku 2.
- Produces: cíl `upgrade` (`.PHONY`), proměnné `STM8_TOOLCHAIN_URL ?= https://gitlab.com/spseol/mit-no/STM8S-toolchain.git` a `UPGRADE_ARGS ?=`.

- [ ] **Step 1: Write the failing test** `test_make_upgrade_runs_script_from_fetched_ref` v `test_make_targets.py`: `toolchain_remote` + projekt = `old_project(with_include=True)` s `.make/vscode.mk` z `ROOT` zkopírovaným a commitnutým (starý `Makefile` jinak cíl `upgrade` nezná) → `run_make(["upgrade", f"STM8_TOOLCHAIN_URL=file://{remote}", "UPGRADE_ARGS=--switch no"], cwd=project)` skončí `returncode == 0` a `Makefile` má `-include .make/vscode.mk` (jeho hlášku upgradu v stdout).
- [ ] **Step 2: Run** → FAIL (`No rule to make target 'upgrade'`).
- [ ] **Step 3: Implement** recept: `git fetch $(STM8_TOOLCHAIN_URL) main` a `$(PYTHON) -c "$$(git show FETCH_HEAD:.make/upgrade.py)" FETCH_HEAD $(UPGRADE_ARGS)`. Stdin zůstává volný pro `input()`.
- [ ] **Step 4: Run** `pytest .make/vscode/test/test_make_targets.py -v` → PASS.
- [ ] **Step 5: Commit** `vscode: make upgrade stahuje toolchain a spouští upgrade.py z něj`.

### Task 4: Plugin — Update Toolchain

**Files:**
- Create: `.make/vscode/src/upgrade.js`
- Modify: `.make/vscode/src/project.js` (`ToolchainError.fix`, konflikt v `readProjectInfo`, `versionNotice`, `upgradeOffer`), `.make/vscode/extension.js`, `.make/vscode/package.json`
- Test: `.make/vscode/test/upgrade.test.js`, `project.test.js`, `extension.test.js`, `test_vscode_files.py`

**Interfaces:**
- Produces:
  - `runUpgrade(root: string, { url: string, switchChoice?: 'yes'|'no', exec?: Function }) → Promise<{ code: 0|1|2|3, output: string, needsSwitch?: string }>` — `git fetch url main`, `git show FETCH_HEAD:.make/upgrade.py` → `python3 -c <skript> FETCH_HEAD --json [--switch X]`; nenulový kód z `python3` se nevyhazuje, ale vrací v `code`; selhání `git fetch` → `code: 1` s `output` po anglicku („Cannot download the toolchain from …“).
  - `project.upgradeOffer(installed: string, projectDir: string) → boolean` — `true`, když existuje `.make/Makefile-sdcc` a `.make/vscode/package.json` chybí nebo má nižší verzi než `installed`.
  - `ToolchainError.fix` (`'updateToolchain'` u hlášky „Old toolchain …“).
  - příkaz `stm8.updateToolchain`, nastavení `stm8.toolchainUrl` (výchozí URL z Global Constraints), `activationEvents` navíc `workspaceContains:.make/Makefile-sdcc`.

- [ ] **Step 1: Write the failing tests:**
  - `upgrade.test.js`: s falešným `exec` ověřit pořadí (`git fetch` → `git show` → `python3 -c`), předání `--switch`, mapování kódů `0..3`, `needsSwitch` z JSON na stdout, chybu fetchu.
  - `project.test.js`: `readProjectInfo` v adresáři s `Makefile` obsahujícím `<<<<<<< Makefile` (falešné `exec` se nesmí zavolat) vyhodí `ToolchainError` s textem `unresolved conflicts`; `upgradeOffer` pro čtyři případy (bez `.make/Makefile-sdcc`, bez vscode `package.json`, starší, shodná verze); „Old toolchain“ chyba má `fix === 'updateToolchain'`; `versionNotice` zmiňuje aktualizaci rozšíření.
  - `extension.test.js`: příkaz `stm8.updateToolchain` při kódu `3` zobrazí dotaz a po „Switch“ zavolá `runUpgrade` znovu s `switchChoice: 'yes'`; při kódu `2` otevře `Makefile` (`vscode.window.showTextDocument`); při `0` ukáže informační hlášku s `output`.
  - `test_vscode_files.py::test_package_json_matches_extension_code` už vyžaduje shodu deklarovaných a registrovaných příkazů; přidat aserci na `activationEvents` a konfiguraci `stm8.toolchainUrl`.
- [ ] **Step 2: Run** `node --test .make/vscode/test/*.test.js` → FAIL.
- [ ] **Step 3: Implement.** Nabídka při aktivaci: tlačítka *Update Toolchain* / *Not now* / *Don't ask again*; třetí uloží `stm8.upgrade.dismissed` do `context.workspaceState`. Modální chybové okno u `error.fix === 'updateToolchain'` má navíc tlačítko *Update Toolchain*, které spustí příkaz. Konflikt: `readProjectInfo` hledá `/^<{7} /m` v `Makefile` dřív, než zavolá `make` („Makefile has unresolved conflicts from Update Toolchain – resolve them and save“; preflight běží až po `readProjectInfo`, takže další kontrola není třeba).
- [ ] **Step 4: Run** `node --test .make/vscode/test/*.test.js` a `pytest .make/vscode` → PASS.
- [ ] **Step 5: Commit** `vscode: příkaz Update Toolchain a nabídka aktualizace starého projektu`.
- [ ] **Step 6: Ruční kontrola uživatelem** (GUI): kopie `../97-nucleo+daughterboard-demo` a `../44-neopixel` v VSCodium → nabídka se objeví, Update projde, `44-…` zeptá na přechod, F5 spustí `STM8 debug`.

### Task 5: Plugin — New Project

**Files:**
- Create: `.make/vscode/src/newproject.js`, `.make/vscode/media/README.project.md` (česká šablona ze `stm8newproject`, titul `{{TITLE}}`), `.make/vscode/media/schema.png` (`curl -sSL -o … https://chytrosti.marrek.cz/mit/dlazdice/urovne.png`; ověřit, že je to PNG)
- Modify: `.make/vscode/extension.js`, `.make/vscode/package.json` (`stm8.newProject`, `stm8.projectsFolder`, `viewsWelcome` pro `explorer` s `when: workbenchState == empty`), `.make/vscode/pack.py` (`media/` už je v `INCLUDE`)
- Test: `.make/vscode/test/newproject.test.js`, `extension.test.js`

**Interfaces:**
- Produces:
  - `validateName(name: string, parent: string) → string | null` — chybový text, nebo `null`. Odmítne prázdné jméno (po `trim`), `/`, `\`, jméno začínající `.`, existující cestu.
  - `renderReadme(template: string, name: string) → string` — `{{TITLE}}` = jméno s velkým prvním písmenem.
  - `createProject({ url, parent, name, mediaDir, exec }) → Promise<{ dir: string, warnings: string[] }>` — kroky `git clone url dir`, `git branch -m upstream`, `git remote rename origin upstream`, `git checkout --orphan main`, `make compile_commands.json` (selhání → varování), `README.md`→`README.origin.md`, nový `README.md`, `docs/schema.png` z `mediaDir`, `git add .`, `git commit -m "Initial commit"` (selhání → varování s textem „set git user.name and user.email“, soubory zůstanou). Chyba clone → `ToolchainError` s URL v textu.

- [ ] **Step 1: Write the failing tests** (`newproject.test.js`, `exec` = skutečný `execFile`, ale `make` nahrazený prázdným úspěchem): v `toolchain_remote`-like repu vytvořeném v `os.tmpdir()` (soubory `Makefile`, `README.md`, `.make/x`, commit na `main`) po `createProject({ url: 'file://…', name: 'Žák Novák 1' })`: větve `main` a `upstream`, remote jen `upstream`, `git log --oneline` má jeden commit „Initial commit“, `README.origin.md` je původní, `README.md` začíná `# Žák Novák 1`, `docs/schema.png` je shodný s `media/schema.png`. `validateName`: `''`, `'a/b'`, `'.x'`, existující složka → text; `'lab 1'`, `'Žák'` → `null`. Chybějící `git.user` (`GIT_CONFIG_GLOBAL=/dev/null`, `GIT_AUTHOR_*` nenastaveno) → `warnings` neprázdné, `README.md` existuje. V `extension.test.js`: příkaz `stm8.newProject` poprvé zavolá `showOpenDialog`, uloží `stm8.projectsFolder`, zeptá se na jméno a volá `vscode.openFolder`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Průběh přes `vscode.window.withProgress`. Otevření: prázdné okno (`workspaceFolders` prázdné) znovu použít, jinak `forceNewWindow: true`. Při dalším spuštění nabídne uloženou složku a „Change…“.
- [ ] **Step 4: Run** `node --test .make/vscode/test/*.test.js`, `pytest .make/vscode` → PASS.
- [ ] **Step 5: Commit** `vscode: příkaz New Project klonuje toolchain jako stm8newproject`.
- [ ] **Step 6: Ruční kontrola uživatelem:** VSCodium bez toolchainu, New Project → projekt otevřen, Build stáhne SPL.

### Task 6: Plugin — vlastní task `stm8: build` (s GUI bránou)

**Files:**
- Create: `.make/vscode/src/tasks.js`
- Modify: `.make/vscode/extension.js`, `.make/vscode/package.json` (`taskDefinitions: [{ type: "stm8" }]`, `problemMatchers: [{ name: "sdcc", … }]` — regex a vlastnosti zkopírovat z `.vscode/tasks.json`)
- Test: `.make/vscode/test/tasks.test.js`, `test_vscode_files.py`

**Interfaces:**
- Produces: `registerBuildTask(vscode) → Disposable` — `registerTaskProvider('stm8', …)`, který vrací jediný task `build` (`ShellExecution('make debug-files')`, scope `WorkspaceFolder`, skupina Build, `problemMatchers: ['$sdcc']`).

- [ ] **Step 1: Write the failing tests:** `tasks.test.js` s falešným `vscode` — provider vrací task s názvem `build`, příkazem `make debug-files` a `$sdcc`; `test_problem_matcher_matches_real_build_output` se rozšíří tak, že čte matcher z `package.json` (`contributes.problemMatchers`) a musí být shodný s tím v `.vscode/tasks.json`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** oba testovací příkazy → PASS.
- [ ] **Step 5: Commit** `vscode: plugin sám nabízí úlohu stm8: build`.
- [ ] **Step 6: GUI brána (uživatel):** v projektu **bez** `.vscode/tasks.json` a v projektu **s** ním stisknout F5. Požadavky: `preLaunchTask: "stm8: build"` se najde, build běží, chyby jdou do Problems, úloha se v nabídce neobjeví dvakrát. **Když `preLaunchTask` z provideru nejde přeložit** nebo se duplikuje: task nepřidávat, vrátit commit a místo toho do `upgrade.py` přidat doplnění chybějícího `.vscode/tasks.json` z `ref` (výjimka z Global Constraints, upravit i test a Review Focus).

### Task 7: VSIX vhodný pro marketplace

**Files:**
- Modify: `.make/vscode/package.json`, `.make/vscode/pack.py`, `.make/vscode/README.md`
- Create: `.make/vscode/CHANGELOG.md`, `.make/vscode/media/icon.png` (provizorní: `magick -size 256x256 xc:'#c0392b' …`, nahradí Task 8)
- Test: `.make/vscode/test/test_vscode_files.py`

**Interfaces:**
- Produces: `pack.pack(src_dir, out_path)` přibalí `LICENSE` z kořene repa jako `extension/LICENSE.txt`, `CHANGELOG.md`, `media/`; manifest dostane `<Tags>`, kategorie `Debuggers,Education` a assety `Microsoft.VisualStudio.Services.Icons.Default`, `…Content.Details`, `…Content.Changelog`, `…Content.License`, `Microsoft.VisualStudio.Services.Links.Source|Getstarted|Support|Learn`. `package.json` má `icon`, `repository` (`https://github.com/spseol/STM8S-toolchain.git`), `homepage`, `bugs`, `keywords` (stm8, stm8s, sdcc, openocd, gdb, debugger, embedded, microcontroller, spl), `categories: ["Debuggers", "Education"]`.

- [ ] **Step 1: Write the failing tests:** `test_vsix_has_marketplace_assets` (v zipu `extension/LICENSE.txt`, `extension/CHANGELOG.md`, `extension/media/icon.png`; manifest obsahuje čtyři `Asset` typy výše a `Education`); `test_icon_is_png_at_least_128` (hlavička PNG, šířka a výška z IHDR); `test_readme_images_are_https_and_not_svg` (regex `!\[[^\]]*\]\(([^)]+)\)` v `README.md`); `test_vsix_excludes_dev_files` doplnit o `RELEASING.md` a `release.py`; `test_package_json_marketplace_fields`.
- [ ] **Step 2: Run** `pytest .make/vscode/test/test_vscode_files.py -v` → FAIL.
- [ ] **Step 3: Implement.** README anglicky pro cizí lidi: co plugin umí, požadavky (SDCC, make, python3, openocd, `stm8-gdb` ≥ 15 s DAP a kde ho vzít), začátek přes `STM8: New Project` a `STM8: Update Toolchain`, ověřená platforma Linux, odkaz na toolchain a české README; stávající sekce o `make vscode` zůstane pro uživatele toolchainu. `CHANGELOG.md`: `0.2.0` (New Project, Update Toolchain, marketplace). Verzi v `package.json` zvýšit na `0.2.0`.
- [ ] **Step 4: Run** oba testovací příkazy; `make vscode IDES=codium` nainstaluje bez chyby (je-li `codium` v `PATH`) → PASS.
- [ ] **Step 5: Commit** `vscode: VSIX s ikonou, licencí a changelogem pro marketplace`.

### Task 8: Logo — papírový dráček

**Files:**
- Create: `.make/vscode/media/icon.svg`, `.make/vscode/media/icon.png` (přepíše provizorní), `.make/vscode/media/banner.png` (+ `banner.svg`)
- Modify: `README.md`, `README.cs.md` (banner nahoře přes relativní cestu `.make/vscode/media/banner.png`)

**Interfaces:**
- Produces: `icon.png` 256×256 (`rsvg-convert -w 256`), čitelný ve 128 px i 32 px na světlém i tmavém pozadí.

- [ ] **Step 1:** Navrhnout 3–4 varianty SVG dráčka (kosočtvercový papírový drak na pouštění, zkřížené špejle, provázek, ocas s barevnými mašličkami; ne drak chrlící oheň; varianty: barevná pole, náznak čipu/„8“, sklon ve větru) do `$SCRATCHPAD/logo/v1.svg … v4.svg` a jeden HTML náhled (každá varianta ve 256, 128 a 32 px na světlém a tmavém pozadí). Otevřít `xdg-open` (nebo visual companion).
- [ ] **Step 2: Uživatel vybere** variantu a případné úpravy; opakovat do schválení. Nic z toho necommitovat dřív.
- [ ] **Step 3:** Schválenou variantu uložit jako `media/icon.svg`, vyrobit `icon.png` 256×256 a `banner.svg/png` (dráček + text „STM8S toolchain“), zkontrolovat obrázky přes `Read` při 128 px a 32 px.
- [ ] **Step 4:** Do `README.md` a `README.cs.md` vložit banner na začátek.
- [ ] **Step 5: Run** `pytest .make/vscode` (test z Tasku 7 hlídá rozměr ikony) → PASS.
- [ ] **Step 6: Commit** `vscode: logo – papírový dráček`.

### Task 9: Vydání — `make vscode-release`

**Files:**
- Create: `.make/vscode/release.py`, `.make/vscode/RELEASING.md`
- Modify: `.make/vscode.mk`
- Test: `.make/vscode/test/test_release.py`

**Interfaces:**
- Produces:
  - `load_token(env: Mapping[str, str], token_file: Path) → str | None` — `OVSX_PAT`, jinak obsah `~/.config/stm8-toolchain/ovsx-token` (oříznutý).
  - `redact(text: str, token: str) → str` — nahradí token `***`.
  - `release(root: Path, *, dry_run: bool = False, run=subprocess.run, env=os.environ, token_file: Path = …) → int` — pořadí: (1) čistý strom, větev `main`, `main` není za `origin/main`; (2) verze z `package.json`, tag `vscode-v<verze>` neexistuje; (3) token existuje (mimo `--dry-run`); (4) `pytest .make/vscode` a `node --test …`; (5) `pack.py`; (6) `npx ovsx publish <vsix> -p <token>`; (7) anotovaný tag, push `main` a tagu na `origin` i `github`; (8) výpis cesty k VSIX a `xdg-open https://marketplace.visualstudio.com/manage/publishers/spseol` (selhání `xdg-open` jen varování). `--dry-run` skončí po kroku 5. Vrací `0`, jinak `1` s anglickou hláškou; výstup `ovsx` jde přes `redact`.
  - `main()` s volbou `--dry-run`; cíl `vscode-release` v `.make/vscode.mk` (`$(if $(DRY_RUN),--dry-run)`).

- [ ] **Step 1: Write the failing tests** (`test_release.py`; temp repo s `main`, dvěma bare remotes `origin` a `github`, `package.json`; `run` zaznamenává příkazy a pro `npx`, `pytest`, `node` vrací falešný výsledek):
  - `test_refuses_dirty_tree`, `test_refuses_other_branch`, `test_refuses_when_behind_origin`, `test_refuses_existing_tag` — návratová hodnota `1`, `run` nevolalo `npx`, žádný nový tag.
  - `test_refuses_without_token` — `1`, pořadí: bez volání testů a `npx`; hláška jmenuje `OVSX_PAT` a cestu k souboru.
  - `test_dry_run_publishes_nothing` — `0`, `npx` nevolán, tag neexistuje, remotes beze změny.
  - `test_full_release_order`: příkazy v pořadí testy → pack → `npx ovsx publish` → tag → push `origin` → push `github`; tag `vscode-v<verze>` je anotovaný a je v obou remotes.
  - `test_failed_publish_creates_no_tag_and_hides_token`: `npx` vrátí kód 1 a ve stderr token; `release()` vrací `1`, tag není, zachycený výstup token neobsahuje.
  - `test_load_token_prefers_env`.
- [ ] **Step 2: Run** `pytest .make/vscode/test/test_release.py -v` → FAIL.
- [ ] **Step 3: Implement.** `RELEASING.md` anglicky: jednorázové kroky (účet a vydavatel `spseol` na Microsoftu; Open VSX: GitHub login, Eclipse účet, Publisher Agreement, `npx ovsx create-namespace spseol -p TOKEN`, žádost o ověření namespace; uložení tokenu s `chmod 600`), postup po `make vscode-release`, upozornění na zrušení PAT 1. 12. 2026 a ruční upload VSIX.
- [ ] **Step 4: Run** testy → PASS; `make vscode-release DRY_RUN=1` na větvi `vscode-marketplace` odmítne (větev není `main`) s čitelnou hláškou.
- [ ] **Step 5: Commit** `vscode: make vscode-release publikuje na Open VSX a připraví Microsoft`.

### Task 10: Dokumentace a úklid

**Files:**
- Modify: `CLAUDE.md`, `README.md`, `README.cs.md`
- Delete: `.make/vscode/DESIGN.md`, `.make/vscode/PLAN.md`

- [ ] **Step 1:** Do `CLAUDE.md` (sekce VS Code) doplnit: `upgrade.py` a `make upgrade` (kódy 0–3, spouštění přes `python3 -c` z `FETCH_HEAD`), New Project, `release.py`, `RELEASING.md`, nastavení `stm8.toolchainUrl` a `stm8.projectsFolder`. Do obou README krátká věta o marketplace, `make upgrade` a `STM8: New Project`.
- [ ] **Step 2: Run** `pytest .make/vscode` a `node --test .make/vscode/test/*.test.js` → PASS.
- [ ] **Step 3:** Smazat `DESIGN.md` a `PLAN.md`. **Commit** `vscode: dokumentace vydání, smazat návrh a plán`.
- [ ] **Step 4:** Uživatel merguje větev na `main` a spustí první `make vscode-release` (pro `0.2.0`); skript nikdy nespouštět bez něj.
