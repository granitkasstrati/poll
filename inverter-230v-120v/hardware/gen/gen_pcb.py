"""
Build inv1200.kicad_pcb from design.py with KiCad 7's pcbnew API.
Run with python3.12 (the interpreter KiCad's pcbnew module is built for).

Stages:  place  -> footprints, outline, net classes, rules
         (route.py does power copper, autorouting and zones)
"""
import json
import os
import sys
import uuid

import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
import design  # noqa: E402

HW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PCB = os.path.join(HW, "inv1200.kicad_pcb")
PRO = os.path.join(HW, "inv1200.kicad_pro")
FPLIB = "/usr/share/kicad/footprints/"
NS = uuid.UUID("6b1c3c52-3b39-4a8e-9f35-0d7f3a8b1200")
W, H = 315.0, 190.0
MM = pcbnew.FromMM

# ----------------------------------------------------------------------------
# Net classes
# ----------------------------------------------------------------------------
# HV_PWR: carried by hand-drawn planes (power.py); autorouter only adds thin taps
HV_PWR = ["RECT_P", "SW_PFC", "VBUS", "SW_A", "SW_B", "OUT_LA", "OUT_LF"]
# HV_HC: high-current HV nets whose pads are all THT/2512 -> autorouted 3 mm tracks
HV_HC = ["AC_L_IN", "AC_L", "AC_N", "AC_L_R", "OUT_N", "OUT_L"]
HV_SIG = ["XBLD", "PFC_VS1", "PFC_VS2", "HO_A", "HO_B", "VB_A", "VB_B", "QAH_G", "QBH_G",
          "VOL1", "VOL2", "VOL3", "VON1", "VON2", "VON3", "BLD1", "BLD2", "BLD3", "VBS1", "VBS2", "VBS3"]
LV_PWR = ["GND", "VCC15", "+5V", "+3V3", "+12V", "PFC_VCC", "RECT_N"]
COLD = ["PROG_GND", "PROG_3V3", "PROG_TXD", "PROG_RXD", "PROG_DTR", "PROG_RTS"]

CLASSES = [
    # name, clearance, track, via_d, via_drill
    ("Default", 0.2, 0.25, 0.6, 0.3),
    ("LV_PWR", 0.25, 0.8, 0.8, 0.4),
    ("HV_SIG", 2.5, 0.5, 0.8, 0.4),
    ("HV_PWR", 2.5, 0.6, 1.0, 0.5),
    ("HV_HC", 2.5, 2.5, 1.6, 0.8),
    ("COLD", 8.0, 0.3, 0.6, 0.3),
]
MEMBERS = {"HV_PWR": HV_PWR, "HV_HC": HV_HC, "HV_SIG": HV_SIG, "LV_PWR": LV_PWR, "COLD": COLD}

# ----------------------------------------------------------------------------
# Placement: ref -> (x, y, rot).  y grows downward, heatsink along y = H.
# ----------------------------------------------------------------------------
YR = 185.5                      # TO-247 pad row (tab face ~4.3 mm below)
LX = 153.0                      # leg A low-side FET centre
P = {
    # --- AC input (top left)
    "J1": (6, 18, 270), "F1": (16, 8, 0), "C1": (16, 26, 0), "RV1": (52, 23, 0),
    "TH1": (64, 31, 0), "K1": (72, 40, 0),
    "PS1": (22, 58, 0), "PS2": (22, 86, 0),
    # --- heatsink row
    "BR1": (42, YR, 180), "Q1": (68 + 5.45, YR, 180), "D2": (90, YR - 0.8, 180),
    "C44": (97.8, 184, 90),
    "Q6": (LX + 5.45, YR, 180), "Q5": (LX + 25.45, YR, 180),
    "Q8": (LX + 50.45, YR, 180), "Q7": (LX + 70.45, YR, 180),
    # --- PFC magnetics / caps
    "L1": (58, 118, 0), "C8": (49.5, 175, 180), "D1": (90, 108, 180),
    "C16": (105, 76, 0), "C17": (105, 112.5, 0), "C18": (105, 149, 0),
    "C19": (LX + 17.05, 174, 180), "C20": (LX + 62.05, 174, 180),
    # --- output filter
    "L2": (LX + 11, 166, 180), "L3": (LX + 56, 128, 180),
    "U6": (250, 80, 90), "C31": (277.5, 100, 180), "F2": (296, 100, 90), "J2": (307, 50, 90), 
    # --- controller
    "U9": (190, 33, 0), "U10": (232, 12, 180), "J3": (250, 4.5, 0), "C42": (244.5, 19.5, 0),
    # --- mounting holes (PE)
    "H1": (4, 4, 0), "H2": (W - 4, 4, 0), "H3": (150, 80, 0), "H4": (W - 4, H - 30, 0),
}

