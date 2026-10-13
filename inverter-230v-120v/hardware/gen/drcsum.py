"""Print DRC violations compactly: drcsum.py report [kind]"""
import re, sys
t = open(sys.argv[1]).read()
kind = sys.argv[2] if len(sys.argv) > 2 else None
for b in re.split(r'\n(?=\[)', t):
    if not b.startswith('['):
        continue
    L = [l.strip() for l in b.strip().splitlines()]
    k = L[0][1:L[0].index(']')]
    if kind and k != kind:
        continue
    if k == 'unconnected_items' and not kind:
        continue
    m = re.search(r'actual ([\d.]+) mm', L[0]); r = re.search(r"\(([^;]*?) clearance ([\d.]+)", L[0])
    print(k, (r.group(2) if r else ''), (m.group(1) if m else ''), '|', ' || '.join(L[2:4])[:230])
