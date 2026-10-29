"""
Routing stage (python3.12):
  1. fresh placed board from gen_pcb.py
  2. pre-routes: ESP32 EPAD vias (locked)
  3. export Specctra DSN -> Freerouting (headless) -> import SES   (or replay the stored session)
  4. pours (GND logic side, FGND isolated side), maze router for leftovers, dangling cleanup, DRC

  python3.12 route.py            # run Freerouting (Java 25) and store gdc1.ses
  python3.12 route.py --reuse    # replay gen/gdc1.ses (deterministic, ~20 s)
  python3.12 route.py --drc      # DRC only
"""
import os
import re
import shutil
import subprocess
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
import gen_pcb  # noqa: E402

HW = gen_pcb.HW
PCB = gen_pcb.PCB
HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("WORK", os.path.join(HERE, "build"))
os.makedirs(WORK, exist_ok=True)
FR = os.environ.get("FREEROUTING", "freerouting.jar")   # app.freerouting:freerouting 2.4.1 from Maven Central
JAVA = os.environ.get("JAVA25", "/usr/lib/jvm/java-25-openjdk-amd64/bin/java")
STORED = os.path.join(HERE, "gdc1.ses")
MM = pcbnew.FromMM


def load():
    pcbnew.GetSettingsManager().LoadProject(gen_pcb.PRO)
    return pcbnew.LoadBoard(PCB)


def via(board, x, y, net, d=0.6, drill=0.3, locked=True):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    v.SetWidth(MM(d))
    v.SetDrill(MM(drill))
    v.SetNet(board.FindNet(net))
    v.SetLocked(locked)
    board.Add(v)
    return v


def track(board, pts, net, w, layer=pcbnew.F_Cu):
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(MM(x1), MM(y1)))
        t.SetEnd(pcbnew.VECTOR2I(MM(x2), MM(y2)))
        t.SetWidth(MM(w))
        t.SetLayer(layer)
        t.SetNet(board.FindNet(net))
        t.SetLocked(True)
        board.Add(t)


def pad_xy(board, ref, num):
    p = [p for p in board.FindFootprintByReference(ref).Pads() if p.GetNumber() == num][0].GetPosition()
    return pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)


def preroute(board):
    """3x3 GND via array in the ESP32-S3 EPAD (replaces the library's 0.2 mm vias), and a GND via
    for the BME280: its corner is walled in by the thermal slots, so the F.Cu pour there is a pocket."""
    x5, y5 = pad_xy(board, "U5", "5")
    vx, vy = x5 + 0.8, y5 + 1.25
    track(board, [(x5, y5), (vx, vy)], "GND", 0.3)
    via(board, vx, vy, "GND")
    # ...and its exit past the right end of the slot, laid before the signals can seal the corner
    track(board, [(vx, vy), (101.6, vy), (101.6, 14.6)], "GND", 0.4, pcbnew.B_Cu)
    via(board, 101.6, 14.6, "GND")
    u4 = board.FindFootprintByReference("U4")
    epad = [p for p in u4.Pads() if p.GetNumber() == "41"][0]
    c = epad.GetPosition()
    for dx in (-1.2, 0, 1.2):
        for dy in (-1.2, 0, 1.2):
            via(board, pcbnew.ToMM(c.x) + dx, pcbnew.ToMM(c.y) + dy, "GND")


