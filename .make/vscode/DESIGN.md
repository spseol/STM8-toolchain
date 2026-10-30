# STM8 Toolchain na marketplacech, nový projekt z pluginu, upgrade starých projektů — návrh

## Kontext

Rozšíření `spseol.stm8-toolchain` v `.make/vscode/` umí F5 ladění, SFR strom a status bar. Instaluje se jen příkazem `make vscode` z toolchainu. Uživatel chce, aby plugin i toolchain byly vidět veřejně a měl z nich užitek víc lidí. Proto:

1. Plugin bude na **Open VSX** (VSCodium, Cursor, …) i na **Microsoft Marketplace** (jen VS Code od Microsoftu, podle jeho podmínek).
2. Kdo nainstaluje jen plugin, založí si projekt příkazem **`STM8: New Project`**. Plugin naklonuje toolchain do nové složky.
3. Staré projekty dostanou cestu k novému toolchainu: **`STM8: Update Toolchain`** / `make upgrade`.
4. Toolchain a plugin dostanou **logo**: papírový dráček.

Plugin zůstává v toolchainu. Samostatné repo pro plugin nebude.

## Zjištěná fakta (30. 10. 2026)

- Microsoft ruší globální Azure DevOps PAT **1. 12. 2026**. Po tom datu nejde lokální `vsce publish` s tokenem. Zbývá ruční upload VSIX na stránce vydavatele, nebo GitHub Actions s Trusted Publishing (OIDC). GitLab CI Trusted Publishing nepodporuje.
- Open VSX: přihlášení přes GitHub, propojení s Eclipse účtem, podpis Publisher Agreement, token bez expirace. `npx ovsx create-namespace spseol -p TOKEN` jednou, potom `npx ovsx publish soubor.vsix -p TOKEN`. Ověření vlastnictví namespace je samostatná žádost. Open VSX při publikaci kontroluje tajemství v souborech, blocklist a podobnost jmen.
- Namespace `spseol` na Open VSX je volný. Na Open VSX není žádný STM8 debugger, jen Embedded IDE a PlatformIO.
- Ikona v `package.json` musí být PNG aspoň 128×128, ne SVG. Obrázky v README a CHANGELOG jen přes https a ne SVG.
- Na tomto počítači jsou `node` 20, `npx`, `rsvg-convert`, `inkscape`, `magick`, `xdg-open`.
- Staré projekty (`../97-…`, `../01-blueboard…`) mají remote `upstream` a orphan `main`. Jejich `main` nemá s toolchainem společnou historii, takže `git pull upstream main` skončí `refusing to merge unrelated histories`.
- Remote `upstream` je v různých projektech různý. `../44-neopixel` má jen vlastní `origin`. `MIT-*` mají `upstream` na lokální složku toolchainu. `XX-4xMAX7219-text` ho má na složku, která už neexistuje. Projekty z `00-STM8S-toolchain-Deroboard` ho mají na tuto kopii toolchainu. `../00-nucleo-daughterboard` je KiCad projekt bez `.make/`.
- Kořenový `Makefile` vznikl z různých variant:
  - z `Makefile-sdcc`: toolchain, `97-…`, `01-blueboard…`; od `.make/Makefile-sdcc` se liší jen řádkem `DEVICE_FLASH`;
  - z `Makefile-sdcc-gas`: `44-neopixel`, `11-ncoder`, `40-…`, `58-…`, `XX-Dero-UART`, `XX-4xMAX7219-text`;
  - z `Makefile-sdccrm`: `MIT-*`, `XX-tentononc`.
  
  Variantu jde spolehlivě poznat: `diff Makefile .make/Makefile-<varianta>` dá u správné varianty 0 řádků nebo jen pár.
- Staré projekty mají `.vscode/launch.json` s konfiguracemi `cppdbg` nebo `stm8-debug`. F5 spustí první z nich. Ve `97-…` a `01-…` je celý `.vscode/` ignorovaný (`.vscode/.gitignore` = `*`).
- Build task `stm8: build` definuje `.vscode/tasks.json` v projektu. Plugin task provider nemá.
- GitHub zrcadlo je 20 commitů za GitLabem.
- Konvence repa: návrh a plán se commitují do `.make/vscode/` (`DESIGN.md`, `PLAN.md`) a po dokončení se smažou (commity `0b2c908` a `8a7ad16`).

