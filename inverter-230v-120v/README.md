# inv1200: 230 VAC → 120 VAC, 1200 W pure-sine converter

Non-isolated AC-DC-AC converter: inrush limiting, a UCC28180 CCM boost PFC to 400 V, a SiC full-bridge
inverter (unipolar SPWM, 40 kHz carrier, 80 kHz ripple), an LC filter, and an ESP32 controller.

| Path | What |
|---|---|
| `docs/DESIGN.md` | spec, calculations, protection, **what to verify**, bring-up procedure |
| `docs/PCB.md` | layout, clearance rules, regeneration steps |
| `hardware/inv1200.kicad_pro` | KiCad 7 project (schematic + PCB) |
| `hardware/fab/` | Gerbers + drill (zip), BOM CSV, pick-and-place, PDFs, renders |
| `hardware/gen/` | Python generators: `design.py` is the single source of truth for parts and nets |
| `firmware/inv1200/` | ESP-IDF ≥ 5.2 controller skeleton (**untested**) |

**Danger:** the whole board, including the ESP32 GND, is at mains potential; the 400 V bus holds ~94 J; and the 120 V
output is not isolated from the mains. Read `docs/DESIGN.md` §0/§7 before powering anything.