# --- gate-drive islands: (role ref per leg), offsets relative to the driver at rot 0.
# Driver HV pins (rot 0): VS (2.48, 0), HO (2.48, -1.27), VB (2.48, -2.54)
ISLAND = [  # (index in leg tuple, dx, dy, rot)
    ("cbs", 5.8, -1.27, 270),   # bootstrap cap: pad1 VB (up), pad2 VS (down)
    ("rho", 8.8, -1.27, 0),     # HO -> high-side gate
    ("rgh", 9.71, 1.9, 270),    # gate pull-down: pad1 gate (up), pad2 SW (down)
    ("dbs", 4.2, -6.4, 180),    # bootstrap diode: K (VB) right, A (VCC15) left
]
LEGS = {"A": ("U4", 130.0, 177.5, 0, {"cbs": "C22", "rho": "R27", "rgh": "R28", "dbs": "D5"}),
        "B": ("U5", 241.0, 176.0, 180, {"cbs": "C26", "rho": "R32", "rgh": "R33", "dbs": "D6"})}


def island_xy(leg, dx, dy):
    u, cx, cy, r, _ = LEGS[leg]
    return (cx + dx, cy + dy) if r == 0 else (cx - dx, cy - dy)


for leg, (u, cx, cy, r, roles) in LEGS.items():
    P[u] = (cx, cy, r)
    for role, dx, dy, rr in ISLAND:
        x, y = island_xy(leg, dx, dy)
        P[roles[role]] = (x, y, (rr + r) % 360)

# --- HV divider chains, placed end to end so neighbouring pads share a net
CHAINS = [  # (refs, x0, y0, rot, pitch_list)  pitch = centre-to-centre spacing to next part
    (["R21", "R22", "R23", "R24", "R25"], 112.0, 52.0, 0, [6.3, 4.7, 4.7, 4.1]),
    (["R17", "R18", "R19", "R20", "D4"], 112.0, 45.0, 0, [8.2, 8.2, 8.2, 6.3]),
    (["R10", "R11", "R12", "R13"], 18.5, 121.0, 270, [6.3, 4.7, 4.1]),
    (["R38", "R39", "R40", "R41", "R46"], 260.0, 72.0, 0, [6.3, 4.7, 4.7, 4.1]),
    (["R42", "R43", "R44", "R45", "R47"], 260.0, 66.0, 0, [6.3, 4.7, 4.7, 4.1]),
    (["R1", "R2"], 24.0, 39.0, 0, [8.2]),
]
for refs, x0, y0, rot, pitch in CHAINS:
    x, y = x0, y0
    for i, ref in enumerate(refs):
        # LEDs: pad1 = K, so flip it to keep A (BLD4) next to the chain
        P[ref] = (x, y, (rot + 180) % 360 if ref.startswith("D") else rot)
        if i < len(pitch):
            if rot == 0:
                x += pitch[i]
            else:
                y += pitch[i]
CHAIN_LINKS = [(a, b) for refs, *_ in CHAINS for a, b in zip(refs, refs[1:])]

