#include "swspi.h"

#define HIGH(BAGR) GPIO_WriteHigh(SWSPI_##BAGR##_PORT, SWSPI_##BAGR##_PIN)
#define LOW(BAGR)  GPIO_WriteLow(SWSPI_##BAGR##_PORT, SWSPI_##BAGR##_PIN)

uint8_t max7219digits[10] = {
    0b01111110,  // 0
    0b00110000,  // 1
    0b01101101,  // 2
    0b01111001,  // 3
    0b00110011,  // 4
    0b01011011,  // 5
    0b01011111,  // 6
    0b01110000,  // 7
    0b01111111,  // 8
    0b01111011,  // 9
};

void swspi_init(void){
    GPIO_Init(SWSPI_CS_PORT,SWSPI_CS_PIN,GPIO_MODE_OUT_PP_HIGH_FAST);
    GPIO_Init(SWSPI_CLK_PORT,SWSPI_CLK_PIN,GPIO_MODE_OUT_PP_LOW_FAST);
    GPIO_Init(SWSPI_DIN_PORT,SWSPI_DIN_PIN,GPIO_MODE_OUT_PP_LOW_FAST);
}

// Odesílá 16bit dat MSB first, SPI mode, sama provádí manipulaci s CS
void swspi_tx16(uint16_t data)
{
    uint16_t maska = 1 << 15;

    HIGH(CS);
    while (maska) {
        if (maska & data) {
            HIGH(DIN);
        } else {
            LOW(DIN);
        }
        HIGH(CLK); 
        maska = maska >> 1;
        LOW(CLK);
    }
    HIGH(CS);
}


void swspi_tx2x8(uint8_t address, uint8_t data)
{
    uint16_t mask ;

    LOW(CS);                    // začánám visílat

    // adresa
    mask = 1 << 7;
    while (mask) {
        LOW(CLK);
        if (address & mask) {
            HIGH(DIN);
        } else {
            LOW(DIN);
        }
        HIGH(CLK);
        mask >>= 1;
        LOW(CLK);
    }

    // data 
    mask = 1 << 7;
    while (mask) {
        LOW(CLK);
        if (data & mask) {
            HIGH(DIN);
        } else {
            LOW(DIN);
        }
        HIGH(CLK);
        mask >>= 1;
        LOW(CLK);
    }

    HIGH(CS);                    // končím vysílán
}
