"""Tiny s-expression reader/writer compatible with KiCad 7 files."""
import re
import uuid as _uuid


class Sym(str):
    """Bare (unquoted) atom."""


_tok = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.S)


def loads(text):
    stack, cur = [], []
    pos = 0
    while True:
        m = _tok.match(text, pos)
        if not m:
            break
        pos = m.end()
        op, cl, st, atom = m.groups()
        if op:
            stack.append(cur)
            cur = []
        elif cl:
            done = cur
            cur = stack.pop()
            cur.append(done)
        elif st is not None:
            cur.append(st.replace('\\"', '"').replace("\\\\", "\\"))
        else:
            try:
                cur.append(int(atom))
            except ValueError:
                try:
                    cur.append(float(atom))
                except ValueError:
                    cur.append(Sym(atom))
    return cur[0]


def _fmt(v):
    if isinstance(v, Sym):
        return str(v)
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        s = f"{v:.4f}".rstrip("0").rstrip(".")
        return "0" if s in ("-0", "") else s
    return str(v)


def dumps(e, ind=0):
    """Order-preserving writer; nested lists go on their own lines."""
    if not isinstance(e, list):
        return _fmt(e)
    if all(not isinstance(x, list) for x in e) or (len(e) <= 3 and e and e[0] in ("at", "xy", "size", "font", "start", "end")):
        return "(" + " ".join(dumps(x) for x in e) + ")"
    out = "("
    for i, x in enumerate(e):
        if isinstance(x, list):
            out += "\n" + "  " * (ind + 1) + dumps(x, ind + 1)
        else:
            out += ("" if i == 0 else " ") + _fmt(x)
    return out + ")"


def S(*a):
    return [Sym(a[0])] + list(a[1:])


def uid():
    return str(_uuid.uuid4())


def find(e, key):
    for x in e:
        if isinstance(x, list) and x and x[0] == key:
            return x
    return None


def findall(e, key):
    return [x for x in e if isinstance(x, list) and x and x[0] == key]
