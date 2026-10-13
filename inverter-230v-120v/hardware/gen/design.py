"""
Single source of truth for the 230 VAC -> 120 VAC / 1200 W converter.

Topology: input EMI/protection -> NTC inrush limiter (relay bypass) -> bridge
-> UCC28180 CCM boost PFC (400 V bus) -> SiC full-bridge inverter, unipolar
SPWM -> LC filter -> 120 VAC 50 Hz.  ESP32 controller referenced to the bus
ground (HOT), programmed through a Si8641 digital isolator.

Both gen_sch.py and gen_pcb.py read this file, so schematic and PCB can never
disagree about connectivity.

Each part: ref -> dict(lib, val, fp, pins={pin_number: net}, extra fields)
A net name of None marks the pin as intentionally not connected.
"""

# --- footprints used repeatedly ------------------------------------------------
R0805 = "Resistor_SMD:R_0805_2012Metric"
R1206 = "Resistor_SMD:R_1206_3216Metric"
R2512 = "Resistor_SMD:R_2512_6332Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
C1206 = "Capacitor_SMD:C_1206_3216Metric"
SOIC8 = "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"
SOT23 = "Package_TO_SOT_SMD:SOT-23"
SOD123 = "Diode_SMD:D_SOD-123"
TO247 = "Package_TO_SOT_THT:TO-247-3_Vertical"
TOROID = "Inductor_THT:L_Toroid_Vertical_L67.6mm_W36.1mm_P31.80mm_Vishay_TJ9"
FUSE = "Fuse:Fuseholder_Cylinder-6.3x32mm_Schurter_0031-8002_Horizontal_Open"
TERM2 = "TerminalBlock_MetzConnect:TerminalBlock_MetzConnect_Type067_RT01902HDWC_1x02_P10.00mm_Horizontal"
SNAPIN = "Capacitor_THT:CP_Radial_D35.0mm_P10.00mm_3pin_SnapIn"
LED0805 = "LED_SMD:LED_0805_2012Metric"

PARTS = {}
BLOCK = {}          # ref -> schematic block name (for grouping)


def part(ref, lib, val, fp, pins, block, mpn="", note=""):
    assert ref not in PARTS, ref
    PARTS[ref] = dict(lib=lib, val=val, fp=fp, pins=pins, mpn=mpn, note=note)
    BLOCK[ref] = block


def R(ref, val, a, b, block, fp=R0805, mpn="", note=""):
    part(ref, "Device:R", val, fp, {"1": a, "2": b}, block, mpn, note)


def C(ref, val, a, b, block, fp=C0805, mpn="", note=""):
    part(ref, "Device:C", val, fp, {"1": a, "2": b}, block, mpn, note)


def CP(ref, val, pos, neg, block, fp, mpn="", note=""):
    part(ref, "Device:C_Polarized", val, fp, {"1": pos, "2": neg}, block, mpn, note)


# =============================================================================
# 1. AC INPUT, PROTECTION, INRUSH
# =============================================================================
B = "1 AC input / inrush"
part("J1", "Connector:Screw_Terminal_01x02", "AC IN 230V", TERM2,
     {"1": "AC_L_IN", "2": "AC_N"}, B, "Metz RT01902HDWC 10 mm pitch",
     "Feed from IEC inlet filter e.g. Schaffner FN9260/FN9264-10 (10 A). PE goes inlet->chassis->outlet, not via PCB")
part("F1", "Device:Fuse", "T10A 250V", FUSE, {"1": "AC_L_IN", "2": "AC_L"}, B,
     "Schurter 0031.8002 holder + 6.3x32 T10A ceramic")
part("RV1", "Device:Varistor", "275VAC", "Varistor:RV_Disc_D15.5mm_W5.9mm_P7.5mm",
     {"1": "AC_L", "2": "AC_N"}, B, "TDK S14K275")
