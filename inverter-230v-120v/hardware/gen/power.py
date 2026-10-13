"""
Hand-defined power copper.

build(board): power planes poured BEFORE autorouting. KiCad exports them to the
              Specctra DSN as fixed `plane` copper, so Freerouting routes the
              signals around them and only adds thin taps to plane nets.
zones(board): GND pours on both layers AFTER autorouting, then fill everything.

All polygons were laid out from the pad map (see docs/PCB.md); each one keeps
>= 2.6 mm from every foreign pad so the 2.5 mm HV rule is met with margin.
Coordinates in mm, y down. LX (leg A low-side FET centre) = 153.
"""
import pcbnew

import gen_pcb

MM = pcbnew.FromMM
W, H = gen_pcb.W, gen_pcb.H

F, B = pcbnew.F_Cu, pcbnew.B_Cu

PLANES = [
    # net,      layer, priority, polygon
    ("SW_A", F, 5, [(151.5, 188), (154.5, 188), (154.5, 181.6), (162.3, 181.6), (162.3, 188), (169.1, 188),
                    (169.1, 179), (166.2, 179), (166.2, 170), (168, 170), (168, 162), (151.5, 162)]),
    ("SW_B", F, 5, [(196.5, 188), (199.5, 188), (199.5, 181.6), (207.3, 181.6), (207.3, 188), (214.1, 188),
                    (214.1, 179), (211.2, 179), (211.2, 124), (205.5, 124), (205.5, 168), (196.5, 168)]),
    ("SW_PFC", F, 5, [(54.5, 146), (61.5, 146), (61.5, 168), (85.9, 168), (85.9, 188), (77.4, 188), (77.4, 181.6),
                      (69.6, 181.6), (69.6, 188), (66.4, 188), (66.4, 181.6), (54.5, 181.6)]),
    ("RECT_P", F, 5, [(41.1, 188), (44.9, 188), (44.9, 180.5), (51.9, 180.5), (51.9, 122), (62, 122), (62, 113),
                      (78, 113), (78, 103.5), (55, 103.5), (55, 113), (46, 113), (46, 177), (41.1, 177)]),
    # VBUS: cap column + D1/D2/C44 branch + band to leg A + leg A strip + band to leg B + leg B strip
    ("VBUS", F, 4, [(98, 60), (106.5, 60), (106.5, 122.3), (171, 122.3), (171, 101), (226, 101), (226, 181.6),
                    (219.5, 181.6), (219.5, 188), (216.7, 188), (216.7, 179), (213.8, 179), (213.8, 121.4),
                    (188.7, 121.4), (188.7, 188), (182.3, 188), (182.3, 181.6), (174.5, 181.6), (174.5, 188),
                    (171.7, 188), (171.7, 179), (170.6, 179), (170.6, 159.4), (171, 159.4), (171, 129.6),
                    (106.5, 129.6), (106.5, 188), (88.5, 188), (88.5, 174), (101.6, 174), (101.6, 164),
                    (98, 164), (98, 111.5), (86.5, 111.5), (86.5, 104.5), (98, 104.5)]),
    # OUT_LA: dives to B.Cu under the VBUS band, back to F.Cu through a via field, east to U6 IP+
    ("OUT_LA", B, 5, [(160.5, 138), (167.5, 138), (167.5, 112), (160.5, 112)]),
    ("OUT_LA", F, 5, [(160.5, 119.5), (167.5, 119.5), (167.5, 88.5), (249.75, 88.5), (249.75, 81.4),
                      (247.5, 81.4), (247.5, 84), (160.5, 84)]),
    ("OUT_LF", F, 5, [(250.25, 81.4), (300, 81.4), (300, 104.5), (253.8, 104.5), (253.8, 92), (250.25, 92)]),
]

STITCH = [("OUT_LA", x, y) for x in (162, 164, 166) for y in (113.5, 115.5, 117.5)]


def _zone(board, net, layer, prio, pts, full=True):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(board.FindNet(net))
    z.SetAssignedPriority(prio)
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL if full else pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetMinThickness(MM(0.4))
    z.SetLocalClearance(MM(0.3))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    o = z.Outline()
    o.NewOutline()
    for x, y in pts:
        o.Append(MM(x), MM(y))
    board.Add(z)
    return z


def _keepout(board, cx, cy, r):
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetDoNotAllowCopperPour(True)
    z.SetDoNotAllowTracks(True)
    z.SetDoNotAllowVias(True)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    ls = pcbnew.LSET()
    ls.AddLayer(F)
    ls.AddLayer(B)
    z.SetLayerSet(ls)
    z.SetZoneName("mount_keepout")
    import math
    o = z.Outline()
    o.NewOutline()
    for i in range(24):
        a = 2 * math.pi * i / 24
        o.Append(MM(cx + r * math.cos(a)), MM(cy + r * math.sin(a)))
    board.Add(z)


