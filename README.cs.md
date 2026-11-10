<p align="center"><img src=".make/vscode/media/banner.png" alt="STM8S toolchain" width="480"></p>

# Open-Source STM8S  toolchain (SDCC + Makefile)

**🇨🇿 Česká verze** | [🇬🇧 English](README.md)

Open-source build systém pro mikrokontroléry STM8 (testováno a používáno na STM8S).
Podporuje Linux, Windows i macOS.

**Zahrnuje** / **Podporuje** / **Umí**:

* *build* pomocí svobodného překladače [SDCC](http://sdcc.sourceforge.net/)
* *flash* přes [OpenOCD](https://openocd.org/) nebo [stm8flash](https://github.com/vdudouyt/stm8flash)
* *debug* pomocí [STM8 GDB](https://gitlab.com/spseol/mit-no/stm8-binutils-gdb) (`stm8-gdb`) a `cgdb`, nebo ve VS Code / VSCodium
*  integraci SPL a podporu VS Code / clangd přes `compile_commands.json`.

## Jak to funguje?

* Jedná se vlasntně "jen" o startovací strom zdrojových kódů a `Makefile` (nejen) pro výuku
  Mikroprocesorové techniky
  s [STM8S](https://www.st.com/en/microcontrollers-microprocessors/stm8s-series.html).
* Strom je určen pro překladač [SDCC](http://sdcc.sourceforge.net/) (nebo
  [SDCC-gas](https://github.com/XaviDCR92/sdcc-gas)).
* Standardní knihovna pro práci s periferiemi
  [SPL](https://www.st.com/content/st_com/en/products/embedded-software/mcu-mpu-embedded-software/stm8-embedded-software/stsw-stm8069.html)
  *by se měla* (z licenčních důvodů) stáhnout zvlášť ze stránek výrobce a použít
  [patch](https://github.com/gicking/STM8-SPL_SDCC_patch). Ale myslím, že když napíšete
  `make spl` že to nebude hřích.
* Konkurence a inspirace:
  * <https://gitlab.com/wykys/stm8-tools>
  * <https://github.com/matejkrenek/stm8-toolchain>



## Použití

Nejprve je třeba v `Makefile` správně nastavit µprocesor a jeho frekvenci;
případně cestu k instalaci SDCC.

```make
#DEVICE_FLASH=stm8s103f3
DEVICE_FLASH=stm8s208rb

F_CPU=16000000

ifeq ($(OS),Windows_NT)
	CC_ROOT = "/c/Program Files/SDCC"
	STVP_ROOT = "/c/Program Files (x86)/STMicroelectronics/st_toolset/stvp"
else
	CC_ROOT = /usr
endif
```

... no a potom už jen bastlíte, programujete a voláte `make`.

| příkaz&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;||
|:---------- |:--------------------------- |
| `make spl` | stáhne a nachystá SPL knihovny |
| `make spl-renew` | znovu stáhne SPL knihovny |
| `make` | provede kompilaci (alias pro `make ihx`) |
| `make ihx` | zkompiluje do Intel HEX formátu |
| `make elf` | zkompiluje do ELF formátu (s debug informacemi) |
| `make all` | zkompiluje obojí (ihx i elf) |
| `make clean` | smaže build výstupy |
| `make clean-spl-objects` | smaže objektové soubory SPL (zkompilovaná knihovna zůstane) |
| `make clean-spl` | smaže zkompilovanou SPL knihovnu (vynutí plné přeložení SPL) |
| `make cleanall` | smaže vše včetně SPL knihoven |
| `make rebuild` | smaže vše a znovu zkompiluje (elf) |
| `make reflash` | smaže vše a znovu nahraje |
| `make flash` | nahraje ihx do chipu — [OpenOCD](https://openocd.org/); na Windows [STVP](https://www.st.com/en/development-tools/stvp-stm8.html), je-li nainstalované, jinak taky OpenOCD; když běží `make debug`, jen přeloží elf a do chipu ho nahraje debugger |
| `make flash-elf` | nahraje elf do chipu přes OpenOCD |
| `make flash-ihex` | převede elf na ihex a nahraje přes OpenOCD |
| `make stm8flash` | záložní metoda nahrávání (používá [stm8flash](https://github.com/vdudouyt/stm8flash)) |
| `make stm8flash-unlock` | odstraní ochranu čtení přes stm8flash |
| `make debug` | ladění jedním příkazem: přeloží elf, nahraje ho, zastaví na `main()` a otevře [cgdb](https://cgdb.github.io/) (bez cgdb gdb TUI), viz [Ladění](#ladění) |
| `make upgrade` | aktualizuje `.make/` a `Makefile` existujícího projektu na aktuální toolchain, viz [Aktualizace toolchainu](#aktualizace-toolchainu) |
| `make vscode` | nainstaluje rozšíření pro ladění do VS Code / VSCodium (jednou na počítač), viz [VS Code](#vs-code--vscodium) |
| `make cgdb` | totéž co `make debug` |
| `make gdb` | totéž, ale v STM8-gdb TUI módu |
| `make openocd` | spustí samostatný OpenOCD na portu 3333 (pro ruční připojení; `make debug` ho nepotřebuje) |
| `make miniterm` | spustí sériový terminál (pyserial-miniterm) na prvním `/dev/ttyUSB*`/`/dev/ttyACM*`, rychlost zjistí z projektu (`UARTx_Init()` nebo zápis do BRR registrů), ručně `BAUD=`, jinak 115200; alias `make pyserial`. Spolehlivě funguje jen v Linuxu (v macOS mají porty jiná jména, použij `pyserial-miniterm` ručně) |
| `make baudrate` | vypíše baud rate zjištěný z projektu a odkud ho vzal |
| `make switch-device` | interaktivně přepne cílový čip v Makefile |
| `make lib` | interaktivně vybere drivery z `lib/` a přesune je do `src/` a `inc/` |
| `make docs-download` | stáhne datasheet/referenční manuál pro aktuální čip |
| `make tree` | zobrazí strom projektu |


## Ladění

K ladění je potřeba `stm8-gdb`: [STM8 binutils-gdb](https://gitlab.com/spseol/mit-no/stm8-binutils-gdb), fork GNU binutils-gdb
s podporou STM8, verze 15 nebo novější, s podporou Pythonu a Debug Adapter Protocol (DAP; ten potřebuje VS Code).
Není součástí tohoto toolchainu, nainstaluj ho nejdřív. Repozitář má balíček pro Debian (APT) a postup sestavení
pro Linux i macOS (Apple Silicon). Pro macOS (Apple Silicon) je v jeho [vydáních](https://gitlab.com/spseol/mit-no/stm8-binutils-gdb/-/releases)
hotový balíček s přibaleným Pythonem (`v15.0.50-stm8.2` nebo novější; starší `v15.0.50-stm8.1` Python nemá).

`make debug` udělá všechno najednou: přeloží projekt s debug informacemi,
spustí OpenOCD (běží jen po dobu ladění), nahraje program do chipu a zastaví
na začátku `main()`. Druhý terminál ani ruční spouštění OpenOCD nejsou potřeba.
Po ukončení debuggeru (`quit`) program v chipu běží znovu od začátku.

V cgdb je nahoře okno se zdrojákem, dole okno gdb. `Esc` přepne do zdrojáku,
`i` zpět do gdb. Ve zdrojáku:

| klávesa | |
|:------- |:- |
| `mezerník` | breakpoint na řádku pod kurzorem |
| `F8` / `F10` | další řádek / vstoupit do funkce |
| `F7` / `F6` | dokončit funkci / pokračovat |
| `F5` | znovu od začátku `main()` |

V okně gdb fungují běžné příkazy (`n`, `s`, `c`, `finish`, `b 42`, `p x`,
`display x`, `Ctrl-C` zastaví běžící program) a navíc:

| příkaz | |
|:------ |:- |
| `flash` | přeloží (`make elf`), nahraje do chipu a zastaví na `main()` |
| `reset`, `r` | resetuje chip a nechá program doběhnout na `main()` |
| `vars` | vypíše lokální proměnné; po každém zastavení se vypisují samy (`vars off` / `vars on`) |
| `display x` | vypisuje proměnnou `x` po každém zastavení; seznam se ukládá do `.debug-display` a příští `make debug` ho obnoví (lokální proměnné jiné funkce až v té funkci) |

**Registry periferií (SFR):** gdb zná periferie ze `stm8s.h` pod stejnými
jmény jako v C, i s doplňováním tabulátorem. Funguje `p TIM4->CR1`,
`display GPIOB->ODR`, `p GPIOB` (celá periferie) a
`set var GPIOD->ODR |= 0x10`, a také bitové masky ze `stm8s.h`:
`p/t SPI->CR2 & SPI_CR2_SSM`. Registr se vypíše šestnáctkově, binárně
a se jmény nastavených bitů. Co se od minulého zastavení změnilo, je žlutě
i s původní hodnotou, třeba `0x21 0010 0001  (bylo 0x01)`. `display/x`
a `p/x` tohle vynechají, proto `display GPIOB->ODR`.

| příkaz | |
|:------ |:- |
| `sfr` | seznam periferií čipu |
| `sfr TIM4 [GPIOB …]` | registry periferie a nastavené bity; vynulovaný bit jako `-UIF` |
| `sfr TIM4.CR1` | jeden registr bit po bitu s popisem a hodnotou po resetu |

Čtení některých registrů maže příznaky (`UART1->DR` maže RXNE, …). `sfr TIM4`
je přeskočí, ale `p UART1` nebo `display UART1` je přečte.

**Nový kód za běhu ladění:** stačí upravit zdroják a v jiném terminálu
(nebo z editoru) spustit `make flash`. Debugger změnu pozná, program zastaví,
nahraje nový a zastaví na `main()`. Totéž udělá příkaz `flash` v gdb.

Konfigurace je v `.make/gdbinit`, `.make/stm8gdb.py` a `.make/stm8sfr.py`; log OpenOCD
v `build-*-elf/openocd.log`. Soubor `.debug-display` (jeden výraz na řádek)
jde upravit i ručně, třeba připravit k příkladu sledované proměnné.


### VS Code / VSCodium

Stejné ladění funguje ve VS Code (nebo VSCodium) s rozšířením z `.make/vscode/`:

1. Nainstaluj rozšíření (stačí jednou na počítač) z obchodu s rozšířeními tvého editoru: hledej
   *STM8 Toolchain Debugger* (vydavatel `spseol`) na [Open VSX](https://open-vsx.org/extension/spseol/stm8-toolchain)
   (VSCodium) nebo ve [Visual Studio Marketplace](https://marketplace.visualstudio.com/items?itemName=spseol.stm8-toolchain)
   (VS Code). Bez obchodu a pro vývoj `make vscode` rozšíření z `.make/vscode/` zabalí a nainstaluje
   (`code` nebo `codium` musí být v `PATH`).
2. Restartuj editor. Nový projekt vytvoř příkazem **`STM8: New Project…`** (Command Palette; naklonuje toolchain
   do nové složky, viz nastavení `stm8.projectsFolder`), nebo otevři složku existujícího projektu.
3. Stiskni `F5`. Projekt se přeloží, nahraje do chipu a program se zastaví na `main()`.

Breakpointy, krokování, proměnné i registry procesoru fungují jako obvykle. Panel **STM8 Peripherals**
v *Run and Debug* ukazuje periferie tvého čipu: zaškrtnutím bitu ho změníš, tužka zapíše celý registr,
ikona otevření ukáže jeden registr podrobně s popisy. Co se od minulého zastavení změnilo, je žlutě.
Strom nečte `UART1->DR` a podobné registry (čtení maže příznaky), dokud neklikneš na *Read*, a najetí
myší na ně ve zdrojáku je nepřečte; Watch, Debug Console a `p UART1` je přečtou, protože jsi o to požádal.
Jednotlivé bity takových registrů nejdou měnit (zápis by registr nejdřív přečetl), zapisuj celý registr. Ve stavovém řádku je *Build*, *Flash*, *Debug* a cílový čip
(kliknutím ho přepneš). Podrobnosti a řešení potíží:
[`.make/vscode/README.md`](.make/vscode/README.md).

Potřebuje [`stm8-gdb`](https://gitlab.com/spseol/mit-no/stm8-binutils-gdb) 15 nebo novější (není součástí rozšíření, nainstaluj ho nejdřív) a `openocd` v `PATH`,
stejně jako `make debug`. Rozšíření je testované na Linuxu. Na macOS (Apple Silicon) je ověřené s Nucleo-STM8S208RB:
`make`, `make flash`, `make cgdb` a ladění v rozšíření (`stm8-gdb` z hotového balíčku, OpenOCD a SDCC z Homebrew).
`stm8-gdb` a `openocd` musí být v `PATH` programu, který editor spouští: VS Code / VSCodium spouštěj z terminálu
(`code .`), ne z Docku, ten `PATH` tvého shellu nevidí.

#### Aktualizace toolchainu

Starší projekt má starší `.make/`. Ve VS Code spusť **`STM8: Update Toolchain`** (rozšíření ji samo nabídne,
když starší projekt pozná); bez editoru `make upgrade`, nebo, pokud ho tvůj projekt ještě nemá:

```bash
git fetch https://gitlab.com/spseol/mit-no/STM8S-toolchain.git main
python3 -I -c "$(git show FETCH_HEAD:.make/upgrade.py)" FETCH_HEAD
```

Na Windows `python3` není (ten ve `WindowsApps` je jen zástupce pro Microsoft Store), napiš `python`. Stejně tak na Linuxu nebo macOS, kde je jen jeden z nich.

Obnoví `.make/` a `.vscode/launch.json` a změny toolchainu slije do tvého `Makefile` (čip, frekvence a cesty
zůstanou; když se změny střetnou, zůstanou v `Makefile` značky konfliktu `<<<<<<<`, které vyřešíš ručně).
Nikdy nesahá na `src/`, `inc/` ani na tvé README a nic necommituje, takže výsledek zkontroluj přes `git diff`
a commitni sám. Vlastní změny v `.make/`, `Makefile` a `.vscode/launch.json` nejdřív commitni.


## Závislosti

* [GNU Make](https://www.gnu.org/software/make/)
* [GNU Bash](https://www.gnu.org/software/bash/) -- ten se na Windows
  dá nainstalovat společně s [Git](https://git-scm.com/download/win)em.
* [SDCC](http://sdcc.sourceforge.net/)
  nebo [SDCC-gas](https://github.com/XaviDCR92/sdcc-gas)
* [STM8 binutils-gdb](https://gitlab.com/spseol/mit-no/stm8-binutils-gdb) -- fork GNU binutils-gdb s podporou STM8
  (`stm8-gdb`, `stm8-ld`); pro ladění `stm8-gdb` 15 nebo novější s Pythonem a DAP
* [OpenOCD](https://openocd.org/) pro `flash` a `debug`
* [cgdb](https://cgdb.github.io/) pro `make debug` (bez něj se použije gdb TUI)
* [STVP](https://www.st.com/en/development-tools/stvp-stm8.html) -- jen Windows a nepovinné:
  je-li nainstalované, použije ho `make flash`, jinak OpenOCD.
* ([stm8flash](https://github.com/vdudouyt/stm8flash) pro `flash2`)

### Na Windows

Všechno potřebné nainstaluje jeden příkaz v PowerShellu (podrobnosti v
[README rozšíření pro VS Code](.make/vscode/README.md#installation)):

```powershell
irm https://gitlab.com/spseol/mit-no/STM8S-toolchain/-/raw/main/install/windows.ps1 | iex
```

## Tři Mejkfaily ....

K dispozici jsou celkem tři `Makefile` v adresáři `.make`. Je to proto, že kompilátor
`SDCC` nedokáže odstranit mrtvý kód. Existují asi tři řešení. To první je
nejoptimálnější, další dvě řešení jsem tu nechal pro strýčka příhodu. **By Default
je Makefile nastaven a první nejoptimálnější řešení `sdcc`.**
Pro více detailů se podívejte na <https://chytrosti.marrek.cz/stm8oss.html>.

```
$ ls .make/Makefile*
.make/Makefile-sdcc
.make/Makefile-sdcc-gas
.make/Makefile-sdccrm
```
