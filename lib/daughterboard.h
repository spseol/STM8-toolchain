/*
 * Soubor:  daughterboard.h
 * Datum:   21.11.2023 19:04
 * Autor:   Marek Nožka, nozka <@t> spseol <d.t> cz
 * Licence: GNU/GPL 
 * Úloha: 
 * Popis:   hlavičkový soubor pro daughterboard.c
 */

#ifndef __DAUGHTERBOARD_H__
#define __DAUGHTERBOARD_H__

/*  ----      LED      ----     */
#define DB_LED1_PORT GPIOG
#define DB_LED1_PIN GPIO_PIN_0
#define DB_LED2_PORT GPIOG
#define DB_LED2_PIN GPIO_PIN_1
#define DB_LED3_PORT GPIOG
#define DB_LED3_PIN GPIO_PIN_2
#define DB_LED4_PORT GPIOG
#define DB_LED4_PIN GPIO_PIN_3
#define DB_LED5_PORT GPIOG
#define DB_LED5_PIN GPIO_PIN_4
#define DB_LED6_PORT GPIOG
#define DB_LED6_PIN GPIO_PIN_5
#define DB_LED7_PORT GPIOG
#define DB_LED7_PIN GPIO_PIN_6
#define DB_LED8_PORT GPIOG
#define DB_LED8_PIN GPIO_PIN_7

/*  ----      Driver      ----     */
#define DB_SDI_PORT GPIOC
#define DB_SDI_PIN GPIO_PIN_6
#define DB_CLK_PORT GPIOC
#define DB_CLK_PIN GPIO_PIN_5
#define DB_OE_PORT GPIOD
#define DB_OE_PIN GPIO_PIN_0
#define DB_LATCH_PORT GPIOC
#define DB_LATCH_PIN GPIO_PIN_4

#define DB_S1_PORT GPIOB
#define DB_S1_PIN GPIO_PIN_2
#define DB_S2_PORT GPIOB
#define DB_S2_PIN GPIO_PIN_3
#define DB_S3_PORT GPIOB
#define DB_S3_PIN GPIO_PIN_4

// RGB LED
#define DB_PWM_B_PORT GPIOD
#define DB_PWM_B_PIN  GPIO_PIN_4
#define DB_PWM_G_PORT GPIOD
#define DB_PWM_G_PIN  GPIO_PIN_3
#define DB_PWM_R_PORT GPIOA
#define DB_PWM_R_PIN  GPIO_PIN_3

// ADC
#define DB_VREF_PORT GPIOF
#define DB_VREF_PIN GPIO_PIN_7
#define DB_VTEMP_PORT GIPOF
#define DB_VTEMP_PIN GPIO_PIN_6
#define DB_CHANNEL_VREF  ADC2_CHANNEL_15      // 2496 mV
#define DB_CHANNEL_VTEMP ADC2_CHANNEL_14


#endif

