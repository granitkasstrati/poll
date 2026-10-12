/*
 * inv1200 - ESP32 controller for the 230 VAC -> 120 VAC / 1200 W converter
 *
 * ESP-IDF >= 5.2.  STATUS: UNTESTED SKELETON. It has not been compiled against
 * hardware. Read docs/DESIGN.md "Bring-up" before running it on a powered board.
 *
 * What it does
 *   - startup sequencing: NTC precharge -> relay -> PFC enable -> inverter soft start
 *   - unipolar SPWM on MCPWM0 (IO25 = leg A, IO26 = leg B), 40 kHz carrier, 50 Hz sine
 *   - IO13 (INV_SD_N read-back) is an MCPWM fault: the LM393 trip or the MCU itself
 *     pulling INV_SD_N low force both generators low in hardware (one-shot brake)
 *   - slow RMS regulation of the output, bus/temperature/current supervision
 *
 * The ESP32 GND is the DC-bus negative, i.e. MAINS POTENTIAL. Only J3 is isolated.
 */
#include <math.h>
#include <stdbool.h>
#include <stdint.h>

#include "driver/gpio.h"
#include "driver/mcpwm_prelude.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_attr.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "inv1200";

/* ---- pins (see hardware/gen/design.py, U9 map) ---------------------------- */
#define PIN_PWM_A     25
#define PIN_PWM_B     26
#define PIN_INV_EN    27   /* high = allow bridge (through R36 1k)            */
#define PIN_INV_SD_N  13   /* read-back, MCPWM fault input (active low)       */
#define PIN_RELAY_EN  32   /* high = bypass NTC                               */
#define PIN_PFC_DIS   33   /* high/floating = PFC off (Q3 pulls VSENSE low)   */
#define PIN_FAN       4
#define PIN_LED       23
/* ADC1: IO36 VBUS, IO39 VOUT, IO34 IOUT, IO35 heatsink NTC */
#define CH_VBUS  ADC_CHANNEL_0
#define CH_VOUT  ADC_CHANNEL_3
#define CH_IOUT  ADC_CHANNEL_6
#define CH_TEMP  ADC_CHANNEL_7

/* ---- power stage constants ------------------------------------------------ */
#define F_SW          40000          /* carrier; output ripple at 2*F_SW (unipolar) */
#define F_OUT         50.0f
#define PWM_RES_HZ    80000000       /* 80 MHz MCPWM tick                          */
#define PERIOD_TICKS  (PWM_RES_HZ / F_SW)   /* up-down: peak = PERIOD_TICKS/2      */
#define PEAK          (PERIOD_TICKS / 2)
#define LUT_N         800            /* samples per output cycle = F_SW / F_OUT    */
#define VOUT_RMS_SET  120.0f

/* sense scaling (calibrate!) */
#define K_VBUS   (4022.0f / 22.0f)          /* R21..R24 4M / R25 22k              */
#define K_VOUT   (4.0e6f / 28.0e3f)         /* diff amp gain 1/142.9, about VREF  */
#define VREF_V   1.65f
#define K_IOUT   (1.0f / (0.1f * 2.0f / 3.0f)) /* ACS724 100 mV/A, 2/3 divider -> A/V */
#define IOUT_ZERO (2.5f * 2.0f / 3.0f)

static mcpwm_cmpr_handle_t s_cmp_a, s_cmp_b;
static mcpwm_timer_handle_t s_timer;
static mcpwm_oper_handle_t s_ops[2];
static int16_t s_lut[LUT_N];                 /* sin table, Q15                    */
static volatile uint32_t s_idx;
static volatile int32_t s_m_q15;             /* modulation index, Q15 (0..~0.9)   */
static adc_oneshot_unit_handle_t s_adc;

