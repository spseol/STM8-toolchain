#include "stm8s.h"

#define SWSPI_DIN_PORT  GPIOE
#define SWSPI_DIN_PIN   GPIO_PIN_0
#define SWSPI_CS_PORT   GPIOD
#define SWSPI_CS_PIN    GPIO_PIN_5
#define SWSPI_CLK_PORT  GPIOD
#define SWSPI_CLK_PIN   GPIO_PIN_6
/*----------------------------------------------------*/

#define SWSPI_NOOP          0   // No operation
#define SWSPI_DIGIT0        1   // zápis hodnoty na 1. cifru
#define SWSPI_DIGIT1        2   // zápis hodnoty na 1. cifru
#define SWSPI_DIGIT2        3   // zápis hodnoty na 1. cifru
#define SWSPI_DIGIT3        4   // zápis hodnoty na 1. cifru
#define SWSPI_DIGIT4        5   // zápis hodnoty na 1. cifru
#define SWSPI_DIGIT5        6   // zápis hodnoty na 1. cifru
#define SWSPI_DIGIT6        7   // zápis hodnoty na 1. cifru
#define SWSPI_DIGIT7        8   // zápis hodnoty na 1. cifru
#define SWSPI_DECODE_MODE   9   // Aktivace/Deaktivace znakové sady (my volíme vždy hodnotu DECODE_ALL)
#define SWSPI_INTENSITY     10  // Nastavení jasu - argument je číslo 0 až 15 (větší číslo větší jas)
#define SWSPI_SCAN_LIMIT    11  // Volba počtu cifer (velikosti displeje) - argument je číslo 0 až 7 (my dáváme vždy 7)
#define SWSPI_SHUTDOWN      12  // Aktivace/Deaktivace displeje (ON / OFF)
#define SWSPI_DISPLAY_TEST  15  // Aktivace/Deaktivace "testu" (rozsvítí všechny segmenty)
// makra argumentů
// argumenty pro SHUTDOWN
#define SWSPI_DISPLAY_ON        1   // zapne displej
#define SWSPI_DISPLAY_OFF       0   // vypne displej
// argumenty pro DISPLAY_TEST
#define SWSPI_DISPLAY_TEST_ON   1   // zapne test displeje
#define SWSPI_DISPLAY_TEST_OFF  0   // vypne test displeje
// argumenty pro DECODE_MOD
#define SWSPI_DECODE_ALL        0b11111111 // (lepší zápis 0xff) zapíná znakovou sadu pro všechny cifry
#define SWSPI_DECODE_NONE       0 // vypíná znakovou sadu pro všechny cifry


void swspi_init(void);
void swspi_tx16(uint16_t data);
void swspi_tx2x8(uint8_t address, uint8_t data);
