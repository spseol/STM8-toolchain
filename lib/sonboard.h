/*
 * Soubor:  sonboard.h
 */

#ifndef __SONBOARD_H__
#define __SONBOARD_H__

/*  ----      LED      ----     */
// Zapojení LED: OD - Open Drain
#define SB_LED1_PORT GPIOB
#define SB_LED1_PIN GPIO_PIN_7
#define SB_LED2_PORT GPIOB
#define SB_LED2_PIN GPIO_PIN_6
#define SB_LED3_PORT GPIOB
#define SB_LED3_PIN GPIO_PIN_5
#define SB_LED4_PORT GPIOB
#define SB_LED4_PIN GPIO_PIN_4
#define SB_LED5_PORT GPIOB
#define SB_LED5_PIN GPIO_PIN_3
#define SB_LED6_PORT GPIOB
#define SB_LED6_PIN GPIO_PIN_2
#define SB_LED7_PORT GPIOB
#define SB_LED7_PIN GPIO_PIN_1
#define SB_LED8_PORT GPIOB
#define SB_LED8_PIN GPIO_PIN_0

/*  ----      BTN      ----     */
// Zapojení BTN:
// S1, S2 -> FL - Float
// S3, S4 -> PU - Pull Up
#define SB_S1_PORT GPIOD
#define SB_S1_PIN GPIO_PIN_6
#define SB_S2_PORT GPIOD
#define SB_S2_PIN GPIO_PIN_5
#define SB_S3_PORT GPIOC
#define SB_S3_PIN GPIO_PIN_1
#define SB_S4_PORT GPIOC
#define SB_S4_PIN GPIO_PIN_2


#endif