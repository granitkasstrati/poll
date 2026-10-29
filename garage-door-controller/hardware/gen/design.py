"""
Single source of truth for gdc1, the smart garage door controller (rev A).

Retrofit controller: it pulses a dry-contact relay wired in parallel with the
opener's wall button, senses door position through three opto-isolated reed
inputs, and talks to Home Assistant over Wi-Fi (ESP32-S3).

Power:  J1 12-24 VDC (any polarity) or 24 VAC -> PTC -> bridge -> TVS -> TPS54360
        60 V buck -> 5.28 V -> Schottky OR with USB-C VBUS -> +5V -> AP7361C LDO -> +3V3
Isolation: field side of the reed inputs runs from a 1 W isolated DC/DC (FIELD_V/FGND);
        relay contacts (OPENER_*) are only connected to the relay's contact set.

Both gen_sch.py and gen_pcb.py read this file, so schematic and PCB can never
disagree about connectivity.

Each part: ref -> dict(lib, val, fp, pins={pin_number: net}, extra fields)
A net name of None marks the pin as intentionally not connected.
"""

# --- footprints used repeatedly ------------------------------------------------
R0603 = "Resistor_SMD:R_0603_1608Metric"
R0805 = "Resistor_SMD:R_0805_2012Metric"
R1206 = "Resistor_SMD:R_1206_3216Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
C1206 = "Capacitor_SMD:C_1206_3216Metric"
C1210 = "Capacitor_SMD:C_1210_3225Metric"
SOT23 = "Package_TO_SOT_SMD:SOT-23"
SOD123 = "Diode_SMD:D_SOD-123"
SMA = "Diode_SMD:D_SMA"
SMB = "Diode_SMD:D_SMB"
LED0805 = "LED_SMD:LED_0805_2012Metric"
TB = "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-{n}-5.08_1x0{n}_P5.08mm_Horizontal"
TP = "TestPoint:TestPoint_Pad_D1.5mm"
SW_SMD = "Button_Switch_SMD:SW_SPST_TL3342"

PARTS = {}
BLOCK = {}          # ref -> schematic block name (for grouping)


def part(ref, lib, val, fp, pins, block, mpn="", note=""):
    assert ref not in PARTS, ref
    PARTS[ref] = dict(lib=lib, val=val, fp=fp, pins=pins, mpn=mpn, note=note)
    BLOCK[ref] = block


def R(ref, val, a, b, block, fp=R0603, mpn="", note=""):
    part(ref, "Device:R", val, fp, {"1": a, "2": b}, block, mpn, note)


def C(ref, val, a, b, block, fp=C0603, mpn="", note=""):
    part(ref, "Device:C", val, fp, {"1": a, "2": b}, block, mpn, note)


def D(ref, val, k, a, block, fp=SOD123, lib="Device:D", mpn="", note=""):
    part(ref, lib, val, fp, {"1": k, "2": a}, block, mpn, note)


def LED(ref, val, k, a, block, mpn="", note=""):
    part(ref, "Device:LED", val, LED0805, {"1": k, "2": a}, block, mpn, note)


def NFET(ref, val, g, d, block, mpn="", note=""):
    lib = "Transistor_FET:AO3400A" if val == "AO3400A" else "Device:Q_NMOS_GSD"
    part(ref, lib, val, SOT23, {"1": g, "2": "GND", "3": d}, block, mpn or val, note)


def TPT(ref, net, block):
    part(ref, "Connector:TestPoint", net, TP, {"1": net}, block)


# =============================================================================
# 1. POWER INPUT + 60 V BUCK (VIN -> 5.28 V)
# =============================================================================
B = "1 Power input + buck"
part("J1", "Connector:Screw_Terminal_01x02", "PWR 12-24V AC/DC", TB.format(n=2),
     {"1": "VIN_A", "2": "VIN_B"}, B, "Phoenix MKDS 1,5/2-5,08 (1715721) or any 5.08 mm clone",
     "Any polarity DC 9-36 V, or 24 VAC (opener accessory / class-2 transformer)")