part("C1", "Device:C", "1uF X2 275VAC", "Capacitor_THT:C_Rect_L31.5mm_W13.0mm_P27.50mm_MKS4",
     {"1": "AC_L", "2": "AC_N"}, B, "KEMET R46KR410000M1M / WIMA MKP X2")
R("R1", "470k", "AC_L", "XBLD", B, R2512, note="X-cap discharge")
R("R2", "470k", "XBLD", "AC_N", B, R2512, note="X-cap discharge")
part("TH1", "Device:Thermistor_NTC", "5R 8A", "Varistor:RV_Disc_D15.5mm_W5.9mm_P7.5mm",
     {"1": "AC_L", "2": "AC_L_R"}, B, "TDK B57237S0509M000 (S237, 5 ohm, 8 A)")
part("K1", "Relay:G2RL-1-E", "G2RL-1-E 12VDC", "Relay_THT:Relay_SPDT_Omron_G2RL-1-E",
     {"11": "AC_L", "14": "AC_L_R", "12": None, "A1": "+12V", "A2": "RLY_COIL"}, B,
     "Omron G2RL-1-E DC12 (16 A)")
part("Q2", "Transistor_BJT:MMBT3904", "MMBT3904", SOT23,
     {"1": "RLY_B", "2": "GND", "3": "RLY_COIL"}, B)
R("R3", "1k", "RELAY_EN", "RLY_B", B)
R("R4", "10k", "RLY_B", "GND", B)
part("D3", "Device:D", "1N4148W", SOD123, {"1": "+12V", "2": "RLY_COIL"}, B)

# =============================================================================
# 2. AUXILIARY SUPPLIES (outputs referenced to bus GND = HOT)
# =============================================================================
B = "2 Aux supplies"
part("PS1", "Converter_ACDC:IRM-10-15", "IRM-10-15", "Converter_ACDC:Converter_ACDC_MeanWell_IRM-10-xx_THT",
     {"1": "AC_N", "2": "AC_L", "3": "GND", "4": "VCC15"}, B, "Mean Well IRM-10-15")
part("PS2", "Converter_ACDC:IRM-05-5", "IRM-05-5", "Converter_ACDC:Converter_ACDC_MeanWell_IRM-05-xx_THT",
     {"1": "AC_N", "2": "AC_L", "3": "GND", "4": "+5V"}, B, "Mean Well IRM-05-5")
CP("C2", "47uF 25V", "VCC15", "GND", B, "Capacitor_THT:CP_Radial_D6.3mm_P2.50mm")
CP("C3", "100uF 10V", "+5V", "GND", B, "Capacitor_THT:CP_Radial_D6.3mm_P2.50mm")
part("U1", "Regulator_Linear:L7812", "L7812", "Package_TO_SOT_THT:TO-220-3_Vertical",
     {"1": "VCC15", "2": "GND", "3": "+12V"}, B, "ST L7812CV")
C("C4", "330nF", "VCC15", "GND", B)
C("C5", "100nF", "+12V", "GND", B)
part("U2", "Regulator_Linear:AMS1117-3.3", "AMS1117-3.3", "Package_TO_SOT_SMD:SOT-223-3_TabPin2",
     {"1": "GND", "2": "+3V3", "3": "+5V"}, B)
C("C6", "10uF", "+5V", "GND", B)
C("C7", "22uF", "+3V3", "GND", B, C1206)

# =============================================================================
# 3. RECTIFIER + PFC BOOST
# =============================================================================
B = "3 Rectifier + PFC"
part("BR1", "Device:D_Bridge_+AA-", "GBU15J", "Diode_THT:Diode_Bridge_Vishay_GBU",
     {"1": "RECT_P", "2": "AC_L_R", "3": "AC_N", "4": "RECT_N"}, B,
     "Vishay GBU15J or Diodes GBU1506 (15 A 600 V) - on heatsink")
