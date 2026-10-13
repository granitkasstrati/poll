# 230 VAC → 120 VAC, 1200 W converter (inv1200)

> **This board is lethal.** The whole PCB, including the ESP32 and its GND, sits at
> mains potential. The 400 V bus stores **~94 J**. The 120 V output is **not isolated**
> from the 230 V mains and has **no neutral**: neither output pin may be bonded to PE.
> Only the programming header J3 is isolated (Si8641, 5 kVrms, with a PCB slot).
> Treat it like a working SMPS primary side: isolation transformer, one hand, differential
> or isolated probes, never a grounded scope probe on the board.

## 1. Specification

| Item | Value |
|---|---|
| Input | 195–265 VAC, 50 Hz (designed for 230 V) |
| Output | 120 VAC ±3 %, 50 Hz (frequency is set in firmware, 60 Hz is a one-line change), pure sine |
| Power | 1200 W continuous (10 A rms), resistive / SMPS / PFC loads |
| Overcurrent | hardware cycle-by-cycle trip at ±19 A pk (LM393 → IR21844 SD̅), firmware latch at 17 A |
| Topology | NTC + relay inrush → bridge → CCM boost PFC (UCC28180, 400 V) → SiC full bridge, unipolar SPWM 40 kHz → LC filter |
| Controller | ESP32-WROOM-32E (MCPWM + ADC1), bus-GND referenced |
| Efficiency (est.) | 92–94 % |
| PCB | 315 × 190 mm, 2 layers, **2 oz (70 µm) copper required**, FR4 1.6 mm |
| Connections | J1 AC in (L, N), J2 AC out: Metz RT01902HDWC 10 mm pitch. **PE does not touch the PCB**: wire it inlet → chassis/heatsink → output socket earth |

## 2. Block diagram

```
 IEC inlet+filter        ┌──────── PS1 IRM-10-15 ─► VCC15 (gate drive, PFC, LM393) ─► L7812 ─► +12V (relay, fan)
 (FN9260 10 A, off-board)├──────── PS2 IRM-05-5  ─► +5V (ACS724, TLV9062)           ─► AMS1117 ─► +3V3 (ESP32)
        │                │        (module outputs are isolated; their −Vo is tied to bus GND)
 L ─J1─F1 T10A─┬─RV1─C1 X2─┬─TH1 5Ω─┬─────► BR1 ─► C8 ─► L1 450µH ─┬─► D2 SiC ─► VBUS 400V ─┬─► Q5/Q6 leg A ─► L2 150µH ─► ACS724 ─┬─ F2 ─► OUT_L
 N ────────────┴──────────┴─K1 relay┘          │                   Q1 (UCC28180)  3×390µF  ├─► Q8/Q7 leg B ─► L3 150µH ───────────┼────► OUT_N
                                               RS1‖RS2 20 mΩ (PFC current)                  │                                C31 3.3µF X2
                                                                                            └─ IR21844 ×2 ◄─ ESP32 MCPWM (IO25/26) ◄── ADC: VBUS, VOUT, IOUT, NTC
```

## 3. Power-stage calculations

**Input current.** P_in = 1200 / 0.92 ≈ 1.30 kW. At PF 0.99:
195 V → 6.8 A rms (9.6 A pk), 230 V → 5.7 A, 265 V → 5.0 A. F1 = T10A (ceramic, 6.3×32).

**Inrush.** TH1 (TDK S237 5 Ω/8 A) limits the cold-plug peak to 325 V / 5 Ω ≈ 65 A (the GBU bridge surge
rating is 200 A+). D1 (1N5408) charges the bus around L1/D2 so the inductor isn't saturated at plug-in.
The firmware closes K1 once the bus is stable above 230 V, then enables the PFC.

**Bridge (BR1).** I_avg ≈ 0.9 × 6.8 = 6.1 A. Loss ≈ 2 × 0.95 V × 6.1 A ≈ **12 W** → heatsink.