part("F1", "Device:Polyfuse", "0.5A 60V", "Fuse:Fuse_Bourns_MF-RHT050",
     {"1": "VIN_A", "2": "VIN_AF"}, B, "Bourns MF-R050 (0.5 A hold, 60 V, radial 5.1 mm)")
part("D1", "Diode_Bridge:MB6S", "MB6S", "Package_TO_SOT_SMD:TO-269AA",
     {"1": "VIN_AF", "2": "VIN_B", "3": "VIN", "4": "GND"}, B, "Vishay/onsemi MB6S (0.5 A 600 V)",
     "makes the input polarity-proof and accepts 24 VAC")
D("D2", "SMBJ40A", "VIN", "GND", B, SMB, "Device:D_Zener", "Littelfuse SMBJ40A",
  "40 V standoff, 44.4 V min breakdown; above 24 VAC +10 % / +15 % no-load peak (41.6 V)")
part("C1", "Device:C_Polarized", "100uF 63V", "Capacitor_SMD:CP_Elec_10x10.5",
     {"1": "VIN", "2": "GND"}, B, "Panasonic EEE-FK1J101P (10x10.2, 105 C)")
part("C2", "Device:C_Polarized", "100uF 63V", "Capacitor_SMD:CP_Elec_10x10.5",
     {"1": "VIN", "2": "GND"}, B, "Panasonic EEE-FK1J101P", "2nd bulk cap: holds VIN up between 24 VAC half-cycles")
C("C3", "2.2uF 100V", "VIN", "GND", B, C1210, "Murata GRM32ER72A225KA35 (X7R)", "place at U1 VIN/GND")
C("C4", "100nF 100V", "VIN", "GND", B, C0805)
R("R1", "243k", "VIN", "BUCK_EN", B, note="UVLO: start 7.0 V, stop 6.0 V")
R("R2", "47.5k", "BUCK_EN", "GND", B)
part("U1", "Regulator_Switching:TPS54360DDA", "TPS54360DDA", "Package_SO:TI_SO-PowerPAD-8_ThermalVias",
     {"1": "BUCK_BOOT", "2": "VIN", "3": "BUCK_EN", "4": "BUCK_RT", "5": "BUCK_FB", "6": "BUCK_COMP",
      "7": "GND", "8": "BUCK_SW", "9": "GND"}, B, "TI TPS54360DDAR (4.5-60 V, 3.5 A)")
R("R3", "243k", "BUCK_RT", "GND", B, note="fsw = 400 kHz")
C("C5", "100nF", "BUCK_BOOT", "BUCK_SW", B, note="bootstrap")
D("D3", "B360A", "BUCK_SW", "GND", B, SMA, "Device:D_Schottky", "Diodes B360A-13-F (60 V 3 A)", "catch diode")
part("L1", "Device:L", "33uH 1.3A", "Inductor_SMD:L_Bourns_SRN6045TA",
     {"1": "BUCK_SW", "2": "BUCK_5V"}, B, "Bourns SRN6045TA-330M")
C("C6", "22uF 10V", "BUCK_5V", "GND", B, C1210, "X7R 1210")
C("C7", "22uF 10V", "BUCK_5V", "GND", B, C1210, "X7R 1210")
R("R4", "56k", "BUCK_5V", "BUCK_FB", B, note="Vout = 0.8*(1+56/10) = 5.28 V")
R("R5", "10k", "BUCK_FB", "GND", B)
R("R6", "4.12k", "BUCK_COMP", "BUCK_CZ", B, note="type II comp, fco ~14 kHz")
C("C8", "39nF", "BUCK_CZ", "GND", B)
C("C9", "180pF", "BUCK_COMP", "GND", B)
R("R7", "100k", "VIN", "VIN_SENSE", B, note="VIN/15.7 -> ADC (45 V = 2.87 V)")
R("R8", "6.8k", "VIN_SENSE", "GND", B)
C("C10", "100nF", "VIN_SENSE", "GND", B)

