"""
Small 2-layer grid maze router (A*) for the last connections Freerouting leaves open.

It reads the finished board, rasterises every foreign copper item per layer, inflated by the
net-class clearance (max of the two classes) plus half the track width, and routes between
the two items DRC reports as unconnected. Vias are allowed where both layers are free.
"""
import heapq
import re

import numpy as np
import pcbnew
import shapely
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

import gen_pcb

MM = lambda v: pcbnew.FromMM(float(v))
T = pcbnew.ToMM
RES = 0.1                       # grid pitch, mm
WIN = 18.0                      # search window margin around the two endpoints, mm
VIA_D, VIA_DRILL = 0.6, 0.3
VIA_COST = 30
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)
GND_POUR = "GND"                # pours are refilled afterwards, so they are not obstacles

CLASS_CLR = {c[0]: c[1] for c in gen_pcb.CLASSES}
for name, nets in gen_pcb.MEMBERS.items():
    pass


def net_clr(board, net):
    if not net:
        return 0.2
    return CLASS_CLR.get(board.FindNet(net).GetNetClassName(), 0.2)


def _poly_of_shape(sh):
    """pcbnew SHAPE_POLY_SET -> shapely geometry"""
    polys = []
    for i in range(sh.OutlineCount()):
        o = sh.Outline(i)
        pts = [(T(o.CPoint(j).x), T(o.CPoint(j).y)) for j in range(o.PointCount())]
        if len(pts) >= 3:
            p = Polygon(pts)
            for h in range(sh.HoleCount(i)):
                hh = sh.Hole(i, h)
                hp = [(T(hh.CPoint(j).x), T(hh.CPoint(j).y)) for j in range(hh.PointCount())]
                if len(hp) >= 3:
                    p = p.difference(Polygon(hp))
            polys.append(p.buffer(0))
    return unary_union(polys) if polys else None


HOLES = []
DEBUG = {}


def copper_items(board):
    """[(net, layer, geometry)] for every copper item (zones = their fill)."""
    items = []
    HOLES.clear()
    for t in board.GetTracks():
        net = t.GetNetname()
        if t.GetClass() == "PCB_VIA":
            HOLES.append((T(t.GetPosition().x), T(t.GetPosition().y), T(t.GetDrillValue()) / 2))
            g = Point(T(t.GetPosition().x), T(t.GetPosition().y)).buffer(T(t.GetWidth()) / 2, 12)
            for L in LAYERS:
                items.append((net, L, g))
        else:
            g = LineString([(T(t.GetStart().x), T(t.GetStart().y)),
                            (T(t.GetEnd().x), T(t.GetEnd().y))]).buffer(T(t.GetWidth()) / 2, 8)
            items.append((net, t.GetLayer(), g))
    for fp in board.GetFootprints():
        for p in fp.Pads():
            for L in LAYERS:
                if p.IsOnLayer(L):
                    sh = p.GetEffectivePolygon()
                    g = _poly_of_shape(sh)
                    if g is not None:
                        items.append((p.GetNetname(), L, g))
            if p.GetDrillSize().x > 0:
                HOLES.append((T(p.GetPosition().x), T(p.GetPosition().y), T(max(p.GetDrillSize().x, p.GetDrillSize().y)) / 2))
            if p.GetDrillSize().x > 0:          # holes block both layers (incl. NPTH)
                r = T(max(p.GetDrillSize().x, p.GetDrillSize().y)) / 2
                c = Point(T(p.GetPosition().x), T(p.GetPosition().y)).buffer(r, 12)
                for L in LAYERS:
                    items.append((p.GetNetname() or "__hole__", L, c))
    for fp in board.GetFootprints():
        for z in fp.Zones():
            if z.GetIsRuleArea() and (z.GetDoNotAllowTracks() or z.GetDoNotAllowVias()):
                g = _poly_of_shape(z.Outline())
                for L in LAYERS:
                    if z.IsOnLayer(L) and g is not None:
                        items.append(("__keepout__", L, g))
    for i in range(board.GetAreaCount()):
        z = board.GetArea(i)
        if z.GetIsRuleArea():
            g = _poly_of_shape(z.Outline())
            for L in LAYERS:
                items.append(("__keepout__", L, g))
            continue
        if z.GetNetname() == GND_POUR:
            continue
        for L in LAYERS:
            if z.IsOnLayer(L):
                g = _poly_of_shape(z.GetFilledPolysList(L))
                if g is not None and not g.is_empty:
                    items.append((z.GetNetname(), L, g))
    return items


