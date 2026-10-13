# inv1200 PCB

315 × 190 mm, 2 layers, FR4 1.6 mm, **2 oz (70 µm) copper both sides**, green mask, HASL or ENIG.
Minimum track/space: **0.18 mm / 0.2 mm**. 17 short escape segments at the ESP32 and SOIC pins are 0.18–0.19 mm and
everything else is ≥ 0.2 mm, so check that your fab accepts 7 mil on 2 oz. Minimum drill 0.2 mm (the ESP32
thermal vias); routing vias are 0.3 mm.

**Status:** KiCad DRC = **0 violations, 0 unconnected** (run with the project's custom rules). The schematic netlist and the
PCB pad nets were both checked against `gen/design.py`: 159 parts and 96 nets, no mismatches. Not done: no SI/thermal
simulation and no 3D mechanical check of the heatsink and enclosure.
Order from `hardware/fab/inv1200_gerbers.zip`, which contains Gerbers plus separate PTH and NPTH Excellon drill files.
Most parts are THT; the SMD parts are 0805, 1206, 2512, SOIC, SOT-23 and SOT-223, all hand-solderable.

## Floor plan

```
 y=0 ┌──────────────────────────────────────────────────────────────────────────────────────────┐
     │ J1 F1 C1 RV1  TH1 K1 │ bleeder + VBUS sense chains │ MCU support │ ESP32 (antenna→edge) │ U10│J3 (ISOLATED, slot)
     │ PS1 IRM-10-15        │                             │             │ TLV9062 LM393 ACS-amp │ J2 OUT (right edge)
     │ PS2 IRM-05-5  aux    │ C16                         │   H3        │ OUT_LA plane ───► U6 ACS724 ─ OUT_LF plane ─ C31 ─ F2
     │                      │ C17   (VBUS column)         │            L3 (leg B inductor, vertical toroid)
     │ L1 PFC 450 µH        │ C18                         L2 (leg A inductor)
     │ UCC28180 cluster     │                       IR21844 A + island          IR21844 B + island
 y=190 BR1  Q1  D2 C44 ─────┴───── Q6 Q5 (leg A) ── Q8 Q7 (leg B) ──── heatsink along this edge ────┘
```

* **Terminals:** J1 and J2 are 10 mm-pitch Metz RT01902HDWC (2.5 mm HV clearance between pins). PE is chassis wiring only.
* **Heatsink edge (bottom):** BR1, Q1, D2, Q6, Q5, Q8 and Q7 have tabs facing the board edge, about 4 mm from it. One
  ~215 mm extruded profile clamps them all through insulating pads. BR1 needs a 1–2 mm thicker pad or a shim.
* **Power copper** is pre-drawn as planes (`gen/power.py`): VBUS (F.Cu: cap column → band → leg strips),
  SW_A, SW_B and SW_PFC (small, as required for EMI), RECT_P, plus OUT_LA (which dives to B.Cu under the VBUS band through a
  9-via field) and OUT_LF. GND is a pour on both layers. The AC nets, OUT_N and OUT_L are 3 mm autorouted tracks.
  At 2 oz, 3 mm carries 10 A with a rise of roughly 20 °C.
* **Commutation loops:** each leg has its own 1 µF/630 V film cap (C19, C20) sitting directly between the high-side
  drain and the low-side source pads. C44 does the same for the PFC loop D2 → Q1.
* **Gate drive:** the IR21844 HV pins (VS/HO/VB) face the FETs. Bootstrap cap, gate resistor and gate pull-down
  form a hand-routed island referenced to SW. The leg-B high-side gate runs on B.Cu under its SW return.
  The leg-A high-side gate goes around the north of the SW_A plane: Q6's gate pad is enclosed by SW_A on F.Cu,
  so the leg-A gate loop is larger than ideal. Use ≥10 Ω gate resistors and look at the gate waveform at bring-up.

## Electrical rules (`hardware/inv1200.kicad_dru` + net classes)

| Rule | Value | Applies to |
|---|---|---|
| HV_PWR / HV_HC / HV_SIG clearance | **2.5 mm** | any mains/bus-potential net to anything else (IPC-2221B B2, ≤500 V) |
| COLD clearance | **8 mm** | isolated programming side (PROG_*) to anything hot; plus a 1 mm milled slot under U10 |
| hs_A / hs_B | 0.3 mm | nets riding on a switch node (SW, VB, HO, high-side gate) |
| acs724_primary | 0.4 mm | IP+ ↔ IP− (milli-volt difference) |
| intra-footprint | 0.2 mm | pins inside one HV part (IC pitch, resistor ends, terminal) |
| HV to board edge | 2 mm | |
| Mounting holes | 7.5 mm copper keepout radius | unplated; screws/standoffs go to chassis (PE) |

HV dividers (bus sense, PFC VSENSE, bleeder, output sense, X-cap discharge) are laid end to end, so neighbouring
pads always share a net and each resistor sees ≤ 100 V. **Conformal coating is recommended** around the gate
drivers and dividers.

## Regenerating

```
cd hardware/gen
python3 gen_sch.py                      # schematic from design.py
python3 check_netlist.py <netlist>      # (after: kicad-cli sch export netlist) schematic == design.py
python3.12 route.py --reuse             # placement + planes + hand routes + stored Freerouting sessions
                                        #   + maze router for the last few nets + GND pours + DRC
python3.12 route.py                     # same, but re-runs Freerouting (Java 25, ~30 min); then optionally --finish
python3.12 route.py --drc               # DRC only (fresh process)
python3 export.py                       # Gerbers, drill, BOM, pick&place, PDFs, renders -> hardware/fab
```
`design.py` is the single source of truth. `power.py` holds the hand-drawn power planes, gate-drive islands and
long HV routes. `inv1200.ses` and `inv1200_finish.ses` are the stored autorouter sessions. `maze.py` is a small
A* router that completes whatever Freerouting leaves open, with net-class-aware clearances.
Use `python3.12` for anything that imports `pcbnew` (that's KiCad 7's binding on Ubuntu 24.04).