## Rozhodnutí uživatele

- Plugin zůstává v `.make/vscode/` na `main`. Publikační skript bude taky na `main`, ne ve zvláštní větvi.
- Vydávání: **lokální skript + ruční upload na Microsoft**. Žádné CI.
- Nový projekt se **klonuje z GitLabu**, nepřibaluje se do VSIX.
- Obsah nového projektu: **jako `stm8newproject`** (`../stm8newproject.auto/stm8newproject`). Tedy větev a remote `upstream`, orphan `main`, česká školní šablona README, `docs/schema.png`, první commit. **Bez zakládání repa na GitLabu.**
- Upgrade starých projektů je **třetí část tohoto projektu**: plugin příkaz + tlačítko + `make upgrade`.
- Kořenový `Makefile` se **nepřepisuje**. Přepíše se `.make/` (tedy i `.make/Makefile-sdcc`). Do `Makefile` se změny dostanou tříčestným mergem. Konflikt nevadí: značky `<<<<<<<` zůstanou v souboru a make nepůjde, dokud je uživatel neopraví.
- Logo: **papírový dráček** na pouštění (ne drak chrlící oheň), s barevnými mašličkami na ocase. Navrhnu 3–4 varianty a ukážu je v prohlížeči. Uživatel vybere. **První vydání počká na logo.**
- Projekt s `Makefile` z `Makefile-sdcc-gas` nebo `Makefile-sdccrm`: upgrade **nabídne přechod na `Makefile-sdcc`**. Když ho uživatel odmítne, nezmění se nic.
- Existující `.vscode/launch.json`: upgrade ho **nahradí celý** verzí z toolchainu (jen `STM8 debug`).

## Rozhodnutí Clauda (uživatel je může zvrátit)

- Toolchain pro New Project i upgrade se stahuje vždy z `main` na URL toolchainu (výchozí GitLab, nastavení `stm8.toolchainUrl`, pro `make upgrade` proměnná `STM8_TOOLCHAIN_URL`). Remote `upstream` se nepoužívá, protože u řady projektů ukazuje jinam (viz fakta). Projekty z kopie Deroboard tak dostanou hlavní toolchain.
- Release pushne `main` i tag na `origin` i `github`. Odmítne vydat, když je lokální `main` za `origin/main`. Tím se srovná i GitHub zrcadlo.
- Plugin poskytne task `stm8: build` sám (task provider). Projekt pak nepotřebuje `.vscode/tasks.json`. Builder vyřeší, aby se task neobjevil dvakrát, když ho `tasks.json` definuje taky.
- Když nahrazovaný `launch.json` git nesleduje (ignorovaný `.vscode/`), upgrade ho nejdřív uloží jako `.vscode/launch.json.bak`. Jinak by šel ztratit.
- Jako výchozí verzi beru, že upgrade `tasks.json` ani `.vscode/.gitignore` nemění.

## Cíle, ne-cíle, anti-cíle

**Cíle**
- `make vscode-release` jedním příkazem otestuje, zabalí a nahraje plugin na Open VSX, vytvoří tag a nachystá upload na Microsoft.
- Uživatel bez toolchainu nainstaluje plugin z marketplace a do minuty má nový projekt otevřený v editoru.
- Starý projekt dostane nový `.make/` jedním příkazem. Jeho kód a úpravy `Makefile` zůstanou.
- Stránka pluginu na marketplace srozumitelně řekne cizímu člověku, co potřebuje nainstalovat.

**Ne-cíle**
- CI (GitHub Actions, GitLab CI), plně automatický upload na Microsoft.
- Přibalení toolchainu do VSIX, práce offline při zakládání projektu.
- Instalace SDCC, OpenOCD a `stm8-gdb` pluginem.
- Zakládání repa na GitLabu.
- Práce na podpoře Windows a macOS. Jen se zdokumentuje, co je ověřené.
- Úpravy `Makefile-sdcc-gas` a `Makefile-sdccrm`.

**Anti-cíle (selhání, i když „to funguje“)**
- Upgrade přepíše `Makefile` uživatele bez jeho souhlasu, nebo sáhne na `src/`, `inc/`, `lib/` či README.
- Token se objeví v repu, v logu nebo ve výpisu.
- Student potřebuje Node.js nebo npm.
- Skript nahraje verzi, které neprošly testy, nebo verzi, která už vyšla.
- Logo kopíruje logo STMicroelectronics (ochranná známka). Dráček je vlastní motiv.

