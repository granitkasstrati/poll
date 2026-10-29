"""
Build gdc1.kicad_pcb from design.py with KiCad 7's pcbnew API.
Run with python3.12 (the interpreter KiCad's pcbnew module is built for).

Stage: place -> footprints, outline, net classes, custom rules, keepouts
       (route.py does pre-routes, autorouting, zones and DRC)
"""
import json
import os
import sys
import uuid

import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
import design  # noqa: E402

HW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PCB = os.path.join(HW, "gdc1.kicad_pcb")
PRO = os.path.join(HW, "gdc1.kicad_pro")
FPLIB = "/usr/share/kicad/footprints/"
NS = uuid.UUID("3f0c9a1e-6d2b-4c57-9b1a-6a1d0e5c6d01")
W, H = 105.0, 85.0
MM = pcbnew.FromMM

# ----------------------------------------------------------------------------
# Net classes
# ----------------------------------------------------------------------------
PWR = ["GND", "VIN", "VIN_A", "VIN_AF", "VIN_B", "BUCK_SW", "BUCK_5V", "+5V", "+3V3",
       "VBUS", "VBUS_F", "WARN_N"]
FIELD = ["FIELD_V", "FGND"] + [f"{p}_{n}" for p in ("FIN", "FLED", "FOPTO") for n in ("CLOSED", "OPEN", "AUX")]
OPENER = ["OPENER_NO", "OPENER_COM", "OPENER_NC"]
USB = ["USB_DP", "USB_DN", "USB_CC1", "USB_CC2"]     # 0.5 mm pitch USB-C pads

CLASSES = [
    # name, clearance, track, via_d, via_drill
    ("Default", 0.2, 0.25, 0.6, 0.3),
    ("PWR", 0.2, 0.6, 0.8, 0.4),
    ("FIELD", 0.25, 0.4, 0.8, 0.4),      # 2 mm to everything else via custom rule + keepout strip
    ("OPENER", 1.0, 0.6, 1.0, 0.5),
    ("USB", 0.15, 0.2, 0.6, 0.3),
]
MEMBERS = {"PWR": PWR, "FIELD": FIELD, "OPENER": OPENER, "USB": USB}
ISO_GAP = 2.0           # field side <-> logic side

# ----------------------------------------------------------------------------
# Placement: ref -> (x, y, rot).  y grows downward. Antenna on the top edge,
# all field wiring on the bottom edge (terminal wire entry faces +y at rot 0).
# ----------------------------------------------------------------------------
TY = 79.5               # terminal pin row
P = {
    "H1": (3.5, 3.5, 0), "H2": (W - 3.5, 3.5, 0), "H3": (3.5, H - 3.5, 0), "H4": (W - 3.5, H - 3.5, 0),
    # --- MCU + USB (top)
    "U4": (52.5, 12.75, 0),
    "J2": (4.4, 14.0, 270),
    "U2": (15.8, 14.0, 0), "R9": (11.7, 12.6, 0), "R10": (11.7, 15.9, 0), "F2": (13.2, 19.6, 0),
    "R11": (3.6, 21.6, 0), "C11": (7.1, 21.6, 0),
    "J5": (67.5, 9.0, 0),
    "SW1": (13.5, 25.5, 0), "SW2": (69.5, 19.0, 0), "SW3": (94.0, 44.0, 0),
    "C14": (39.8, 9.0, 90), "C15": (41.6, 15.0, 90), "C10": (64.0, 21.0, 90),
    # --- terminals (bottom edge)
    "J1": (13.0, TY, 0), "J4": (25.0, TY, 0), "J3": (37.0, TY, 0), "J8": (70.0, TY, 0),
    # --- power input + buck (bottom left)
    "C1": (8.5, 46.0, 0), "C2": (8.5, 58.5, 0),
    "F1": (2.6, 68.0, 0), "D1": (14.0, 68.5, 0), "D2": (23.0, 68.0, 0),
    "U1": (24.0, 53.0, 0), "C3": (18.6, 53.0, 90), "C4": (18.6, 47.9, 90),
    "D3": (25.5, 47.5, 0), "L1": (31.6, 54.0, 90),
    "C6": (36.8, 51.3, 90), "C7": (36.8, 56.4, 90),
    "D4": (32.2, 46.4, 90), "D5": (20.0, 22.0, 90),
    "U3": (24.0, 40.0, 0), "C12": (31.5, 40.5, 90), "C13": (17.2, 40.0, 90),
    "C21": (55.5, 66.4, 0),
    # --- relay (bottom centre)
    "K1": (42.0, 55.0, 0),
    # --- isolated input island (bottom right)
    "PS1": (55.0, 63.5, 90),
    "U6": (73.5, 58.0, 90), "U7": (80.5, 58.0, 90), "U8": (87.5, 58.0, 90),
    # --- UI / sensors (right)
    "BZ1": (78.0, 36.0, 0),
    "U5": (95.5, 9.0, 0), "J7": (W - 3.3, 20.0, 90), "J6": (W - 2.2, 27.5, 0),
    "D7": (70.0, 29.0, 0),
}