**PFC inductor (L1).** f_sw = 65 kHz, V_o = 400 V, worst case at 195 V peak (276 V): D = 1 − 276/400 = 0.31.
For 30 % ripple (2.9 A pp): L = V·D / (f·ΔI) = 276 × 0.31 / (65 k × 2.9) ≈ **460 µH → 450 µH**.
Peak current 11 A, so **I_sat ≥ 15 A** at the 450 µH point. Suggested core: 2 stacked Magnetics 0077439A7
(Kool Mµ 60µ, 47 mm), ~70 turns of 1.6 mm wire (check roll-off with the Magnetics designer). Mounted vertically (TJ9 footprint).

**PFC switch / diode.** I_sw,rms ≈ 6.8 × √(1 − 8√2·V_pk/(3π·V_o)) ≈ 4.4 A. IPW65R045C7: conduction ≈ 1.8 W +
switching ≈ 4–5 W. C6D10065A SiC (zero Qrr): ≈ 3.3 A avg × 1.5 V ≈ 5 W.

**Current shunt.** RS1‖RS2 = 20 mΩ. 11 A pk gives −220 mV on ISENSE; dissipation ≈ 0.95 W total.
*Check the UCC28180 soft-OCP and peak-current-limit thresholds in the datasheet against this value.*

**Bulk capacitance.** 3 × 390 µF / 450 V = 1170 µF.
- 100 Hz ripple per source: ΔV = P/(2π·f·C·V) ≈ 8.9 V pp. The PFC input and the 50 Hz inverter output both
  pulse at 100 Hz, so the worst case (anti-phase) is ≈ 18 V pp. The firmware feed-forward on V_bus cancels it.
- Hold-up from 400 V to 300 V: C(V₁² − V₂²)/(2P) ≈ **31 ms**.
- Stored energy: ½CV² ≈ **94 J**. Bleeder R17–R20 (108 kΩ) gives τ ≈ 126 s, so **wait 10 min or discharge
  manually**. D4 (red) stays lit while the bus is above ~30 V.
- Ripple current ≈ 4–5 A rms total: about 1.6 A per cap, well inside a 105 °C snap-in's rating.
- C19 and C20 (1 µF 630 V MKP) sit right on each leg. C44 (100 nF 630 V) closes the D2–Q1 loop.

**Inverter.** V_out,pk = 170 V → modulation index m = 170/400 = 0.42 (feed-forward m = √2·V_set/V_bus).
Unipolar SPWM on a common 40 kHz carrier makes the differential ripple appear at **80 kHz**, and the
common-mode voltage of the two legs stays at V_bus/2.
- Per-switch I_rms ≈ 14.1/2 = 7.1 A. C3M0060065D (≈ 80 mΩ hot): 4 W conduction + 1–2 W switching ≈ **6 W each**.
  SiC body diodes have near-zero Qrr, which matters in a hard-switched bridge.
- Dead time: IR21844 with DT tied to VSS = minimum ≈ 0.4 µs (1.6 % of the period). Add R_DT (DT→VSS) to lengthen it.
- Bootstrap: ES1J + 1 µF. The duty cycle stays between 29 and 71 %, so it never starves.

**Output filter.** L_total = 2 × 150 µH (split, one per leg). Worst ripple:
ΔI = (V_dc − v)·v / (V_dc·L·2f_sw) = 230 × 170 / (400 × 300 µ × 80 k) ≈ **4.1 A pp** (29 % of peak).
Use Kool Mµ 0077439A7, ~45 turns of 1.8 mm, **I_sat ≥ 20 A** (above the trip level).
C31 = 3.3 µF X2 → f₀ = 1/(2π√(LC)) ≈ **5.1 kHz**, giving ~48 dB at 80 kHz. Reactive current 0.12 A.

**Heatsink.** BR1 12 W + Q1 7 W + D2 5 W + 4 × 6 W = **~48 W**. For T_case < 90 °C at 40 °C ambient you need
θ_sa ≤ ~0.8 K/W including the insulating pads: an extruded profile ~200 mm long with a 12 V fan (J5,
PWM via Q11). All tabs are live: use Sil-Pad/ceramic insulators and shoulder washers, and **bond the heatsink to PE**.

## 4. Control, sensing, protection

