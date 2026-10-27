#ifndef MILIS_H
#define MILIS_H

#define MILIS_32BIT_TIME 1

//#include "stm8s.h"
#include "stm8s_conf.h"

// configure PRESCALER and PERIOD according to your clock, to setup 1ms time base
#if F_CPU==16000000
// varianta pro 16MHz
#define PRESCALER TIM4_PRESCALER_128
#define PERIOD (125-1)

#elif F_CPU==2000000
// varianta pro 2MHz
#define _PRESCALER TIM4_PRESCALER_16
#define _PERIOD (125-1)

#else
#warning "milis timer parameters not defined for this clock !"

#endif /* F_CPU */

#if MILIS_32BIT_TIME!=0
#define MILIS_PROTOTYPE uint32_t milis(void)
#else
#define MILIS_PROTOTYPE uint16_t milis(void)
#endif /* MILIS_32BIT_TIME */

void init_milis(void);
MILIS_PROTOTYPE;

#endif /* MILIS_H */