def _pad(board, ref, num):
    for pd in board.FindFootprintByReference(ref).Pads():
        if pd.GetNumber() == str(num):
            q = pd.GetPosition()
            return pcbnew.ToMM(q.x), pcbnew.ToMM(q.y)
    raise KeyError(f"{ref}.{num}")


def _track(board, net, pts, w=0.5, layer=F):
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(MM(x1), MM(y1)))
        t.SetEnd(pcbnew.VECTOR2I(MM(x2), MM(y2)))
        t.SetWidth(MM(w))
        t.SetLayer(layer)
        t.SetNet(board.FindNet(net))
        t.SetLocked(True)          # exported as (type protect): the autorouter keeps it as is
        board.Add(t)


def _via(board, net, x, y, d=1.0, drill=0.5):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    v.SetDrill(MM(drill))
    v.SetWidth(MM(d))
    v.SetNet(board.FindNet(net))
    v.SetLocked(True)
    board.Add(v)


def islands(board):
    """High-side gate-drive islands + gate escapes (geometry: see gen_pcb.ISLAND / docs/PCB.md)."""
    for leg, (u, cx, cy, rot, r) in gen_pcb.LEGS.items():
        s = 1 if rot == 0 else -1
        sw, vb, ho, g = f"SW_{leg}", f"VB_{leg}", f"HO_{leg}", f"Q{leg}H_G"
        cb1, cb2 = _pad(board, r["cbs"], 1), _pad(board, r["cbs"], 2)
        rh1, rh2 = _pad(board, r["rho"], 1), _pad(board, r["rho"], 2)
        rg1, rg2 = _pad(board, r["rgh"], 1), _pad(board, r["rgh"], 2)
        dk = _pad(board, r["dbs"], 1)
        _track(board, vb, [_pad(board, u, 13), cb1])
        _track(board, vb, [dk, cb1])
        _track(board, ho, [_pad(board, u, 12), rh1])
        xj = cx + s * 7.0
        _track(board, sw, [_pad(board, u, 11), cb2, (xj, cb2[1]), (xj, rg2[1]), rg2])
        _track(board, g, [rh2, rg1])
        if leg == "A":
            # SW_A tap east into the SW_A plane; QAH_G north around the plane, then B.Cu to Q5.G
            _track(board, sw, [rg2, (153.0, rg2[1])], 0.6)
            gx = rh2[0] + 1.9
            _track(board, g, [rh2, (gx, rh2[1]), (gx, 159.6), (167.4, 159.6)])
            _via(board, g, 167.4, 159.6)
            q5g = _pad(board, "Q5", 1)
            _track(board, g, [(167.4, 159.6), (q5g[0], 170.6), q5g], 0.5, B)
        else:
            # SW_B tap: via, B.Cu under the VBUS strip, via into the SW_B plane
            vx = rg2[0] - 1.8
            _track(board, sw, [rg2, (vx, rg2[1])], 0.6)
            _via(board, sw, vx, rg2[1])
            _track(board, sw, [(vx, rg2[1]), (225.0, 168.5), (208.5, 168.5)], 0.6, B)
            _via(board, sw, 208.5, 168.5)
            gx = rh2[0] - 1.7
            _track(board, g, [rh2, (gx, rh2[1])])
            _via(board, g, gx, rh2[1])
            q7g = _pad(board, "Q7", 1)
            _track(board, g, [(gx, rh2[1]), (gx, 181.0), (q7g[0], 184.0), q7g], 0.5, B)


def chains(board):
    """Short links between neighbouring divider resistors (always the same net)."""
    for a, b in gen_pcb.CHAIN_LINKS:
        fa = board.FindFootprintByReference(a)
        fb = board.FindFootprintByReference(b)
        best = None
        for pa in fa.Pads():
            for pb in fb.Pads():
                if pa.GetNetname() and pa.GetNetname() == pb.GetNetname():
                    d = (pa.GetPosition() - pb.GetPosition()).EuclideanNorm()
                    if best is None or d < best[0]:
                        best = (d, pa, pb)
        assert best, (a, b)
        _, pa, pb = best
        q1, q2 = pa.GetPosition(), pb.GetPosition()
        _track(board, pa.GetNetname(), [(pcbnew.ToMM(q1.x), pcbnew.ToMM(q1.y)),
                                        (pcbnew.ToMM(q2.x), pcbnew.ToMM(q2.y))], 0.5)


