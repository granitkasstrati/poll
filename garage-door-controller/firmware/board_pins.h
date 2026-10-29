/*
 * gdc1 rev A - board pin map (ESP32-S3-WROOM-1-N8R2)
 * Mirrors hardware/gen/design.py; if you change one, change the other.
 */
#pragma once

#include "driver/gpio.h"
#include "hal/adc_types.h"

/* --- door position inputs (opto-isolated, ACTIVE LOW: reed closed = 0) ------ */
#define PIN_IN_CLOSED       GPIO_NUM_16     /* reed at fully-closed position */
#define PIN_IN_OPEN         GPIO_NUM_17     /* reed at fully-open position */
#define PIN_IN_AUX          GPIO_NUM_18     /* spare: pedestrian door, wall-button sense, ... */

/* --- outputs ---------------------------------------------------------------- */
/* RELAY_CMD is AC-coupled (C20/R23, tau ~0.7-1 s): drive a 300-500 ms HIGH pulse,
 * then LOW. Holding it HIGH does NOT hold the relay: it drops out after <=1.6 s. */
#define PIN_RELAY_CMD       GPIO_NUM_7
#define PIN_BUZZER          GPIO_NUM_10     /* self-drive buzzer via AO3400A, active high */
#define PIN_WARN_OUT        GPIO_NUM_15     /* J4 low-side switch (VIN), active high, <=300 mA */
#define PIN_WARN_LED        GPIO_NUM_12     /* red LED, active high */
#define PIN_RGB_DIN         GPIO_NUM_13     /* WS2812B data (RMT), VDD ~4.3 V */

/* --- user interface ---------------------------------------------------------- */
#define PIN_USER_BTN        GPIO_NUM_14     /* active low, 10k pull-up */
#define PIN_BOOT_BTN        GPIO_NUM_0      /* strap; usable as an input after boot */

/* --- I2C: BME280 (0x76) + Qwiic J7 (e.g. VL53L1X 0x29) ------------------------- */
#define PIN_I2C_SDA         GPIO_NUM_8
#define PIN_I2C_SCL         GPIO_NUM_9
#define BME280_I2C_ADDR     0x76

/* --- analog (ADC1 only: ADC2 is unusable while Wi-Fi runs) -------------------- */
#define PIN_VIN_SENSE       GPIO_NUM_4      /* ADC1_CH3, VIN / 15.7 (R7 100k, R8 6.8k) */
#define ADC_CH_VIN_SENSE    ADC_CHANNEL_3
#define VIN_SENSE_RATIO     ((100.0f + 6.8f) / 6.8f)
#define PIN_EXP_ADC         GPIO_NUM_2      /* ADC1_CH1 on J6 pin 2 (CT clamp burden) */
#define ADC_CH_EXP          ADC_CHANNEL_1

/* --- expansion header J6 --------------------------------------------------- */
#define PIN_EXP_IO38        GPIO_NUM_38
#define PIN_EXP_IO39        GPIO_NUM_39
#define PIN_EXP_IO40        GPIO_NUM_40     /* suggested UART1 TX */
#define PIN_EXP_IO41        GPIO_NUM_41     /* suggested UART1 RX */

/* USB D-/D+ = GPIO19/GPIO20 (USB-Serial-JTAG), UART0 = GPIO43/44 on J5 (ESP-Prog). */