part("C8", "Device:C", "1uF 630VDC", "Capacitor_THT:C_Rect_L26.5mm_W8.5mm_P22.50mm_MKS4",
     {"1": "RECT_P", "2": "RECT_N"}, B, "WIMA MKP4 1uF 630VDC", "PFC input HF cap")
R("RS1", "40m 2W", "RECT_N", "GND", B, R2512, "Vishay WSL2512R0400 (or Bourns CRA2512)", "PFC shunt (2 in parallel = 20 mOhm)")
R("RS2", "40m 2W", "RECT_N", "GND", B, R2512, "Vishay WSL2512R0400")
part("L1", "Device:L", "450uH 15A", TOROID, {"1": "RECT_P", "2": "SW_PFC"}, B,
     "2x Magnetics 0077439A7 Kool Mu 60u stacked, ~70 T 1.6 mm (or custom)")
part("D1", "Device:D", "1N5408", "Diode_THT:D_DO-201AD_P15.24mm_Horizontal",
     {"1": "VBUS", "2": "RECT_P"}, B, note="Inrush bypass around L1/D2")
part("Q1", "Device:Q_NMOS_GDS", "IPW65R045C7", TO247,
     {"1": "PFC_G", "2": "SW_PFC", "3": "GND"}, B, "Infineon IPW65R045C7 - on heatsink")
part("D2", "Device:D", "C6D10065A", "Package_TO_SOT_THT:TO-220-2_Vertical",
     {"1": "VBUS", "2": "SW_PFC"}, B, "Wolfspeed C6D10065A SiC 650 V 10 A - on heatsink")
R("R5", "4R7", "PFC_GATE", "PFC_G", B)
R("R6", "10k", "PFC_G", "GND", B)
part("U3", "inverter:UCC28180", "UCC28180", SOIC8,
     {"1": "GND", "2": "PFC_ICOMP", "3": "PFC_ISNS", "4": "PFC_FREQ",
      "5": "PFC_VCOMP", "6": "PFC_VSNS", "7": "PFC_VCC", "8": "PFC_GATE"}, B,
     "TI UCC28180DR")
C("C9", "1nF", "PFC_ICOMP", "GND", B, note="tune w/ TI calculator")
R("R7", "220R", "RECT_N", "PFC_ISNS", B)
C("C10", "100pF", "PFC_ISNS", "GND", B)
R("R8", "33k2", "PFC_FREQ", "GND", B, note="~65 kHz, check datasheet eq.")
R("R9", "22k", "PFC_VCOMP", "PFC_VCZ", B, note="tune w/ TI calculator")
C("C11", "2.2uF", "PFC_VCZ", "GND", B)
C("C12", "100nF", "PFC_VCOMP", "GND", B)
R("R10", "1M2", "VBUS", "PFC_VS1", B, R2512)
R("R11", "1M2", "PFC_VS1", "PFC_VS2", B, R1206)
R("R12", "1M2", "PFC_VS2", "PFC_VSNS", B, R1206)
R("R13", "45k3", "PFC_VSNS", "GND", B, note="0.1%; sets 402 V bus")
C("C13", "1nF", "PFC_VSNS", "GND", B)
part("Q3", "Transistor_BJT:MMBT3904", "MMBT3904", SOT23,
     {"1": "PFC_DIS_B", "2": "GND", "3": "PFC_VSNS"}, B, note="pulls VSENSE low = PFC off")
R("R14", "4k7", "PFC_DIS", "PFC_DIS_B", B)
R("R15", "10k", "+3V3", "PFC_DIS", B, note="PFC off by default")
R("R16", "10R", "VCC15", "PFC_VCC", B)
C("C14", "10uF 25V", "PFC_VCC", "GND", B, C1206)
C("C15", "100nF", "PFC_VCC", "GND", B)

# =============================================================================
# 4. DC BUS
# =============================================================================
B = "4 DC bus 400V"
for i, ref in enumerate(["C16", "C17", "C18"]):
    CP(ref, "390uF 450V", "VBUS", "GND", B, SNAPIN, "Nichicon LGU2W391MELB / Rubycon 450MXK390 (35x45)")
