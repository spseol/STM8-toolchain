#ifndef DELAY_H
#define DELAY_H

#include <stdint.h>

#ifndef F_CPU
#error F_CPU is not defined! Nastav F_CPU v Makefile.
#endif /* F_CPU */

// Aktivní čekání (busy wait) odvozené od F_CPU. Přerušení zpoždění natahuje.
// Přesnost: viz tabulka změřených cyklů v src/delay.c.
void delay_us(uint16_t us);     // 0 = hned návrat
void delay_ms(uint16_t ms);     // 0 = hned návrat

#endif /* DELAY_H */