# clusters of small parts: name -> (x0, y0, x1, y1, refs)
CL = {
    "relay": (85, 40, 100, 58, ["Q2", "R3", "R4", "D3"]),
        "aux": (66, 70, 91, 100, ["C2", "C3", "U1", "C4", "C5", "U2", "C6", "C7"]),
    "shunt": (16, 171, 26, 186, ["RS1", "RS2"]),
    "pfc": (16, 154, 43, 170, ["U3", "C9", "R7", "C10", "R8", "R9", "C11", "C12", "C13",
                               "Q3", "R14", "R15", "R16", "C14", "C15", "R5", "R6"]),
    "bus": (135.5, 50, 142, 56, ["C21"]),
    "drvA": (109, 169, 125.5, 189, ["R26", "C23", "C24", "R29", "R30", "C25", "R36", "R37"]),
    "drvB": (246, 166, 262, 186, ["R31", "C27", "C28", "R34", "R35", "C29"]),
    "amp": (222, 30, 282, 56, ["U7", "C32", "R48", "C33", "R49", "R50", "C34",
                               "R51", "R52", "C35", "U8", "C36", "R53", "R54", "R55", "C37", "C30"]),
    "mcu": (132, 4, 166, 60, ["C38", "C39", "R56", "C40", "R57", "SW1", "SW2", "Q9", "Q10", "R58",
                              "R59", "R60", "D7", "R61", "C41", "J4", "J5", "Q11", "R62", "R63", "D8"]),
    "iso": (216, 20, 230, 28, ["C43"]),
}


def kiid(ref):
    return str(uuid.uuid5(NS, ref + ":1"))


def write_project():
    pro = json.load(open("/usr/share/kicad/template/kicad.kicad_pro"))
    pro["meta"]["filename"] = "inv1200.kicad_pro"
    classes = []
    for name, clr, tw, vd, vdr in CLASSES:
        classes.append({"bus_width": 12, "clearance": clr, "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25,
                        "diff_pair_width": 0.2, "line_style": 0, "microvia_diameter": 0.3, "microvia_drill": 0.1,
                        "name": name, "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)",
                        "track_width": tw, "via_diameter": vd, "via_drill": vdr, "wire_width": 6})
    pats = [{"netclass": c, "pattern": n} for c, nets in MEMBERS.items() for n in nets]
    pro["net_settings"] = {"classes": classes, "meta": {"version": 3}, "net_colors": None,
                           "netclass_assignments": None, "netclass_patterns": pats}
    pro["board"] = {"design_settings": {"defaults": {"board_outline_line_width": 0.1, "copper_line_width": 0.2},
                    "rules": {"min_clearance": 0.2, "min_track_width": 0.18, "min_via_diameter": 0.5,
                              "min_through_hole_diameter": 0.2, "min_copper_edge_clearance": 0.5,
                              "min_hole_clearance": 0.25, "min_hole_to_hole": 0.25, "min_silk_clearance": 0.0,
                              "min_text_height": 0.8, "min_text_thickness": 0.08,
                              "allow_blind_buried_vias": False, "allow_microvias": False},
                    "rule_severities": {"silk_overlap": "ignore", "silk_over_copper": "ignore",
                                        "silk_edge_clearance": "ignore", "lib_footprint_issues": "ignore",
                                        "lib_footprint_mismatch": "ignore", "text_thickness": "ignore",
                                        "text_height": "ignore"}}}
    pro["sheets"] = [[str(uuid.uuid5(NS, "root")), ""]]
    json.dump(pro, open(PRO, "w"), indent=2)


def _anyof(side, nets):
    return "(" + " || ".join(f"{side}.NetName == '{n}'" for n in nets) + ")"


GROUPS = {  # nets that sit within ~20 V of each other (or within one divider step)
    "hs_A": ["SW_A", "VB_A", "HO_A", "QAH_G"],
    "hs_B": ["SW_B", "VB_B", "HO_B", "QBH_G"],
}