# clusters of small parts: name -> (x0, y0, x1, y1, refs[, rot])
CL = {
    "usb": (18.5, 5.0, 27.5, 10.0, ["R12", "D6"]),
    "esp": (34.5, 12.0, 39.6, 22.0, ["R13", "C17", "C16", "R14"], 90),
    "buckctl": (16.5, 57.4, 28.0, 63.6, ["C5", "R1", "R2", "R3", "R4", "R5", "R6", "C8", "C9", "R7", "R8"]),
    "warn": (27.5, 62.5, 39.5, 73.4, ["D14", "Q3", "R25", "R26"]),
    "relay": (39.0, 41.0, 58.0, 52.0, ["Q2", "R22", "C20", "R23", "D11", "D12", "R24", "D13"]),
    "ui": (61.0, 32.0, 72.0, 47.5, ["Q1", "R20", "R21", "D10", "D8", "C19", "R18", "R19", "D9"]),
    "sense": (80.0, 3.0, 99.0, 16.0, ["C18", "R16", "R17"]),
    "user": (84.0, 23.5, 98.0, 38.0, ["R15"]),
    "optlogic": (68.0, 47.5, 92.0, 51.5, ["R31", "C26", "R32", "C27", "R33", "C28"]),
    "field": (60.5, 65.0, 96.0, 73.6, ["C22", "R27", "D15", "C23", "R28", "D16", "C24", "R29", "D17",
                                       "C25", "R30", "D18"]),
}
TPS = {  # test points
    "TP1": (30.0, 60.5), "TP2": (34.5, 41.0), "TP3": (37.5, 38.0), "TP4": (51.0, 70.0),
    "TP5": (35.8, 46.0), "TP6": (57.0, 54.5), "TP7": (62.0, 75.0), "TP8": (98.0, 75.0),
    "TP9": (95.0, 50.0), "TP10": (98.0, 53.5), "TP11": (64.0, 25.0),
}
for r, (x, y) in TPS.items():
    P[r] = (x, y, 0)

# isolation fence: (x0, y0, x1, y1) keepout rectangles (no tracks, no vias, no pour)
SPLIT_X, SPLIT_Y = 58.8, 58.0            # PS1 pin 2|3 gap, optocoupler mid-body
FENCE = [
    (SPLIT_X - 1.0, SPLIT_Y + 1.0, SPLIT_X + 1.0, 61.6),        # above PS1 pads
    (SPLIT_X - 0.3, 61.6, SPLIT_X + 0.3, 65.4),                 # between PS1 pin 2 and 3 (inside its body)
    (SPLIT_X - 1.0, 65.4, SPLIT_X + 1.0, H),                    # below PS1 to the board edge
    (SPLIT_X - 1.0, SPLIT_Y - 1.0, W, SPLIT_Y + 1.0),           # under the optocouplers to the right edge
]
ISLAND = [(SPLIT_X + 1.0, SPLIT_Y + 1.0), (W, SPLIT_Y + 1.0), (W, H), (SPLIT_X + 1.0, H)]


def kiid(ref):
    return str(uuid.uuid5(NS, ref + ":1"))


