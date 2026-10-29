"""Fabrication outputs: Gerbers + drill (zipped), BOM CSV, schematic PDF, PCB renders."""
import csv
import os
import shutil
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
import design  # noqa: E402

HW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HW, "fab")
PCB = os.path.join(HW, "gdc1.kicad_pcb")
SCH = os.path.join(HW, "gdc1.kicad_sch")
LAYERS = "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts"


def run(*a):
    r = subprocess.run(a, capture_output=True, text=True)
    if r.returncode:
        print(r.stdout, r.stderr)
        raise SystemExit(f"failed: {' '.join(a)}")


def bom():
    groups = defaultdict(list)
    for ref, p in design.PARTS.items():
        groups[(p["val"], p["fp"], p["mpn"])].append(ref)

    def key(r):
        import re
        m = re.match(r"([A-Z]+)(\d+)", r)
        return (m.group(1), int(m.group(2))) if m else (r, 0)
    rows = sorted(groups.items(), key=lambda kv: key(sorted(kv[1], key=key)[0]))
    with open(os.path.join(OUT, "gdc1_bom.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Qty", "References", "Value", "Footprint", "MPN / suggestion", "Notes"])
        for (val, fp, mpn), refs in rows:
            refs = sorted(refs, key=key)
            noted = [r for r in refs if design.PARTS[r]["note"]]
            notes = "; ".join((f"{r}: " if len(refs) > 1 else "") + design.PARTS[r]["note"] for r in noted)
            w.writerow([len(refs), " ".join(refs), val, fp.split(":")[1], mpn, notes])
    return len(rows)


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    g = os.path.join(OUT, "gerbers")
    os.makedirs(g)
    run("kicad-cli", "pcb", "export", "gerbers", "-l", LAYERS, "--subtract-soldermask", "-o", g + "/", PCB)
    run("kicad-cli", "pcb", "export", "drill", "--format", "excellon", "--excellon-separate-th",
        "--generate-map", "--map-format", "pdf", "-o", g + "/", PCB)
    shutil.make_archive(os.path.join(OUT, "gdc1_gerbers"), "zip", g)
    run("kicad-cli", "pcb", "export", "pos", "--side", "both", "--format", "csv", "--units", "mm",
        "-o", os.path.join(OUT, "gdc1_pos.csv"), PCB)
    run("kicad-cli", "sch", "export", "pdf", "-o", os.path.join(OUT, "gdc1_schematic.pdf"), SCH)
    run("kicad-cli", "pcb", "export", "pdf", "-l", "F.Cu,F.SilkS,Edge.Cuts", "-o",
        os.path.join(OUT, "gdc1_pcb_top.pdf"), PCB)
    run("kicad-cli", "pcb", "export", "pdf", "-l", "B.Cu,Edge.Cuts", "--mirror", "-o",
        os.path.join(OUT, "gdc1_pcb_bottom.pdf"), PCB)
    for name, lay in (("top", "F.Cu,F.SilkS,Edge.Cuts"), ("bottom", "B.Cu,Edge.Cuts"),
                      ("assembly", "F.Fab,F.SilkS,Edge.Cuts")):
        svg = os.path.join(OUT, f"render_{name}.svg")
        run("kicad-cli", "pcb", "export", "svg", "--exclude-drawing-sheet", "--page-size-mode", "2",
            "-l", lay, "-o", svg, PCB)
        run("rsvg-convert", "-w", "2400", "-b", "white", svg, "-o", svg[:-4] + ".png")
        os.remove(svg)
    print("BOM lines:", bom())
    print("wrote", OUT)


if __name__ == "__main__":
    main()