## Části

### A. Logo

- Motiv: kosočtvercový papírový dráček se zkříženými špejlemi, provázkem a ocasem s barevnými mašličkami. Prostor pro variace: rozdělení dráčka na barevná pole, náznak čipu (nožičky, „8“), sklon ve větru.
- 3–4 varianty jako SVG, vedle sebe v prohlížeči (visual companion skillu brainstorming). Uživatel vybere a případně upraví.
- Výstupy: zdroj `.make/vscode/media/icon.svg`, `icon.png` 256×256 (`rsvg-convert`), banner pro README toolchainu (dráček + text). Umístění banneru určí builder. Kořen projektu se nesmí zaplevelit, protože se klonuje do každého projektu studenta.
- Logo musí být čitelné v 128 px a na světlém i tmavém pozadí.

### B. VSIX vhodný pro marketplace (`pack.py`, `package.json`)

- `package.json` dostane `icon`, `repository` (GitHub zrcadlo `spseol/STM8S-toolchain`), `homepage`, `bugs`, `keywords` (stm8, stm8s, sdcc, openocd, gdb, debugger, embedded, microcontroller, spl) a kategorie `Debuggers` + `Education`. `displayName` a `description` vyladit pro vyhledávání (builder).
- `activationEvents` dostanou navíc `workspaceContains:.make/Makefile-sdcc`, aby plugin poznal i staré projekty bez `.make/gdbinit`. Příkazy aktivují plugin samy (engine ≥ 1.74).
- `pack.py` doplní do manifestu tagy, odkazy a assety Icon, Details (README), Changelog a License. Do VSIX přibalí `LICENSE` z kořene repa, `CHANGELOG.md` a `media/`. `pack.py` zůstává bez Node. `make vscode` funguje dál.
- `README.md` pluginu se přepíše pro cizí lidi, anglicky:
  - co plugin umí,
  - požadavky: SDCC, make, python3, openocd, `stm8-gdb` ≥ 15 s DAP a kde ho vzít,
  - začátek přes `STM8: New Project`, potom `STM8: Update Toolchain`,
  - ověřené platformy (Linux),
  - odkaz na toolchain a jeho české README.
  
  Obrázky jen přes https. Sekce o `make vscode` zůstane pro uživatele toolchainu.
- Nový `CHANGELOG.md`.

### C. Vydání: `make vscode-release`

- Logika v `.make/vscode/release.py`, cíl v `.make/vscode.mk`.
- Kroky v tomto pořadí. Při chybě skript skončí a nic dalšího neudělá.
  1. Repo je čisté a aktuální větev je `main`.
  2. Verze z `package.json`. Tag `vscode-vX.Y.Z` nesmí existovat. Verzi zvyšuje uživatel ručně.
  3. `pytest .make/vscode` a `node --test .make/vscode/test/*.test.js`.
  4. `pack.py` vyrobí VSIX.
  5. `npx ovsx publish <vsix> -p <token>`. Token z `OVSX_PAT`, jinak ze souboru `~/.config/stm8-toolchain/ovsx-token`. Nikdy se nevypíše.
  6. Anotovaný tag `vscode-vX.Y.Z`, push `main` a tagu na `origin` (GitLab) i `github`. Krok 1 navíc ověří, že `main` není za `origin/main`.
  7. Vypíše cestu k VSIX a přes `xdg-open` otevře `https://marketplace.visualstudio.com/manage/publishers/spseol`. Uživatel tam VSIX nahraje ručně.
- `--dry-run` udělá kroky 1–4 bez nahrání a tagu (builder).
- Jednorázové ruční kroky uživatele popíše krátký `.make/vscode/RELEASING.md`: účet na Microsoftu a vydavatel `spseol`, Open VSX + Eclipse + Publisher Agreement + namespace + žádost o ověření, uložení tokenu. `RELEASING.md` nesmí do VSIX.

### D. Nový projekt: `STM8: New Project…` (`stm8.newProject`)