def write_project():
    pro = json.load(open("/usr/share/kicad/template/kicad.kicad_pro"))
    pro["meta"]["filename"] = "gdc1.kicad_pro"
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
                    "rules": {"min_clearance": 0.15, "min_track_width": 0.2, "min_via_diameter": 0.6,
                              "min_through_hole_diameter": 0.3, "min_copper_edge_clearance": 0.5,
                              "min_hole_clearance": 0.25, "min_hole_to_hole": 0.25, "min_silk_clearance": 0.0,
                              "min_text_height": 0.8, "min_text_thickness": 0.08,
                              "allow_blind_buried_vias": False, "allow_microvias": False},
                    "rule_severities": {"silk_overlap": "ignore", "silk_over_copper": "ignore",
                                        "silk_edge_clearance": "ignore", "lib_footprint_issues": "ignore",
                                        "lib_footprint_mismatch": "ignore", "text_thickness": "ignore",
                                        "text_height": "ignore"}}}
    pro["sheets"] = [[str(uuid.uuid5(NS, "root")), ""]]
    json.dump(pro, open(PRO, "w"), indent=2)


def write_rules():
    """KiCad custom rules. Later rules win, so the general isolation rules come first and the
    intra-footprint exemptions after them."""
    L = ["(version 1)", "",
         "# field side (isolated DC/DC output, reed inputs) to everything that is not field side",
         '(rule "field_iso" (condition "A.NetClass == \'FIELD\' && B.NetClass != \'FIELD\'")',
         f"   (constraint clearance (min {ISO_GAP}mm)))",
         "# relay contacts: keep 1 mm from everything else, 0.5 mm between themselves",
         '(rule "opener_internal" (condition "A.NetClass == \'OPENER\' && B.NetClass == \'OPENER\'")',
         "   (constraint clearance (min 0.5mm)))",
         "# unconnected pads only need manufacturing clearance",
         '(rule "nc_pins" (condition "A.Type == \'Pad\' && A.NetName == \'\'")',
         "   (constraint clearance (min 0.2mm)))",
         "# parts that bridge the barrier by design (their own internal isolation applies)"]
    L += ["# USB4105 library footprint: its NPTH pegs sit 0.19 mm from its own GND pads",
          '(rule "usb4105_pegs" (condition "A.intersectsCourtyard(\'J2\') && B.intersectsCourtyard(\'J2\')")',
          "   (constraint hole_clearance (min 0.15mm)))"]
    for ref in ("K1", "PS1", "U6", "U7", "U8"):
        L.append(f'(rule "intra_{ref}" (condition "A.intersectsCourtyard(\'{ref}\') && B.intersectsCourtyard(\'{ref}\')")')
        L.append("   (constraint clearance (min 0.2mm)))")
    open(os.path.join(HW, "gdc1.kicad_dru"), "w").write("\n".join(L) + "\n")


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


def crtyd_box(fp, ref=None):
    xs, ys = [], []
    for g in list(fp.GraphicalItems()):
        if g.GetLayer() in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            b = g.GetBoundingBox()
            xs += [b.GetLeft(), b.GetRight()]
            ys += [b.GetTop(), b.GetBottom()]
    if not xs:
        b = fp.GetBoundingBox(False, False)
        xs, ys = [b.GetLeft(), b.GetRight()], [b.GetTop(), b.GetBottom()]
    bx = Box(min(xs), min(ys), max(xs), max(ys))
    if fp.GetReference() == "U4":       # library courtyard includes the antenna keepout; use the module body
        c = fp.GetPosition()
        bx = Box(c.x - MM(9.2), c.y - MM(12.95), c.x + MM(9.2), bx.b)
    return bx


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
        fp.SetSheetfile("gdc1.kicad_sch")
    except AttributeError:
        pass
    fp.SetFPIDAsString(p["fp"])
    if ref == "U4":
        # the library EPAD carries 0.2 mm thermal vias; replace them with 0.3 mm routing vias (route.py)
        for pad in list(fp.Pads()):
            if pad.GetNumber() == "41" and pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                fp.Remove(pad)
    return fp


def rect_zone(board, pts, layers, net=None, keepout=False, priority=0, name=""):
    z = pcbnew.ZONE(board)
    ls = pcbnew.LSET()
    for L in layers:
        ls.AddLayer(L)
    z.SetLayerSet(ls)
    ol = z.Outline()
    ol.NewOutline()
    for x, y in pts:
        ol.Append(MM(x), MM(y))
    if keepout:
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowCopperPour(True)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
    else:
        z.SetNet(net)
        z.SetAssignedPriority(priority)
        z.SetMinThickness(MM(0.25))
        z.SetThermalReliefGap(MM(0.3))
        z.SetThermalReliefSpokeWidth(MM(0.4))
        z.SetLocalClearance(MM(0.25))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)   # SMD solid, THT with reliefs
    if name:
        z.SetZoneName(name)
    board.Add(z)
    return z