/* Called at every counter-empty event (40 kHz). Keep it short and in IRAM. */
static bool IRAM_ATTR on_tez(mcpwm_timer_handle_t t, const mcpwm_timer_event_data_t *e, void *ctx)
{
    uint32_t i = s_idx + 1;
    if (i >= LUT_N) i = 0;
    s_idx = i;
    /* duty_A = 0.5 + m/2*sin, duty_B = 0.5 - m/2*sin  (unipolar, common carrier) */
    int32_t d = (int32_t)(((int64_t)s_m_q15 * s_lut[i]) >> 15);      /* Q15 m*sin  */
    int32_t ca = PEAK / 2 + (int32_t)(((int64_t)d * (PEAK / 2)) >> 15);
    int32_t cb = PEAK - ca;
    if (ca < 2) ca = 2; if (ca > PEAK - 2) ca = PEAK - 2;
    if (cb < 2) cb = 2; if (cb > PEAK - 2) cb = PEAK - 2;
    /* generator: HIGH while counter < compare  -> duty = cmp / PEAK              */
    mcpwm_comparator_set_compare_value(s_cmp_a, ca);
    mcpwm_comparator_set_compare_value(s_cmp_b, cb);
    return false;
}

static void pwm_init(void)
{
    for (int i = 0; i < LUT_N; i++) s_lut[i] = (int16_t)lrintf(32767.0f * sinf(2.0f * (float)M_PI * i / LUT_N));

    mcpwm_timer_config_t tc = {
        .group_id = 0, .clk_src = MCPWM_TIMER_CLK_SRC_DEFAULT, .resolution_hz = PWM_RES_HZ,
        .count_mode = MCPWM_TIMER_COUNT_MODE_UP_DOWN, .period_ticks = PERIOD_TICKS,
    };
    ESP_ERROR_CHECK(mcpwm_new_timer(&tc, &s_timer));

    mcpwm_gpio_fault_config_t fc = {
        .group_id = 0, .gpio_num = PIN_INV_SD_N, .flags.active_level = 0, .flags.pull_up = false,
    };
    mcpwm_fault_handle_t fault;
    ESP_ERROR_CHECK(mcpwm_new_gpio_fault(&fc, &fault));

    const int pins[2] = {PIN_PWM_A, PIN_PWM_B};
    mcpwm_cmpr_handle_t *cmps[2] = {&s_cmp_a, &s_cmp_b};
    for (int k = 0; k < 2; k++) {
        mcpwm_oper_handle_t op;
        mcpwm_operator_config_t oc = {.group_id = 0};
        ESP_ERROR_CHECK(mcpwm_new_operator(&oc, &op));
        ESP_ERROR_CHECK(mcpwm_operator_connect_timer(op, s_timer));
        s_ops[k] = op;

        mcpwm_comparator_config_t cc = {.flags.update_cmp_on_tez = true};
        ESP_ERROR_CHECK(mcpwm_new_comparator(op, &cc, cmps[k]));
        ESP_ERROR_CHECK(mcpwm_comparator_set_compare_value(*cmps[k], PEAK / 2));

        mcpwm_gen_handle_t g;
        mcpwm_generator_config_t gc = {.gen_gpio_num = pins[k]};
        ESP_ERROR_CHECK(mcpwm_new_generator(op, &gc, &g));
        ESP_ERROR_CHECK(mcpwm_generator_set_action_on_timer_event(g,
            MCPWM_GEN_TIMER_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP, MCPWM_TIMER_EVENT_EMPTY, MCPWM_GEN_ACTION_HIGH)));
        ESP_ERROR_CHECK(mcpwm_generator_set_action_on_compare_event(g,
            MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP, *cmps[k], MCPWM_GEN_ACTION_LOW)));
        ESP_ERROR_CHECK(mcpwm_generator_set_action_on_compare_event(g,
            MCPWM_GEN_COMPARE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_DOWN, *cmps[k], MCPWM_GEN_ACTION_HIGH)));

        /* hardware trip: latch outputs low until the firmware clears the brake */
        mcpwm_brake_config_t bc = {.fault = fault, .brake_mode = MCPWM_OPER_BRAKE_MODE_OST};
        ESP_ERROR_CHECK(mcpwm_operator_set_brake_on_fault(op, &bc));
        ESP_ERROR_CHECK(mcpwm_generator_set_action_on_brake_event(g,
            MCPWM_GEN_BRAKE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_UP, MCPWM_OPER_BRAKE_MODE_OST, MCPWM_GEN_ACTION_LOW)));
        ESP_ERROR_CHECK(mcpwm_generator_set_action_on_brake_event(g,
            MCPWM_GEN_BRAKE_EVENT_ACTION(MCPWM_TIMER_DIRECTION_DOWN, MCPWM_OPER_BRAKE_MODE_OST, MCPWM_GEN_ACTION_LOW)));
    }

    mcpwm_timer_event_callbacks_t cb = {.on_empty = on_tez};
    ESP_ERROR_CHECK(mcpwm_timer_register_event_callbacks(s_timer, &cb, NULL));
    ESP_ERROR_CHECK(mcpwm_timer_enable(s_timer));
    ESP_ERROR_CHECK(mcpwm_timer_start_stop(s_timer, MCPWM_TIMER_START_NO_STOP));
}