def autoroute(board, passes=30):
    dsn = os.path.join(WORK, "gdc1.dsn")
    ses = os.path.join(WORK, "gdc1.ses")
    if os.path.exists(ses):
        os.remove(ses)
    assert pcbnew.ExportSpecctraDSN(board, dsn)
    txt = open(dsn).read()
    assert "(class FIELD" in txt and "(class OPENER" in txt, "DSN lacks net classes"
    cmd = [JAVA, "-jar", FR, "-de", dsn, "-do", ses, "-mp", str(passes), "--gui.enabled=false", "-mt", "4"]
    print(" ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=7000)
    log = r.stdout + r.stderr
    open(os.path.join(WORK, "freerouting.log"), "w").write(log)
    print("\n".join([ln for ln in log.splitlines() if "INFO" in ln][-6:]))
    assert os.path.exists(ses), "freerouting produced no session"
    shutil.copy(ses, STORED)
    return import_ses(board, ses)


def import_ses(board, ses):
    """KiCad 7's ImportSpecctraSES() needs the GUI frame, so parse the session here.
    Wires/vias marked (type protect) are the pre-routed copper already on the board."""
    from sexp import loads, find, findall
    d = loads(open(ses).read())
    routes = find(d, "routes")
    res = find(routes, "resolution")
    k = 1e-3 / res[2] if str(res[1]) == "um" else 1e-3   # -> mm
    nt = nv = 0
    for net in findall(find(routes, "network_out"), "net"):
        ni = board.FindNet(net[1])
        for w in findall(net, "wire"):
            if any(isinstance(x, list) and x[0] == "type" and str(x[1]) == "protect" for x in w):
                continue
            p = find(w, "path")
            layer = board.GetLayerID(str(p[1]))
            width = max(p[2] * k, 0.2)
            xy = p[3:]
            pts = [(xy[i] * k, -xy[i + 1] * k) for i in range(0, len(xy), 2)]
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(pcbnew.VECTOR2I(MM(x1), MM(y1)))
                t.SetEnd(pcbnew.VECTOR2I(MM(x2), MM(y2)))
                t.SetWidth(MM(width))
                t.SetLayer(layer)
                t.SetNet(ni)
                board.Add(t)
                nt += 1
        for v in findall(net, "via"):
            if any(isinstance(x, list) and x[0] == "type" and str(x[1]) == "protect" for x in v):
                continue
            m = re.search(r"_(\d+):(\d+)_um", v[1])
            vv = pcbnew.PCB_VIA(board)
            vv.SetPosition(pcbnew.VECTOR2I(MM(v[2] * k), MM(-v[3] * k)))
            vv.SetWidth(MM(int(m.group(1)) / 1000))
            vv.SetDrill(MM(int(m.group(2)) / 1000))
            vv.SetNet(ni)
            board.Add(vv)
            nv += 1
    print(f"imported {nt} track segments, {nv} vias")


def zones(board):
    W, H = gen_pcb.W, gen_pcb.H
    sx, sy = gen_pcb.SPLIT_X, gen_pcb.SPLIT_Y
    logic = [(0, 0), (W, 0), (W, sy - 1.0), (sx - 1.0, sy - 1.0), (sx - 1.0, H), (0, H)]
    for L in (pcbnew.F_Cu, pcbnew.B_Cu):
        gen_pcb.rect_zone(board, logic, (L,), board.FindNet("GND"), name="GND")
        gen_pcb.rect_zone(board, gen_pcb.ISLAND, (L,), board.FindNet("FGND"), name="FGND")
    islands(board, keep=True)


def islands(board, keep):
    """Keep pour islands while stitching (so a via can rescue them), drop the dead ones afterwards."""
    mode = pcbnew.ISLAND_REMOVAL_MODE_NEVER if keep else pcbnew.ISLAND_REMOVAL_MODE_ALWAYS
    for z in board.Zones():
        if not z.GetIsRuleArea():
            z.SetIslandRemovalMode(mode)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def _foreign_copper(board, net):
    """union of every copper item of another net, each grown by its own isolation requirement"""
    from shapely.ops import unary_union
    import maze
    grow = {"FIELD": gen_pcb.ISO_GAP, "OPENER": 1.0}
    geo = []
    for n, L, g in maze.copper_items(board):
        if n != net and not n.startswith("__"):
            geo.append(g.buffer(grow.get(board.FindNet(n).GetNetClassName(), 0.25) + 0.05, 6))
    return unary_union(geo)


def _fills(board, net, shrink):
    from shapely.ops import unary_union
    import maze
    out = []
    for L in (pcbnew.F_Cu, pcbnew.B_Cu):
        polys = [maze._poly_of_shape(z.GetFilledPolysList(L)) for z in board.Zones()
                 if z.GetNetname() == net and z.IsOnLayer(L) and not z.GetIsRuleArea()]
        out.append(unary_union([g for g in polys if g is not None]).buffer(-shrink))
    return out


def _holes(board, net=None):
    h = [(pcbnew.ToMM(t.GetPosition().x), pcbnew.ToMM(t.GetPosition().y)) for t in board.GetTracks()
         if t.GetClass() == "PCB_VIA" and net in (None, t.GetNetname())]
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetDrillSize().x > 0 and net in (None, p.GetNetname()):
                h.append((pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)))
    return h


