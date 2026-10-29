"""Compare the netlist KiCad extracts from the schematic against design.py."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import design
from sexp import loads, find, findall

def main(path):
    d = loads(open(path).read())
    got = {}
    for n in findall(find(d, "nets"), "net"):
        name = find(n, "name")[1].lstrip("/")
        nodes = {(find(x, "ref")[1], str(find(x, "pin")[1])) for x in findall(n, "node")}
        nodes = {x for x in nodes if not x[0].startswith("#")}
        if name.startswith("unconnected-") or name.startswith("Net-("):
            for x in nodes:
                got.setdefault("__nc__", set()).add(x)
            continue
        if nodes:
            got[name] = nodes
    want = {k: set(v) for k, v in design.nets().items()}
    errs = 0
    for k in sorted(set(want) | set(got) - {"__nc__"}):
        if want.get(k) != got.get(k):
            errs += 1
            print("MISMATCH", k, "want-got:", sorted(want.get(k, set()) - got.get(k, set())),
                  "got-want:", sorted(got.get(k, set()) - want.get(k, set())))
    comps = {find(c, "ref")[1] for c in findall(find(d, "components"), "comp")}
    missing = set(design.PARTS) - comps
    if missing:
        errs += 1; print("MISSING COMPONENTS", missing)
    print(f"{len(want)} nets / {len(design.PARTS)} parts checked, {errs} mismatches")
    return errs

if __name__ == "__main__":
    sys.exit(1 if main(sys.argv[1]) else 0)
