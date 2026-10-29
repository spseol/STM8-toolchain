#ifndef DELAY_H
#define DELAY_H

#include <stdint.h>

#ifndef F_CPU
#error F_CPU is not defined! Set F_CPU in the Makefile.
#endif /* F_CPU */

// Busy-wait delays derived from F_CPU. Interrupts make the delay longer.
// Accuracy: see the table of measured cycles in src/delay.c.
void delay_us(uint16_t us);     // 0 = return immediately
void delay_ms(uint16_t ms);     // 0 = return immediately

#endif /* DELAY_H */