# =============================================================================
# 2. USB-C, 5 V OR-ING, 3.3 V
# =============================================================================
B = "2 USB-C + 5V/3V3 rails"
usb = {"A1": "GND", "B1": "GND", "A12": "GND", "B12": "GND",
       "A4": "VBUS", "A9": "VBUS", "B4": "VBUS", "B9": "VBUS",
       "A5": "USB_CC1", "B5": "USB_CC2", "A6": "USB_DP", "B6": "USB_DP",
       "A7": "USB_DN", "B7": "USB_DN", "A8": None, "B8": None, "S1": "USB_SHIELD"}
part("J2", "Connector:USB_C_Receptacle_USB2.0_16P", "USB-C",
     "Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal", usb, B,
     "GCT USB4105-GF-A", "native USB of the ESP32-S3: power + flashing + JTAG")
R("R9", "5.1k", "USB_CC1", "GND", B, note="UFP Rd")
R("R10", "5.1k", "USB_CC2", "GND", B, note="UFP Rd")
R("R11", "1M", "USB_SHIELD", "GND", B)
C("C11", "4.7nF", "USB_SHIELD", "GND", B, C0805)
part("F2", "Device:Polyfuse", "0.5A 6V", "Fuse:Fuse_1206_3216Metric",
     {"1": "VBUS", "2": "VBUS_F"}, B, "Littelfuse 1206L050YR")
part("U2", "Power_Protection:USBLC6-2SC6", "USBLC6-2SC6", SOT23 + "-6",
     {"1": "USB_DN", "6": "USB_DN", "3": "USB_DP", "4": "USB_DP", "2": "GND", "5": "VBUS_F"}, B,
     "ST USBLC6-2SC6")
D("D4", "SS34", "+5V", "BUCK_5V", B, SMA, "Device:D_Schottky", "SS34 (40 V 3 A)", "OR-ing: buck path")
D("D5", "SS34", "+5V", "VBUS_F", B, SMA, "Device:D_Schottky", "SS34 (40 V 3 A)", "OR-ing: USB path")
C("C12", "22uF 10V", "+5V", "GND", B, C1206)
part("U3", "Regulator_Linear:AP7361C-33E", "AP7361C-33E", "Package_TO_SOT_SMD:SOT-223-3_TabPin2",
     {"1": "+5V", "2": "GND", "3": "+3V3"}, B, "Diodes AP7361C-33E-13 (1 A, 0.36 V dropout)")
C("C13", "22uF 10V", "+3V3", "GND", B, C1206)
R("R12", "2.2k", "+3V3", "LED_PWR_A", B)
LED("D6", "GREEN PWR", "GND", "LED_PWR_A", B)

# =============================================================================
# 3. ESP32-S3 + PROGRAMMING
# =============================================================================
B = "3 ESP32-S3"
esp = {"1": "GND", "40": "GND", "41": "GND", "2": "+3V3", "3": "EN",
       "4": "VIN_SENSE",     # IO4  ADC1_CH3 (left side, faces the buck)
       "38": "EXP_ADC",      # IO2  ADC1_CH1
       "9": "IN_CLOSED",     # IO16
       "10": "IN_OPEN",      # IO17
       "11": "IN_AUX",       # IO18
       "7": "RELAY_CMD",     # IO7
       "12": "I2C_SDA",      # IO8
       "17": "I2C_SCL",      # IO9
       "18": "BUZZER_CMD",   # IO10
       "8": "WARN_CMD",      # IO15 (left side, faces the WARN terminal)
       "20": "WARN_LED",     # IO12
       "21": "RGB_DIN",      # IO13 (RMT)
       "22": "USER_BTN",     # IO14
       "31": "EXP_IO38", "32": "EXP_IO39", "33": "EXP_IO40", "34": "EXP_IO41",   # right side, next to J6
       "13": "USB_DN",       # IO19
       "14": "USB_DP",       # IO20
       "27": "BOOT",         # IO0 strap
       "37": "U0TXD", "36": "U0RXD",
       }