def cold(board):
    """Isolated (USB-UART) side of U10 -> J3, hand-routed (the 8 mm COLD class defeats the autorouter).
    J3 pin order matches U10 pins 8..3, so the fan-out has no crossings."""
    w = 0.3
    for upin, jpin in ((8, 1), (7, 2), (6, 3), (5, 4), (4, 5), (3, 6)):
        a, b = _pad(board, "U10", upin), _pad(board, "J3", jpin)
        net = board.FindFootprintByReference("J3").FindPadByNumber(str(jpin)).GetNetname()
        _track(board, net, [a, (243.0, a[1]), (247.5, b[1]), b], w)
    # pins 2 (GND) / 1 (3V3) join pins 8 / 7 on B.Cu
    g2, g8 = _pad(board, "U10", 2), _pad(board, "U10", 8)
    p1, p7 = _pad(board, "U10", 1), _pad(board, "U10", 7)
    _track(board, "PROG_GND", [g2, (239.4, g2[1])], w)
    _via(board, "PROG_GND", 239.4, g2[1], 0.8, 0.4)
    _track(board, "PROG_GND", [(239.4, g2[1]), (239.4, g8[1])], w, B)
    _via(board, "PROG_GND", 239.4, g8[1], 0.8, 0.4)
    c1, c2 = _pad(board, "C42", 1), _pad(board, "C42", 2)
    _track(board, "PROG_3V3", [p1, (240.8, p1[1]), (242.6, c1[1] - 1.0), c1], w)
    _via(board, "PROG_3V3", 240.8, p1[1], 0.8, 0.4)
    _track(board, "PROG_3V3", [(240.8, p1[1]), (240.8, p7[1])], w, B)
    _via(board, "PROG_3V3", 240.8, p7[1], 0.8, 0.4)
    j1 = _pad(board, "J3", 1)
    _track(board, "PROG_GND", [c2, (246.5, c2[1])], w)
    _via(board, "PROG_GND", 246.5, c2[1], 0.8, 0.4)
    _track(board, "PROG_GND", [(246.5, c2[1]), (246.5, j1[1]), j1], w, B)


# fixed stubs leading out of a plane so the autorouter has a target outside the keepout
STUBS = []
ROUTE_KEEPOUTS = []


def _route_keepout(board, layer, pts):
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetDoNotAllowCopperPour(False)
    z.SetDoNotAllowTracks(True)
    z.SetDoNotAllowVias(True)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    ls = pcbnew.LSET()
    ls.AddLayer(layer)
    z.SetLayerSet(ls)
    z.SetZoneName("autoroute_keepout")
    o = z.Outline()
    o.NewOutline()
    for x, y in pts:
        o.Append(MM(x), MM(y))
    board.Add(z)
    ROUTE_KEEPOUTS.append(z)


def remove_route_keepouts(board):
    for z in ROUTE_KEEPOUTS:
        board.Remove(z)
    ROUTE_KEEPOUTS.clear()