part("C19", "Device:C", "1uF 630VDC", "Capacitor_THT:C_Rect_L26.5mm_W8.5mm_P22.50mm_MKS4",
     {"1": "VBUS", "2": "GND"}, B, "WIMA MKP4 1uF 630V", "leg A decoupling")
part("C20", "Device:C", "1uF 630VDC", "Capacitor_THT:C_Rect_L26.5mm_W8.5mm_P22.50mm_MKS4",
     {"1": "VBUS", "2": "GND"}, B, "WIMA MKP4 1uF 630V", "leg B decoupling")
part("C44", "Device:C", "100nF 630VDC", "Capacitor_THT:C_Rect_L18.0mm_W6.0mm_P15.00mm_FKS3_FKP3",
     {"1": "VBUS", "2": "GND"}, B, "WIMA FKP3/MKP 100nF 630V", "PFC D2-Q1 HF loop cap, place at D2/Q1")
R("R17", "27k 1W", "VBUS", "BLD1", B, R2512, note="bleeder")
R("R18", "27k 1W", "BLD1", "BLD2", B, R2512)
R("R19", "27k 1W", "BLD2", "BLD3", B, R2512)
R("R20", "27k 1W", "BLD3", "BLD4", B, R2512)
part("D4", "Device:LED", "RED BUS LIVE", LED0805, {"1": "GND", "2": "BLD4"}, B,
     note="lit while bus > ~30 V")
R("R21", "1M", "VBUS", "VBS1", B, R2512)
R("R22", "1M", "VBS1", "VBS2", B, R1206)
R("R23", "1M", "VBS2", "VBS3", B, R1206)
R("R24", "1M", "VBS3", "VBUS_SENSE", B, R1206)
R("R25", "22k", "VBUS_SENSE", "GND", B, note="2.19 V @ 400 V")
C("C21", "100nF", "VBUS_SENSE", "GND", B)

# =============================================================================
# 5. FULL-BRIDGE INVERTER
# =============================================================================
B = "5 Inverter bridge"
part("Q5", "Device:Q_NMOS_GDS", "C3M0060065D", TO247, {"1": "QAH_G", "2": "VBUS", "3": "SW_A"}, B,
     "Wolfspeed C3M0060065D SiC - on heatsink")
part("Q6", "Device:Q_NMOS_GDS", "C3M0060065D", TO247, {"1": "QAL_G", "2": "SW_A", "3": "GND"}, B,
     "Wolfspeed C3M0060065D SiC - on heatsink")
part("Q7", "Device:Q_NMOS_GDS", "C3M0060065D", TO247, {"1": "QBH_G", "2": "VBUS", "3": "SW_B"}, B,
     "Wolfspeed C3M0060065D SiC - on heatsink")
part("Q8", "Device:Q_NMOS_GDS", "C3M0060065D", TO247, {"1": "QBL_G", "2": "SW_B", "3": "GND"}, B,
     "Wolfspeed C3M0060065D SiC - on heatsink")