for p in ["5", "6", "15", "16", "19", "23", "24", "25", "26", "28", "29", "30", "35", "39"]:
    esp[p] = None           # IO3/IO45/IO46 are straps: left at their internal defaults
part("U4", "RF_Module:ESP32-S3-WROOM-1", "ESP32-S3-WROOM-1-N8R2", "RF_Module:ESP32-S3-WROOM-1", esp, B,
     "Espressif ESP32-S3-WROOM-1-N8R2", "antenna over the board edge, no copper under it")
C("C14", "22uF 10V", "+3V3", "GND", B, C1206, note="Wi-Fi TX burst reservoir")
C("C15", "100nF", "+3V3", "GND", B)
C("C16", "100nF", "+3V3", "GND", B)
R("R13", "10k", "+3V3", "EN", B)
C("C17", "1uF", "EN", "GND", B, note="EN delay per Espressif HW guide")
R("R14", "10k", "+3V3", "BOOT", B)
part("SW1", "Switch:SW_Push", "RESET", SW_SMD, {"1": "EN", "2": "GND"}, B, "E-Switch TL3342")
part("SW2", "Switch:SW_Push", "BOOT", SW_SMD, {"1": "BOOT", "2": "GND"}, B, "E-Switch TL3342")
part("SW3", "Switch:SW_Push", "USER", SW_SMD, {"1": "USER_BTN", "2": "GND"}, B, "E-Switch TL3342",
     "hold 10 s at boot = factory reset / provisioning portal")
R("R15", "10k", "+3V3", "USER_BTN", B)
part("J5", "Connector_Generic:Conn_02x03_Odd_Even", "ESP-PROG", "Connector_PinHeader_2.54mm:PinHeader_2x03_P2.54mm_Vertical",
     {"1": "EN", "2": "+3V3", "3": "U0TXD", "4": "GND", "5": "U0RXD", "6": "BOOT"}, B,
     note="ESP-Prog 'Program' pinout: 1 EN, 2 VDD, 3 TXD, 4 GND, 5 RXD, 6 IO0 (auto-reset is on the ESP-Prog)")
part("J6", "Connector_Generic:Conn_01x08", "EXPANSION", "Connector_PinHeader_2.54mm:PinHeader_1x08_P2.54mm_Vertical",
     {"1": "+3V3", "2": "EXP_ADC", "3": "EXP_IO38", "4": "EXP_IO39", "5": "EXP_IO40", "6": "EXP_IO41",
      "7": "+5V", "8": "GND"}, B, note="CT clamp (IO2 = ADC1), UART1 (IO40/41), spare GPIO")

# =============================================================================
# 4. SENSORS + USER INTERFACE
# =============================================================================
B = "4 Sensors + UI"
part("U5", "Sensor:BME280", "BME280", "Package_LGA:Bosch_LGA-8_2.5x2.5mm_P0.65mm_ClockwisePinNumbering",
     {"1": "GND", "7": "GND", "2": "+3V3", "3": "I2C_SDA", "4": "I2C_SCL", "5": "GND",
      "6": "+3V3", "8": "+3V3"}, B, "Bosch BME280", "I2C addr 0x76 (SDO=GND); thermally isolated by slots")
C("C18", "100nF", "+3V3", "GND", B)
R("R16", "4.7k", "+3V3", "I2C_SDA", B)
R("R17", "4.7k", "+3V3", "I2C_SCL", B)
part("J7", "Connector_Generic:Conn_01x04", "QWIIC", "Connector_JST:JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal",
     {"1": "GND", "2": "+3V3", "3": "I2C_SDA", "4": "I2C_SCL", "MP": None}, B, "JST SM04B-SRSS-TB",
     "Qwiic/STEMMA QT: e.g. VL53L1X time-of-flight door observer")
