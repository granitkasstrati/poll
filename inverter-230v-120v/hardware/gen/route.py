"""
Routing stage (python3.12):
  1. strip old tracks/vias/zones
  2. pre-route fixed power copper defined in power.py (tracks + zones)
  3. export Specctra DSN -> Freerouting (headless) -> import SES
  4. pour zones, fill, save, write DRC report
"""
import os
import subprocess
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(__file__))
import gen_pcb  # noqa: E402

HW = gen_pcb.HW
PCB = gen_pcb.PCB
WORK = os.environ.get("WORK", os.path.join(os.path.dirname(os.path.abspath(__file__)), "build"))
os.makedirs(WORK, exist_ok=True)
FR = os.environ.get("FREEROUTING", "freerouting.jar")   # app.freerouting:freerouting 2.4.1 from Maven Central
JAVA = os.environ.get("JAVA25", "/usr/lib/jvm/java-25-openjdk-amd64/bin/java")
MM = pcbnew.FromMM


def load():
    pcbnew.GetSettingsManager().LoadProject(gen_pcb.PRO)
    return pcbnew.LoadBoard(PCB)


def clear(board):
    for t in list(board.GetTracks()):
        board.Remove(t)
    for z in [board.GetArea(i) for i in range(board.GetAreaCount())]:
        board.Remove(z)


