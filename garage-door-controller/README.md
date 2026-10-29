# gdc1: open-source smart garage door controller (rev A)

A local-first retrofit controller that works with the opener you already have. A dry-contact relay presses the
wall button. Three opto-isolated reed inputs sense the door. An ESP32-S3 connects it to MQTT/Home Assistant,
with no cloud.

| Path | What |
|---|---|
| `docs/DESIGN.md` | requirements → hardware map, **calculations**, pin map, **what to verify**, bring-up, installation |
| `docs/PCB.md` | floor plan, layout rules, DRC status, how to regenerate |
| `hardware/gdc1.kicad_pro` | KiCad 7 project (schematic + PCB) |
| `hardware/fab/` | Gerbers + drill (zip), BOM CSV, pick-and-place, schematic/PCB PDFs, renders |
| `hardware/gen/` | Python generators. `design.py` is the single source of truth for parts and nets |
| `firmware/board_pins.h` | GPIO map for the ESP-IDF firmware (Phase 2/3 of the plan) |

**Board:** 105 × 85 mm, 2 layers, 1.6 mm FR4, 1 oz. 122 parts, mostly SMD 0603/0805/1206. The fine-pitch
parts are the ESP32-S3 module, the USB-C receptacle and the BME280 LGA (hot air recommended for that one).

**Highlights**
* Input: 9–36 VDC (either polarity) or 24 VAC → TPS54360 60 V buck. A USB-C alone also powers and flashes the board.
* Relay drive is AC-coupled in hardware, so a crashed MCU cannot hold the opener button "pressed" (SR4).
* Door inputs run from an isolated 1 W DC/DC, with a 2 mm isolation fence on the PCB. Each input has an LED
  that lights when its reed is closed, with or without firmware.
* Pre-close warning: on-board buzzer + red LED, plus a switched 12/24 V output for a strobe at the door (UL 325).
* BME280 sits in a thermally slotted corner. A Qwiic port takes a ToF sensor, and an expansion header
  takes a CT clamp or UART.

Licences: hardware CERN-OHL-S-2.0, firmware/scripts MIT.