def write_rules():
    """KiCad custom rules. Later rules win, so the general HV rules come first and the
    intra-footprint / same-potential exemptions after them."""
    exempt = []
    for ref, p in design.PARTS.items():
        nets = {n for n in p["pins"].values() if n}
        if nets & set(HV_PWR + HV_HC + HV_SIG + COLD):
            exempt.append(ref)
    L = ["(version 1)", "",
         "# HV nets to board edge",
         '(rule "hv_to_edge" (condition "(A.NetClass == \'HV_PWR\' || A.NetClass == \'HV_HC\') && B.Type == \'Edge\'")',
         "   (constraint edge_clearance (min 2mm)))",
         "# cold (isolated) side internally only needs normal spacing",
         '(rule "cold_internal" (condition "A.NetClass == \'COLD\' && B.NetClass == \'COLD\'")',
         "   (constraint clearance (min 0.2mm)))",
         "# ACS724 primary: IP+ and IP- differ by milli-volts",
         '(rule "acs724_primary" (condition "A.NetName == \'OUT_LA\' && B.NetName == \'OUT_LF\'")',
         "   (constraint clearance (min 0.4mm)))"]
    for g_, nets in GROUPS.items():
        L += [f"# {g_}: floating high-side gate-drive island",
              f'(rule "{g_}" (condition "{_anyof("A", nets)} && {_anyof("B", nets)}")',
              "   (constraint clearance (min 0.3mm)))"]
    L += ["# unconnected (NC) IC pins float; they only need manufacturing clearance",
          '(rule "nc_pins" (condition "A.Type == \'Pad\' && A.NetName == \'\'")',
          "   (constraint clearance (min 0.2mm)))"]
    L.append("# pins inside one footprint (IC pin pitch, divider resistor ends, terminal blocks)")
    for ref in exempt:
        L.append(f'(rule "intra_{ref}" (condition "A.intersectsCourtyard(\'{ref}\') && B.intersectsCourtyard(\'{ref}\')")')
        L.append("   (constraint clearance (min 0.2mm)))")
    open(os.path.join(HW, "inv1200.kicad_dru"), "w").write("\n".join(L) + "\n")
    return exempt


class Box:
    """plain-python box in nm (avoids BOX2I lifetime issues in the SWIG binding)"""
    def __init__(self, l, t, r, b):
        self.l, self.t, self.r, self.b = l, t, r, b

    def GetLeft(self): return self.l
    def GetTop(self): return self.t
    def GetRight(self): return self.r
    def GetBottom(self): return self.b
    def GetWidth(self): return self.r - self.l
    def GetHeight(self): return self.b - self.t

    def Intersects(self, o):
        return self.l < o.r and o.l < self.r and self.t < o.b and o.t < self.b


def crtyd_box(fp):
    xs, ys = [], []
    for g in list(fp.GraphicalItems()):
        if g.GetLayer() in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            b = g.GetBoundingBox()
            xs += [b.GetLeft(), b.GetRight()]
            ys += [b.GetTop(), b.GetBottom()]
    if not xs:
        b = fp.GetBoundingBox(False, False)
        xs, ys = [b.GetLeft(), b.GetRight()], [b.GetTop(), b.GetBottom()]
    return Box(min(xs), min(ys), max(xs), max(ys))


def load_fp(ref):
    p = design.PARTS[ref]
    lib, name = p["fp"].split(":")
    fp = pcbnew.FootprintLoad(FPLIB + lib + ".pretty", name)
    assert fp is not None, p["fp"]
    fp.SetReference(ref)
    fp.SetValue(p["val"])
    fp.SetPath(pcbnew.KIID_PATH("/" + kiid(ref)))
    try:
        fp.SetSheetname("Root")
        fp.SetSheetfile("inv1200.kicad_sch")
    except AttributeError:
        pass
    fp.SetFPIDAsString(p["fp"])
    return fp