- Příkaz v paletě a tlačítko ve `viewsWelcome` Exploreru při prázdném okně (`workbenchState == empty`).
- Složka projektů: nastavení `stm8.projectsFolder`. Poprvé výběr složky, potom ji nabídne znovu s možností změny. Projekty musí být sourozenci, protože sdílejí `../SPLSPL` a `../SPL.tgz`.
- Jméno: InputBox. Bez lomítek. Když složka existuje, plugin odmítne.
- URL toolchainu: nastavení `stm8.toolchainUrl`, výchozí `https://gitlab.com/spseol/mit-no/STM8S-toolchain.git`. Testy podstrčí lokální `file://` repo.
- Kroky stejně jako `stm8newproject`:
  1. `git clone`
  2. `git branch -m upstream`
  3. `git remote rename origin upstream`
  4. `git checkout --orphan main`
  5. `make compile_commands.json`
  6. `README.md` → `README.origin.md`
  7. šablona README: text ze `stm8newproject`, nadpis je jméno s velkým prvním písmenem
  8. `docs/schema.png`
  9. `git add . && git commit -m "Initial commit"`
- `schema.png` se přibalí do VSIX (zdroj `https://chytrosti.marrek.cz/mit/dlazdice/urovne.png`). Šablona README bude ve VSIX jako soubor, ne v kódu (builder).
- Průběh v notifikaci. Chyby srozumitelně: chybí `git`, clone selhal (síť), `make` chybí (`compile_commands.json` se přeskočí s varováním), commit selhal kvůli chybějícímu `user.name`/`user.email` (soubory zůstanou, hláška řekne, jak git nastavit).
- Na konci otevře projekt (`vscode.openFolder`). Prázdné okno se použije, jinak se otevře nové (builder).
- Čip se při zakládání nevybírá. Vybere se po prvním buildu ve status baru, protože seznam čipů potřebuje SPL.

### E. Upgrade: `STM8: Update Toolchain` (`stm8.updateToolchain`) a `make upgrade`

- Logika v `.make/upgrade.py` v toolchainu. Starý projekt ten soubor ani cíl `make upgrade` nemá. Proto se nejdřív stáhne toolchain a spustí se skript z **nově staženého commitu**: `git show FETCH_HEAD:.make/upgrade.py | python3 - FETCH_HEAD`. Totéž dělá plugin i cíl `make upgrade`, takže kód je na jednom místě a vždy nejnovější.
- Fetch: `git fetch <URL toolchainu> main`, bez přidání remote.
- Kroky skriptu:
  1. Projekt musí být git repo. `.make/`, `Makefile` a sledovaný `.vscode/launch.json` nesmějí mít necommitnuté změny, jinak skript odmítne.
  2. Pozná variantu `Makefile`: porovná ho se starými `.make/Makefile-sdcc`, `-sdcc-gas` a `-sdccrm` a vezme tu s nejmenším rozdílem.
     - **sdcc:** uloží si starý `.make/Makefile-sdcc` jako základ mergu.
     - **sdcc-gas / sdccrm:** zeptá se, jestli přejít na `Makefile-sdcc`. Plugin dialogem, `make upgrade` dotazem v terminálu nebo volbou (builder). Při ne skončí a nezmění nic. Při ano bude nový `Makefile` = nový `.make/Makefile-sdcc` s `DEVICE_FLASH` převzatým ze starého `Makefile`. Hláška řekne, že starý `Makefile` vrátí `git diff` / `git checkout Makefile`.
  3. Nahradí sledované soubory v `.make/` obsahem z `FETCH_HEAD`, včetně smazání souborů, které nová verze nemá. Ignorované a nesledované soubory (`linker_output`, cgdb historie) zůstanou.
  4. Varianta sdcc: `git merge-file -L Makefile -L "old .make/Makefile-sdcc" -L "new .make/Makefile-sdcc" Makefile <starý> <nový>`. Čistý merge zapíše výsledek. Konflikt nechá značky v `Makefile`.
  5. `.vscode/launch.json` nahradí verzí z toolchainu. Když ho git nesleduje, nejdřív ho uloží jako `.vscode/launch.json.bak`. Chybějící `launch.json` doplní.
  6. Do `.gitignore` připíše chybějící řádky z nové verze, nic v něm nemaže.
  7. Nic necommitne. Vypíše přehled: kolik souborů v `.make/` se změnilo, výsledek mergu nebo přechodu `Makefile`, nahrazené a doplněné soubory.
