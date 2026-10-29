# gdc1 — design notes (rev A)

Smart garage door controller, retrofit style. The opener keeps its motor, its travel limits, its force
limiting and its photo-eye. gdc1 only does three things:

1. It **presses the wall button** with a dry relay contact wired in parallel with the real button.
2. It **senses the door** with up to three reed switches through opto-isolated inputs.
3. It **talks** over Wi-Fi (ESP32-S3) to MQTT/Home Assistant, and also serves a local web UI.

The board does **not** sit in series with anything the opener needs. If gdc1 is unpowered or dead, the
wall button, the remotes and the photo-eye all keep working (FR4).

| Section | |
|---|---|
| §1 | Requirements → hardware feature map |
| §2 | Block diagram and power tree |
| §3 | Calculations (buck, LDO, power budget, relay pulse limiter, opto inputs, VIN sense) |
| §4 | Pin map |
| §5 | **Verify before ordering** (values taken from memory, not re-checked against datasheets) |
| §6 | Bring-up procedure |
| §7 | Installation and wiring |
| §8 | Errata / rev-B backlog |

---

## 1. Requirements → hardware

| Req | How the board covers it |
|---|---|
| FR1 open/close/stop | K1 (Omron G5V-1) contacts across the wall-button terminals. One pulse = one button press, so the opener's own open/stop/close cycle applies |
| FR2 true state | J8: CLOSED and OPEN reeds, plus AUX. Input LEDs D16–D18 light whenever a reed is closed, even with no firmware (useful for aligning magnets) |
| FR3 HA / MQTT | ESP32-S3-WROOM-1-N8R2, 2.4 GHz. Antenna on the board edge with a copper keep-out |
| FR4 wall button always works | gdc1 is only ever in parallel with the button. Relay NO is open when unpowered |
| FR5 OTA | 8 MB flash allows two OTA slots plus NVS/SPIFFS. 2 MB PSRAM for the TLS buffers |
| FR6/7 local UI, provisioning | SW3 USER: hold for 10 s at boot to re-enter the SoftAP portal (firmware convention) |
| SR1 pre-close warning | BZ1 (85 dB @ 10 cm) + D9 red LED on board, plus J4 WARN OUT for an external 12/24 V strobe or sounder at the door |
| SR2 never touch the photo-eye | No connection to it at all |
| SR3 dry contact, isolated | Only the relay contact set touches OPENER_*. 1.0 mm min clearance to all other copper |
| SR4 relay fails open | (a) R23 holds the FET gate low through reset/boot/brown-out. (b) **AC-coupled gate (C20)**: a GPIO stuck high (firmware hang, crash mid-pulse) still releases the relay within ≤ 1.6 s. Firmware cannot "hold" the button even if it wants to |
| SR5 rate limit | Firmware (≥ 2 s between pulses). The C20 recovery time (~1 ms via D11) does not limit it |
| NFR1/2 TLS, signed OTA | ESP32-S3 secure boot v2 + flash encryption (eFuse). Nothing extra on the board |
| NFR4 −20…+60 °C | All parts are rated at least −40…+85 °C. The electrolytics are 105 °C parts |
| NFR5 BOM < $60 | Roughly $35–45 in qty 1 (module ~$4, TPS54360 ~$3, MEE1S0505SC ~$5, relay ~$2, terminals ~$5) |

## 2. Block diagram

```
J1 (9–36 VDC any polarity / 24 VAC)
   │
   F1 PTC 0.5 A/60 V ─ D1 MB6S bridge ─┬─ D2 SMBJ40A ─┬─ C1,C2 2×100 µF/63 V ─ VIN ──► J4 WARN OUT (low-side, Q3)
                                        │              │                         └──► R7/R8 → VIN_SENSE (IO1)
                                        │              U1 TPS54360  400 kHz, L1 33 µH, D3 B360A
                                        │              │
                                        │            BUCK_5V 5.28 V ─ D4 SS34 ─┐
J2 USB-C ─ F2 0.5 A PTC ─ VBUS_F ──────────────────────────── D5 SS34 ─────────┴─ +5V ─┬─ K1 coil, BZ1, WS2812B (via D8)
            (D+/D- → U2 USBLC6 → IO19/IO20)                                             ├─ PS1 MEE1S0505SC ═╪═ FIELD_V/FGND → J8 inputs
                                                                                        └─ U3 AP7361C-33 → +3V3 → ESP32-S3, BME280, optos (logic side)
```

Both 5 V sources are diode-OR'ed. USB alone powers the whole board, which is how you flash and bench-test
it. When both are present, the buck (5.28 V) wins, and nothing is back-fed into the USB host or into the buck.

## 3. Calculations

### 3.1 Input stage

