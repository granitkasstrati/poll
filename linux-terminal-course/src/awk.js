/* Sandbox awk: tokenizer, recursive-descent compiler to closures, and runtime. */
(function (G) {
'use strict';
const S = G.Sandbox, { Abort, sprintf, FsErr } = S;
const KWS = new Set(['in', 'if', 'else', 'while', 'for', 'do', 'print', 'printf', 'next', 'exit', 'break', 'continue', 'return', 'delete', 'function', 'func', 'BEGIN', 'END', 'getline']);
const BUILT = new Set(['length', 'substr', 'index', 'split', 'sub', 'gsub', 'match', 'sprintf', 'toupper', 'tolower', 'int', 'sqrt', 'exp', 'log', 'sin', 'cos', 'atan2', 'rand', 'srand', 'system', 'systime', 'strftime']);
const NEXT = {}, BRK = {}, CNT = {};
class AwkExit { constructor(c) { this.code = c; } }
class AwkRet { constructor(v) { this.v = v; } }
const OPS = ['**=', '**', '+=', '-=', '*=', '/=', '%=', '^=', '==', '!=', '<=', '>=', '&&', '||', '++', '--', '!~', '>>'];
function awkLex(src) {
  const T = []; let i = 0;
  const valEnd = () => { const t = T[T.length - 1]; return !!t && (t.t === 'num' || t.t === 'str' || (t.t === 'name' && !KWS.has(t.v)) || (t.t === 'op' && (t.v === ')' || t.v === ']' || t.v === '++' || t.v === '--'))); };
  while (i < src.length) {
    const c = src[i];
    if (c === '\\' && src[i + 1] === '\n') { i += 2; continue; }
    if (c === ' ' || c === '\t' || c === '\r') { i++; continue; }
    if (c === '\n') { T.push({ t: 'nl' }); i++; continue; }
    if (c === '#') { while (i < src.length && src[i] !== '\n') i++; continue; }
    if (c === '"') {
      let s = ''; i++;
      while (i < src.length && src[i] !== '"') { if (src[i] === '\\') { const n = src[i + 1]; s += ({ n: '\n', t: '\t', r: '\r', '\\': '\\', '"': '"', '/': '/', a: '\x07' })[n] ?? ('\\' + n); i += 2; } else s += src[i++]; }
      if (i >= src.length) throw new Abort('awk: unterminated string'); i++; T.push({ t: 'str', v: s }); continue;
    }
    if (c === '/' && !valEnd()) {
      let s = ''; i++;
      while (i < src.length && src[i] !== '/') {
        if (src[i] === '\n') throw new Abort('awk: unterminated regexp');
        if (src[i] === '\\' && src[i + 1] === '/') { s += '/'; i += 2; continue; }
        if (src[i] === '\\') { s += src[i] + src[i + 1]; i += 2; continue; }
        if (src[i] === '[') { let j = i + 1; if (src[j] === '^') j++; if (src[j] === ']') j++; while (j < src.length && src[j] !== ']') j++; s += src.slice(i, j + 1); i = j + 1; continue; }
        s += src[i++];
      }
      if (i >= src.length) throw new Abort('awk: unterminated regexp'); i++; T.push({ t: 'ere', v: s }); continue;
    }
    let m = /^(0[xX][0-9a-fA-F]+|\d+\.?\d*(?:[eE][-+]?\d+)?|\.\d+(?:[eE][-+]?\d+)?)/.exec(src.slice(i, i + 40));
    if (m) { T.push({ t: 'num', v: Number(m[1]) }); i += m[1].length; continue; }
    m = /^[A-Za-z_]\w*/.exec(src.slice(i, i + 80));
    if (m) { i += m[0].length; T.push({ t: 'name', v: m[0], call: src[i] === '(' }); continue; }
    const op = OPS.find(o => src.startsWith(o, i));
    if (op) { T.push({ t: 'op', v: op }); i += op.length; continue; }
    if ('{}()[];,+-*/%^!<>=~?:$|'.includes(c)) { T.push({ t: 'op', v: c }); i++; continue; }
    throw new Abort('awk: syntax error: unexpected character ' + c);
  }
  return T;
}
const looksNum = s => /^\s*[-+]?(\d+\.?\d*([eE][-+]?\d+)?|\.\d+([eE][-+]?\d+)?)\s*$/.test(s);
const num = v => { if (typeof v === 'number') return v; if (v === undefined) return 0; const f = parseFloat(v); return isNaN(f) ? 0 : f; };
const str = v => v === undefined ? '' : typeof v === 'number' ? (Number.isInteger(v) ? String(v) : String(parseFloat(v.toPrecision(6)))) : v;
const truthy = v => v === undefined ? false : typeof v === 'number' ? v !== 0 : looksNum(v) ? parseFloat(v) !== 0 : v !== '';
const numLike = v => v === undefined || typeof v === 'number' || looksNum(v);
function compare(a, b, strc, op) {
  let c;
  if (!strc && numLike(a) && numLike(b)) c = num(a) - num(b); else { const x = str(a), y = str(b); c = x < y ? -1 : x > y ? 1 : 0; }
  switch (op) { case '<': return +(c < 0); case '<=': return +(c <= 0); case '==': return +(c === 0); case '!=': return +(c !== 0); case '>=': return +(c >= 0); default: return +(c > 0); }
}
function arith(op, a, b) { switch (op) { case '+': return a + b; case '-': return a - b; case '*': return a * b; case '/': if (b === 0) throw new Abort('awk: division by zero'); return a / b; case '%': if (b === 0) throw new Abort('awk: division by zero in %'); return a % b; default: return Math.pow(a, b); } }

function compile(src, R) {
  const T = awkLex(src); let p = 0;
  const pk = () => T[p] || { t: 'eof' }; const isOp = v => pk().t === 'op' && pk().v === v; const isName = v => pk().t === 'name' && pk().v === v;
  const acc = v => { if (isOp(v)) { p++; return true; } return false; };
  const bad = w => new Abort('awk: syntax error near ' + (pk().t === 'eof' ? 'end of program' : pk().t === 'nl' ? 'newline' : JSON.stringify(pk().v)) + (w ? ' (expected ' + w + ')' : ''));
  const exp = v => { if (!acc(v)) throw bad(v); };
  const nls = () => { while (pk().t === 'nl' || isOp(';')) p++; }; const onl = () => { while (pk().t === 'nl') p++; };
  const atEnd = () => isOp(';') || pk().t === 'nl' || isOp('}') || pk().t === 'eof';
  function assign(f) {
    const l = tern(f);
    if (pk().t === 'op' && /^(=|\+=|-=|\*=|\/=|%=|\^=|\*\*=)$/.test(pk().v) && l.set) {
      const op = T[p++].v; onl(); const r = assign(f);
      if (op === '=') return { ev: () => { const v = r.ev(); l.set(v); return v; } };
      const b = op === '**=' ? '^' : op.slice(0, -1); return { ev: () => { const v = arith(b, num(l.ev()), num(r.ev())); l.set(v); return v; } };
    }
    return l;
  }
  function tern(f) { const c = or(f); if (acc('?')) { onl(); const a = assign(f); onl(); exp(':'); onl(); const b = assign(f); return { ev: () => truthy(c.ev()) ? a.ev() : b.ev() }; } return c; }
  function or(f) { let l = and(f); while (acc('||')) { onl(); const a = l, r = and(f); l = { ev: () => (truthy(a.ev()) || truthy(r.ev())) ? 1 : 0 }; } return l; }
  function and(f) { let l = inop(f); while (acc('&&')) { onl(); const a = l, r = inop(f); l = { ev: () => (truthy(a.ev()) && truthy(r.ev())) ? 1 : 0 }; } return l; }
  function inop(f) { let l = match(f); while (!f.noIn && isName('in')) { p++; const arr = T[p++].v; const a = l; l = { ev: () => R.arr(arr).has(a.list ? a.list.map(x => str(x.ev())).join('\x1c') : str(a.ev())) ? 1 : 0 }; } return l; }
  function match(f) { let l = cmp(f); while (isOp('~') || isOp('!~')) { const neg = T[p++].v === '!~'; const a = l, r = cmp(f); l = { ev: () => ((r.re || R.re(str(r.ev()))).test(str(a.ev())) !== neg) ? 1 : 0 }; } return l; }
  function cmp(f) { let l = cat(f); const o = pk(); if (o.t === 'op' && /^(<|<=|==|!=|>=|>)$/.test(o.v) && !(o.v === '>' && f.noGt)) { p++; const a = l, r = cat(f); const strc = !!(a.isStr || r.isStr); l = { ev: () => compare(a.ev(), r.ev(), strc, o.v) }; } return l; }
  function cat(f) {
    let l = add(f);
    for (;;) { const t = pk(); if (t.t === 'num' || t.t === 'str' || (t.t === 'name' && !KWS.has(t.v)) || (t.t === 'op' && (t.v === '$' || t.v === '(' || t.v === '++' || t.v === '--'))) { const a = l, r = add(f); l = { ev: () => str(a.ev()) + str(r.ev()) }; } else break; }
    return l;
  }
  function add(f) { let l = mul(f); while (isOp('+') || isOp('-')) { const o = T[p++].v, a = l, r = mul(f); l = { ev: () => arith(o, num(a.ev()), num(r.ev())) }; } return l; }
  function mul(f) { let l = unary(f); while (isOp('*') || isOp('/') || isOp('%')) { const o = T[p++].v, a = l, r = unary(f); l = { ev: () => arith(o, num(a.ev()), num(r.ev())) }; } return l; }
  function unary(f) { if (acc('!')) { const a = unary(f); return { ev: () => truthy(a.ev()) ? 0 : 1 }; } if (acc('-')) { const a = unary(f); return { ev: () => -num(a.ev()) }; } if (acc('+')) { const a = unary(f); return { ev: () => num(a.ev()) }; } return pow(f); }
  function pow(f) { const b = post(f); if (acc('^') || acc('**')) { const e = unary(f); return { ev: () => Math.pow(num(b.ev()), num(e.ev())) }; } return b; }
  function post(f) {
    if (isOp('++') || isOp('--')) { const d = T[p++].v === '++' ? 1 : -1; const l = post(f); if (!l.set) throw bad('variable'); return { ev: () => { const v = num(l.ev()) + d; l.set(v); return v; } }; }
    const l = prim(f);
    if (l.set && (isOp('++') || isOp('--'))) { const d = T[p++].v === '++' ? 1 : -1; return { ev: () => { const v = num(l.ev()); l.set(v + d); return v; } }; }
    return l;
  }
  function prim(f) {
    const t = T[p++]; if (!t) throw new Abort('awk: unexpected end of program');
    if (t.t === 'num') return { ev: () => t.v };
    if (t.t === 'str') return { ev: () => t.v, isStr: true };
    if (t.t === 'ere') { const re = R.re(t.v); return { re, ev: () => re.test(R.field(0)) ? 1 : 0 }; }
    if (t.t === 'op' && t.v === '$') { const e = prim(f); return { ev: () => R.field(num(e.ev())), set: v => R.setField(num(e.ev()), v) }; }
    if (t.t === 'op' && t.v === '(') { const e = assign({}); if (isOp(',')) { const list = [e]; while (acc(',')) list.push(assign({})); exp(')'); return { list, ev: () => list.map(x => str(x.ev())).join('\x1c') }; } exp(')'); return { ev: e.ev }; }
    if (t.t === 'op' && t.v === '-') { const a = unary(f); return { ev: () => -num(a.ev()) }; }
    if (t.t === 'op' && t.v === '!') { const a = unary(f); return { ev: () => truthy(a.ev()) ? 0 : 1 }; }
    if (t.t === 'name' && !KWS.has(t.v)) {
      if (isOp('(') && (BUILT.has(t.v) || t.call)) { p++; const args = []; onl(); while (!isOp(')')) { args.push(assign({})); onl(); if (!acc(',')) break; onl(); } exp(')'); return call(t.v, args); }
      if (t.v === 'length') return call('length', []);
      if (acc('[')) { const subs = [assign({})]; while (acc(',')) subs.push(assign({})); exp(']'); const key = () => subs.map(s => str(s.ev())).join('\x1c'); return { ev: () => { const a = R.arr(t.v), k = key(); if (!a.has(k)) a.set(k, undefined); return a.get(k); }, set: v => R.arr(t.v).set(key(), v) }; }
      return { ev: () => { const v = R.get(t.v); return v instanceof Map ? undefined : v; }, set: v => R.set(t.v, v), name: t.v };
    }
    if (t.t === 'name' && t.v === 'getline') throw new Abort('awk: getline is not supported in the sandbox');
    p--; throw bad();
  }
  function call(name, args) {
    const a = i => args[i] ? args[i].ev() : undefined; const reOf = n => n.re || R.re(str(n.ev()));
    const subst = all => { const tgt = args[2] || { ev: () => R.field(0), set: v => R.setField(0, v) }; if (!tgt.set) throw new Abort('awk: ' + name + ' third argument must be assignable'); return { ev: () => { const re = reOf(args[0]); const rep = str(a(1)); let n = 0; const s = str(tgt.ev()); const out = s.replace(new RegExp(re.source, re.flags.replace('g', '') + (all ? 'g' : '')), m => { n++; return rep.replace(/\\\\|\\&|&/g, x => x === '&' ? m : x === '\\&' ? '&' : '\\'); }); if (n) tgt.set(out); return n; } }; };
    switch (name) {
      case 'length': return { ev: () => { if (args[0] && args[0].name && R.get(args[0].name) instanceof Map) return R.get(args[0].name).size; return str(args.length ? a(0) : R.field(0)).length; } };
      case 'substr': return { ev: () => { const s = str(a(0)); let i = Math.round(num(a(1))), n = args[2] ? Math.round(num(a(2))) : Infinity; if (i < 1) { n += i - 1; i = 1; } return n <= 0 ? '' : s.substr(i - 1, n === Infinity ? undefined : n); } };
      case 'index': return { ev: () => str(a(0)).indexOf(str(a(1))) + 1 };
      case 'split': return { ev: () => { const s = str(a(0)); if (!args[1] || !args[1].name) throw new Abort('awk: split: second argument must be an array'); const arr = R.arr(args[1].name); arr.clear(); const parts = args[2] ? (args[2].re ? s.split(args[2].re) : R.splitBy(s, str(a(2)))) : R.splitBy(s, str(R.get('FS'))); if (s === '') return 0; parts.forEach((x, i) => arr.set(String(i + 1), x)); return parts.length; } };
      case 'sub': return subst(false); case 'gsub': return subst(true);
      case 'match': return { ev: () => { const m = reOf(args[1]).exec(str(a(0))); R.set('RSTART', m ? m.index + 1 : 0); R.set('RLENGTH', m ? m[0].length : -1); return m ? m.index + 1 : 0; } };
      case 'sprintf': return { ev: () => sprintf(str(a(0)), args.slice(1).map(x => x.ev())) };
      case 'toupper': return { ev: () => str(a(0)).toUpperCase() }; case 'tolower': return { ev: () => str(a(0)).toLowerCase() };
      case 'int': return { ev: () => Math.trunc(num(a(0))) }; case 'sqrt': return { ev: () => Math.sqrt(num(a(0))) }; case 'exp': return { ev: () => Math.exp(num(a(0))) }; case 'log': return { ev: () => Math.log(num(a(0))) };
      case 'sin': return { ev: () => Math.sin(num(a(0))) }; case 'cos': return { ev: () => Math.cos(num(a(0))) }; case 'atan2': return { ev: () => Math.atan2(num(a(0)), num(a(1))) };
      case 'rand': return { ev: () => Math.random() }; case 'srand': return { ev: () => 0 }; case 'systime': return { ev: () => Math.floor(Date.now() / 1000) };
      case 'strftime': return { ev: () => new Date().toISOString().slice(0, 19).replace('T', ' ') };
      case 'system': return { ev: () => { R.flush(); return R.sh.execSrc(str(a(0)), R.io.ctx); } };
    }
    return { ev: () => {
      const fn = R.funcs[name]; if (!fn) throw new Abort('awk: function ' + name + ' never defined');
      const frame = new Map(); fn.params.forEach((pn, i) => { const x = args[i]; if (x && x.name && R.get(x.name) instanceof Map) frame.set(pn, R.get(x.name)); else if (x && x.name && R.get(x.name) === undefined) { frame.set(pn, undefined); frame.byRef = frame.byRef || []; frame.byRef.push([pn, x.name]); } else frame.set(pn, x ? x.ev() : undefined); });
      if (R.frames.length > 200) throw new Abort('awk: function call nesting too deep'); R.frames.push(frame);
      try { fn.body(); return undefined; } catch (e) { if (e instanceof AwkRet) return e.v; throw e; }
      finally { R.frames.pop(); for (const [pn, outer] of frame.byRef || []) if (frame.get(pn) instanceof Map) R.set(outer, frame.get(pn)); }
    } };
  }
  function block() { exp('{'); const ss = []; nls(); while (!isOp('}')) { if (pk().t === 'eof') throw new Abort('awk: syntax error: missing }'); ss.push(stmt()); nls(); } p++; return () => { for (const s of ss) s(); }; }
  const sob = () => { onl(); return isOp('{') ? block() : stmt(); };
  const end = () => { if (isOp(';') || pk().t === 'nl') { p++; return; } if (isOp('}') || pk().t === 'eof') return; throw bad(); };
  const loopBody = body => { R.tick(); try { body(); } catch (e) { if (e === BRK) return true; if (e !== CNT) throw e; } return false; };
  function stmt() {
    const t = pk();
    if (isOp('{')) return block();
    if (isOp(';')) { p++; return () => {}; }
    if (t.t === 'name') switch (t.v) {
      case 'if': { p++; exp('('); const c = assign({}); exp(')'); const a = sob(); const save = p; nls(); let b = null; if (isName('else')) { p++; b = sob(); } else p = save; return () => { if (truthy(c.ev())) a(); else if (b) b(); }; }
      case 'while': { p++; exp('('); const c = assign({}); exp(')'); const body = sob(); return () => { while (truthy(c.ev())) if (loopBody(body)) break; }; }
      case 'do': { p++; const body = sob(); nls(); if (!isName('while')) throw bad('while'); p++; exp('('); const c = assign({}); exp(')'); end(); return () => { do { if (loopBody(body)) break; } while (truthy(c.ev())); }; }
      case 'for': {
        p++; exp('(');
        if (pk().t === 'name' && T[p + 1] && T[p + 1].t === 'name' && T[p + 1].v === 'in' && T[p + 2] && T[p + 2].t === 'name' && T[p + 3] && T[p + 3].t === 'op' && T[p + 3].v === ')') { const v = T[p].v, arr = T[p + 2].v; p += 4; const body = sob(); return () => { for (const k of [...R.arr(arr).keys()]) { R.set(v, k); if (loopBody(body)) break; } }; }
        const init = isOp(';') ? null : assign({}); exp(';'); onl(); const c = isOp(';') ? null : assign({}); exp(';'); onl(); const st = isOp(')') ? null : assign({}); exp(')'); const body = sob();
        return () => { if (init) init.ev(); for (;;) { if (c && !truthy(c.ev())) break; if (loopBody(body)) break; if (st) st.ev(); } };
      }
      case 'print': case 'printf': {
        p++; let args = []; if (!atEnd() && !isOp('>') && !isOp('>>') && !isOp('|')) { args.push(assign({ noGt: true })); while (acc(',')) { onl(); args.push(assign({ noGt: true })); } }
        if (args.length === 1 && args[0].list) args = args[0].list;
        let mode = null, dest = null; if (acc('>')) mode = 'w'; else if (acc('>>')) mode = 'a'; else if (acc('|')) mode = 'p'; if (mode) dest = cat({ noGt: true }); end();
        const pf = t.v === 'printf'; if (pf && !args.length) throw new Abort('awk: printf: no format');
        return () => { const s = pf ? sprintf(str(args[0].ev()), args.slice(1).map(x => x.ev())) : (args.length ? args.map(x => str(x.ev())).join(str(R.get('OFS'))) : R.field(0)) + str(R.get('ORS')); R.emit(s, mode, dest && str(dest.ev())); };
      }
      case 'next': p++; end(); return () => { throw NEXT; };
      case 'exit': { p++; const c = atEnd() ? null : assign({}); end(); return () => { throw new AwkExit(c ? num(c.ev()) : 0); }; }
      case 'break': p++; end(); return () => { throw BRK; };
      case 'continue': p++; end(); return () => { throw CNT; };
      case 'return': { p++; const e = atEnd() ? null : assign({}); end(); return () => { throw new AwkRet(e ? e.ev() : undefined); }; }
      case 'delete': { p++; const name = T[p++].v; if (acc('[')) { const subs = [assign({})]; while (acc(',')) subs.push(assign({})); exp(']'); end(); return () => { R.arr(name).delete(subs.map(s => str(s.ev())).join('\x1c')); }; } end(); return () => { R.arr(name).clear(); }; }
    }
    const e = assign({}); end(); return () => { e.ev(); };
  }
  const prog = { begins: [], ends: [], rules: [] };
  for (;;) {
    nls(); if (pk().t === 'eof') break;
    if (isName('function') || isName('func')) { p++; const name = T[p++].v; exp('('); const params = []; while (!isOp(')')) { if (pk().t !== 'name') throw bad('parameter name'); params.push(T[p++].v); acc(','); onl(); } p++; onl(); R.funcs[name] = { params, body: block() }; continue; }
    if (isName('BEGIN')) { p++; onl(); prog.begins.push(block()); continue; }
    if (isName('END')) { p++; onl(); prog.ends.push(block()); continue; }
    let pat = null, pat2 = null, act = null;
    if (!isOp('{')) { pat = assign({}); if (acc(',')) { onl(); pat2 = assign({}); } }
    if (isOp('{')) act = block();
    prog.rules.push({ pat, pat2, act, on: false });
  }
  return prog;
}

S.C('awk gawk', (a, io, sh) => {
  let fs = ' ', progSrc = null; const pre = [], files = []; let i = 0;
  for (; i < a.length; i++) { const x = a[i]; if (x === '-F') fs = a[++i]; else if (/^-F./.test(x)) fs = x.slice(2); else if (x === '-v') pre.push(a[++i]); else if (/^-v./.test(x)) pre.push(x.slice(2)); else if (x === '-f') progSrc = sh.read(a[++i]); else if (x === '--') { i++; break; } else break; }
  if (progSrc === null) progSrc = a[i++];
  if (progSrc === undefined) return io.fail('usage: awk [-F fs] [-v var=value] \'program\' [file ...]', 2);
  const rest = a.slice(i);
  if (fs === 't') fs = '\t'; fs = S.unesc(fs);
  const Gv = new Map([['FS', fs], ['OFS', ' '], ['ORS', '\n'], ['NR', 0], ['NF', 0], ['FNR', 0], ['RS', '\n'], ['SUBSEP', '\x1c'], ['FILENAME', ''], ['RSTART', 0], ['RLENGTH', -1]]);
  Gv.set('ENVIRON', new Map(Object.entries(sh.env())));
  let F = ['']; let steps = 0; const outs = new Map(), pipes = new Map(), reCache = new Map();
  const R = {
    sh, io, funcs: {}, frames: [],
    tick() { if (++steps > 400000) throw new Abort('awk: sandbox stopped a runaway loop'); },
    re(s) { let r = reCache.get(s); if (!r) { r = S.mkRe(s, true); reCache.set(s, r); } return r; },
    get(n) { const f = R.frames[R.frames.length - 1]; if (f && f.has(n)) return f.get(n); return Gv.get(n); },
    set(n, v) { const f = R.frames[R.frames.length - 1]; if (f && f.has(n)) { f.set(n, v); return; } Gv.set(n, v); if (n === 'NF') { const k = num(v); F.length = k + 1; for (let j = 1; j <= k; j++) if (F[j] === undefined) F[j] = ''; F[0] = F.slice(1).join(str(Gv.get('OFS'))); } },
    arr(n) { let x = R.get(n); if (!(x instanceof Map)) { x = new Map(); R.set(n, x); } return x; },
    splitBy(s, sep) { if (sep === ' ') { const t = s.trim(); return t === '' ? [] : t.split(/[ \t\n]+/); } if (s === '') return []; if (sep === '') return [...s]; if (sep.length === 1 && sep !== '\\') return s.split(sep); return s.split(R.re(sep)); },
    setRecord(s) { F = [s, ...R.splitBy(s, str(Gv.get('FS')))]; Gv.set('NF', F.length - 1); },
    field(k) { k = Math.trunc(k); if (k < 0) throw new Abort('awk: attempt to access field ' + k); return F[k] === undefined ? '' : F[k]; },
    setField(k, v) { k = Math.trunc(k); v = str(v); if (k === 0) { R.setRecord(v); return; } while (F.length <= k) F.push(''); F[k] = v; Gv.set('NF', F.length - 1); F[0] = F.slice(1).join(str(Gv.get('OFS'))); },
    emit(s, mode, dest) { if (!mode) { io.out(s); return; } if (mode === 'p') { pipes.set(dest, (pipes.get(dest) || '') + s); return; } if (!outs.has(dest)) { outs.set(dest, true); sh.write(dest, s, mode === 'a'); } else sh.write(dest, s, true); },
    flush() {}
  };
  const setCli = x => { const k = x.indexOf('='); const v = S.unesc(x.slice(k + 1)); R.set(x.slice(0, k), looksNum(v) ? v : v); };
  pre.forEach(setCli);
  const prog = compile(progSrc, R); let code = 0, exited = false;
  const guard = fn => { try { fn(); return true; } catch (e) { if (e instanceof AwkExit) { code = e.code; exited = true; return false; } if (e === NEXT) throw new Abort('awk: `next\' used in BEGIN or END'); throw e; } };
  for (const b of prog.begins) if (!guard(b)) break;
  let hard = false;
  if (!exited && (prog.rules.length || prog.ends.length)) {
    const inputs = rest.length ? rest : ['-']; let st = 0;
    outer: for (const f of inputs) {
      if (/^[A-Za-z_]\w*=/.test(f) && !sh.lookup(f)) { setCli(f); continue; }
      let data; try { data = f === '-' ? (io.inTty && io.err('(sandbox: awk is waiting on stdin, and there is none; give it a file or a pipe)\n'), io.stdin()) : sh.read(f); } catch (e) { if (!(e instanceof FsErr)) throw e; io.err('awk: cannot open "' + f + '" (' + e.msg + ')\n'); code = 2; continue; }
      Gv.set('FILENAME', f === '-' ? '' : f); Gv.set('FNR', 0);
      const recs = Gv.get('RS') === '' ? data.replace(/^\n+|\n+$/g, '').split(/\n\n+/).filter(x => x !== '') : S.lines(data);
      for (const rec of recs) {
        Gv.set('NR', num(Gv.get('NR')) + 1); Gv.set('FNR', num(Gv.get('FNR')) + 1); R.setRecord(rec); R.tick();
        try {
          for (const r of prog.rules) {
            let hit;
            if (!r.pat) hit = true;
            else if (r.pat2) { if (r.on) { hit = true; if (truthy(r.pat2.ev())) r.on = false; } else if (truthy(r.pat.ev())) { hit = true; if (!truthy(r.pat2.ev())) r.on = true; } else hit = false; }
            else hit = truthy(r.pat.ev());
            if (hit) { if (r.act) r.act(); else io.out(R.field(0) + str(Gv.get('ORS'))); }
          }
        } catch (e) { if (e === NEXT) continue; if (e instanceof AwkExit) { code = e.code; exited = true; break outer; } if (e === BRK || e === CNT) throw new Abort('awk: break or continue outside a loop'); throw e; }
      }
    }
  }
  if (!hard) for (const b of prog.ends) { try { b(); } catch (e) { if (e instanceof AwkExit) { code = e.code; break; } throw e; } }
  for (const [cmd, data] of pipes) sh.execSrc(cmd, { in: { s: data, p: 0 }, fd: io.ctx.fd });
  return code;
}, "awk [-F SEP] [-v VAR=VAL] 'PATTERN { ACTION }' [FILE] — field processing language. $1..$NF fields, NR line number, BEGIN/END blocks, associative arrays, printf");
})(typeof window !== 'undefined' ? window : globalThis);