- `src/`, `inc/`, `lib/`, README, `tasks.json` a ostatní `.vscode/` se nemění.
- Projekt bez gitu nebo bez `.make/Makefile-sdcc` skript odmítne s hláškou, co udělat ručně.
- Plugin:
  - Hláška „Old toolchain“ (`readProjectInfo`, `No rule to make target`) dostane tlačítko *Update Toolchain*.
  - Při aktivaci v projektu, který má starší nebo žádný `.make/vscode/package.json` než nainstalovaný plugin, nabídne *Update Toolchain* / *Not now* / *Don't ask again*. Poslední volba se uloží do `workspaceState`.
  - Po konfliktu otevře `Makefile` v editoru. VS Code u značek ukáže *Accept Current/Incoming*.
  - Když `Makefile` obsahuje `<<<<<<<`, preflight a `readProjectInfo` řeknou „Makefile has unresolved conflicts from Update Toolchain“ místo `missing separator`.
- `versionNotice` (projekt nese novější plugin než nainstalovaný) dostane znění vhodné i pro instalaci z marketplace: aktualizovat rozšíření, nebo `make vscode`.

## Omezení

- Rozhraní `make dap-info` (JSON) je smlouva mezi pluginem a toolchainem. Plugin z marketplace se aktualizuje sám a musí zvládnout staré projekty. Změny musí být zpětně kompatibilní.
- UI pluginu, nový kód a nové hlášky jsou anglicky. Výjimkou je česká šablona README nového projektu, protože to rozhodl uživatel.
- Plugin dál bez npm závislostí, čisté JS.
- Po úpravě `.make/Makefile-sdcc` zkopírovat soubor do `Makefile` (hlídá test).
- `DEFAULT_SIDE_EFFECTS` a řetězec `| openocd …` zůstávají hlídané existujícími testy.
- Práce na feature větvi, ne na `main`. Návrh a plán se commitují podle konvence repa a na konci se smažou.

## Nechává se na builderovi

- Přesné texty `displayName`/`description`, umístění banneru, rozdělení kódu do modulů v `src/`.
- Chování `--dry-run`, otevření nového projektu ve stejném nebo novém okně.
- Formát přehledu po upgradu.
- Jak testovat release skript bez sítě, třeba falešným `npx` a `git` remotes v temp adresáři.

## Postup po schválení

1. Založit větev (např. `vscode-marketplace`). Tento návrh uložit jako `.make/vscode/DESIGN.md` a commitnout.
2. `superpowers:writing-plans` → `.make/vscode/PLAN.md`.
3. Pořadí implementace: **E (upgrade)** → **D (new project)** → **B (VSIX)** → **A (logo, s uživatelem v prohlížeči)** → **C (release)**. Pak první vydání.

## Ověření

- `pytest .make/vscode` a `node --test .make/vscode/test/*.test.js` projdou. Testy pokrývají nové části a dělají se stejně jako stávající: falešný modul `vscode`, temp git repa.
- Upgrade: temp repo se strukturou starého projektu (orphan `main`, starý `.make/`, upravený `Makefile`) a lokální „toolchain“ remote.
  - Čistý merge přidá `-include .make/vscode.mk` a zachová `DEVICE_FLASH`.
  - Konflikt nechá značky.
  - `src/` je netknutý.
  - Odmítnutí při necommitnutých změnách.
  - Varianta gas/sdccrm: při ne se nezmění nic, při ano je `Makefile` = `Makefile-sdcc` s původním `DEVICE_FLASH`.
  - `launch.json` je nahrazený. Ignorovaný `launch.json` má `.bak`.
- Ručně na kopiích `../97-nucleo+daughterboard-demo` (sdcc) a `../44-neopixel` (sdcc-gas): Update Toolchain, potom F5 na Nucleo.
- New Project: test s `stm8.toolchainUrl` na `file://` kopii repa ověří větve, remote, README, `docs/schema.png` a commit. Ručně: VSCodium bez toolchainu, instalace VSIX, New Project, Build, F5.
- VSIX: `unzip -l` ukáže ikonu, LICENSE, CHANGELOG a README a žádné testy. Instalace do `code` i `codium` projde.
- Release: `make vscode-release --dry-run` (nebo `DRY_RUN=1`). První ostré vydání sleduje uživatel: Open VSX stránka, ruční upload na Microsoft, tag na obou remotes.
