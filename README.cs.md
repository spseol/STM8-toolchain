# Open-Source STM8S  toolchain (SDCC + Makefile)

**🇨🇿 Česká verze** | [🇬🇧 English](README.md)

Open-source build systém pro mikrokontroléry STM8 (testováno a používáno na STM8S).
Podporuje Linux, Windows i macOS.

**Zahrnuje** / **Podporuje** / **Umí**:

* *build* pomocí svobodného překladače [SDCC](http://sdcc.sourceforge.net/)
* *flash* přes [OpenOCD](https://openocd.org/) nebo [stm8flash](https://github.com/vdudouyt/stm8flash)
* *debug* pomocí GDB a `cgdb`
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
případně cestu k instalaci SDCC, 
[STVP](https://www.st.com/en/development-tools/stvp-stm8.html).

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
| `make flash` | nahraje ihx do chipu — [OpenOCD](https://openocd.org/) na Linuxu, [STVP](https://www.st.com/en/development-tools/stvp-stm8.html) na Windows |
| `make flash-elf` | nahraje elf do chipu přes OpenOCD |
| `make flash-ihex` | převede elf na ihex a nahraje přes OpenOCD |
| `make stm8flash` | záložní metoda nahrávání (používá [stm8flash](https://github.com/vdudouyt/stm8flash)) |
| `make stm8flash-unlock` | odstraní ochranu čtení přes stm8flash |
| `make openocd` | spustí OpenOCD pro ladění (běží dál, pak použij `make gdb`) |
| `make gdb` | spustí STM8-gdb v TUI módu |
| `make cgdb` | spustí cgdb se STM8-gdb |
| `make switch-device` | interaktivně přepne cílový čip v Makefile |
| `make lib` | interaktivně vybere drivery z `lib/` a přesune je do `src/` a `inc/` |
| `make docs-download` | stáhne datasheet/referenční manuál pro aktuální čip |
| `make tree` | zobrazí strom projektu |


## Závislosti

* [GNU Make](https://www.gnu.org/software/make/)
* [GNU Bash](https://www.gnu.org/software/bash/) -- ten se na Windows
  dá nainstalovat společně s [Git](https://git-scm.com/download/win)em.
* [SDCC](http://sdcc.sourceforge.net/)
  nebo [SDCC-gas](https://github.com/XaviDCR92/sdcc-gas)
* [STM8 binutils](https://stm8-binutils-gdb.sourceforge.io) (`stm8-gdb`, `stm8-ld`)
* [OpenOCD](https://openocd.org/) pro `flash` a `debug`
  nebo [STVP](https://www.st.com/en/development-tools/stvp-stm8.html)
  pro `flash` na Windows.
* ([stm8flash](https://github.com/vdudouyt/stm8flash) pro `flash2`)

### Na Windows

[`choco`](https://chocolatey.org/)` install git make vscode mingw`

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