def stitch(board, net="GND", pitch=4.0, d=0.6, clr=0.35):
    """Via-stitch the two pours of `net` wherever both layers have solid fill around the point."""
    from shapely.geometry import Point
    f, b_ = _fills(board, net, d / 2 + clr)
    both = f.intersection(b_).difference(_foreign_copper(board, net).buffer(d / 2))
    holes = _holes(board)
    n = 0
    y = pitch / 2
    while y < gen_pcb.H:
        x = pitch / 2 + (pitch / 2 if int(y / pitch) % 2 else 0)
        while x < gen_pcb.W:
            if both.contains(Point(x, y)) and all((x - hx) ** 2 + (y - hy) ** 2 > 1.5 ** 2 for hx, hy in holes):
                via(board, x, y, net, d, 0.3, locked=False)
                holes.append((x, y))
                n += 1
            x += pitch
        y += pitch
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    print(f"stitched {net}: {n} vias")
    stitch_islands(board, net, d, clr)


def _components(board, net):
    """Pour fragments of `net` on both layers, grouped into connected components through vias and
    plated pads. Returns (fragments, list of components as index lists), largest component first."""
    from shapely.geometry import Point
    raw = _fills(board, net, 0.0)
    frags = [(k, g) for k in (0, 1) for g in getattr(raw[k], "geoms", [raw[k]]) if not g.is_empty]
    links = [Point(x, y) for x, y in _holes(board, net)]
    parent = list(range(len(frags)))

    def root(i):
        while parent[i] != i:
            i = parent[i]
        return i
    for v in links:
        hit = [i for i, (k, g) in enumerate(frags) if g.buffer(0.05).contains(v)]
        for i in hit[1:]:
            parent[root(i)] = root(hit[0])
    comps = {}
    for i in range(len(frags)):
        comps.setdefault(root(i), []).append(i)
    order = sorted(comps.values(), key=lambda c: -sum(frags[i][1].area for i in c))
    return frags, order


def stitch_islands(board, net, d=0.6, clr=0.35):
    """Tie every pour component that is not part of the main one back to it: a via where the other
    layer belongs to the main component, else a routed track from one of its pads to a main via."""
    from shapely.ops import unary_union
    added = 0
    for _ in range(6):
        frags, comps = _components(board, net)
        if len(comps) < 2:
            break
        main = comps[0]
        main_fill = [unary_union([frags[i][1] for i in main if frags[i][0] == k] or [Point0()]) for k in (0, 1)]
        safe = _fills(board, net, d / 2 + clr)
        foreign = _foreign_copper(board, net).buffer(d / 2)
        new = 0
        for comp in comps[1:]:
            done = False
            for i in comp:
                k, frag = frags[i]
                spot = frag.intersection(safe[k]).intersection(safe[1 - k]).intersection(
                    main_fill[1 - k].buffer(-(d / 2 + clr))).difference(foreign)
                if not spot.is_empty:
                    pt = spot.representative_point()
                    via(board, pt.x, pt.y, net, d, 0.3, locked=False)
                    done = True
                    break
            if not done and _has_pad(board, net, unary_union([frags[i][1] for i in comp])):
                region = unary_union([frags[i][1] for i in comp])
                mains = [v for v in _hole_points(board, net) if main_fill[0].buffer(0.05).contains(v)
                         or main_fill[1].buffer(0.05).contains(v)]
                done = bool(_route_out(board, net, region, mains))
            new += done
        if not new:
            break
        added += new
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    frags, comps = _components(board, net)
    live = [c for c in comps[1:] if _has_pad(board, net, unary_union([frags[i][1] for i in c]))]
    print(f"island fixes {net}: {added}, detached components with pads: {len(live)}")


def _has_pad(board, net, region):
    """True if a pad of `net` sits in this pour region (otherwise it is dead copper, removed later)."""
    from shapely.geometry import Point
    r = region.buffer(0.05)
    return any(r.contains(Point(pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)))
               for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetname() == net)


def Point0():
    from shapely.geometry import Point
    return Point(-100, -100).buffer(0.1)


def _hole_points(board, net):
    from shapely.geometry import Point
    return [Point(x, y) for x, y in _holes(board, net)]