static void gpio_init(void)
{
    gpio_config_t out = {
        .pin_bit_mask = (1ULL << PIN_INV_EN) | (1ULL << PIN_RELAY_EN) | (1ULL << PIN_FAN) | (1ULL << PIN_LED),
        .mode = GPIO_MODE_OUTPUT,
    };
    ESP_ERROR_CHECK(gpio_config(&out));
    gpio_set_level(PIN_INV_EN, 0);
    gpio_set_level(PIN_RELAY_EN, 0);
    /* PFC_DIS: leave as input (R15 pull-up keeps PFC OFF) until we want it on */
    gpio_reset_pin(PIN_PFC_DIS);
    gpio_set_direction(PIN_PFC_DIS, GPIO_MODE_INPUT);
}

static void pfc_enable(bool on)
{
    if (on) {
        gpio_set_direction(PIN_PFC_DIS, GPIO_MODE_OUTPUT);
        gpio_set_level(PIN_PFC_DIS, 0);            /* Q3 off -> UCC28180 runs   */
    } else {
        gpio_set_direction(PIN_PFC_DIS, GPIO_MODE_INPUT);  /* pull-up -> off    */
    }
}

static void adc_init(void)
{
    adc_oneshot_unit_init_cfg_t uc = {.unit_id = ADC_UNIT_1};
    ESP_ERROR_CHECK(adc_oneshot_new_unit(&uc, &s_adc));
    adc_oneshot_chan_cfg_t cc = {.atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_12};
    const adc_channel_t chs[] = {CH_VBUS, CH_VOUT, CH_IOUT, CH_TEMP};
    for (int i = 0; i < 4; i++) ESP_ERROR_CHECK(adc_oneshot_config_channel(s_adc, chs[i], &cc));
}

/* raw -> volts. ESP32 ADC is non-linear: replace with adc_cali_* curve fitting. */
static float adc_v(adc_channel_t ch)
{
    int raw = 0;
    adc_oneshot_read(s_adc, ch, &raw);
    return raw * (3.1f / 4095.0f);
}

static float vbus(void) { return adc_v(CH_VBUS) * K_VBUS; }

static void trip(const char *why)
{
    gpio_set_level(PIN_INV_EN, 0);
    s_m_q15 = 0;
    pfc_enable(false);
    ESP_LOGE(TAG, "TRIP: %s", why);
    for (;;) {                                  /* latched: power-cycle to clear */
        gpio_set_level(PIN_LED, 1); vTaskDelay(pdMS_TO_TICKS(100));
        gpio_set_level(PIN_LED, 0); vTaskDelay(pdMS_TO_TICKS(100));
    }
}

