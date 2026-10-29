// Busy-wait delay library for SDCC, derived from F_CPU.
// The delay is computed at compile time, nothing is computed at run time. The
// loops are written in assembler, so they do not depend on CFLAGS. Interrupts
// make the delay longer.
//
// Measured on STM8S208RB (Nucleo), HSI 16 MHz, TIM2 clocked at F_CPU. The whole
// call (parameter load, call, ret) is measured minus two counter reads:
//
//   delay_us(n)   n=0: 15 cycles, n=1: 17 cycles (minimum, 1.06 us)
//                 n>=2: n * 16 cycles, error -1 cycle (62 ns), n=4000 is fine
//   delay_ms(n)   n * 16000 + 17 cycles, error <= 1 cycle per ms (0.006 %)
//                 delay_ms(10/100/500/1000) = 625/6250/31248/62497 ticks of
//                 256 cycles (ideal 625/6250/31250/62500)
//   2 MHz (HSIDIV8): delay_ms(n) = n * 2000 + 17 cycles, error -1 cycle per ms
//
// The +-1 cycle error depends on the code alignment in flash (read in 4-byte
// words) and can flip when the code in front of the functions changes.

#include "delay.h"

// F_CPU that is not a whole number of MHz is rounded to the nearest MHz.
#if (F_CPU % 1000000) != 0
#warning "delay: F_CPU is not a whole number of MHz, delays will be slightly inaccurate"
#endif

// CPU cycles per 1 us. Only small numbers go into the assembler, because sdas
// evaluates expressions in 16 bits (F_CPU itself would overflow).
#if ((F_CPU + 500000) / 1000000) == 1
#define CYC_US 1
#elif ((F_CPU + 500000) / 1000000) == 2
#define CYC_US 2
#elif ((F_CPU + 500000) / 1000000) == 3
#define CYC_US 3
#elif ((F_CPU + 500000) / 1000000) == 4
#define CYC_US 4
#elif ((F_CPU + 500000) / 1000000) == 5
#define CYC_US 5
#elif ((F_CPU + 500000) / 1000000) == 6
#define CYC_US 6
#elif ((F_CPU + 500000) / 1000000) == 7
#define CYC_US 7
#elif ((F_CPU + 500000) / 1000000) == 8
#define CYC_US 8
#elif ((F_CPU + 500000) / 1000000) == 9
#define CYC_US 9
#elif ((F_CPU + 500000) / 1000000) == 10
#define CYC_US 10
#elif ((F_CPU + 500000) / 1000000) == 11
#define CYC_US 11
#elif ((F_CPU + 500000) / 1000000) == 12
#define CYC_US 12
#elif ((F_CPU + 500000) / 1000000) == 13
#define CYC_US 13
#elif ((F_CPU + 500000) / 1000000) == 14
#define CYC_US 14
#elif ((F_CPU + 500000) / 1000000) == 15
#define CYC_US 15
#elif ((F_CPU + 500000) / 1000000) == 16
#define CYC_US 16
#elif ((F_CPU + 500000) / 1000000) == 17
#define CYC_US 17
#elif ((F_CPU + 500000) / 1000000) == 18
#define CYC_US 18
#elif ((F_CPU + 500000) / 1000000) == 19
#define CYC_US 19
#elif ((F_CPU + 500000) / 1000000) == 20
#define CYC_US 20
#elif ((F_CPU + 500000) / 1000000) == 21
#define CYC_US 21
#elif ((F_CPU + 500000) / 1000000) == 22
#define CYC_US 22
#elif ((F_CPU + 500000) / 1000000) == 23
#define CYC_US 23
#elif ((F_CPU + 500000) / 1000000) == 24
#define CYC_US 24
#else
#error "delay: F_CPU must be 0.5 to 24.5 MHz"
#endif

#define STR_(x) #x
#define STR(x) STR_(x)
// N nop instructions (1 cycle each), N is evaluated at compile time
#define NOPS(n) ".rept " STR(n) "\n nop\n .endm\n"

// delay_us(n): the total duration of the call (including parameter load, call
// and ret) is n * CYC_US cycles for n >= 2. The first pass of the loop is
// unrolled so that the call overhead (~16 cycles) is subtracted from the wait:
//   tnzw x; jreq 8$      n == 0: ret at once
//   decw x; jreq 7$      n == 1: pad with nops and ret
//   [nop * US_P0]        overhead fine-tuning
//   1$: [nop * (CYC_US - 3)] decw x (1c) jrne (2c)   -> one pass = CYC_US
// At 16 MHz the minimum is delay_us(1) = 17 cycles (1.06 us), delay_us(0) = 15.
#if CYC_US < 3
// Below 3 MHz a loop of 1 us is impossible (the shortest pass takes 3 cycles).
// One pass takes 3 / CYC_US us, so delay_us(n) waits n * 3 / CYC_US us
// (1.5 us at 2 MHz). The delay is coarse, the call itself costs tens of cycles.
#warning "delay: F_CPU < 3 MHz, delay_us is coarse (3-cycle step)"
void delay_us(uint16_t us) __naked
{
    (void)us;   // the parameter is in register X
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
    (void)us;   // the parameter is in register X
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

// delay_ms: outer loop per 1 ms, inner loop (P cycles per pass)
//   ldw y,#N (2c)
//   [nop nop] decw y (1c) jrne (2c)        -> P = 5c, N*P - 1 in total
//   [nop * R]                               -> pad to a whole ms
//   decw x (1c) jrne (2c)
// One millisecond = 1000 * CYC_US cycles. MS_ADJ is the tuning knob.
#define MS_ADJ 0
#define MS_CYC (1000 * CYC_US - 5 - MS_ADJ)
#define MS_P 5
#define MS_N (MS_CYC / MS_P)
#define MS_R (MS_CYC - MS_N * MS_P)    // sdas has no modulo

void delay_ms(uint16_t ms) __naked
{
    (void)ms;   // the parameter is in register X
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