def hand_routes(board):
    """Long HV runs the autorouter could not finish (geometry in docs/PCB.md)."""
    W_AC = 2.5
    # AC_N: PS2 AC_N pin -> left-edge trunk (B.Cu) -> BR1 pin 3
    psn = _pad(board, "PS2", 1)
    br3, br2 = _pad(board, "BR1", 3), _pad(board, "BR1", 2)
    _track(board, "AC_N", [psn, (13.0, psn[1] + 9.0), (13.0, 180.0), (br3[0], 180.0), br3], W_AC, B)
    # AC_L_R: TH1 pin 2 -> B.Cu down x=40 -> hop to F.Cu over the VBUS feed -> BR1 pin 2
    th = _pad(board, "TH1", 2)
    _track(board, "AC_L_R", [th, (66.0, 40.0), (40.0, 40.0), (40.0, 98.0)], W_AC, B)
    _track(board, "AC_L_R", [(40.0, 98.0), (40.0, 107.0)], W_AC, F)
    for dx in (-1.4, 0.0, 1.4):
        _via(board, "AC_L_R", 40.0 + dx, 98.0, 1.2, 0.6)
        _via(board, "AC_L_R", 40.0 + dx, 107.0, 1.2, 0.6)
    _track(board, "AC_L_R", [(40.0, 107.0), (br2[0], 109.5), br2], W_AC, B)
    # relay duplicate pads (COM and NO are each two pins)
    for num in ("11", "14"):
        pads = [p for p in board.FindFootprintByReference("K1").Pads() if p.GetNumber() == num]
        a, b = [(pcbnew.ToMM(q.GetPosition().x), pcbnew.ToMM(q.GetPosition().y)) for q in pads]
        _track(board, pads[0].GetNetname(), [a, b], W_AC, F)
    # VBUS taps to the divider/bleeder chains (from the top of the cap-column plane)
    r17, r21 = _pad(board, "R17", 1), _pad(board, "R21", 1)
    _track(board, "VBUS", [(104.0, 64.0), (104.0, r21[1]), r21], 0.6)
    _track(board, "VBUS", [(104.0, r21[1]), (104.0, r17[1]), r17], 0.6)
    # VBUS to the PFC VSENSE divider R10: B.Cu under L1 / RECT_P plane
    r10 = _pad(board, "R10", 1)
    _via(board, "VBUS", 95.0, 106.0)
    _track(board, "VBUS", [(95.0, 106.0), (92.0, 102.3), (r10[0], 102.3), (r10[0], 113.8)], 0.6, B)
    _via(board, "VBUS", r10[0], 113.8)
    _track(board, "VBUS", [(r10[0], 113.8), r10], 0.6)
    # relay NO (K1.14) -> AC_L_R trunk at TH1, around the east side of K1 (carries full current
    # once the relay bypasses the NTC)
    k14 = [q for q in board.FindFootprintByReference("K1").Pads() if q.GetNumber() == "14"]
    k14 = max(((pcbnew.ToMM(q.GetPosition().x), pcbnew.ToMM(q.GetPosition().y)) for q in k14))
    _track(board, "AC_L_R", [k14, (84.5, k14[1]), (84.5, 35.0), (73.0, 35.0), th], W_AC, B)
    # isolator -> auto-program transistors (DTR_H/RTS_H), B.Cu under the ESP32
    w = 0.25
    dtr_u, rts_u = _pad(board, "U10", 13), _pad(board, "U10", 12)
    dtr_r, rts_r = _pad(board, "R58", 1), _pad(board, "R59", 1)
    _track(board, "DTR_H", [dtr_u, (225.0, dtr_u[1])], w)
    _via(board, "DTR_H", 225.0, dtr_u[1], 0.6, 0.3)
    _track(board, "DTR_H", [(225.0, dtr_u[1]), (225.0, 48.2), (147.8, 48.2), (147.8, 15.0)], w, B)
    _via(board, "DTR_H", 147.8, 15.0, 0.6, 0.3)
    _track(board, "DTR_H", [(147.8, 15.0), dtr_r], w)
    _track(board, "RTS_H", [rts_u, (223.6, rts_u[1])], w)
    _via(board, "RTS_H", 223.6, rts_u[1], 0.6, 0.3)
    _track(board, "RTS_H", [(223.6, rts_u[1]), (223.6, 47.0), (149.8, 47.0), (149.8, 15.6)], w, B)
    _via(board, "RTS_H", 149.8, 15.6, 0.6, 0.3)
    _track(board, "RTS_H", [(149.8, 15.6), rts_r], w)
    # VON: output-sense divider -> TLV9062 inverting input, B.Cu
    von_r, von_u = _pad(board, "R47", 1), _pad(board, "U7", 2)
    _track(board, "VON", [von_r, (von_r[0], 63.3)], w)
    _via(board, "VON", von_r[0], 63.3, 0.6, 0.3)
    _track(board, "VON", [(von_r[0], 63.3), (226.5, 63.3), (226.5, von_u[1])], w, B)
    _via(board, "VON", 226.5, von_u[1], 0.6, 0.3)
    _track(board, "VON", [(226.5, von_u[1]), von_u], w)
    # OUT_LF tap to the output-voltage divider R38
    r38 = _pad(board, "R38", 1)
    _track(board, "OUT_LF", [r38, (r38[0], 84.5)], 0.6)


def build(board):
    cold(board)
    hand_routes(board)
    for net, pts in STUBS:
        _track(board, net, pts, 0.6)
    islands(board)
    chains(board)
    for net, layer, prio, pts in PLANES:
        _zone(board, net, layer, prio, pts)
        _route_keepout(board, layer, pts)
    for net, x, y in STITCH:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
        v.SetDrill(MM(0.8))
        v.SetWidth(MM(1.5))
        v.SetNet(board.FindNet(net))
        board.Add(v)
    for ref in ("H1", "H2", "H3", "H4"):
        p = board.FindFootprintByReference(ref).GetPosition()
        _keepout(board, pcbnew.ToMM(p.x), pcbnew.ToMM(p.y), 7.5)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def zones(board):
    """Board-wide GND pours on both layers (lowest priority), then refill all."""
    remove_route_keepouts(board)
    m = 0.6
    for layer in (F, B):
        _zone(board, "GND", layer, 0, [(m, m), (W - m, m), (W - m, H - m), (m, H - m)])
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())