* **24 VAC worst case.** +10 % line and ~+15 % transformer no-load rise give 30.4 VAC. The peak is 43 V,
  or 41.6 V after the bridge. D2 SMBJ40A has 40 V standoff and 44.4 V minimum breakdown, so it does not
  conduct in normal service. Its clamp is 64.5 V at the full 9.3 A rated pulse. In practice F1 (~1 Ω)
  and the bridge limit surge current to a few amps, which keeps the clamp in the mid-40s V. TPS54360 VIN
  is 60 V operating / 65 V abs max.
* **Hold-up at 24 VAC/60 Hz with 2×100 µF.** At a 0.25 A total load (board + a 150 mA strobe on J4), the
  ripple is ΔV = I/(2·f·C) = 0.25/(120·200 µF) ≈ 10 V. The valley stays ~22 V, far above UVLO.
  **On 24 VAC, keep the J4 load ≤ 150 mA.** On DC input, 300 mA is fine.
* **Polarity:** the bridge makes it a non-issue (−1.6 V of headroom, 0.5 A average rating, 30 A surge).

### 3.2 Buck, TPS54360 (VIN → 5.28 V)

| Item | Value | Notes |
|---|---|---|
| fsw | 400 kHz | RT = 101756 / f(kHz)^1.008 = 242.5 kΩ → **R3 = 243 k** |
| min on-time check | 5.28/(41.6 V·400 kHz) = 317 ns | > 135 ns minimum on-time |
| Vout | 0.8·(1 + 56k/10k) = **5.28 V** | R4/R5. Leaves ~4.9 V on +5V after D4 |
| L1 | 33 µH | ΔI = (41.6−5.28)·5.28/(41.6·33 µH·400 kHz) = 0.35 A pp at the 41.6 V maximum input. Design Iout = 0.8 A → Ipk ≈ 0.98 A. Choose Isat ≥ 1.3 A |
| Cout | 2×22 µF X7R 1210 (≈ 30 µF effective at 5.3 V) | Ripple ≈ ΔI/(8·f·C) ≈ 4 mV plus ESR |
| Compensation | fp_mod = Iout/(2π·Vout·Cout) ≈ 1.0 kHz, fco = √(fp_mod·fsw/2) ≈ 14 kHz | Rcomp = 2π·fco·Cout/gm_ps · Vout/(Vref·gm_ea) with gm_ps = 12 A/V and gm_ea = 350 µS gives **R6 = 4.12 k**. Ccomp = 1/(2π·Rcomp·fp_mod) gives **C8 = 39 nF**. Cpole = 1/(π·Rcomp·fsw) gives **C9 = 180 pF** |
| UVLO | start 7.0 V, stop 6.0 V | R1 = 243 k, R2 = 47.5 k (EN 1.2 V, Ip = 1.2 µA, Ih = 3.4 µA) |
| D3 catch | B360A, 60 V / 3 A | Avg ≈ 0.8 A·(1−D) ≈ 0.7 A, ≈ 0.35 W |
| Input caps | C3 2.2 µF/100 V X7R 1210 + C4 100 nF at the pins | The 1210 derates to ~1 µF at 40 V. C1/C2 carry the bulk |

These are first-pass values from the datasheet procedure. Cross-check them with TI's WEBENCH or the
TPS54360 design spreadsheet (§5), then measure the load-step response at bring-up (§6).

### 3.3 5 V / 3.3 V budget

| Load | Typ | Peak |
|---|---|---|
| ESP32-S3 (Wi-Fi connected, modem sleep off) | 100 mA | 350 mA (TX burst) |
| Relay coil G5V-1 DC5 (167 Ω) | — | 30 mA (≤ 0.5 s) |
| Buzzer | — | 30 mA |
| WS2812B (firmware caps it at 1/3 brightness) | 5 mA | 20 mA |
| PS1 isolated DC/DC (3 inputs closed + preload) | 40 mA | 60 mA |
| LEDs, BME280, pull-ups | 10 mA | 25 mA |
| **Total on +5V** | **~155 mA** | **~515 mA** |

U3 AP7361C-33 (1 A, 0.36 V dropout) dissipates (4.93 − 3.3)·0.12 A ≈ 0.2 W typ and ≈ 0.6 W peak in a
SOT-223 on a GND pour, a ~15 °C rise. From USB alone, +5V is about 4.5 V, which still leaves > 1 V of headroom.

### 3.4 Relay drive with a hardware pulse limit (SR4)

```
RELAY_CMD ─ R22 100R ─┬─ C20 10 µF ─┬─ RLY_G ─ Q2 AO3400A gate        K1 coil: +5V → pin 2, pin 9 → Q2 drain
                      │             ├─ R23 100k → GND (τ = R23·C20)    D12 flyback, D13 "relay on" LED
                      │             └─ D11 (K) … (A) GND: clamps the negative swing
```
* A rising edge puts ~3.3 V on the gate, which then decays: Vg = 3.3·e^(−t/τ). With 10 µF X7R/25 V 1206
  derated to 7–10 µF, τ ≈ 0.7–1.0 s.