for leg, U, (rlo, rho, dbs, cbs, cvcc, cvc2, rgh, rgl, rin, cin) in (
        ("A", "U4", ("R26", "R27", "D5", "C22", "C23", "C24", "R28", "R29", "R30", "C25")),
        ("B", "U5", ("R31", "R32", "D6", "C26", "C27", "C28", "R33", "R34", "R35", "C29"))):
    part(U, "Driver_FET:IR21844", "IR21844S", "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
         {"1": f"PWM_{leg}_D", "2": "INV_SD_N", "3": "GND", "4": "GND", "5": "GND", "6": f"LO_{leg}",
          "7": "VCC15", "8": None, "9": None, "10": None, "11": f"SW_{leg}", "12": f"HO_{leg}",
          "13": f"VB_{leg}", "14": None}, B, "Infineon IR21844STRPBF",
         "DT tied to VSS = minimum (~0.4 us) dead time; HV pins isolated on one side")
    R(rlo, "10R", f"LO_{leg}", f"Q{leg}L_G", B)
    R(rho, "10R", f"HO_{leg}", f"Q{leg}H_G", B)
    part(dbs, "Device:D", "ES1J", "Diode_SMD:D_SMA", {"1": f"VB_{leg}", "2": "VCC15"}, B,
         note="bootstrap 600 V fast")
    C(cbs, "1uF 50V", f"VB_{leg}", f"SW_{leg}", B, C1206, note="bootstrap")
    C(cvcc, "10uF 25V", "VCC15", "GND", B, C1206)
    C(cvc2, "100nF", "VCC15", "GND", B)
    R(rgh, "10k", f"Q{leg}H_G", f"SW_{leg}", B)
    R(rgl, "10k", f"Q{leg}L_G", "GND", B)
    R(rin, "100R", f"PWM_{leg}", f"PWM_{leg}_D", B)
    C(cin, "100pF", f"PWM_{leg}_D", "GND", B)
R("R36", "1k", "INV_EN", "INV_SD_N", B, note="MCU enable; LM393 can override low")
R("R37", "10k", "INV_SD_N", "GND", B, note="bridge off by default")

# =============================================================================
# 6. OUTPUT FILTER + SENSING
# =============================================================================
B = "6 Output filter + sensing"
part("L2", "Device:L", "150uH 20A", TOROID, {"1": "SW_A", "2": "OUT_LA"}, B,
     "Kool Mu 0077439A7 ~45 T 1.8 mm (Isat >= 20 A)")
part("L3", "Device:L", "150uH 20A", TOROID, {"1": "SW_B", "2": "OUT_N"}, B,
     "Kool Mu 0077439A7 ~45 T 1.8 mm (Isat >= 20 A)")
part("U6", "Sensor_Current:ACS724xLCTR-20AB", "ACS724LLCTR-20AB", SOIC8,
     {"1": "OUT_LA", "2": "OUT_LA", "3": "OUT_LF", "4": "OUT_LF",
      "5": "GND", "6": "GND", "7": "IOUT_RAW", "8": "+5V"}, B,
     "Allegro ACS724LLCTR-20AB-T", "pin 6 = BW_SEL tied GND")
C("C30", "100nF", "+5V", "GND", B)
part("C31", "Device:C", "3.3uF X2 275VAC", "Capacitor_THT:C_Rect_L31.5mm_W17.0mm_P27.50mm_MKS4",
     {"1": "OUT_LF", "2": "OUT_N"}, B, "KEMET R46 3.3uF X2 / WIMA MKP X2")
part("F2", "Device:Fuse", "T12.5A 250V", FUSE, {"1": "OUT_LF", "2": "OUT_L"}, B,
     "Schurter 0031.8002 holder + 6.3x32 T12.5A")
part("J2", "Connector:Screw_Terminal_01x02", "AC OUT 120V", TERM2,
     {"1": "OUT_L", "2": "OUT_N"}, B, "Metz RT01902HDWC 10 mm pitch",
     "NOT isolated from mains - neither pin is neutral/earth")
# differential output voltage amp, Vout = VREF + 0.007*(V_LF - V_N)
for i, (a, b) in enumerate([("OUT_LF", "VOL1"), ("VOL1", "VOL2"), ("VOL2", "VOL3"), ("VOL3", "VOP")]):
    R(f"R{38+i}", "1M", a, b, B, R2512 if i == 0 else R1206)
for i, (a, b) in enumerate([("OUT_N", "VON1"), ("VON1", "VON2"), ("VON2", "VON3"), ("VON3", "VON")]):
    R(f"R{42+i}", "1M", a, b, B, R2512 if i == 0 else R1206)