part("D7", "LED:WS2812B", "WS2812B", "LED_SMD:LED_WS2812B_PLCC4_5.0x5.0mm_P3.2mm",
     {"1": "RGB_VDD", "2": None, "3": "GND", "4": "RGB_DI"}, B, "Worldsemi WS2812B", "status LED")
D("D8", "1N4148W", "RGB_VDD", "+5V", B, note="drops VDD to ~4.3 V so 3.3 V logic meets VIH = 0.7 VDD")
C("C19", "100nF", "RGB_VDD", "GND", B)
R("R18", "33R", "RGB_DIN", "RGB_DI", B)
R("R19", "150R", "WARN_LED", "LED_WARN_A", B)
LED("D9", "RED WARN", "GND", "LED_WARN_A", B, note="flashes during the pre-close warning (SR1)")
part("BZ1", "Device:Buzzer", "BUZZER 5V", "Buzzer_Beeper:Buzzer_12x9.5RM7.6",
     {"1": "+5V", "2": "BUZ_N"}, B, "CUI CMI-1295IC-0585T (5 V, 85 dB, self-drive)")
NFET("Q1", "AO3400A", "BUZ_G", "BUZ_N", B)
R("R20", "100R", "BUZZER_CMD", "BUZ_G", B)
R("R21", "100k", "BUZ_G", "GND", B)
D("D10", "1N4148W", "+5V", "BUZ_N", B)

# =============================================================================
# 5. RELAY (opener wall-button contact) WITH HARDWARE PULSE LIMIT
# =============================================================================
B = "5 Relay"
part("K1", "Relay:G5V-1", "G5V-1 5VDC", "Relay_THT:Relay_SPDT_Omron_G5V-1",
     {"2": "+5V", "9": "RLY_N", "5": "OPENER_COM", "6": "OPENER_COM", "1": "OPENER_NC", "10": "OPENER_NO"}, B,
     "Omron G5V-1-DC5", "contacts 0.5 A 125 VAC / 1 A 24 VDC; only OPENER_* nets touch them")
NFET("Q2", "AO3400A", "RLY_G", "RLY_N", B)
R("R22", "100R", "RELAY_CMD", "RLY_AC", B)
C("C20", "10uF 25V", "RLY_AC", "RLY_G", B, C1206,
  note="AC coupling: a GPIO stuck high releases the relay after ~0.7 s (SR4)")
R("R23", "100k", "RLY_G", "GND", B, note="tau = 1 s; also holds the FET off through reset/boot")
D("D11", "1N4148W", "RLY_G", "GND", B, note="clamps the negative gate swing so the next pulse is full height")
D("D12", "1N4148W", "+5V", "RLY_N", B, note="coil flyback")
R("R24", "1k", "+5V", "LED_RLY_A", B)
LED("D13", "YELLOW RELAY", "RLY_N", "LED_RLY_A", B)
part("J3", "Connector:Screw_Terminal_01x03", "OPENER NC/COM/NO", TB.format(n=3),
     {"1": "OPENER_NC", "2": "OPENER_COM", "3": "OPENER_NO"}, B, "Phoenix MKDS 1,5/3-5,08",
     "COM+NO in parallel with the wall button")

# =============================================================================
# 6. WARNING OUTPUT (external strobe / sounder, switched from VIN)
# =============================================================================
B = "6 Warning output"
part("J4", "Connector:Screw_Terminal_01x02", "WARN OUT", TB.format(n=2),
     {"1": "VIN", "2": "WARN_N"}, B, "Phoenix MKDS 1,5/2-5,08", "VIN (rectified), low-side switched, 300 mA")