* The relay stays in while Vg > Vth (AO3400A: 0.65–1.45 V). Hold time = τ·ln(3.3/Vth), between
  **0.58 s and 1.6 s**. The firmware pulse is 300–500 ms; at 400 ms, Vg ≥ 1.86 V, which is above the
  worst-case Vth. The 30 mA coil needs very little overdrive.
* GPIO stuck high (hang, crash, bad OTA): the relay releases on its own. It cannot keep the button pressed.
  (A held button means something different on some openers, e.g. lock or learn mode.)
* Falling edge: the gate swings negative, D11 clamps it at −0.7 V, and C20 resets through R22 in ~1 ms.
  The next pulse is therefore full height straight away.
* A µs boot glitch on IO7 transfers only µs of gate charge, and the relay needs ~10 ms to pull in.

### 3.5 Isolated door inputs

```
J8.1 FIELD_V ── reed ── J8.x FIN_x ─┬─ C (10 nF) → FGND          logic side:  +3V3 ─ 10k ─┬─ IN_x → GPIO (active low)
                                    └─ R 390R 1206 ─ LED (red) ─ PC817 LED ─ FGND           PC817 C/E ─┴─ 10 nF → GND
```
* PS1 Murata MEE1S0505SC: 1 W, 5 V → 5 V unregulated. R27 (2.2 k) is a pre-load so that the light-load
  output stays near 5–6 V. D15 SMAJ12A protects the field rail.
* Loop current = (V_field − 1.9 V − 1.2 V)/390 Ω ≈ **4.9 mA at 5 V, 7.4 mA at 6 V**. That is plenty of
  wetting current for a reed contact.
* PC817 CTR ≥ 50 % (unranked, end of life), so ≥ 2.4 mA is available against the 0.33 mA the 10 k
  pull-up needs: > 7× margin over temperature and ageing. The 10 k·10 nF = 100 µs filter is plenty, and
  firmware debounces at ~50 ms.
* Isolation: the module (3 kVDC rating) and the PC817s bridge the barrier. On the PCB, a 2 mm keep-out
  fence plus a custom DRC rule enforce ≥ 2.0 mm between any field net and any other copper. Long
  bell-wire runs on a metal door track can pick up kilovolt-class common-mode transients, and none of it
  reaches the logic ground.

### 3.6 VIN sense
R7/R8 = 100 k/6.8 k (÷15.7): 45 V → 2.87 V, inside the ESP32-S3 ADC1 range at 12 dB attenuation.
Firmware can use it to report "opener supply lost" and to log brown-outs. It goes to IO4 (ADC1_CH3), the
ADC pin on the module side that faces the buck, so the divider output does not cross the board.

### 3.7 WS2812B on a 3.3 V GPIO
D8 (1N4148W) drops the LED's VDD to ~4.3 V, so its VIH (0.7·VDD ≈ 3.0 V) sits below the ESP32's 3.3 V
high level. No level shifter needed.

## 4. Pin map (also `firmware/board_pins.h`)

| GPIO | Net | Use |
|---|---|---|
| IO4 | VIN_SENSE | ADC1_CH3 |
| IO2 | EXP_ADC | ADC1_CH1 → J6.2 (CT clamp etc.) |
| IO16 / IO17 / IO18 | IN_CLOSED / IN_OPEN / IN_AUX | opto inputs, active low |
| IO7 | RELAY_CMD | pulse 300–500 ms, AC-coupled |
| IO8 / IO9 | I2C_SDA / I2C_SCL | BME280 @0x76, Qwiic J7 |
| IO10 | BUZZER_CMD | active high |
| IO15 | WARN_CMD | J4 external strobe, active high |
| IO12 | WARN_LED | red LED, active high |
| IO13 | RGB_DIN | WS2812B (RMT) |
| IO14 | USER_BTN | active low |
| IO38–IO41 | EXP_IO38–41 | J6 (IO40/41 suggested as UART1) |
| IO19 / IO20 | USB D− / D+ | native USB-Serial-JTAG |
| IO43 / IO44 | U0TXD / U0RXD | J5 ESP-Prog |
| IO0 | BOOT | strap, SW2, J5.6 |
| EN | EN | SW1, J5.1, RC 10 k / 1 µF |
| IO3, IO45, IO46 | — | straps, left at their internal defaults (NC) |
| IO1, IO5, IO6, IO11, IO21, IO35–37, IO42, IO47/48 | — | unused (NC) |

## 5. Verify before ordering

The datasheet sites (ti.com, omron.com, espressif.com) could not be reached from the environment this was
designed in. The values below come from memory and the KiCad libraries, so **check each one against the
current datasheet** before you order:

1. **K1 Omron G5V-1 contacts.** The KiCad symbol draws pin 1 as NC and pin 10 as NO, with COM = 5/6 and
   coil = 2/9. J3 is labelled NC/COM/NO to match. At bring-up, measure with an ohmmeter: unpowered, J3
   COM–NC should read 0 Ω.
2. **TPS54360 constants:** the RT equation, Vref = 0.8 V, gm_ea = 350 µS, gm_ps = 12 A/V, EN 1.2 V /
   1.2 µA / 3.4 µA, t_on(min) = 135 ns. Re-run the compensation with the TI spreadsheet.
3. **ESP-Prog header pinout** (J5): EN, VDD, TXD, GND, RXD, IO0 on pins 1–6. The silkscreen shows pin 1.
4. **Bourns MF-R050:** F1 uses the KiCad MF-RHT050 footprint (5.1 mm radial pitch). Check the lead
   pitch and hole size of whichever radial PTC you buy (it must be rated ≥ 60 V).
5. **IRLML0060 at Vgs = 3.3 V** (VGS(th) max 2.5 V). Fine for ≤ 300 mA in typical parts. If you see
   heating with a big strobe, swap in a 60 V FET specified at 2.5 V gate drive.
6. **SRN6045TA-330M saturation current** must be ≥ 1.3 A (otherwise use a 6x6 mm 33 µH part that is).
7. **MEE1S0505SC pinout** (−Vin, +Vin, −Vout, +Vout = 1, 2, 3, 4, from the KiCad symbol). The cheap
   B0505S-1W is **not** pin-compatible.

## 6. Bring-up procedure (write every result down; it becomes the errata table)

1. **Bare board:** check for shorts VIN–GND, +5V–GND, +3V3–GND and FIELD_V–FGND. Check isolation GND–FGND
   and GND–OPENER_* (expect > 10 MΩ).
2. **Populate the power stage only** (J1, F1, D1, D2, C1–C10, U1, L1, D3, R1–R8, D4). Bench supply at
   12 V with a 100 mA current limit:
   BUCK_5V = 5.28 V ±2 %. Probe TP5 (SW): clean 400 kHz switching. Sweep VIN 9→36 V and confirm UVLO
   start ≈ 7 V and stop ≈ 6 V. Scope the output ripple at 0 and 0.5 A (electronic load on BUCK_5V).
3. Add D4, U3, C12, C13: +3V3 = 3.30 V. Then do the same from USB-C alone (D5, F2): +5V ≈ 4.5 V, +3V3 OK.
4. **ESP32-S3:** fit U4, the decoupling and the EN/BOOT parts. Plug in USB: `esptool.py chip_id` should
   answer over the native USB port. Flash a blinky that toggles WS2812B / D9 / BZ1.
5. **Relay:** pulse IO7 for 400 ms. K1 clicks and D13 lights. Then hold IO7 high and confirm that the relay
   drops out within 0.6–1.6 s (record τ). Reset the MCU mid-pulse and confirm the relay releases.
6. **Inputs:** fit PS1 and measure FIELD_V (5–6 V). Short J8 COM to each input in turn: the matching
   D16–D18 lights and the GPIO reads 0.
7. **WARN:** connect a 12 V lamp or strobe to J4 and switch it. Check that Q3 stays cool.
8. **RF:** check RSSI at the install location (garages are often marginal; there is a 2 mm ground clearance
   margin round the keep-out).

## 7. Installation

* **Opener:** J3 COM + NO go to the opener's wall-button terminals, in parallel with the existing button.
  **Check the opener first.** If it uses a serial wall control (Chamberlain/LiftMaster Security+ 2.0,
  yellow learn button), the terminals carry data, not a simple short. Put the relay across the contacts
  of the physical wall-button instead, or across the button of a spare remote.
* **Power:** J1 from the opener's accessory terminals (if they deliver ≥ 9 V and enough current), or from
  any 12–24 V DC adapter, or from a 24 VAC class-2 transformer.
* **Sensors:** J8.1 (COM) to one leg of each reed switch. The other legs go to CLOSED, OPEN and AUX. Use
  overhead-door-rated wide-gap reeds. If the cable is shielded, terminate the shield on J8.5 (FGND) only.
  The input LEDs let you align the magnets with no firmware running.
* **Warning:** for unattended remote close, UL 325 expects the audible and visual warning **at the door**.
  BZ1 inside an enclosure may not be enough, so put a 12/24 V strobe or sounder on J4.

## 8. Errata / rev-B backlog

* Matter / Thread: move to the ESP32-C6 (802.15.4) and keep the rest of the board.
* Optional: VL53L1X ToF on the Qwiic port as an independent third observer (no board change needed).
* Optional: CT clamp on J6 to watch the opener motor current.