| Signal | Path | Scaling at the ESP32 pin |
|---|---|---|
| VBUS (IO36) | R21–R24 4 MΩ / R25 22 k | 2.19 V @ 400 V |
| VOUT (IO39) | 2× 4 MΩ diff amp, gain 1/143 around VREF 1.65 V (TLV9062) | 1.65 ± 1.19 V @ 170 V pk |
| IOUT (IO34) | ACS724LLCTR-20AB (100 mV/A), 2/3 divider | 1.67 ± 0.067 V/A |
| Heatsink (IO35) | 10 k NTC on J4, 10 k pull-up | — |
| OC trip | LM393 window at 0.60 / 4.40 V on the ACS output (±19 A) | pulls INV_SD_N low |

- **INV_SD_N** is wired-AND: the MCU drives it high through R36 1 k (IO27), R37 holds it low at reset, and
  either LM393 output can pull it low. Both IR21844s shut off in < 1 µs, independent of firmware.
  IO13 reads it back as an MCPWM one-shot fault.
- **PFC_DIS** (IO33): R15 pulls Q3 on → VSENSE low → UCC28180 in standby. The PFC is **off unless the MCU
  actively drives IO33 low**.
- **Relay** (IO32, Q2) bypasses TH1 after precharge. **Fan** (IO4, Q11).
- **Programming:** J3 = GND, 3V3, TXD, RXD, DTR, RTS from any 3.3 V USB-UART. The adapter powers only the cold side
  of the Si8641. The standard DTR/RTS → EN/IO0 transistor pair (Q9/Q10) gives auto-reset into the bootloader.
  The ESP32 Wi-Fi is the other "isolated" interface. Telemetry/OTA over Wi-Fi is the intended way to talk to the
  running unit.

Firmware skeleton: [`firmware/inv1200/main/main.c`](../firmware/inv1200/main/main.c) (ESP-IDF ≥ 5.2, **untested**).
It sequences precharge → relay → PFC → soft start, generates the SPWM from an 800-point LUT in the 40 kHz
timer ISR, and regulates RMS with V_bus feed-forward plus a slow integrator.

## 5. PCB

See [`PCB.md`](PCB.md) for the layout description, rules and fabrication notes.

## 6. Things you must verify before ordering / powering

1. **UCC28180 symbol pinout** (custom symbol, `hardware/inverter.kicad_sym`, drawn from memory of TI SLUSBQ5:
   1 GND, 2 ICOMP, 3 ISENSE, 4 FREQ, 5 VCOMP, 6 VSENSE, 7 VCC, 8 GATE). Check it against the datasheet.
2. **UCC28180 component values:** R8 (f_sw), C9 (ICOMP), R9/C11/C12 (VCOMP) are starting values. Run TI's
   UCC28180 design calculator for 1.3 kW / 65 kHz / 450 µH / 20 mΩ.
3. **ACS724 pin 6** (BW_SEL on the LLCTR variant): tied to GND here. Confirm against the Allegro datasheet.
4. **BR1 on the heatsink:** a GBU's back face sits ~1–2 mm behind the TO-247 tab plane. Use a thicker pad or shim.
5. **Inductors:** winding counts are first-pass. Measure L at rated DC current before use.
6. **EMC:** the board relies on an external IEC inlet filter. Nothing here has been EMC- or safety-tested.
7. **Firmware:** the skeleton is not compiled. The ESP32 ADC needs `adc_cali` curve fitting plus a
   two-point calibration of VOUT against a true-RMS meter.

## 7. Bring-up (recommended order)

1. **Unpowered:** check for shorts VBUS–GND, SW_A/B–GND and VCC15/5V/3V3–GND. Program the ESP32 with the
   board powered only from a **bench 5 V into +5V** (no mains), through J3.
2. **Low-voltage inverter test:** remove F1. Feed **VBUS from a current-limited bench supply (30–60 V)** and
   VCC15 from a bench 15 V. Comment out the PFC/relay sequencing, run the inverter at m = 0.8 into a resistive
   load, and check gate waveforms (isolated probes), dead time, the OC trip and the sine.
3. **PFC alone:** isolation transformer + variac + 100 W bulb in series. Ramp the AC up slowly with no
   inverter load. Check that the bus regulates at 400 V and watch the UCC28180 current loop.
4. **Full chain:** 100 W → 500 W → 1200 W resistive load, watching heatsink temperature and THD.