NFET("Q3", "IRLML0060", "WARN_G", "WARN_N", B, "Infineon IRLML0060TRPBF (60 V)")
R("R25", "100R", "WARN_CMD", "WARN_G", B)
R("R26", "100k", "WARN_G", "GND", B)
D("D14", "B360A", "VIN", "WARN_N", B, SMA, "Device:D_Schottky", "Diodes B360A-13-F", "freewheel for inductive sounders")

# =============================================================================
# 7. ISOLATED DOOR-POSITION INPUTS
# =============================================================================
B = "7 Isolated inputs"
part("PS1", "Converter_DCDC:MEE1S0505SC", "MEE1S0505SC", "Converter_DCDC:Converter_DCDC_Murata_MEE1SxxxxSC_THT",
     {"1": "GND", "2": "+5V", "3": "FGND", "4": "FIELD_V"}, B, "Murata MEE1S0505SC (1 W, 3 kVDC)")
C("C21", "4.7uF", "+5V", "GND", B, C0805)
C("C22", "1uF 25V", "FIELD_V", "FGND", B, C0805)
R("R27", "2.2k", "FIELD_V", "FGND", B, R0805,
  note="pre-load keeps the unregulated output near 5 V")
D("D15", "SMAJ12A", "FIELD_V", "FGND", B, SMA, "Device:D_Zener", "Littelfuse SMAJ12A")
part("J8", "Connector:Screw_Terminal_01x05", "DOOR SENSORS", TB.format(n=5),
     {"1": "FIELD_V", "2": "FIN_CLOSED", "3": "FIN_OPEN", "4": "FIN_AUX", "5": "FGND"}, B,
     "Phoenix MKDS 1,5/5-5,08", "reed switches from COM (pin 1) to each input; pin 5 = cable shield")
for name, nr, nd, nu, nc, rp, cl in (("CLOSED", "R28", "D16", "U6", "C23", "R31", "C26"),
                                     ("OPEN", "R29", "D17", "U7", "C24", "R32", "C27"),
                                     ("AUX", "R30", "D18", "U8", "C25", "R33", "C28")):
    C(nc, "10nF 50V", f"FIN_{name}", "FGND", B, C0805, note="field-side HF filter")
    R(nr, "390R", f"FIN_{name}", f"FLED_{name}", B, R1206, note="~6 mA loop, 1206 for surge")
    LED(nd, f"RED {name}", f"FOPTO_{name}", f"FLED_{name}", B,
        note="lights when the reed closes, with or without firmware")
    part(nu, "Isolator:PC817", "PC817", "Package_DIP:SMDIP-4_W9.53mm",
         {"1": f"FOPTO_{name}", "2": "FGND", "3": "GND", "4": f"IN_{name}"}, B, "Sharp/Everlight PC817 (gull-wing)")
    R(rp, "10k", "+3V3", f"IN_{name}", B)
    C(cl, "10nF", f"IN_{name}", "GND", B)

# =============================================================================
# 8. TEST POINTS + MECHANICAL
# =============================================================================
B = "8 Test points + mechanical"
for i, net in enumerate(["VIN", "+5V", "+3V3", "GND", "BUCK_SW", "RLY_G", "FIELD_V", "FGND",
                         "IN_CLOSED", "IN_OPEN", "GND"]):
    TPT(f"TP{i + 1}", net, B)
for i in range(1, 5):
    part(f"H{i}", "Mechanical:MountingHole", "M3", "MountingHole:MountingHole_3.2mm_M3", {}, B)

# PWR_FLAGs for nets driven only by passive pins (keeps KiCad ERC clean)
PWR_FLAGS = ["VIN", "GND", "+5V", "RGB_VDD", "BUCK_5V", "VBUS_F"]


def nets():
    n = {}
    for ref, p in PARTS.items():
        for pin, net in p["pins"].items():
            if net is not None:
                n.setdefault(net, []).append((ref, pin))
    return n


if __name__ == "__main__":
    n = nets()
    bad = {k: v for k, v in n.items() if len(v) < 2}
    print(len(PARTS), "parts,", len(n), "nets")
    print("single-pin nets:", bad)
