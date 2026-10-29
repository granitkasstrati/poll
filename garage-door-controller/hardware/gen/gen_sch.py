"""Generate gdc1.kicad_sch from design.py (label-connected, block-grouped)."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from sexp import S, Sym, dumps, find, findall, loads, uid  # noqa: E402
import design  # noqa: E402

HW = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = "gdc1"
SYMDIR = "/usr/share/kicad/symbols"
LOCAL = {}
G = 2.54
_libcache = {}


def lib_file(nick):
    if nick not in _libcache:
        path = LOCAL.get(nick, os.path.join(SYMDIR, nick + ".kicad_sym"))
        _libcache[nick] = loads(open(path).read())
    return _libcache[nick]


def raw_symbol(nick, name):
    for e in lib_file(nick)[1:]:
        if isinstance(e, list) and e[0] == "symbol" and e[1] == name:
            return e
    raise KeyError(f"{nick}:{name}")


def flat_symbol(lib_id):
    """Return an embedded-library copy named 'Nick:Name', with `extends` resolved."""
    nick, name = lib_id.split(":", 1)
    e = raw_symbol(nick, name)
    ext = find(e, "extends")
    if not ext:
        return [Sym("symbol"), lib_id] + list(e[2:])
    parent = raw_symbol(nick, ext[1])
    assert not find(parent, "extends")
    dprops = {p[1]: p for p in findall(e, "property")}
    head, subs = [], []
    for x in parent[2:]:
        if isinstance(x, list) and x[0] == "symbol":
            sub = list(x)
            sub[1] = name + sub[1][len(ext[1]):]
            subs.append(sub)
        elif isinstance(x, list) and x[0] == "property":
            head.append(dprops.pop(x[1], x))
        else:
            head.append(x)
    return [Sym("symbol"), lib_id] + head + list(dprops.values()) + subs


def sym_name(lib_id):
    return lib_id.split(":", 1)[1]


def units_pins(flat):
    """{unit: [(num, x, y, ang, length)]}  unit 0 = common pins."""
    name = sym_name(flat[1])
    res = {}

    def walk(n, unit):
        for x in n:
            if isinstance(x, list):
                if x[0] == "symbol" and isinstance(x[1], str):
                    u, style = x[1].rsplit("_", 2)[-2:]
                    if style not in ("0", "1"):
                        continue
                    walk(x, int(u))
                elif x[0] == "pin":
                    at = find(x, "at")
                    ln = find(x, "length")
                    num = find(x, "number")[1]
                    hidden = Sym("hide") in x
                    res.setdefault(unit, []).append((str(num), at[1], at[2], at[3] if len(at) > 3 else 0,
                                                     ln[1] if ln else 2.54, hidden))
    walk(flat, 0)
    return res


def body_box(flat):
    xs, ys = [0], [0]

    def walk(n):
        for x in n:
            if isinstance(x, list):
                if x[0] in ("start", "end", "xy", "center") and len(x) >= 3 and all(isinstance(v, (int, float)) for v in x[1:3]):
                    xs.append(x[1]); ys.append(x[2])
                elif x[0] == "pin":
                    at = find(x, "at"); xs.append(at[1]); ys.append(at[2])
                    continue
                if x[0] != "property":
                    walk(x)
    walk(flat)
    return min(xs), min(ys), max(xs), max(ys)


def xf(sx, sy, rot):
    """rotate a screen-space offset by the symbol rotation (KiCad convention)"""
    return (sx, sy) if rot == 0 else (sy, -sx)


ROT_LIBS = {"Device:R", "Device:C", "Device:C_Polarized", "Device:L", "Device:Polyfuse"}


def snap(v):
    return round(v / G) * G


NS = __import__("uuid").UUID("3f0c9a1e-6d2b-4c57-9b1a-6a1d0e5c6d01")


def det_uuid(key):
    return str(__import__("uuid").uuid5(NS, key))


class Sheet:
    def __init__(self):
        self.root = det_uuid("root")
        self.items = []
        self.libs = {}

    def lib(self, lib_id):
        if lib_id not in self.libs:
            self.libs[lib_id] = flat_symbol(lib_id)
        return self.libs[lib_id]

    def place(self, ref, lib_id, unit, x, y, value, fp, fields, hide_ref=False, rot=0):
        flat = self.lib(lib_id)
        u = det_uuid(f"{ref}:{unit or 1}")
        allpins = units_pins(flat)
        pins = allpins.get(0, []) + (allpins.get(unit, []) if unit else [])
        bx = body_box(flat)
        props = [
            S("property", "Reference", ref, S("at", x + bx[2] + 1.27, y - 1.27, 0),
              S("effects", S("font", S("size", 1.27, 1.27)), S("justify", Sym("left")),
                *( [Sym("hide")] if hide_ref else []))),
            S("property", "Value", value, S("at", x + bx[2] + 1.27, y + 1.27, 0),
              S("effects", S("font", S("size", 1.27, 1.27)), S("justify", Sym("left")))),
            S("property", "Footprint", fp, S("at", x, y, 0), S("effects", S("font", S("size", 1.27, 1.27)), Sym("hide"))),
            S("property", "Datasheet", "~", S("at", x, y, 0), S("effects", S("font", S("size", 1.27, 1.27)), Sym("hide"))),
        ]
        for k, v in fields.items():
            if v:
                props.append(S("property", k, v, S("at", x, y, 0), S("effects", S("font", S("size", 1.27, 1.27)), Sym("hide"))))
        is_pwr = lib_id.startswith("power:")
        if rot:
            props[0][3] = S("at", x, y - 2.54, rot); props[0][4][2] = S("justify", Sym("bottom"))
            props[1][3] = S("at", x, y + 2.54, rot); props[1][4][2] = S("justify", Sym("top"))
        e = S("symbol", S("lib_id", lib_id), S("at", x, y, rot), S("unit", unit or 1),
              S("in_bom", Sym("no") if is_pwr else Sym("yes")), S("on_board", Sym("no") if is_pwr else Sym("yes")),
              S("dnp", Sym("no")), S("uuid", u), *props,
              *[S("pin", p[0], S("uuid", uid())) for p in {p[0]: p for p in pins}.values()],
              S("instances", S("project", PROJECT, S("path", "/" + self.root, S("reference", ref), S("unit", unit or 1)))))
        self.items.append(e)
        return u, [(p[0], x + xf(p[1], -p[2], rot)[0], y + xf(p[1], -p[2], rot)[1], (p[3] + rot) % 360, p[5])
                   for p in pins]

    def label(self, net, x, y, ang):
        just = "right" if ang in (180, 270) else "left"
        self.items.append(S("label", net, S("at", x, y, ang), S("fields_autoplaced"),
                            S("effects", S("font", S("size", 1.27, 1.27)), S("justify", Sym(just), Sym("bottom"))),
                            S("uuid", uid())))

    def wire(self, x1, y1, x2, y2):
        self.items.append(S("wire", S("pts", S("xy", x1, y1), S("xy", x2, y2)),
                            S("stroke", S("width", 0), S("type", Sym("default"))), S("uuid", uid())))

    def nc(self, x, y):
        self.items.append(S("no_connect", S("at", x, y), S("uuid", uid())))

    def text(self, t, x, y, size=1.27, bold=False):
        f = S("font", S("size", size, size), *( [Sym("bold")] if bold else []))
        self.items.append(S("text", t, S("at", x, y, 0), S("effects", f, S("justify", Sym("left"), Sym("bottom"))),
                            S("uuid", uid())))

    def box(self, x1, y1, x2, y2):
        self.items.append(S("polyline", S("pts", S("xy", x1, y1), S("xy", x2, y1), S("xy", x2, y2), S("xy", x1, y2), S("xy", x1, y1)),
                            S("stroke", S("width", 0.3), S("type", Sym("dash"))), S("uuid", uid())))

    def write(self, path, title):
        libs = S("lib_symbols", *self.libs.values())
        doc = S("kicad_sch", S("version", 20230121), S("generator", Sym("eeschema")), S("uuid", self.root),
                S("paper", "A1"),
                S("title_block", S("title", title), S("date", "2026-10-29"), S("rev", "A"),
                  S("comment", 1, "Generated from hardware/gen/design.py - edit there and regenerate"),
                  S("comment", 2, "Isolated: FIELD_V/FGND (door sensors) and OPENER_* (relay contacts). Everything else is logic GND.")),
                libs, *self.items,
                S("sheet_instances", S("path", "/", S("page", "1"))))
        open(path, "w").write(dumps(doc) + "\n")


STUB = 2.54
FRAME_OVERRIDE = {}


def connect_pins(sh, ref, pins, pinmap):
    """Stub + label on every pin, no-connect flags on unused."""
    seen = set()
    for num, px, py, ang, hidden in pins:
        key = (num, round(px, 2), round(py, 2))
        if key in seen:
            continue
        seen.add(key)
        net = pinmap.get(num, "__missing__")
        if net == "__missing__":
            raise SystemExit(f"{ref} pin {num} not assigned in design.py")
        if net is None:
            sh.nc(px, py)
            continue
        if hidden:
            sh.label(net, px, py, 0)
            continue
        # pin 'at' angle is direction from connection point toward body
        dx, dy, lang = {0: (-STUB, 0, 180), 180: (STUB, 0, 0), 90: (0, STUB, 270), 270: (0, -STUB, 90)}[int(ang) % 360]
        ex, ey = px + dx, py + dy
        sh.wire(px, py, ex, ey)
        sh.label(net, ex, ey, lang)


def label_len(pins, pinmap, side):
    m = 0
    for num, px, py, ang, _len, hidden in pins:
        n = pinmap.get(num)
        if n and int(ang) % 360 == side:
            m = max(m, len(n))
    return m * 1.1 + STUB + 2


def main():
    sh = Sheet()
    blocks = {}
    for ref in design.PARTS:
        blocks.setdefault(design.BLOCK[ref], []).append(ref)

    # A1 = 841 x 594 mm. 3 columns x 3 rows of blocks
    order = sorted(blocks)
    X0, Y0, BW = 12, 14, 266
    rows = [(Y0, 176), (Y0 + 182, 176), (Y0 + 364, 176)]
    frames = [(X0 + c * (BW + 6), rows[r][0], BW, rows[r][1]) for r in range(3) for c in range(3)]
    for k, v in FRAME_OVERRIDE.items():
        frames[k] = v
    assert len(frames) >= len(order)
    for bi, bname in enumerate(order):
        bx0, by0, BWb, BH = frames[bi]
        sh.box(bx0, by0, bx0 + BWb, by0 + BH)
        sh.text(bname.upper(), bx0 + 3, by0 + 8, 3.0, True)
        cx, cy, rowh = bx0 + 6, by0 + 12, 0
        for ref in blocks[bname]:
            p = design.PARTS[ref]
            flat = sh.lib(p["lib"])
            up = units_pins(flat)
            units = sorted(u for u in up if u) or [0]
            rot = 90 if p["lib"] in ROT_LIBS else 0
            for unit in units:
                pins = up.get(0, []) + (up.get(unit, []) if unit else [])
                bx = body_box(flat)
                corners = [xf(cx_, -cy_, rot) for cx_ in (bx[0], bx[2]) for cy_ in (bx[1], bx[3])]
                ext = {0: 0, 90: 0, 180: 0, 270: 0}
                for q in pins:
                    n = p["pins"].get(q[0])
                    ang = (q[3] + rot) % 360
                    ext[ang] = max(ext[ang], (len(n) * 1.15 if n else 0) + STUB + 1.5)
                xs = [c[0] for c in corners]; ys = [c[1] for c in corners]
                left, right = ext[0], ext[180]
                top, bot = max(ext[270], 3), max(ext[90], 3)
                if rot:
                    top, bot = max(top, 4.5), max(bot, 4.5)
                w = (max(xs) - min(xs)) + left + right + (4 if rot else 16)
                h = (max(ys) - min(ys)) + top + bot + 3
                if cx + w > bx0 + BWb - 3:
                    cx, cy, rowh = bx0 + 6, cy + rowh + 2, 0
                ox = snap(cx + left - min(xs))
                oy = snap(cy + top - min(ys))
                fields = {"MPN": p["mpn"], "Note": p["note"]}
                _, pp = sh.place(ref, p["lib"], unit, ox, oy, p["val"], p["fp"], fields, rot=rot)
                connect_pins(sh, ref, pp, p["pins"])
                cx += w
                rowh = max(rowh, h)
            if cy + rowh > by0 + BH:
                print("WARN block overflow", bname, ref)

    # PWR_FLAGs in a strip along the bottom
    fx, fy = X0 + 6, Y0 + 364 + 176 + 10
    sh.text("PWR_FLAG markers (ERC only)", fx, fy - 2, 2.0, True)
    for i, net in enumerate(design.PWR_FLAGS):
        _, pp = sh.place(f"#FLG{i+1:02d}", "power:PWR_FLAG", 1, fx + i * 25, fy + 6, "PWR_FLAG", "", {}, hide_ref=True)
        num, px, py, ang, hid = pp[0]
        sh.wire(px, py, px, py + STUB)
        sh.label(net, px, py + STUB, 270)

    notes = [
        "gdc1 rev A - smart garage door controller (retrofit). Relay NO/COM in parallel with the wall button.",
        "Input: 9-36 VDC any polarity or 24 VAC. USB-C 5 V alone also runs the board (bench / flashing).",
        "U1 compensation (R6, C8, C9) and UVLO (R1, R2) are calculated starting values - see docs/DESIGN.md.",
        "C20/R23 make the relay drive AC-coupled: a stuck-high GPIO cannot hold the opener button (SR4).",
    ]
    for i, t in enumerate(notes):
        sh.text(t, X0 + 200, fy - 4 + i * 4.5, 1.8)
    out = os.path.join(HW, PROJECT + ".kicad_sch")
    sh.write(out, "gdc1 smart garage door controller")
    print("wrote", out, len(sh.items), "items")


if __name__ == "__main__":
    main()