static void control_task(void *arg)
{
    /* 1. precharge through TH1: wait for a stable, plausible rectified bus */
    float last = 0;
    for (int stable = 0; stable < 20;) {
        float v = vbus();
        stable = (v > 230.0f && fabsf(v - last) < 5.0f) ? stable + 1 : 0;
        last = v;
        vTaskDelay(pdMS_TO_TICKS(50));
    }
    ESP_LOGI(TAG, "precharged %.0f V -> relay", last);
    gpio_set_level(PIN_RELAY_EN, 1);
    vTaskDelay(pdMS_TO_TICKS(100));

    /* 2. PFC boost to ~400 V */
    pfc_enable(true);
    int64_t t0 = esp_timer_get_time();
    while (vbus() < 380.0f) {
        if (esp_timer_get_time() - t0 > 2000000) trip("PFC did not reach 380 V");
        vTaskDelay(pdMS_TO_TICKS(10));
    }
    ESP_LOGI(TAG, "bus %.0f V -> inverter soft start", vbus());

    /* 3. inverter soft start: ramp modulation over 0.5 s */
    gpio_set_level(PIN_FAN, 1);
    s_m_q15 = 0;
    gpio_set_level(PIN_INV_EN, 1);
    vTaskDelay(pdMS_TO_TICKS(2));
    /* INV_SD_N idles low (R37) so the one-shot brake latched at boot: clear it now */
    if (gpio_get_level(PIN_INV_SD_N) == 0) trip("INV_SD_N stuck low (comparator trip?)");
    for (int k = 0; k < 2; k++) ESP_ERROR_CHECK(mcpwm_operator_recover_from_fault(s_ops[k]));
    float m = 0.0f, m_ff;
    const TickType_t period = pdMS_TO_TICKS(20);           /* one output cycle */
    TickType_t wake = xTaskGetTickCount();
    float sq = 0; int n = 0;
    for (;;) {
        float vb = vbus();
        if (vb > 440.0f) trip("bus over-voltage");
        if (vb < 330.0f) trip("bus under-voltage");
        if (gpio_get_level(PIN_INV_SD_N) == 0 && gpio_get_level(PIN_INV_EN)) trip("hardware over-current");

        /* coarse RMS: ~1 kHz sampling inside this task */
        for (int k = 0; k < 20; k++) {
            float v = (adc_v(CH_VOUT) - VREF_V) * K_VOUT;
            float i = (adc_v(CH_IOUT) - IOUT_ZERO) * K_IOUT;
            if (fabsf(i) > 17.0f) trip("software over-current");
            sq += v * v; n++;
            vTaskDelay(1);
        }
        float vrms = sqrtf(sq / n); sq = 0; n = 0;

        /* feed-forward on bus voltage + slow integral trim on RMS error */
        m_ff = VOUT_RMS_SET * 1.41421f / vb;
        static float integ = 0;
        if (m >= m_ff * 0.98f) integ += 0.0005f * (VOUT_RMS_SET - vrms);
        if (integ > 0.08f) integ = 0.08f; if (integ < -0.08f) integ = -0.08f;
        float target = m_ff + integ;
        m += (target - m > 0.02f) ? 0.02f : (target - m);  /* 0.5 s ramp */
        if (m > 0.92f) m = 0.92f; if (m < 0) m = 0;
        s_m_q15 = (int32_t)(m * 32767.0f);

        float t_hs = adc_v(CH_TEMP);   /* TODO: NTC -> degC, derate above 80 degC */
        (void)t_hs;
        vTaskDelayUntil(&wake, period);
    }
}

void app_main(void)
{
    gpio_init();
    adc_init();
    pwm_init();
    gpio_set_level(PIN_LED, 1);
    xTaskCreatePinnedToCore(control_task, "ctl", 4096, NULL, 10, NULL, 1);
}