R("R46", "28k 0.1%", "VOP", "VREF", B)
R("R47", "28k 0.1%", "VON", "VOUT_AMP", B)
part("U7", "Amplifier_Operational:TLV9062xD", "TLV9062IDR", SOIC8,
     {"3": "VOP", "2": "VON", "1": "VOUT_AMP",
      "5": "VREF_DIV", "6": "VREF", "7": "VREF",
      "8": "+5V", "4": "GND"}, B, "TI TLV9062IDR")
C("C32", "100nF", "+5V", "GND", B)
R("R48", "1k", "VOUT_AMP", "VOUT_SENSE", B)
C("C33", "10nF", "VOUT_SENSE", "GND", B)
R("R49", "10k", "+3V3", "VREF_DIV", B)
R("R50", "10k", "VREF_DIV", "GND", B)
C("C34", "100nF", "VREF_DIV", "GND", B)
# current: ACS724 2.5 V +/-100 mV/A -> 2/3 divider -> ESP32 ADC
R("R51", "10k", "IOUT_RAW", "IOUT_SENSE", B)
R("R52", "20k", "IOUT_SENSE", "GND", B)
C("C35", "1nF", "IOUT_SENSE", "GND", B)
# hardware over-current trip at +/-19 A -> pulls INV_SD_N low (cycle by cycle)
part("U8", "Comparator:LM393", "LM393", SOIC8,
     {"3": "VTH_H", "2": "IOUT_RAW", "1": "INV_SD_N",
      "5": "IOUT_RAW", "6": "VTH_L", "7": "INV_SD_N",
      "8": "VCC15", "4": "GND"}, B, "TI LM393DR")
C("C36", "100nF", "VCC15", "GND", B)
R("R53", "1k", "+5V", "VTH_H", B, note="4.40 V = +19 A")
R("R54", "6k34", "VTH_H", "VTH_L", B)
R("R55", "1k", "VTH_L", "GND", B, note="0.60 V = -19 A")
C("C37", "100nF", "VTH_H", "GND", B)

# =============================================================================
# 7. CONTROLLER (ESP32) + ISOLATED PROGRAMMING PORT
# =============================================================================
B = "7 ESP32 controller"
esp = {"1": "GND", "15": "GND", "38": "GND", "39": "GND", "2": "+3V3", "3": "EN",
       "4": "VBUS_SENSE",   # IO36  ADC1_CH0
       "5": "VOUT_SENSE",   # IO39  ADC1_CH3
       "6": "IOUT_SENSE",   # IO34  ADC1_CH6
       "7": "TEMP_NTC",     # IO35  ADC1_CH7
       "8": "RELAY_EN",     # IO32
       "9": "PFC_DIS",      # IO33
       "10": "PWM_A",       # IO25  MCPWM0A
       "11": "PWM_B",       # IO26  MCPWM0B
       "12": "INV_EN",      # IO27
       "16": "INV_SD_N",    # IO13  fault read-back (MCPWM fault input)
       "25": "BOOT",        # IO0
       "26": "FAN_PWM",     # IO4
       "34": "ESP_RXD",     # RXD0
       "35": "ESP_TXD",     # TXD0
       "37": "LED_STAT",    # IO23
       }
for p in ["13", "14", "17", "18", "19", "20", "21", "22", "23", "24", "27", "28", "29",
          "30", "31", "32", "33", "36"]:
    esp[p] = None
part("U9", "RF_Module:ESP32-WROOM-32E", "ESP32-WROOM-32E-N4", "RF_Module:ESP32-WROOM-32D", esp, B,
     "Espressif ESP32-WROOM-32E-N4")
