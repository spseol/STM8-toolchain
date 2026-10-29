// Knihovna pro aktivní čekání (busy wait) v SDCC, odvozená od F_CPU.
// Zpoždění je spočítané při překladu, za běhu se nepočítá nic. Smyčky jsou
// v assembleru, takže nezávisí na CFLAGS. Přerušení zpoždění natahují.
//
// Naměřeno na STM8S208RB (Nucleo), HSI 16 MHz, TIM2 s taktem F_CPU. Měří se
// celé volání (nahrání parametru, call, ret) mínus dvě čtení čítače:
//
//   delay_us(n)   n=0: 15 cyklů, n=1: 17 cyklů (minimum, 1,06 us)
//                 n>=2: n * 16 cyklů, chyba -1 cyklus (62 ns), n=4000 v pořádku
//   delay_ms(n)   n * 16000 + 17 cyklů, chyba <= 1 cyklus na ms (0,006 %)
//                 delay_ms(10/100/500/1000) = 625/6250/31248/62497 tiků po
//                 256 cyklech (ideál 625/6250/31250/62500)
//   2 MHz (HSIDIV8): delay_ms(n) = n * 2000 + 17 cyklů, chyba -1 cyklus na ms
//
// Chyba +-1 cyklus závisí na zarovnání kódu ve flash (čtení po 4 bajtech), při
// změně kódu před funkcemi se může přehodit.

#include "delay.h"

// Počet cyklů CPU na 1 µs. Do assembleru (sdas) jdou jen malá čísla, protože
// sdas počítá výrazy 16bitově (F_CPU samotné by přetekl).
#if (F_CPU / 1000000) == 1
#define CYC_US 1
#elif (F_CPU / 1000000) == 2
#define CYC_US 2
#elif (F_CPU / 1000000) == 3
#define CYC_US 3
#elif (F_CPU / 1000000) == 4
#define CYC_US 4
#elif (F_CPU / 1000000) == 5
#define CYC_US 5
#elif (F_CPU / 1000000) == 6
#define CYC_US 6
#elif (F_CPU / 1000000) == 7
#define CYC_US 7
#elif (F_CPU / 1000000) == 8
#define CYC_US 8
#elif (F_CPU / 1000000) == 9
#define CYC_US 9
#elif (F_CPU / 1000000) == 10
#define CYC_US 10
#elif (F_CPU / 1000000) == 11
#define CYC_US 11
#elif (F_CPU / 1000000) == 12
#define CYC_US 12
#elif (F_CPU / 1000000) == 13
#define CYC_US 13
#elif (F_CPU / 1000000) == 14
#define CYC_US 14
#elif (F_CPU / 1000000) == 15
#define CYC_US 15
#elif (F_CPU / 1000000) == 16
#define CYC_US 16
#elif (F_CPU / 1000000) == 17
#define CYC_US 17
#elif (F_CPU / 1000000) == 18
#define CYC_US 18
#elif (F_CPU / 1000000) == 19
#define CYC_US 19
#elif (F_CPU / 1000000) == 20
#define CYC_US 20
#elif (F_CPU / 1000000) == 21
#define CYC_US 21
#elif (F_CPU / 1000000) == 22
#define CYC_US 22
#elif (F_CPU / 1000000) == 23
#define CYC_US 23
#elif (F_CPU / 1000000) == 24
#define CYC_US 24
#else
#error "delay: F_CPU musi byt 1 az 24 MHz (cele MHz)"
#endif

#define STR_(x) #x
#define STR(x) STR_(x)
// N instrukcí nop (1 cyklus), N se vyhodnotí při překladu
#define NOPS(n) ".rept " STR(n) "\n nop\n .endm\n"

// delay_us(n): celková doba volání (včetně nahrání parametru, call a ret)
// je n * CYC_US cyklů pro n >= 2. První průchod smyčky je rozbalený, aby se
// režie volání (~16 cyklů) odečetla od čekání:
//   tnzw x; jreq 8$      n == 0: hned ret
//   decw x; jreq 7$      n == 1: doplnění nopy a ret
//   [nop * US_P0]        doladění režie
//   1$: [nop * (CYC_US - 3)] decw x (1c) jrne (2c)   -> jeden průchod = CYC_US
// Na 16 MHz je minimum delay_us(1) = 18 cyklů (1,125 us), delay_us(0) = 14.
#if CYC_US < 3
// Pod 3 MHz nejde smyčka o délce 1 us (nejkratší průchod má 3 cykly). Jeden
// průchod trvá 3 / CYC_US us, tedy delay_us(n) čeká n * 3 / CYC_US us
// (1,5 us na 2 MHz). Je to hrubé zpoždění, volání samo stojí desítky cyklů.
#warning "delay: F_CPU < 3 MHz, delay_us je hrube (krok 3 cykly)"
void delay_us(uint16_t us) __naked
{
    (void)us;   // parametr je v registru X
    __asm__(
        "tnzw x\n"
        "jreq 9$\n"
        "1$:\n"
        "decw x\n"
        "jrne 1$\n"
        "9$:\n"
        "ret\n");
}
#else
#if CYC_US > 16
#define US_P0 (CYC_US - 16)
#else
#define US_P0 0
#endif
#if CYC_US > 18
#define US_P1 (CYC_US - 18)
#else
#define US_P1 0
#endif

void delay_us(uint16_t us) __naked
{
    (void)us;   // parametr je v registru X
    __asm__(
        "tnzw x\n"
        "jreq 8$\n"
        "decw x\n"
        "jreq 7$\n"
        NOPS(US_P0)
        "1$:\n"
        NOPS(CYC_US - 3)
        "decw x\n"
        "jrne 1$\n"
        "ret\n"
        "7$:\n"
        NOPS(US_P1)
        "8$:\n"
        "ret\n");
}
#endif /* CYC_US < 3 */

// delay_ms: vnější smyčka po 1 ms, vnitřní smyčka (P cyklů na průchod)
//   ldw y,#N (2c)
//   [nop nop] decw y (1c) jrne (2c)        -> P = 5c, celkem N*P - 1
//   [nop * R]                               -> doplnění do celé ms
//   decw x (1c) jrne (2c)
// Jedna milisekunda = 1000 * CYC_US cyklů. Ladí se MS_ADJ.
#define MS_ADJ 0
#define MS_CYC (1000 * CYC_US - 5 - MS_ADJ)
#define MS_P 5
#define MS_N (MS_CYC / MS_P)
#define MS_R (MS_CYC - MS_N * MS_P)    // sdas nezná modulo

void delay_ms(uint16_t ms) __naked
{
    (void)ms;   // parametr je v registru X
    __asm__(
        "tnzw x\n"
        "jreq 9$\n"
        "pushw y\n"
        "1$:\n"
        "ldw y, #" STR(MS_N) "\n"
        "2$:\n"
        "nop\n"
        "nop\n"
        "decw y\n"
        "jrne 2$\n"
        NOPS(MS_R)
        "decw x\n"
        "jrne 1$\n"
        "popw y\n"
        "9$:\n"
        "ret\n");
}
