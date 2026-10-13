"""List foreign-net tracks/vias that cross a hand-drawn power plane (they split the fill)."""
import sys
sys.path.insert(0, ".")
import pcbnew
from shapely.geometry import Polygon, LineString, Point
import power, gen_pcb
pcbnew.GetSettingsManager().LoadProject(gen_pcb.PRO)
b = pcbnew.LoadBoard(gen_pcb.PCB)
T = lambda v: pcbnew.ToMM(v)
from collections import defaultdict
hits = defaultdict(list)
for net, layer, prio, pts in power.PLANES:
    poly = Polygon(pts)
    for t in b.GetTracks():
        if t.GetNetname() == net:
            continue
        if t.GetClass() == "PCB_VIA":
            g = Point(T(t.GetPosition().x), T(t.GetPosition().y)).buffer(T(t.GetWidth()) / 2)
        else:
            if t.GetLayer() != layer:
                continue
            g = LineString([(T(t.GetStart().x), T(t.GetStart().y)), (T(t.GetEnd().x), T(t.GetEnd().y))]).buffer(T(t.GetWidth()) / 2)
        if poly.intersects(g):
            c = g.centroid
            hits[(net, b.GetLayerName(layer))].append((t.GetNetname(), round(c.x, 1), round(c.y, 1)))
for k, v in hits.items():
    nets = defaultdict(int)
    for n, x, y in v: nets[n] += 1
    print(k, dict(nets), v[:4])