def _route_out(board, net, frag, vias):
    """No room for a via in this pour pocket: route a track from a pad in it to the nearest via outside."""
    from shapely.geometry import Point
    import maze
    pads = [(pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)) for fp in board.GetFootprints()
            for p in fp.Pads() if p.GetNetname() == net and frag.contains(Point(pcbnew.ToMM(p.GetPosition().x),
                                                                                  pcbnew.ToMM(p.GetPosition().y)))]
    outside = [v for v in vias if not frag.buffer(0.5).contains(v)]
    pads += [(v.x, v.y) for v in _hole_points(board, net) if frag.buffer(0.05).contains(v)]
    for a in pads:
        for v in sorted(outside, key=lambda q: (q.x - a[0]) ** 2 + (q.y - a[1]) ** 2)[:4]:
            if maze.route_pair(board, maze.copper_items(board), net, a, (v.x, v.y), 0.3,
                               la=(pcbnew.F_Cu,), lb=maze.LAYERS):
                return 1
    return 0


def drc(board, name="drc.rpt"):
    rpt = os.path.join(WORK, name)
    pcbnew.WriteDRCReport(board, rpt, pcbnew.EDA_UNITS_MILLIMETRES, True)
    txt = open(rpt).read()
    kinds = {}
    for m in re.finditer(r"^\[(\w+)\]", txt, re.M):
        kinds[m.group(1)] = kinds.get(m.group(1), 0) + 1
    print("\n".join(ln for ln in txt.splitlines() if ln.startswith("**")))
    print(kinds)
    return txt


def remove_dangling(board):
    """drop autorouter leftovers (vias / stubs connected to nothing), repeat until clean"""
    for _ in range(6):
        txt = drc(board, "drc_dangling.rpt")
        spots = [(k, float(x), float(y), float(ln) if ln else 0.0) for k, x, y, ln in re.findall(
            r"\[(via_dangling|track_dangling)\][^\n]*\n[^\n]*\n\s*@\(([\d.]+) mm, ([\d.]+) mm\)[^\n]*?(?:length ([\d.]+) mm)?\n", txt)]
        if not spots:
            return
        for k, x, y, ln in spots:
            p = pcbnew.VECTOR2I(MM(x), MM(y))
            for t in list(board.GetTracks()):
                if t.IsLocked():
                    continue
                if (k == "via_dangling" and t.GetClass() == "PCB_VIA" and (t.GetPosition() - p).EuclideanNorm() < MM(0.01)) or \
                   (k == "track_dangling" and t.GetClass() == "PCB_TRACK" and abs(pcbnew.ToMM(t.GetLength()) - ln) < 0.002
                        and min((t.GetStart() - p).EuclideanNorm(), (t.GetEnd() - p).EuclideanNorm()) < MM(0.01)):
                    board.Remove(t)
                    print("removed dangling", t.GetClass(), (x, y))
                    break
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def save(board):
    board.Save(PCB)
    gen_pcb.write_project()


if __name__ == "__main__" and "--drc" in sys.argv:
    drc(load())
    sys.exit(0)

def maze_passes(board, skip=(), passes=4, label=""):
    import maze
    for k in range(passes):
        txt = drc(board, f"drc_{label}{k}.rpt")
        done = maze.finish(board, txt, skip=skip, win=12.0 + 8.0 * k)
        print(f"pass {label}{k}: routed {done}")
        if not done:
            break


if __name__ == "__main__":
    # fresh placed board. Run as a child process: if the placement runs in this process,
    # the settings manager keeps a project without net classes.
    subprocess.run([sys.executable, os.path.join(HERE, "gen_pcb.py")], check=True)
    b = load()
    assert b.FindNet("FIELD_V").GetNetClassName() == "FIELD", "net classes not loaded"
    preroute(b)
    if "--freerouting" in sys.argv:          # optional: needs Freerouting 2.4.1 + Java 25
        autoroute(b, int(os.environ.get("PASSES", "30")))
    elif "--reuse" in sys.argv and os.path.exists(STORED):
        import_ses(b, STORED)
    maze_passes(b, skip=("GND", "FGND"), label="sig")       # signals and power, no pours yet
    zones(b)
    maze_passes(b, label="gnd", passes=2)                    # pads the pours did not reach
    stitch(b, "GND")                                          # tie F.Cu and B.Cu pour fragments together
    stitch(b, "FGND")
    islands(b, keep=False)
    maze_passes(b, label="fin", passes=2)                               # whatever the pours left open
    remove_dangling(b)
    save(b)
    drc(b)