C("C38", "10uF", "+3V3", "GND", B)
C("C39", "100nF", "+3V3", "GND", B)
R("R56", "10k", "+3V3", "EN", B)
C("C40", "1uF", "EN", "GND", B)
R("R57", "10k", "+3V3", "BOOT", B)
part("SW1", "Switch:SW_Push", "RESET", "Button_Switch_SMD:SW_SPST_TL3342", {"1": "EN", "2": "GND"}, B)
part("SW2", "Switch:SW_Push", "BOOT", "Button_Switch_SMD:SW_SPST_TL3342", {"1": "BOOT", "2": "GND"}, B)
# classic DTR/RTS auto-program pair (after the isolator)
part("Q9", "Transistor_BJT:MMBT3904", "MMBT3904", SOT23, {"1": "Q9_B", "2": "RTS_H", "3": "EN"}, B)
part("Q10", "Transistor_BJT:MMBT3904", "MMBT3904", SOT23, {"1": "Q10_B", "2": "DTR_H", "3": "BOOT"}, B)
R("R58", "10k", "DTR_H", "Q9_B", B)
R("R59", "10k", "RTS_H", "Q10_B", B)
R("R60", "1k", "LED_STAT", "LED_A", B)
part("D7", "Device:LED", "GREEN STATUS", LED0805, {"1": "GND", "2": "LED_A"}, B)
R("R61", "10k", "+3V3", "TEMP_NTC", B, note="with 10k NTC on heatsink")
C("C41", "100nF", "TEMP_NTC", "GND", B)
part("J4", "Connector_Generic:Conn_01x02", "HEATSINK NTC", "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical",
     {"1": "TEMP_NTC", "2": "GND"}, B, "10k B3950 NTC glued to heatsink, insulated")
part("J5", "Connector_Generic:Conn_01x02", "FAN 12V", "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical",
     {"1": "+12V", "2": "FAN_N"}, B)
part("Q11", "Device:Q_NMOS_GSD", "AO3400A", SOT23, {"1": "FAN_G", "2": "GND", "3": "FAN_N"}, B)
R("R62", "100R", "FAN_PWM", "FAN_G", B)
R("R63", "100k", "FAN_G", "GND", B)
part("D8", "Device:D", "1N4148W", SOD123, {"1": "+12V", "2": "FAN_N"}, B)

B = "8 Isolated prog port + mechanical"
part("U10", "Isolator:Si8641ED-B-IS", "Si8641ED-B-IS", "Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm",
     {"1": "PROG_3V3", "2": "PROG_GND", "3": "PROG_TXD", "4": "PROG_DTR", "5": "PROG_RTS",
      "6": "PROG_RXD", "7": "PROG_3V3", "8": "PROG_GND", "9": "GND", "10": "+3V3",
      "11": "ESP_TXD", "12": "RTS_H", "13": "DTR_H", "14": "ESP_RXD", "15": "GND", "16": "+3V3"}, B,
     "Skyworks Si8641ED-B-IS (5 kVrms, default-high outputs)")
C("C42", "100nF", "PROG_3V3", "PROG_GND", B)
C("C43", "100nF", "+3V3", "GND", B)
part("J3", "Connector_Generic:Conn_01x06", "PROG (ISOLATED)", "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical",
     {"1": "PROG_GND", "2": "PROG_3V3", "3": "PROG_RXD", "4": "PROG_RTS", "5": "PROG_DTR", "6": "PROG_TXD"}, B,
     note="1 GND, 2 3V3, 3 to adapter RX, 4 RTS, 5 DTR, 6 from adapter TX (order matches U10 pins)")

# mounting holes: unplated, 7.5 mm copper keepout each (screws/standoffs go to chassis = PE)
B = "8 Isolated prog port + mechanical"
for i in range(1, 5):
    part(f"H{i}", "Mechanical:MountingHole", "M3", "MountingHole:MountingHole_3.2mm_M3", {}, B)

# PWR_FLAGs for nets driven only by passive pins (keeps KiCad ERC clean)
PWR_FLAGS = ["AC_L", "AC_N", "PFC_VCC", "PROG_3V3", "PROG_GND", "GND", "VBUS"]


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
