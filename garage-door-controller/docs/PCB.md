# gdc1 PCB

105 × 85 mm, 2 layers, FR4 1.6 mm, 1 oz copper, any mask colour, HASL or ENIG. Four M3 holes, 3.5 mm in from
each corner.

The rules fit a standard JLCPCB/PCBWay 2-layer order:

| | |
|---|---|
| Min track | 0.2 mm |
| Min clearance | 0.2 mm, except **0.15 mm** around the USB-C pads (`USB` net class; the receptacle has a 0.5 mm pitch) |
| Vias | 0.6 / 0.3 mm (power 0.8 / 0.4) |
| Min drill | 0.3 mm |

The library ESP32-S3 footprint has 0.2 mm EPAD vias. They are removed and replaced by a 3 × 3 array of
0.3 mm vias, so no drill is below 0.3 mm.

**Status (`hardware/gen/build/drc.rpt`): KiCad DRC = 0 violations, 0 unconnected**, run with the project's
custom rules (`gdc1.kicad_dru`). The netlist exported from the schematic matches `gen/design.py`: 69 nets,
122 parts, 0 mismatches.

Not done:
* ERC: KiCad 7's CLI has no ERC command. Open the schematic in KiCad 8+ and run it once.
* No SI, thermal or RF simulation.
* No 3D enclosure check.

## Floor plan

```
y=0  ┌─H1──────────[ antenna keep-out 48 mm, no copper either layer ]───────────────H2─┐
     │ J2 USB-C  R9/R10 U2(ESD) F2        C14 ┌──────────────┐ J5 ESP-Prog  BME280 ┌──┤ (slotted corner)
     │ R11/C11  SW1 RESET  D5              EN │ ESP32-S3     │ SW2 BOOT           J7 Qwiic
     │                                    RC  │  WROOM-1     │ TP11  D7 WS2812B    J6 expansion
     │ C1  C13 U3 LDO  C12 TP2/TP3            └──────────────┘ Q1/D9/R19   BZ1      SW3 USER
     │ C2  C4 U1 TPS54360 L1 C6/C7  D4      relay driver (Q2, C20, R23, D11-D13)   opto pull-ups
     │     buck ctl R1-R8, C5, C8, C9      K1 G5V-1          PS1 ║ U6 U7 U8 PC817 ║  (fence)
     │ F1  D1 bridge  D2 TVS  WARN Q3/D14                       ║ field R/LED/C   ║  ISOLATED
y=85 └─H3─ J1 PWR ── J4 WARN ── J3 NC/COM/NO ──────────────────── J8 COM CLOSED OPEN AUX FGND ─H4┘
```

* **Every field connection is on the bottom edge.** Wire entry faces outwards (Phoenix MKDS 5.08 mm).
  Each screw has its function printed next to it on the silkscreen.
* **Antenna:** the module sits flush with the top edge. Its own keep-out zone, from the library footprint,
  clears both layers across the 48 mm band. Mount the board with nothing metallic within ~15 mm of that
  edge.
* **Isolation:** the field side (PS1 output, the reed inputs, J8) lives in the bottom-right island. It has
  its own FGND pour and is fenced off by a 2 mm keep-out strip (no tracks, vias or pour). PS1 and the three
  PC817s straddle the fence. The custom rule `field_iso` makes DRC enforce ≥ 2.0 mm from any field net to
  any other copper.
* **Relay contacts:** the OPENER_* nets keep ≥ 1.0 mm from all other copper. The 0.54 mm between the
  relay's own coil and contact pins is the relay's design, and is exempted inside K1's courtyard only.
* **Buck:** C3 sits on the VIN/GND pins of U1, and D3 (catch diode) sits next to the SW pin. L1 and C6/C7
  are directly to the right. The PowerPAD has 8 thermal vias into the B.Cu ground pour.
* **BME280:** an L-shaped slot thermally separates it from the rest of the board. Its GND gets a dedicated
  via and a B.Cu exit track laid before routing, because otherwise the signal traces seal the corner off.
* **Layers:** signals run on F.Cu. B.Cu is an almost unbroken GND plane with only short jumper hops
  (the router charges extra for B.Cu), which gives the 2.4 GHz radio and the buck a clean return path.
* **Ground:** GND pours on both layers, stitched by a via grid on a 4 mm pitch wherever both layers are
  poured. Any pour fragment that would otherwise float gets its own via or track. SMD pads connect solid;
  THT pads use thermal reliefs.

## Electrical rules (`hardware/gdc1.kicad_dru` + net classes)

| Rule | Value | Applies to |
|---|---|---|
| Default | 0.2 mm clearance, 0.25 mm track | signals |
| PWR | 0.2 mm / 0.5 mm track | VIN, BUCK_SW, BUCK_5V, +5V, +3V3, VBUS, GND, WARN_N |
| USB | 0.15 mm / 0.2 mm track | USB_DP/DN, CC1/2 (0.5 mm pitch receptacle) |
| OPENER | **1.0 mm** to everything, 0.5 mm internal | relay contact nets |
| field_iso | **2.0 mm** field ↔ non-field | FIELD_V, FGND, FIN_*, FLED_*, FOPTO_* |
| intra K1/PS1/U6–U8 | 0.2 mm inside the part's courtyard | parts that bridge a barrier by design |
| usb4105_pegs | 0.15 mm hole clearance inside J2 | the library footprint's NPTH pegs vs its own GND pads |

## How it was routed

`gen/route.py` does the routing with `gen/maze.py`, a small grid A* router (0.05 mm grid, net-class-aware
clearances, rule areas and board cut-outs as obstacles, B.Cu costs 1.6× so the bottom stays mostly
plane). It routes every ratsnest connection, shortest and most local first, and retries from neighbouring
pads of the same net when one end is boxed in. Then it pours, stitches and fixes islands, removes dangling
stubs, and runs DRC.

The result is deterministic: the same inputs always give the same board, in about 6 minutes.
`--freerouting` swaps in Freerouting 2.4.1 (Java 25) for the main pass if you prefer it.

The traces are autorouter traces: correct and DRC-clean, but not as tidy as hand routing. Two places are
worth a manual touch-up in KiCad if you want to polish:
1. Tighten the USB D+/D− pair from U2 to the module.
2. Shorten the EN line from the left side of the module to J5.

## Regenerating

```
cd hardware/gen
python3 design.py                       # sanity check: parts, nets, single-pin nets
python3 gen_sch.py                      # schematic from design.py
kicad-cli sch export netlist -o /tmp/gdc1.net ../gdc1.kicad_sch
python3 check_netlist.py /tmp/gdc1.net  # schematic == design.py
python3.12 route.py                     # placement (gen_pcb.py) + routing + pours + DRC  (~6 min)
python3.12 route.py --drc               # DRC only
python3 export.py                       # Gerbers, drill, BOM, pick&place, PDFs, renders -> hardware/fab
```
Use `python3.12` for anything that imports `pcbnew` (that's KiCad 7's binding on Ubuntu 24.04). The router
also needs `numpy` and `shapely` for that interpreter.