def route_pair(board, items, net, a, b, w=0.25, log=print, la=LAYERS, lb=LAYERS):
    clr = net_clr(board, net)
    x0, x1 = min(a[0], b[0]) - WIN, max(a[0], b[0]) + WIN
    y0, y1 = min(a[1], b[1]) - WIN, max(a[1], b[1]) + WIN
    x0, y0 = max(x0, 0.6), max(y0, 0.6)
    x1, y1 = min(x1, gen_pcb.W - 0.6), min(y1, gen_pcb.H - 0.6)
    win = box(x0, y0, x1, y1)
    nx, ny = int((x1 - x0) / RES) + 1, int((y1 - y0) / RES) + 1
    xs = x0 + np.arange(nx) * RES
    ys = y0 + np.arange(ny) * RES
    gx, gy = np.meshgrid(xs, ys)
    free = {}
    vfree = None
    for L in LAYERS:
        trk, via = [], []
        for n, l, g in items:
            if l != L or n == net or not g.intersects(win):
                continue
            c = max(clr, net_clr(board, n if not n.startswith("__") else ""))
            if n == "__keepout__":
                c = 0.0
            trk.append(g.buffer(c + w / 2 + 0.08, 6))
            via.append(g.buffer(c + VIA_D / 2 + 0.08, 6))
        ob = unary_union(trk) if trk else None
        ov = unary_union(via) if via else None
        f = np.ones((ny, nx), bool) if ob is None else ~shapely.contains_xy(ob, gx, gy)
        v = np.ones((ny, nx), bool) if ov is None else ~shapely.contains_xy(ov, gx, gy)
        free[L] = f
        vfree = v if vfree is None else (vfree & v)
    hs = [Point(x, y).buffer(r + VIA_DRILL / 2 + 0.35, 8) for x, y, r in HOLES if win.buffer(2).contains(Point(x, y))]
    if hs:
        vfree &= ~shapely.contains_xy(unary_union(hs), gx, gy)
    # own-net copper around the endpoints is passable
    def cell(p):
        return int(round((p[1] - y0) / RES)), int(round((p[0] - x0) / RES))
    sa, sb = cell(a), cell(b)
    starts = [(L, sa) for L in la]
    goal = sb
    goal_layers = {LAYERS.index(L) for L in lb}
    for L in la:
        free[L][sa] = True
    for L in lb:
        free[L][sb] = True
    DEBUG.update(free=free, vfree=vfree, sa=sa, sb=sb, x0=x0, y0=y0)
    li = {L: k for k, L in enumerate(LAYERS)}
    INF = 1 << 60
    dist = np.full((2, ny, nx), INF, np.int64)
    prev = {}
    pq = []
    for L, (r, c) in starts:
        if free[L][r, c]:
            dist[li[L], r, c] = 0
            heapq.heappush(pq, (0, 0, li[L], r, c))
    moves = [(0, 1, 10), (1, 0, 10), (0, -1, 10), (-1, 0, 10), (1, 1, 14), (1, -1, 14), (-1, 1, 14), (-1, -1, 14)]
    found = None
    while pq:
        _, d, k, r, c = heapq.heappop(pq)
        if d != dist[k, r, c]:
            continue
        if (r, c) == goal and k in goal_layers:
            found = (k, r, c)
            break
        for dr, dc, cost in moves:
            rr, cc = r + dr, c + dc
            if 0 <= rr < ny and 0 <= cc < nx and free[LAYERS[k]][rr, cc]:
                g = d + cost
                if g < dist[k, rr, cc]:
                    dist[k, rr, cc] = g
                    prev[(k, rr, cc)] = (k, r, c)
                    heapq.heappush(pq, (g + int(10 * np.hypot(goal[0] - rr, goal[1] - cc)), g, k, rr, cc))
        if vfree[r, c]:
            k2 = 1 - k
            if free[LAYERS[k2]][r, c] and d + VIA_COST < dist[k2, r, c]:
                dist[k2, r, c] = d + VIA_COST
                prev[(k2, r, c)] = (k, r, c)
                heapq.heappush(pq, (d + VIA_COST + int(10 * np.hypot(goal[0] - r, goal[1] - c)), d + VIA_COST, k2, r, c))
    if not found:
        log(f"  maze: no path for {net}")
        return False
    path = [found]
    while path[-1] in prev:
        path.append(prev[path[-1]])
    path.reverse()
    # emit: split at layer changes, simplify collinear runs
    ni = board.FindNet(net)
    seg = [path[0]]
    out = []
    for p in path[1:]:
        if p[0] != seg[-1][0]:
            out.append(seg)
            r, c = p[1], p[2]
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(MM(xs[c]), MM(ys[r])))
            v.SetWidth(MM(VIA_D))
            v.SetDrill(MM(VIA_DRILL))
            v.SetNet(ni)
            board.Add(v)
            seg = [p]
        else:
            seg.append(p)
    out.append(seg)
    nseg = 0
    for s in out:
        pts = [(xs[c], ys[r]) for _, r, c in s]
        if len(pts) < 2:
            continue
        simp = LineString(pts).simplify(RES * 0.6)
        q = list(simp.coords)
        q[0] = (a if s is out[0] else q[0])
        q[-1] = (b if s is out[-1] else q[-1])
        for (xa, ya), (xb, yb) in zip(q, q[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(MM(xa), MM(ya)))
            t.SetEnd(pcbnew.VECTOR2I(MM(xb), MM(yb)))
            t.SetWidth(MM(w))
            t.SetLayer(LAYERS[s[0][0]])
            t.SetNet(ni)
            board.Add(t)
            nseg += 1
    log(f"  maze: {net} routed, {nseg} segments, {len(out) - 1} vias")
    return True


def unconnected_pairs(rpt_txt):
    pairs = []
    for blk in re.split(r"\n(?=\[)", rpt_txt):
        if not blk.startswith("[unconnected_items]"):
            continue
        pts = re.findall(r"@\(([\d.]+) mm, ([\d.]+) mm\): ([^\[]*)\[([^\]]*)\]([^\n|]*)", blk)
        if len(pts) == 2 and pts[0][3] == pts[1][3] and pts[0][3] != GND_POUR:
            def lay(kind, rest):
                if "PTH" in kind or "Via" in kind:
                    return LAYERS
                return (pcbnew.B_Cu,) if "B.Cu" in rest else (pcbnew.F_Cu,)
            pairs.append((pts[0][3], (float(pts[0][0]), float(pts[0][1])), (float(pts[1][0]), float(pts[1][1])),
                          lay(pts[0][2], pts[0][4]), lay(pts[1][2], pts[1][4])))
    return pairs


def _net_pads(board, net):
    out = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == net:
                lay = tuple(L for L in LAYERS if p.IsOnLayer(L))
                out.append(((T(p.GetPosition().x), T(p.GetPosition().y)), lay))
    return out


def finish(board, rpt_txt, log=print):
    pairs = unconnected_pairs(rpt_txt)
    log(f"maze router: {len(pairs)} open connections")
    done = 0
    for net, a, b, la, lb in pairs:
        items = copper_items(board)
        w = 0.25 if board.FindNet(net).GetNetClassName() in ("Default", "COLD") else 0.4
        if route_pair(board, items, net, a, b, w, log, la, lb):
            done += 1
            continue
        # retry from other pads of the net, nearest first (one end may simply be boxed in)
        pads = _net_pads(board, net)
        near_a = sorted(pads, key=lambda q: np.hypot(q[0][0] - a[0], q[0][1] - a[1]))[:3]
        near_b = sorted(pads, key=lambda q: np.hypot(q[0][0] - b[0], q[0][1] - b[1]))[:3]
        tries = sorted(((pa, pb) for pa in near_a for pb in near_b if pa[0] != pb[0]),
                       key=lambda t: np.hypot(t[0][0][0] - a[0], t[0][0][1] - a[1]) + np.hypot(t[1][0][0] - b[0], t[1][0][1] - b[1]))
        for (pa, la2), (pb, lb2) in tries[:6]:
            if route_pair(board, items, net, pa, pb, w, log, la2, lb2):
                done += 1
                break
    return done