def autoroute(board, passes=40):
    dsn = os.path.join(WORK, "inv1200.dsn")
    ses = os.path.join(WORK, "inv1200.ses")
    if os.path.exists(ses):
        os.remove(ses)
    assert pcbnew.ExportSpecctraDSN(board, dsn)
    txt = open(dsn).read()
    assert "(class HV_PWR" in txt and "(class HV_SIG" in txt, "DSN lacks net classes"
    cmd = [JAVA, "-jar", FR, "-de", dsn, "-do", ses, "-mp", str(passes), "--gui.enabled=false",
           "-mt", "4"]
    print(" ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=7000)
    log = r.stdout + r.stderr
    open(os.path.join(WORK, "freerouting.log"), "w").write(log)
    tail = [l for l in log.splitlines() if "INFO" in l][-6:]
    print("\n".join(tail))
    assert os.path.exists(ses), "freerouting produced no session"
    return import_ses(board, ses)


NECKED = []   # (track, original width) for autorouter neck-downs below 0.2 mm


def widen_necks(board):
    """2 oz copper wants >= 0.2 mm traces. Widen every neck-down, then put back the few
    segments where DRC reports a clearance problem."""
    import re
    if not NECKED:
        return
    for t, w in NECKED:
        t.SetWidth(MM(0.2))
    txt = drc(board, "drc_widen.rpt")
    pts = []
    for blk in re.split(r"\n(?=\[)", txt):
        if blk.startswith("[clearance]"):
            pts += [(float(x), float(y)) for x, y in re.findall(r"@\(([\d.]+) mm, ([\d.]+) mm\): Track", blk)]
    reverted = 0
    for t, w in NECKED:
        s, e = t.GetStart(), t.GetEnd()
        for x, y in pts:
            p = pcbnew.VECTOR2I(MM(x), MM(y))
            if t.HitTest(p, MM(0.05)):
                t.SetWidth(MM(w))
                reverted += 1
                break
    print(f"neck-downs: {len(NECKED)} widened to 0.2 mm, {reverted} left narrow (clearance)")
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def import_ses(board, ses):
    """KiCad 7's ImportSpecctraSES() needs the GUI frame, so parse the session here.
    Wires/vias marked (type protect) are the pre-routed copper already on the board."""
    import re
    from sexp import loads, find, findall
    d = loads(open(ses).read())
    routes = find(d, "routes")
    res = find(routes, "resolution")
    k = 1e-3 / res[2] if str(res[1]) == "um" else 1e-3   # -> mm
    nt = nv = 0
    created = []
    for net in findall(find(routes, "network_out"), "net"):
        name = net[1]
        ni = board.FindNet(name)
        for w in findall(net, "wire"):
            if any(isinstance(x, list) and x[0] == "type" and str(x[1]) == "protect" for x in w):
                continue
            p = find(w, "path")
            layer = board.GetLayerID(str(p[1]))
            width = p[2] * k
            xy = p[3:]
            pts = [(xy[i] * k, -xy[i + 1] * k) for i in range(0, len(xy), 2)]
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                t = pcbnew.PCB_TRACK(board)
                if width < 0.2:
                    NECKED.append((t, width))
                t.SetStart(pcbnew.VECTOR2I(MM(x1), MM(y1)))
                t.SetEnd(pcbnew.VECTOR2I(MM(x2), MM(y2)))
                t.SetWidth(MM(width))
                t.SetLayer(layer)
                t.SetNet(ni)
                board.Add(t)
                created.append(t)
                nt += 1
        for v in findall(net, "via"):
            if any(isinstance(x, list) and x[0] == "type" and str(x[1]) == "protect" for x in v):
                continue
            m = re.search(r"_(\d+):(\d+)_um", v[1])
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(pcbnew.VECTOR2I(MM(v[2] * k), MM(-v[3] * k)))
            via.SetWidth(MM(int(m.group(1)) / 1000))
            via.SetDrill(MM(int(m.group(2)) / 1000))
            via.SetNet(ni)
            board.Add(via)
            created.append(via)
            nv += 1
    print(f"imported {nt} track segments, {nv} vias")
    return created


def drc(board, name="drc.rpt"):
    rpt = os.path.join(WORK, name)
    pcbnew.WriteDRCReport(board, rpt, pcbnew.EDA_UNITS_MILLIMETRES, True)
    txt = open(rpt).read()
    import re
    kinds = {}
    for m in re.finditer(r"^\[(\w+)\]", txt, re.M):
        kinds[m.group(1)] = kinds.get(m.group(1), 0) + 1
    summ = [l for l in txt.splitlines() if l.startswith("**")]
    print("\n".join(summ))
    print(kinds)
    return txt


def save(board):
    board.Save(PCB)
    gen_pcb.write_project()


if __name__ == "__main__" and "--drc" in sys.argv:
    b = load()
    print("VBUS class:", b.FindNet("VBUS").GetNetClassName())
    drc(b)
    sys.exit(0)

if __name__ == "__main__":
    # fresh placed board (no tracks/zones). Run as a child process: if the placement runs in this
    # process, the settings manager keeps a project without net classes.
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "gen_pcb.py")], check=True)
    b = load()
    assert b.FindNet("VBUS").GetNetClassName() == "HV_PWR", "net classes not loaded"
    import power
    power.build(b)
    here = os.path.dirname(__file__)
    stored, finish = os.path.join(here, "inv1200.ses"), os.path.join(here, "inv1200_finish.ses")
    import shutil
    if "--reuse" in sys.argv:          # replay the stored sessions without running Freerouting
        import_ses(b, stored)
        if os.path.exists(finish):
            import_ses(b, finish)
    elif "--finish" in sys.argv:       # incremental pass on top of the stored session
        import_ses(b, stored)
        autoroute(b, int(os.environ.get("PASSES", "15")))   # session holds only the new wires
        shutil.copy(os.path.join(WORK, "inv1200.ses"), finish)
    elif "--noroute" not in sys.argv:
        autoroute(b, int(os.environ.get("PASSES", "40")))
        shutil.copy(os.path.join(WORK, "inv1200.ses"), stored)
        if os.path.exists(finish):
            os.remove(finish)
    power.zones(b)
    widen_necks(b)
    import maze
    if maze.finish(b, drc(b, "drc_pre_maze.rpt")):
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    # drop autorouter leftovers (vias / track stubs connected to nothing), repeat until clean
    import re
    for _ in range(6):
        txt = drc(b, "drc_dangling.rpt")
        spots = [(k, float(x), float(y), float(ln) if ln else 0.0) for k, x, y, ln in re.findall(
            r"\[(via_dangling|track_dangling)\][^\n]*\n[^\n]*\n\s*@\(([\d.]+) mm, ([\d.]+) mm\)[^\n]*?(?:length ([\d.]+) mm)?\n", txt)]
        if not spots:
            break
        for k, x, y, ln in spots:
            p = pcbnew.VECTOR2I(MM(x), MM(y))
            for t in list(b.GetTracks()):
                if t.IsLocked():
                    continue
                if (k == "via_dangling" and t.GetClass() == "PCB_VIA" and (t.GetPosition() - p).EuclideanNorm() < MM(0.01)) or \
                   (k == "track_dangling" and t.GetClass() == "PCB_TRACK" and abs(pcbnew.ToMM(t.GetLength()) - ln) < 0.002
                        and min((t.GetStart() - p).EuclideanNorm(), (t.GetEnd() - p).EuclideanNorm()) < MM(0.01)):
                    b.Remove(t)
                    print("removed dangling", t.GetClass(), (x, y))
                    break
    save(b)
    drc(b)