def main():
    exempt = write_rules()
    board = pcbnew.BOARD()
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(2)
    ds.SetBoardThickness(MM(1.6))

    nets = {}
    for n in sorted(design.nets()):
        ni = pcbnew.NETINFO_ITEM(board, n)
        board.Add(ni)
        nets[n] = ni

    fps = {}
    for ref in design.PARTS:
        fp = load_fp(ref)
        board.Add(fp)
        fps[ref] = fp
        for pad in fp.Pads():
            num = pad.GetNumber()
            net = design.PARTS[ref]["pins"].get(num)
            if num and net:
                pad.SetNet(nets[net])
            elif num and num not in design.PARTS[ref]["pins"]:
                raise SystemExit(f"{ref} pad {num} has no pin mapping")

    for ref, (x, y, r) in P.items():
        fps[ref].SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
        fps[ref].SetOrientationDegrees(r)

    # cluster packer (courtyard-based shelf packing)
    placed = set(P)
    for name, spec in CL.items():
        x0, y0, x1, y1, refs = spec[:5]
        crot = spec[5] if len(spec) > 5 else 0
        cx, cy, rowh = x0, y0, 0.0
        for ref in refs:
            fp = fps[ref]
            fp.SetPosition(pcbnew.VECTOR2I(0, 0))
            fp.SetOrientationDegrees(crot)
            bb = crtyd_box(fp)
            w, h = pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())
            if cx + w > x1 and cx > x0:
                cx, cy, rowh = x0, cy + rowh + 0.6, 0.0
            dx, dy = cx - pcbnew.ToMM(bb.GetLeft()), cy - pcbnew.ToMM(bb.GetTop())
            fp.SetPosition(pcbnew.VECTOR2I(MM(dx), MM(dy)))
            cx += w + 0.6
            rowh = max(rowh, h)
            placed.add(ref)
        if cy + rowh > y1:
            print(f"WARN cluster {name} overflows by {cy + rowh - y1:.1f} mm")
    missing = set(design.PARTS) - placed
    if missing:
        raise SystemExit(f"unplaced: {sorted(missing)}")

    # outline
    pts = [(0, 0), (W, 0), (W, H), (0, H)]
    for i in range(4):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(MM(pts[i][0]), MM(pts[i][1])))
        s.SetEnd(pcbnew.VECTOR2I(MM(pts[(i + 1) % 4][0]), MM(pts[(i + 1) % 4][1])))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(MM(0.1))
        board.Add(s)

    # isolation slot under the Si8641 (adds creepage between cold and hot sides)
    ux, uy = P["U10"][0], P["U10"][1]
    slot = [(ux - 0.5, uy - 6.5), (ux + 0.5, uy - 6.5), (ux + 0.5, uy + 6.5), (ux - 0.5, uy + 6.5)]
    for i in range(4):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(MM(slot[i][0]), MM(slot[i][1])))
        s.SetEnd(pcbnew.VECTOR2I(MM(slot[(i + 1) % 4][0]), MM(slot[(i + 1) % 4][1])))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(MM(0.1))
        board.Add(s)

    board.Save(PCB)
    write_project()          # after Save: Save() rewrites the .kicad_pro with in-memory defaults
    print(f"placed {len(fps)} footprints; {len(exempt)} intra-footprint HV exemptions")

    # courtyard overlap report
    boxes = {r: crtyd_box(f) for r, f in fps.items()}
    refs = sorted(boxes)
    ov = []
    for i, a in enumerate(refs):
        for b in refs[i + 1:]:
            if boxes[a].Intersects(boxes[b]):
                ov.append((a, b))
    print("courtyard overlaps:", ov)
    for r, f in fps.items():
        bb = boxes[r]
        if bb.GetLeft() < 0 or bb.GetTop() < 0 or bb.GetRight() > MM(W) or bb.GetBottom() > MM(H):
            print("OFF BOARD", r)


if __name__ == "__main__":
    main()