def outline(board, pts, closed=True):
    n = len(pts)
    for i in range(n if closed else n - 1):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(MM(pts[i][0]), MM(pts[i][1])))
        s.SetEnd(pcbnew.VECTOR2I(MM(pts[(i + 1) % n][0]), MM(pts[(i + 1) % n][1])))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(MM(0.1))
        board.Add(s)


def silk_text(board, txt, x, y, size=1.0, layer=pcbnew.F_SilkS, rot=0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(txt)
    t.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
    t.SetTextThickness(MM(size * 0.15))
    t.SetTextAngleDegrees(rot)
    if layer == pcbnew.B_SilkS:
        t.SetMirrored(True)
    board.Add(t)


# silkscreen: terminal labels next to each screw (wire side) + board info
LABELS = [
    ("VIN~", 13.0, 72.6), ("VIN~", 18.1, 72.6), ("+VIN", 25.0, 72.6), ("WARN-", 30.1, 72.6),
    ("NC", 37.0, 72.6), ("COM", 42.1, 72.6), ("NO", 47.2, 72.6),
    ("COM", 70.0, 72.6), ("CLOSED", 75.1, 72.6), ("OPEN", 80.2, 72.6), ("AUX", 85.2, 72.6), ("FGND", 90.3, 72.6),
]


def main():
    write_rules()
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

    # header GND pins hemmed in by signal pins cannot get two thermal spokes: connect them solid
    for ref in ("J5", "J6", "J7"):
        for pad in fps[ref].Pads():
            if pad.GetNetname() == "GND":
                pad.SetZoneConnection(pcbnew.ZONE_CONNECTION_FULL)

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
                cx, cy, rowh = x0, cy + rowh + 0.3, 0.0
            dx, dy = cx - pcbnew.ToMM(bb.GetLeft()), cy - pcbnew.ToMM(bb.GetTop())
            fp.SetPosition(pcbnew.VECTOR2I(MM(dx), MM(dy)))
            cx += w + 0.3
            rowh = max(rowh, h)
            placed.add(ref)
        if cy + rowh > y1:
            print(f"WARN cluster {name} overflows by {cy + rowh - y1:.1f} mm")
    missing = set(design.PARTS) - placed
    if missing:
        raise SystemExit(f"unplaced: {sorted(missing)}")

    outline(board, [(0, 0), (W, 0), (W, H), (0, H)])
    # thermal slots around the BME280 so the buck/LDO/ESP heat does not bias the reading
    ux, uy = P["U5"][0], P["U5"][1]
    outline(board, [(ux - 4.5, uy + 3.6), (ux + 4.5, uy + 3.6), (ux + 4.5, uy + 4.6), (ux - 4.5, uy + 4.6)])
    outline(board, [(ux - 5.6, uy - 5.0), (ux - 4.6, uy - 5.0), (ux - 4.6, uy + 4.6), (ux - 5.6, uy + 4.6)])

    for f in FENCE:
        x0, y0, x1, y1 = f
        rect_zone(board, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], (pcbnew.F_Cu, pcbnew.B_Cu), keepout=True,
                  name="ISOLATION_FENCE")

    for txt, x, y in LABELS:
        silk_text(board, txt, x, y, 0.9)
    silk_text(board, "gdc1 rev A  -  smart garage door controller", 30.0, 83.6, 1.0, pcbnew.B_SilkS)
    silk_text(board, "ISOLATED", 93.6, 58.0, 0.9, rot=90)
    silk_text(board, "CERN-OHL-S-2.0", 30.0, 81.6, 0.8, pcbnew.B_SilkS)

    board.Save(PCB)
    write_project()          # after Save: Save() rewrites the .kicad_pro with in-memory defaults
    print(f"placed {len(fps)} footprints")

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
            print("OFF BOARD", r, [round(pcbnew.ToMM(v), 2) for v in (bb.l, bb.t, bb.r, bb.b)])


if __name__ == "__main__":
    main()
