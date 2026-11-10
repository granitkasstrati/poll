/* Sandbox shell: a small bash-compatible interpreter over an in-memory filesystem. */
(function (G) {
'use strict';
class Incomplete extends Error {}
class SynErr extends Error {}
class FsErr extends Error { constructor(path, msg) { super(msg); this.path = path; this.msg = msg; } }
class ExitEx { constructor(c) { this.code = c; } }
class RetEx { constructor(c) { this.code = c; } }
class BrkEx { constructor(n) { this.n = n; } }
class CntEx { constructor(n) { this.n = n; } }
class Abort { constructor(m) { this.msg = m; } }

/* ---------- lexer ---------- */
const META = ' \t\n;|&()<>';
const KW_PRE = new Set(['if', 'then', 'else', 'elif', 'do', 'while', 'until', '{', '!', 'for', 'time']);
const RES = new Set(['then', 'else', 'elif', 'fi', 'do', 'done', 'esac', '}', 'in']);
function skipSq(s, i) { const j = s.indexOf("'", i); if (j < 0) throw new Incomplete(); return j + 1; }
function skipBt(s, i) { for (; i < s.length; i++) { if (s[i] === '\\') { i++; continue; } if (s[i] === '`') return i + 1; } throw new Incomplete(); }
function skipDq(s, i) {
  while (i < s.length) {
    const c = s[i];
    if (c === '\\') { i += 2; continue; }
    if (c === '"') return i + 1;
    if (c === '$' && s[i + 1] === '(') { i = skipPar(s, i + 2); continue; }
    if (c === '$' && s[i + 1] === '{') { i = skipBr(s, i + 2); continue; }
    if (c === '`') { i = skipBt(s, i + 1); continue; }
    i++;
  }
  throw new Incomplete();
}
function skipPar(s, i) {
  let d = 1;
  while (i < s.length) {
    const c = s[i];
    if (c === '\\') { i += 2; continue; }
    if (c === "'") { i = skipSq(s, i + 1); continue; }
    if (c === '"') { i = skipDq(s, i + 1); continue; }
    if (c === '`') { i = skipBt(s, i + 1); continue; }
    if (c === '(') d++; else if (c === ')') { d--; if (!d) return i + 1; }
    i++;
  }
  throw new Incomplete();
}
function skipBr(s, i) {
  let d = 1;
  while (i < s.length) {
    const c = s[i];
    if (c === '\\') { i += 2; continue; }
    if (c === "'") { i = skipSq(s, i + 1); continue; }
    if (c === '"') { i = skipDq(s, i + 1); continue; }
    if (c === '$' && s[i + 1] === '(') { i = skipPar(s, i + 2); continue; }
    if (c === '$' && s[i + 1] === '{') { d++; i += 2; continue; }
    if (c === '}') { d--; if (!d) return i + 1; }
    i++;
  }
  throw new Incomplete();
}
function skipAnsi(s, i) { for (; i < s.length; i++) { if (s[i] === '\\') { i++; continue; } if (s[i] === "'") return i + 1; } throw new Incomplete(); }
function wordEnd(s, i) {
  const st = i;
  while (i < s.length) {
    const c = s[i];
    if (c === '\\') { if (i + 1 >= s.length) throw new Incomplete(); i += 2; continue; }
    if (c === "'") { i = skipSq(s, i + 1); continue; }
    if (c === '"') { i = skipDq(s, i + 1); continue; }
    if (c === '`') { i = skipBt(s, i + 1); continue; }
    if (c === '$' && s[i + 1] === '(') { i = skipPar(s, i + 2); continue; }
    if (c === '$' && s[i + 1] === '{') { i = skipBr(s, i + 2); continue; }
    if (c === '$' && s[i + 1] === "'") { i = skipAnsi(s, i + 2); continue; }
    if ((c === '<' || c === '>') && s[i + 1] === '(' && i === st) { i = skipPar(s, i + 2); continue; }
    if (c === '(' && /^[A-Za-z_]\w*\+?=$/.test(s.slice(st, i))) { i = skipPar(s, i + 1); continue; }
    if (META.includes(c)) break;
    i++;
  }
  return i;
}
const unq = r => r.replace(/\\(.)/g, '$1').replace(/['"]/g, '');
const RE_REDIR = /(\d*)(&>>|&>|>>|>&|<<<|<<-|<<|<&|>\||>|<)/y;
function lex(src) {
  if (/(^|[^\\])(\\\\)*\\$/.test(src)) throw new Incomplete();
  src = src.replace(/\\\n/g, '');
  const T = []; let i = 0, cond = false; const pend = [];
  const cmdPos = () => { const p = T[T.length - 1]; return !p || p.t === 'nl' || (p.t === 'op' && p.v !== ')') || (p.t === 'word' && KW_PRE.has(p.raw)); };
  while (i < src.length) {
    const c = src[i];
    if (c === ' ' || c === '\t') { i++; continue; }
    if (c === '\n') {
      T.push({ t: 'nl' }); i++;
      while (pend.length) {
        const h = pend.shift(); const lines = []; let found = false;
        while (i < src.length) {
          let j = src.indexOf('\n', i); if (j < 0) j = src.length;
          let ln = src.slice(i, j); i = Math.min(j + 1, src.length);
          if (h.op === '<<-') ln = ln.replace(/^\t+/, '');
          if (ln === h.delim) { found = true; break; }
          lines.push(ln);
        }
        if (!found) throw new Incomplete();
        h.body = lines.length ? lines.join('\n') + '\n' : '';
      }
      continue;
    }
    if (c === '#') { while (i < src.length && src[i] !== '\n') i++; continue; }
    if (cond) {
      const two = src.substr(i, 2);
      if (two === '&&' || two === '||') { T.push({ t: 'word', raw: two }); i += 2; continue; }
      if ('<>()'.includes(c)) { T.push({ t: 'word', raw: c }); i++; continue; }
    } else {
      if (c === '(' && src[i + 1] === '(' && cmdPos()) {
        let j = i + 2, d = 0;
        for (; j < src.length; j++) { if (src[j] === '(') d++; else if (src[j] === ')') { if (!d && src[j + 1] === ')') break; d--; } }
        if (j >= src.length) throw new Incomplete();
        T.push({ t: 'arith', src: src.slice(i + 2, j) }); i = j + 2; continue;
      }
      RE_REDIR.lastIndex = i; const m = RE_REDIR.exec(src);
      if (m && !((m[2] === '<' || m[2] === '>') && !m[1] && src[i + m[0].length] === '(')) {
        const tok = { t: 'redir', op: m[2] === '>|' ? '>' : m[2], fd: m[1] ? +m[1] : null }; i += m[0].length;
        if (tok.op === '<<' || tok.op === '<<-') {
          while (src[i] === ' ' || src[i] === '\t') i++;
          const e = wordEnd(src, i), raw = src.slice(i, e);
          if (!raw) throw new SynErr("syntax error near unexpected token `newline'");
          tok.quoted = /['"\\]/.test(raw); tok.delim = unq(raw); i = e; pend.push(tok);
        }
        T.push(tok); continue;
      }
      const two = src.substr(i, 2);
      if (two === '&&' || two === '||' || two === ';;' || two === '|&') { T.push({ t: 'op', v: two }); i += 2; continue; }
      if (';|&()'.includes(c)) { T.push({ t: 'op', v: c }); i++; continue; }
    }
    const e = wordEnd(src, i);
    if (e === i) throw new SynErr("syntax error near unexpected token `" + c + "'");
    const raw = src.slice(i, e), cp = cmdPos();
    T.push({ t: 'word', raw });
    if (raw === '[[' && cp) cond = true; else if (raw === ']]') cond = false;
    i = e;
  }
  if (pend.length) throw new Incomplete();
  return T;
}

/* ---------- parser ---------- */
function parse(src) {
  const T = lex(src); let p = 0;
  const isOp = v => T[p] && T[p].t === 'op' && T[p].v === v;
  const isKw = w => T[p] && T[p].t === 'word' && T[p].raw === w;
  const skipNl = () => { while (T[p] && T[p].t === 'nl') p++; };
  const bad = () => { const t = T[p]; return new SynErr("syntax error near unexpected token `" + (t ? (t.v || t.raw || t.op || 'newline') : 'newline') + "'"); };
  const need = w => { if (!T[p]) throw new Incomplete(); if (!isKw(w)) throw bad(); p++; };
  function list(stop) {
    const items = [];
    for (;;) {
      while (T[p] && (T[p].t === 'nl' || (items.length === 0 && false))) p++;
      const t = T[p]; if (!t) break;
      if (t.t === 'word' && stop.includes(t.raw)) break;
      if (t.t === 'op' && (t.v === ')' || t.v === ';;')) break;
      const node = andor(); let bg = false;
      if (isOp('&')) { bg = true; p++; } else if (isOp(';')) p++;
      else if (T[p] && T[p].t !== 'nl' && !(T[p].t === 'op' && (T[p].v === ')' || T[p].v === ';;')) && !(T[p].t === 'word' && stop.includes(T[p].raw))) throw bad();
      items.push({ node, bg });
    }
    return { k: 'list', items };
  }
  function andor() {
    const first = pipe(), rest = [];
    while (isOp('&&') || isOp('||')) { const op = T[p++].v; skipNl(); if (!T[p]) throw new Incomplete(); rest.push({ op, node: pipe() }); }
    return rest.length ? { k: 'andor', first, rest } : first;
  }
  function pipe() {
    let neg = false, time = false;
    if (isKw('time')) { time = true; p++; }
    while (isKw('!')) { neg = !neg; p++; }
    const cmds = [cmd()];
    while (isOp('|') || isOp('|&')) { if (T[p].v === '|&') cmds[cmds.length - 1].errToo = true; p++; skipNl(); if (!T[p]) throw new Incomplete(); cmds.push(cmd()); }
    return (cmds.length === 1 && !neg && !time) ? cmds[0] : { k: 'pipe', neg, time, cmds };
  }
  function cmd() {
    const t = T[p]; if (!t) throw new Incomplete(); let n;
    if (t.t === 'arith') { p++; n = { k: 'arith', src: t.src }; }
    else if (t.t === 'op' && t.v === '(') { p++; const body = list([]); if (!T[p]) throw new Incomplete(); if (!isOp(')')) throw bad(); p++; n = { k: 'sub', body }; }
    else if (t.t === 'word') {
      switch (t.raw) {
        case '{': { p++; const body = list(['}']); need('}'); n = { k: 'group', body }; break; }
        case 'if': {
          p++; const clauses = []; let els = null;
          let c = list(['then']); need('then'); clauses.push({ cond: c, body: list(['elif', 'else', 'fi']) });
          while (isKw('elif')) { p++; c = list(['then']); need('then'); clauses.push({ cond: c, body: list(['elif', 'else', 'fi']) }); }
          if (isKw('else')) { p++; els = list(['fi']); }
          need('fi'); n = { k: 'if', clauses, els }; break;
        }
        case 'while': case 'until': { p++; const c = list(['do']); need('do'); const body = list(['done']); need('done'); n = { k: 'while', until: t.raw === 'until', cond: c, body }; break; }
        case 'for': {
          p++; if (!T[p]) throw new Incomplete();
          if (T[p].t === 'arith') {
            const parts = T[p++].src.split(';'); if (isOp(';')) p++; skipNl(); need('do'); const body = list(['done']); need('done');
            n = { k: 'cfor', parts, body };
          } else {
            const v = T[p++].raw; let words = null; skipNl();
            if (isKw('in')) { p++; words = []; while (T[p] && T[p].t === 'word') words.push(T[p++].raw); }
            if (isOp(';')) p++; skipNl(); need('do'); const body = list(['done']); need('done');
            n = { k: 'for', v, words, body };
          }
          break;
        }
        case 'case': {
          p++; if (!T[p]) throw new Incomplete(); const word = T[p++].raw; skipNl(); need('in'); const items = [];
          for (;;) {
            skipNl(); if (!T[p]) throw new Incomplete(); if (isKw('esac')) break;
            if (isOp('(')) p++;
            const pats = [];
            for (;;) { if (!T[p] || T[p].t !== 'word') throw bad(); pats.push(T[p++].raw); if (isOp('|')) { p++; continue; } break; }
            if (!isOp(')')) throw bad(); p++;
            const body = list(['esac']); if (isOp(';;')) p++;
            items.push({ pats, body });
          }
          need('esac'); n = { k: 'case', word, items }; break;
        }
        case 'function': {
          p++; const name = T[p++].raw; if (isOp('(')) { p++; if (!isOp(')')) throw bad(); p++; } skipNl(); if (!T[p]) throw new Incomplete();
          return { k: 'func', name, body: cmd() };
        }
        default:
          if (RES.has(t.raw)) throw bad();
          if (T[p + 1] && T[p + 1].t === 'op' && T[p + 1].v === '(' && T[p + 2] && T[p + 2].t === 'op' && T[p + 2].v === ')' && /^[\w:.-]+$/.test(t.raw)) {
            p += 3; skipNl(); if (!T[p]) throw new Incomplete(); return { k: 'func', name: t.raw, body: cmd() };
          }
          return simple();
      }
    } else if (t.t === 'redir') return simple();
    else throw bad();
    n.redirs = []; while (T[p] && T[p].t === 'redir') n.redirs.push(redir());
    return n;
  }
  function redir() {
    const t = T[p++]; if (t.op === '<<' || t.op === '<<-') return t;
    const w = T[p]; if (!w || w.t !== 'word') throw bad(); p++; t.target = w.raw; return t;
  }
  function simple() {
    const n = { k: 'simple', assigns: [], words: [], redirs: [] };
    for (;;) {
      const t = T[p]; if (!t) break;
      if (t.t === 'redir') { n.redirs.push(redir()); continue; }
      if (t.t !== 'word') break;
      if (!n.words.length && /^[A-Za-z_]\w*(\[[^\]]*\])?\+?=/.test(t.raw)) n.assigns.push(t.raw); else n.words.push(t.raw);
      p++;
    }
    return n;
  }
  const ast = list([]);
  if (p < T.length) throw bad();
  return ast;
}

/* ---------- word parts ---------- */
function unesc(s, oct3) {
  return s.replace(/\\(n|t|r|a|b|e|E|f|v|\\|'|"|x[0-9a-fA-F]{1,2}|0[0-7]{0,3}|[1-7][0-7]{0,2})/g, (m, c) => {
    switch (c[0]) {
      case 'n': return '\n'; case 't': return '\t'; case 'r': return '\r'; case 'a': return '\x07'; case 'b': return '\b';
      case 'e': case 'E': return '\x1b'; case 'f': return '\f'; case 'v': return '\v'; case '\\': return '\\'; case "'": return "'"; case '"': return '"';
      case 'x': return String.fromCharCode(parseInt(c.slice(1), 16));
      default: return String.fromCharCode(parseInt(c, 8) & 255);
    }
  });
}
function parseParts(raw, dq) {
  const parts = []; let i = 0;
  const lit = (s, q) => { const l = parts[parts.length - 1]; if (l && l.k === 'lit' && l.q === q) l.s += s; else parts.push({ k: 'lit', s, q }); };
  while (i < raw.length) {
    const c = raw[i];
    if (c === '\\') {
      const n = raw[i + 1];
      if (dq) { if (n !== undefined && '$`"\\'.includes(n)) lit(n, true); else if (n === '\n') { /* skip */ } else lit('\\' + (n === undefined ? '' : n), true); }
      else if (n !== undefined) lit(n, true);
      i += 2; continue;
    }
    if (!dq && c === "'") { const e = skipSq(raw, i + 1); lit(raw.slice(i + 1, e - 1), true); i = e; continue; }
    if (!dq && c === '"') { const e = skipDq(raw, i + 1); const inner = parseParts(raw.slice(i + 1, e - 1), true); if (!inner.length) lit('', true); for (const x of inner) { if (x.k === 'lit') lit(x.s, true); else parts.push(x); } i = e; continue; }
    if (c === '`') { const e = skipBt(raw, i + 1); parts.push({ k: 'cmd', src: raw.slice(i + 1, e - 1).replace(/\\([`$\\])/g, '$1'), q: !!dq }); i = e; continue; }
    if (c === '$') {
      const n = raw[i + 1];
      if (!dq && n === "'") { const e = skipAnsi(raw, i + 2); lit(unesc(raw.slice(i + 2, e - 1)), true); i = e; continue; }
      if (n === '(' && raw[i + 2] === '(') {
        const e = skipPar(raw, i + 2);
        if (raw[e - 2] === ')') { parts.push({ k: 'arith', src: raw.slice(i + 3, e - 2), q: !!dq }); i = e; continue; }
      }
      if (n === '(') { const e = skipPar(raw, i + 2); parts.push({ k: 'cmd', src: raw.slice(i + 2, e - 1), q: !!dq }); i = e; continue; }
      if (n === '{') { const e = skipBr(raw, i + 2); parts.push({ k: 'param', raw: raw.slice(i + 2, e - 1), q: !!dq }); i = e; continue; }
      const m = /^([A-Za-z_]\w*|[0-9]|[@*#?$!-])/.exec(raw.slice(i + 1));
      if (m) { parts.push({ k: 'param', raw: m[1], q: !!dq, simple: true }); i += 1 + m[1].length; continue; }
      lit('$', !!dq); i++; continue;
    }
    if (!dq && (c === '<' || c === '>') && raw[i + 1] === '(') { const e = skipPar(raw, i + 2); parts.push({ k: 'psub', src: raw.slice(i + 2, e - 1), dir: c }); i = e; continue; }
    let j = i + 1; while (j < raw.length && !'\\\'"`$'.includes(raw[j]) && !(!dq && (raw[j] === '<' || raw[j] === '>'))) j++;
    lit(raw.slice(i, j), !!dq); i = j;
  }
  return parts;
}
function braceExpand(s) {
  try {
    let i = 0;
    while (i < s.length) {
      const c = s[i];
      if (c === '\\') { i += 2; continue; }
      if (c === "'") { i = skipSq(s, i + 1); continue; }
      if (c === '"') { i = skipDq(s, i + 1); continue; }
      if (c === '`') { i = skipBt(s, i + 1); continue; }
      if (c === '$' && s[i + 1] === '{') { i = skipBr(s, i + 2); continue; }
      if (c === '$' && s[i + 1] === '(') { i = skipPar(s, i + 2); continue; }
      if (c === '{') {
        let d = 1, j = i + 1; const commas = [];
        for (; j < s.length; j++) {
          const e = s[j];
          if (e === '\\') { j++; continue; }
          if (e === "'") { j = skipSq(s, j + 1) - 1; continue; }
          if (e === '"') { j = skipDq(s, j + 1) - 1; continue; }
          if (e === '$' && s[j + 1] === '{') { j = skipBr(s, j + 2) - 1; continue; }
          if (e === '{') d++; else if (e === '}') { d--; if (!d) break; } else if (e === ',' && d === 1) commas.push(j);
        }
        if (j < s.length) {
          const pre = s.slice(0, i), post = s.slice(j + 1), inner = s.slice(i + 1, j); let alts = null;
          if (commas.length) { alts = []; let st = i + 1; for (const k of [...commas, j]) { alts.push(s.slice(st, k)); st = k + 1; } }
          else {
            let m = /^(-?\d+)\.\.(-?\d+)(?:\.\.(-?\d+))?$/.exec(inner);
            if (m) {
              const a = +m[1], b = +m[2], st = Math.abs(+m[3] || 1) || 1, w = (/^-?0\d/.test(m[1]) || /^-?0\d/.test(m[2])) ? Math.max(m[1].length, m[2].length) : 0;
              alts = []; for (let x = a; a <= b ? x <= b : x >= b; x += a <= b ? st : -st) alts.push(w ? (x < 0 ? '-' : '') + String(Math.abs(x)).padStart(w - (x < 0 ? 1 : 0), '0') : '' + x);
            } else if ((m = /^([a-zA-Z])\.\.([a-zA-Z])$/.exec(inner))) {
              const a = m[1].charCodeAt(0), b = m[2].charCodeAt(0); alts = [];
              for (let x = a; a <= b ? x <= b : x >= b; x += a <= b ? 1 : -1) alts.push(String.fromCharCode(x));
            }
          }
          if (alts) { const res = []; for (const a of alts) for (const x of braceExpand(a + post)) res.push(pre + x); return res; }
        }
      }
      i++;
    }
  } catch (e) { /* fallthrough */ }
  return [s];
}
const POSIX = { digit: '0-9', alpha: 'a-zA-Z', alnum: 'a-zA-Z0-9', upper: 'A-Z', lower: 'a-z', space: ' \\t\\n\\r\\f\\v', blank: ' \\t', punct: '!-\\/:-@\\[-`{-~', xdigit: '0-9a-fA-F', word: '\\w', cntrl: '\\x00-\\x1f', print: '\\x20-\\x7e', graph: '\\x21-\\x7e' };
const reEsc = s => s.replace(/[.*+?^${}()|[\]\\\/]/g, '\\$&');
function globRe(pat, any) {
  let r = '';
  for (let i = 0; i < pat.length; i++) {
    const c = pat[i];
    if (c === '\\' && i + 1 < pat.length) r += reEsc(pat[++i]);
    else if (c === '*') r += any ? '[\\s\\S]*' : '[^/]*';
    else if (c === '?') r += any ? '[\\s\\S]' : '[^/]';
    else if (c === '[') {
      let j = i + 1; if (pat[j] === '!' || pat[j] === '^') j++; if (pat[j] === ']') j++;
      while (j < pat.length && pat[j] !== ']') { if (pat[j] === '[' && pat[j + 1] === ':') { const k = pat.indexOf(':]', j); if (k < 0) { j = pat.length; break; } j = k + 1; } j++; }
      if (j >= pat.length) { r += '\\['; continue; }
      let cls = pat.slice(i + 1, j), neg = false; if (cls[0] === '!' || cls[0] === '^') { neg = true; cls = cls.slice(1); }
      cls = cls.replace(/\\/g, '\\\\').replace(/\[:(\w+):\]/g, (_, n) => POSIX[n] || '').replace(/^\]/, '\\]');
      r += '[' + (neg ? '^' : '') + cls + ']'; i = j;
    } else r += reEsc(c);
  }
  return r;
}
/* POSIX BRE/ERE -> JS regex source */
function reConv(src, ere) {
  let r = '';
  for (let i = 0; i < src.length; i++) {
    const c = src[i];
    if (c === '[') {
      let j = i + 1; if (src[j] === '^') j++; if (src[j] === ']') j++;
      while (j < src.length && src[j] !== ']') { if (src[j] === '[' && src[j + 1] === ':') { const k = src.indexOf(':]', j); if (k < 0) break; j = k + 1; } j++; }
      if (j >= src.length) { r += '\\['; continue; }
      let cls = src.slice(i + 1, j), neg = false; if (cls[0] === '^') { neg = true; cls = cls.slice(1); }
      cls = cls.replace(/\\(?![wsdbnt\\\]\-])/g, '\\\\').replace(/\[:(\w+):\]/g, (_, n) => POSIX[n] || '').replace(/^\]/, '\\]').replace(/\[/g, '\\[');
      r += '[' + (neg ? '^' : '') + cls + ']'; i = j; continue;
    }
    if (c === '\\') {
      const n = src[++i]; if (n === undefined) { r += '\\\\'; break; }
      if (n === '<' || n === '>') r += '\\b';
      else if (!ere && '(){}|+?'.includes(n)) r += n;
      else r += '\\' + n;
      continue;
    }
    if (!ere && '(){}|+?'.includes(c)) { r += '\\' + c; continue; }
    if (c === '/') { r += '\\/'; continue; }
    r += c;
  }
  return r;
}
function mkRe(src, ere, flags) { try { return new RegExp(reConv(src, ere), flags || ''); } catch (e) { throw new Abort('Invalid regular expression: ' + src); } }

/* ---------- printf ---------- */
function fmtNum(n) { if (Number.isInteger(n)) return String(n); const s = Number(n.toPrecision(6)); return String(s); }
function sprintf(fmt, args, shellMode) {
  let ai = 0, used = false; const next = () => { used = true; return args[ai++]; };
  const toN = v => { if (v === undefined || v === '') return 0; if (typeof v === 'number') return v; const s = String(v).trim(); if (/^-?0x/i.test(s)) return parseInt(s, 16); if (/^['"]./.test(s)) return s.charCodeAt(1); const f = parseFloat(s); return isNaN(f) ? 0 : f; };
  const once = () => fmt.replace(/%(%|([-+ 0#]*)(\*|\d+)?(?:\.(\*|\d+))?([sdiouxXeEfgGcbq]))/g, (m, pc, fl, w, pr, cv) => {
    if (pc === '%') return '%';
    if (w === '*') w = toN(next()); if (pr === '*') pr = toN(next());
    w = w === undefined ? 0 : +w; let s, v = next();
    switch (cv) {
      case 'd': case 'i': { const n = Math.trunc(toN(v)); s = String(Math.abs(n)); if (pr !== undefined) s = s.padStart(+pr, '0'); if (n < 0) s = '-' + s; else if (fl.includes('+')) s = '+' + s; else if (fl.includes(' ')) s = ' ' + s; break; }
      case 'u': s = String(Math.trunc(toN(v)) >>> 0); break;
      case 'o': s = (Math.trunc(toN(v)) >>> 0).toString(8); if (fl.includes('#')) s = '0' + s; break;
      case 'x': case 'X': s = (Math.trunc(toN(v)) >>> 0).toString(16); if (pr !== undefined) s = s.padStart(+pr, '0'); if (cv === 'X') s = s.toUpperCase(); if (fl.includes('#')) s = (cv === 'X' ? '0X' : '0x') + s; break;
      case 'f': { const n = toN(v); s = n.toFixed(pr === undefined ? 6 : +pr); if (fl.includes('+') && n >= 0) s = '+' + s; break; }
      case 'e': case 'E': { s = toN(v).toExponential(pr === undefined ? 6 : +pr).replace(/e([+-])(\d)$/, 'e$10$2'); if (cv === 'E') s = s.toUpperCase(); break; }
      case 'g': case 'G': s = String(Number(toN(v).toPrecision(pr === undefined ? 6 : (+pr || 1)))); break;
      case 'c': s = v === undefined ? '' : (typeof v === 'number' ? String.fromCharCode(v) : String(v).charAt(0)); break;
      case 'b': s = unesc(String(v === undefined ? '' : v)); break;
      case 'q': s = "'" + String(v === undefined ? '' : v).replace(/'/g, "'\\''") + "'"; break;
      default: s = v === undefined ? '' : (typeof v === 'number' ? fmtNum(v) : String(v)); if (pr !== undefined) s = s.slice(0, +pr);
    }
    if (s.length < w) { if (fl.includes('-')) s = s.padEnd(w); else if (fl.includes('0') && 'diuoxXfeEgG'.includes(cv)) { const neg = /^[-+]/.test(s) ? s[0] : ''; s = neg + s.slice(neg.length).padStart(w - neg.length, '0'); } else s = s.padStart(w); }
    return s;
  });
  let out = once();
  if (shellMode) { let guard = 0; while (ai < args.length && used && guard++ < 10000) { out += once(); } }
  return out;
}

/* ---------- filesystem nodes ---------- */
let INO = 2000;
function mkNode(type, mode, uid, gid, extra) {
  const n = { type, mode, uid: uid || 0, gid: gid || 0, mtime: Date.now(), ino: INO++, nlink: type === 'd' ? 2 : 1 };
  if (type === 'd') n.kids = new Map(); if (type === 'f') n.data = '';
  return Object.assign(n, extra || {});
}
const CMDS = {}, BUILTINS = {}, MAN = {};

class Shell {
  constructor() {
    this.root = mkNode('d', 0o755);
    this.cwd = '/'; this.vars = new Map(); this.funcs = {}; this.aliases = {}; this.opts = {}; this.traps = {};
    this.uid = 0; this.gid = 0; this.groups = [0]; this.umask = 0o022;
    this.users = { 0: 'root' }; this.groupNames = { 0: 'root' }; this.homes = { root: '/root' };
    this.status = 0; this.pos = []; this.arg0 = 'bash'; this.hist = []; this.pid = 2317; this.nextPid = 2400;
    this.procs = []; this.jobs = []; this.dirstack = []; this.depth = 0; this.noErr = 0; this.steps = 0; this.world = {};
    this.astCache = new Map(); this.tick = 0;
  }
  clone() {
    const c = new Shell();
    for (const k of ['root', 'vars', 'funcs', 'aliases', 'opts', 'traps', 'groups', 'users', 'groupNames', 'homes', 'pos', 'procs', 'jobs', 'dirstack', 'world', 'hist']) c[k] = structuredClone(this[k]);
    for (const k of ['cwd', 'uid', 'gid', 'umask', 'status', 'arg0', 'pid', 'nextPid', 'lastBg']) c[k] = this[k];
    c.quiet = true;
    return c;
  }
  /* ----- fs ----- */
  abs(p) { if (p === '') p = '.'; if (p[0] !== '/') p = this.cwd + '/' + p; const out = []; for (const s of p.split('/')) { if (!s || s === '.') continue; if (s === '..') out.pop(); else out.push(s); } return '/' + out.join('/'); }
  can(n, bit) {
    if (this.uid === 0) return true;
    const m = n.uid === this.uid ? n.mode >> 6 : this.groups.includes(n.gid) ? n.mode >> 3 : n.mode;
    return !!(m & bit);
  }
  lookup(p, follow = true, depth = 0) {
    const parts = this.abs(p).split('/').filter(Boolean); let n = this.root, cur = '';
    this.err = 'No such file or directory';
    for (let i = 0; i < parts.length; i++) {
      if (n.type !== 'd') { this.err = 'Not a directory'; return null; }
      if (!this.can(n, 1)) { this.err = 'Permission denied'; return null; }
      const c = n.kids.get(parts[i]); if (!c) return null;
      if (c.type === 'l' && (follow || i < parts.length - 1)) {
        if (depth > 20) { this.err = 'Too many levels of symbolic links'; return null; }
        const tgt = (c.target[0] === '/' ? c.target : (cur || '') + '/' + c.target) + (i < parts.length - 1 ? '/' + parts.slice(i + 1).join('/') : '');
        return this.lookup(tgt, follow, depth + 1);
      }
      cur += '/' + parts[i]; n = c;
    }
    return n;
  }
  stat(p, follow = true) { const n = this.lookup(p, follow); if (!n) throw new FsErr(p, this.err); return n; }
  parentOf(p) { const a = this.abs(p), i = a.lastIndexOf('/'); const dir = a.slice(0, i) || '/', name = a.slice(i + 1); const d = this.lookup(dir); if (!d) throw new FsErr(p, this.err); if (d.type !== 'd') throw new FsErr(p, 'Not a directory'); return { d, name, dir }; }
  devRead(n, p) {
    switch (n.dev) {
      case 'null': return ''; case 'zero': return '\0'.repeat(65536);
      case 'urandom': { let s = ''; for (let i = 0; i < 4096; i++) s += String.fromCharCode(Math.floor(Math.random() * 256)); return s; }
      default: return this.world.devRead ? G.SandboxWorld.devRead(this, n, p) : '';
    }
  }
  read(p) {
    const n = this.stat(p);
    if (n.type === 'd') throw new FsErr(p, 'Is a directory');
    if (!this.can(n, 4)) throw new FsErr(p, 'Permission denied');
    if (n.type === 'c') return this.devRead(n, p);
    return n.data;
  }
  write(p, data, append) {
    let n = this.lookup(p);
    if (n) {
      if (n.type === 'd') throw new FsErr(p, 'Is a directory');
      if (!this.can(n, 2)) throw new FsErr(p, 'Permission denied');
      if (n.type === 'c') return n;
      n.data = append ? n.data + data : data; n.mtime = Date.now() + (this.tick++); return n;
    }
    if (this.err !== 'No such file or directory') throw new FsErr(p, this.err);
    const { d, name } = this.parentOf(p);
    if (!this.can(d, 2)) throw new FsErr(p, 'Permission denied');
    n = mkNode('f', 0o666 & ~this.umask, this.uid, (d.mode & 0o2000) ? d.gid : this.gid); n.data = data; n.mtime += this.tick++; d.kids.set(name, n); return n;
  }
  mkdir(p, parents, mode) {
    const a = this.abs(p); if (this.lookup(a)) { if (parents) return; throw new FsErr(p, 'File exists'); }
    if (parents) { const up = a.slice(0, a.lastIndexOf('/')) || '/'; if (!this.lookup(up)) this.mkdir(up, true); }
    const { d, name } = this.parentOf(a);
    if (!this.can(d, 2)) throw new FsErr(p, 'Permission denied');
    const n = mkNode('d', (mode === undefined ? 0o777 & ~this.umask : mode) | (d.mode & 0o2000), this.uid, (d.mode & 0o2000) ? d.gid : this.gid);
    d.kids.set(name, n); d.nlink++; return n;
  }
  unlink(p) {
    const { d, name } = this.parentOf(p); const n = d.kids.get(name); if (!n) throw new FsErr(p, 'No such file or directory');
    if (!this.can(d, 2) || ((d.mode & 0o1000) && this.uid !== 0 && n.uid !== this.uid && d.uid !== this.uid)) throw new FsErr(p, d.mode & 0o1000 && this.can(d, 2) ? 'Operation not permitted' : 'Permission denied');
    d.kids.delete(name); n.nlink--; if (n.type === 'd') d.nlink--;
  }
  /* ----- variables ----- */
  getv(name) {
    switch (name) {
      case '?': return '' + this.status; case '$': return '' + this.pid; case '!': return this.lastBg ? '' + this.lastBg : ''; case '#': return '' + this.pos.length;
      case '0': return this.arg0; case '@': case '*': return this.pos.join(' '); case '-': return 'himBHs'; case 'PWD': return this.cwd;
      case 'RANDOM': return '' + Math.floor(Math.random() * 32768); case 'UID': case 'EUID': return '' + this.uid; case 'PPID': return '2301';
    }
    if (/^\d+$/.test(name)) return this.pos[+name - 1];
    const v = this.vars.get(name); if (!v) return undefined;
    return Array.isArray(v.v) ? v.v[0] : (v.v && typeof v.v === 'object' ? v.v['0'] : v.v);
  }
  setv(name, val, exp) {
    let v = this.vars.get(name);
    if (v && v.ro) throw new Abort('bash: ' + name + ': readonly variable');
    if (!v) { v = { v: val, x: !!this.opts.a }; this.vars.set(name, v); } else v.v = val;
    if (exp) v.x = true;
    if (v.int && typeof val === 'string') v.v = '' + this.arith(val);
  }
  arrVals(name) { if (name === '@') return this.pos.slice(); const v = this.vars.get(name); if (!v) return []; if (Array.isArray(v.v)) return v.v.filter(x => x !== undefined); if (typeof v.v === 'object') return Object.values(v.v); return [v.v]; }
  arrKeys(name) { const v = this.vars.get(name); if (!v) return []; if (Array.isArray(v.v)) return v.v.map((x, i) => x === undefined ? null : '' + i).filter(x => x !== null); if (typeof v.v === 'object') return Object.keys(v.v); return ['0']; }
  arrGet(name, k) {
    const v = this.vars.get(name); if (!v) return undefined;
    if (Array.isArray(v.v)) { let i = this.arith(k); if (i < 0) i += v.v.length; return v.v[i]; }
    if (typeof v.v === 'object') return v.v[this.expStr(k)];
    return this.arith(k) === 0 ? v.v : undefined;
  }
  arrSet(name, k, val) {
    let v = this.vars.get(name); if (!v) { v = { v: [], x: false }; this.vars.set(name, v); }
    if (typeof v.v === 'string') v.v = [v.v];
    if (Array.isArray(v.v)) v.v[this.arith(k)] = val; else v.v[this.expStr(k)] = val;
  }
  env() { const e = {}; for (const [k, v] of this.vars) if (v.x && typeof v.v === 'string') e[k] = v.v; e.PWD = this.cwd; return e; }
  /* ----- expansion ----- */
  expDq(src) { return parseParts(src, true).map(p => { if (p.k === 'lit') return p.s; const r = this.expPart(p); return r && r.list ? r.list.join(' ') : r; }).join(''); }
  expStr(raw) { return this.segs(raw, { nosplit: true }).map(f => f.map(s => s.s).join('')).join(' '); }
  expPat(raw) { return this.segs(raw, { nosplit: true }).map(f => f.map(s => s.q ? s.s.replace(/[\\*?[\]]/g, '\\$&') : s.s).join('')).join(' '); }
  matchPat(str, pat) { return new RegExp('^(?:' + globRe(pat, true) + ')$').test(str); }
  unbound(name) { throw new Abort('bash: ' + name + ': unbound variable'); }
  expPart(p) {
    if (p.k === 'param') {
      if (p.simple) {
        if (p.raw === '@' || p.raw === '*') return { list: this.pos.slice(), star: p.raw === '*' };
        const v = this.getv(p.raw); if (v === undefined && this.opts.u && !/^[?$!#0-]$/.test(p.raw)) this.unbound(p.raw);
        return v === undefined ? '' : v;
      }
      return this.expParam(p.raw);
    }
    if (p.k === 'cmd') return this.capture(p.src).replace(/\n+$/, '');
    if (p.k === 'arith') return '' + this.arith(p.src);
    if (p.k === 'psub') {
      if (p.dir === '>') return '/dev/null';
      const data = this.capture(p.src); const fdDir = this.lookup('/dev/fd') || (() => { const d = mkNode('d', 0o755); this.lookup('/dev').kids.set('fd', d); return d; })();
      const name = '' + (63 - (this.psubN = ((this.psubN || 0) + 1) % 40)); const n = mkNode('f', 0o666, this.uid, this.gid); n.data = data; fdDir.kids.set(name, n);
      return '/dev/fd/' + name;
    }
    return '';
  }
  expParam(body) {
    let m;
    if ((m = /^#([A-Za-z_]\w*|@)\[?[@*]?\]?$/.exec(body)) && /[@*]/.test(body.slice(1))) return '' + this.arrVals(m[1]).length;
    if (body === '#') return '' + this.pos.length;
    if ((m = /^#([A-Za-z_]\w*|\d+)(?:\[([^\]]*)\])?$/.exec(body))) { const v = m[2] !== undefined ? this.arrGet(m[1], m[2]) : this.getv(m[1]); return '' + (v === undefined ? 0 : String(v).length); }
    if ((m = /^!([A-Za-z_]\w*)\[[@*]\]$/.exec(body))) return { list: this.arrKeys(m[1]) };
    if ((m = /^!([A-Za-z_]\w*)$/.exec(body))) { const v = this.getv(this.getv(m[1]) || ''); return v === undefined ? '' : v; }
    m = /^([A-Za-z_]\w*|[0-9]+|[@*#?$!-])(\[[^\]]*\])?([\s\S]*)$/.exec(body);
    if (!m) throw new Abort('bash: ${' + body + '}: bad substitution');
    const name = m[1], sub = m[2], op = m[3]; let val, isList = false, star = false;
    if (name === '@' || name === '*') { val = this.pos.slice(); isList = true; star = name === '*'; }
    else if (sub) { const k = sub.slice(1, -1); if (k === '@' || k === '*') { val = this.arrVals(name); isList = true; star = k === '*'; } else val = this.arrGet(name, k); }
    else val = this.getv(name);
    const ret = v => isList ? { list: v, star } : v;
    const map = f => isList ? { list: val.map(f), star } : f(val === undefined ? '' : val);
    if (!op) { if (val === undefined && this.opts.u && !isList) this.unbound(name); return ret(val === undefined ? '' : val); }
    let o;
    if ((o = /^(:?)([-=+?])([\s\S]*)$/.exec(op))) {
      const unset = isList ? val.length === 0 : (val === undefined || (o[1] && val === ''));
      switch (o[2]) {
        case '-': return unset ? this.expStr(o[3]) : ret(val);
        case '=': if (unset) { const w = this.expStr(o[3]); this.setv(name, w); return w; } return ret(val);
        case '+': return unset ? '' : this.expStr(o[3]);
        case '?': if (unset) throw new Abort('bash: ' + name + ': ' + (this.expStr(o[3]) || 'parameter null or not set')); return ret(val);
      }
    }
    if (val === undefined) { if (this.opts.u && !isList) this.unbound(name); val = ''; }
    if ((o = /^(##?|%%?)([\s\S]*)$/.exec(op))) {
      const re = new RegExp('^(?:' + globRe(this.expPat(o[2]), true) + ')$');
      return map(v => {
        const n = v.length;
        if (o[1] === '#') { for (let i = 0; i <= n; i++) if (re.test(v.slice(0, i))) return v.slice(i); }
        else if (o[1] === '##') { for (let i = n; i >= 0; i--) if (re.test(v.slice(0, i))) return v.slice(i); }
        else if (o[1] === '%') { for (let i = n; i >= 0; i--) if (re.test(v.slice(i))) return v.slice(0, i); }
        else { for (let i = 0; i <= n; i++) if (re.test(v.slice(i))) return v.slice(0, i); }
        return v;
      });
    }
    if (op[0] === '/') {
      let all = false, anchor = '', rest = op.slice(1);
      if (rest[0] === '/') { all = true; rest = rest.slice(1); } else if (rest[0] === '#' || rest[0] === '%') { anchor = rest[0]; rest = rest.slice(1); }
      let i = 0; while (i < rest.length && rest[i] !== '/') { if (rest[i] === '\\') i++; i++; }
      const pat = this.expPat(rest.slice(0, i)), rep = this.expStr(rest.slice(i + 1));
      const re = new RegExp((anchor === '#' ? '^' : '') + '(?:' + globRe(pat, true) + ')' + (anchor === '%' ? '$' : ''), all ? 'g' : '');
      return map(v => v.replace(re, () => rep));
    }
    if (op === '^^') return map(v => v.toUpperCase()); if (op === ',,') return map(v => v.toLowerCase());
    if (op === '^') return map(v => v.charAt(0).toUpperCase() + v.slice(1)); if (op === ',') return map(v => v.charAt(0).toLowerCase() + v.slice(1));
    if (op[0] === ':') {
      const [a, b] = op.slice(1).split(':'); let off = this.arith(a);
      if (isList) { if (off < 0) off += val.length; const len = b === undefined ? val.length : this.arith(b); return { list: val.slice(off, off + len), star }; }
      if (off < 0) off = Math.max(0, val.length + off);
      if (b === undefined) return val.slice(off);
      const len = this.arith(b); return len < 0 ? val.slice(off, val.length + len) : val.slice(off, off + len);
    }
    throw new Abort('bash: ${' + body + '}: bad substitution');
  }
  segs(raw, o) {
    const parts = parseParts(raw), fields = []; let cur = null;
    if (parts[0] && parts[0].k === 'lit' && !parts[0].q && parts[0].s[0] === '~') {
      const m = /^~([\w-]*)(?=\/|$)/.exec(parts[0].s);
      if (m && (!m[1] || this.homes[m[1]])) { const rest = parts[0].s.slice(m[0].length); parts.splice(0, 1, { k: 'lit', s: m[1] ? this.homes[m[1]] : (this.getv('HOME') || '/'), q: true }); if (rest) parts.splice(1, 0, { k: 'lit', s: rest, q: false }); }
    }
    const add = (s, q, keep) => { if (!cur) { cur = []; fields.push(cur); } cur.push({ s, q, keep }); };
    const brk = () => { cur = null; };
    for (const p of parts) {
      if (p.k === 'lit') { add(p.s, p.q); continue; }
      let r = this.expPart(p);
      if (r && r.list) {
        if (p.q && !o.nosplit) { if (r.star) add(r.list.join(' '), true); else r.list.forEach((x, i) => { if (i) brk(); add(x, true); }); continue; }
        if (p.q) { add(r.list.join(' '), true); continue; }
        r = r.list.join(' ');
      }
      if (p.q) { add(r, true); continue; }
      if (o.nosplit) { add(r, false); continue; }
      let ifs = this.getv('IFS'); if (ifs === undefined) ifs = ' \t\n';
      if (ifs === '') { if (r !== '') add(r, false); continue; }
      const ws = [...ifs].filter(c => ' \t\n'.includes(c)).map(reEsc).join(''), nws = [...ifs].filter(c => !' \t\n'.includes(c)).map(reEsc).join('');
      const lead = ws && new RegExp('^[' + ws + ']').test(r), trail = ws && new RegExp('[' + ws + ']$').test(r);
      const t = ws ? r.replace(new RegExp('^[' + ws + ']+|[' + ws + ']+$', 'g'), '') : r;
      const sep = new RegExp(ws && nws ? '[' + ws + ']*[' + nws + '][' + ws + ']*|[' + ws + ']+' : nws ? '[' + nws + ']' : '[' + ws + ']+');
      const pieces = t === '' ? [] : t.split(sep); if (pieces.length > 1 && pieces[pieces.length - 1] === '') pieces.pop();
      if (lead) brk();
      pieces.forEach((x, i) => { if (i) brk(); add(x, false, x === '' && !!nws); });
      if (trail) brk();
    }
    return fields;
  }
  expand1(raw, o = {}) {
    const out = [];
    for (const f of this.segs(raw, o)) {
      const str = f.map(s => s.s).join('');
      if (str === '' && !f.some(s => s.q || s.keep)) continue;
      if (o.glob !== false && !this.opts.f && f.some(s => !s.q && /[*?[]/.test(s.s))) {
        const m = this.glob(f.map(s => s.q ? s.s.replace(/[\\*?[\]]/g, '\\$&') : s.s).join(''));
        if (m.length) { out.push(...m); continue; }
      }
      out.push(str);
    }
    return out;
  }
  expand(raw, o) { const out = []; for (const w of braceExpand(raw)) out.push(...this.expand1(w, o)); return out; }
  glob(pat) {
    const abs = pat[0] === '/', dirOnly = /\/$/.test(pat); const segs = pat.split('/').filter(s => s !== ''); let cur = [abs ? '/' : ''];
    const join = (b, n) => b === '' ? n : b === '/' ? '/' + n : b + '/' + n;
    for (const seg of segs) {
      const next = [], magic = /[*?[]/.test(seg.replace(/\\./g, ''));
      for (const base of cur) {
        if (!magic) { const p = join(base, seg.replace(/\\(.)/g, '$1')); if (this.lookup(p, false)) next.push(p); continue; }
        const d = this.lookup(base === '' ? '.' : base); if (!d || d.type !== 'd' || !this.can(d, 4)) continue;
        const re = new RegExp('^' + globRe(seg) + '$');
        for (const name of [...d.kids.keys()].sort()) { if (name[0] === '.' && seg[0] !== '.') continue; if (re.test(name)) next.push(join(base, name)); }
      }
      cur = next; if (!cur.length) break;
    }
    if (dirOnly) cur = cur.filter(p => { const n = this.lookup(p); return n && n.type === 'd'; }).map(p => p + '/');
    return cur;
  }
  /* ----- arithmetic ----- */
  arith(src) {
    const s = this.expDq(String(src)); const tk = []; const re = /\s*(?:(\d+#\w+|0[xX][0-9a-fA-F]+|\d+)|([A-Za-z_]\w*)|(\*\*|<<=|>>=|[-+*\/%&|^]=|<<|>>|<=|>=|==|!=|&&|\|\||\+\+|--|[-+*\/%<>=!~&|^?:(),\[\]]))/y;
    let pos = 0; while (pos < s.length) { re.lastIndex = pos; const m = re.exec(s); if (!m) { if (/^\s*$/.test(s.slice(pos))) break; throw new Abort('bash: ' + s + ': syntax error in expression'); } pos = re.lastIndex; tk.push(m[1] !== undefined ? { n: m[1] } : m[2] !== undefined ? { id: m[2] } : { op: m[3] }); }
    let i = 0; const sh = this; const pk = () => tk[i] && tk[i].op;
    const num = v => { if (v === undefined || v === '') return 0; if (/^-?\d+$/.test(v)) return parseInt(v, 10); if (/^0x/i.test(v)) return parseInt(v, 16); try { return sh.arith(v); } catch (e) { return 0; } };
    const rd = lv => num(lv.k !== undefined ? sh.arrGet(lv.id, lv.k) : sh.getv(lv.id));
    const wr = (lv, v) => { v = Math.trunc(v); if (lv.k !== undefined) sh.arrSet(lv.id, lv.k, '' + v); else sh.setv(lv.id, '' + v); return v; };
    const BIN = [['||'], ['&&'], ['|'], ['^'], ['&'], ['==', '!='], ['<', '<=', '>', '>='], ['<<', '>>'], ['+', '-'], ['*', '/', '%']];
    const ap = (op, a, b) => { switch (op) { case '||': return (a || b) ? 1 : 0; case '&&': return (a && b) ? 1 : 0; case '|': return a | b; case '^': return a ^ b; case '&': return a & b; case '==': return +(a === b); case '!=': return +(a !== b); case '<': return +(a < b); case '<=': return +(a <= b); case '>': return +(a > b); case '>=': return +(a >= b); case '<<': return a << b; case '>>': return a >> b; case '+': return a + b; case '-': return a - b; case '*': return a * b; case '/': if (!b) throw new Abort('bash: division by 0 (error token is "' + b + '")'); return Math.trunc(a / b); case '%': if (!b) throw new Abort('bash: division by 0'); return a % b; case '**': return Math.pow(a, b); } };
    function prim() {
      const t = tk[i++]; if (!t) throw new Abort('bash: ' + s + ': syntax error: operand expected');
      if (t.n !== undefined) { if (t.n.includes('#')) { const [b, d] = t.n.split('#'); return { v: parseInt(d, +b) }; } if (/^0[xX]/.test(t.n)) return { v: parseInt(t.n, 16) }; if (/^0\d/.test(t.n)) return { v: parseInt(t.n, 8) }; return { v: parseInt(t.n, 10) }; }
      if (t.id !== undefined) { const lv = { id: t.id }; if (pk() === '[') { i++; let d = 1, st = i; while (i < tk.length && d) { if (tk[i].op === '[') d++; if (tk[i].op === ']') d--; i++; } lv.k = tk.slice(st, i - 1).map(x => x.n !== undefined ? x.n : x.id !== undefined ? x.id : x.op).join(''); } return { lv }; }
      if (t.op === '(') { const v = comma(); if (pk() !== ')') throw new Abort('bash: ' + s + ': missing )'); i++; return { v }; }
      throw new Abort('bash: ' + s + ': syntax error: operand expected (error token is "' + t.op + '")');
    }
    function unary() {
      const o = pk();
      if (o === '!' || o === '~' || o === '-' || o === '+') { i++; const v = unary(); return o === '!' ? +!v : o === '~' ? ~v : o === '-' ? -v : v; }
      if (o === '++' || o === '--') { i++; const p = prim(); return wr(p.lv, rd(p.lv) + (o === '++' ? 1 : -1)); }
      const p = prim(); let v = p.lv ? rd(p.lv) : p.v;
      if (p.lv && (pk() === '++' || pk() === '--')) { wr(p.lv, v + (tk[i++].op === '++' ? 1 : -1)); }
      if (pk() === '**') { i++; v = Math.pow(v, unary()); }
      return v;
    }
    function bin(l) { if (l >= BIN.length) return unary(); let a = bin(l + 1); while (pk() && BIN[l].includes(pk())) { const op = tk[i++].op; a = ap(op, a, bin(l + 1)); } return a; }
    function tern() { const c = bin(0); if (pk() === '?') { i++; const a = assign(); if (pk() !== ':') throw new Abort('bash: ' + s + ': `:\' expected'); i++; const b = assign(); return c ? a : b; } return c; }
    function assign() {
      if (tk[i] && tk[i].id !== undefined) {
        const save = i; const p = prim(); const o = pk();
        if (o === '=' || (o && /^(\*\*|<<|>>|[-+*\/%&|^])=$/.test(o))) { i++; const r = assign(); return wr(p.lv, o === '=' ? r : ap(o.slice(0, -1), rd(p.lv), r)); }
        i = save;
      }
      return tern();
    }
    function comma() { let v = assign(); while (pk() === ',') { i++; v = assign(); } return v; }
    if (!tk.length) return 0;
    const v = comma(); if (i < tk.length) throw new Abort('bash: ' + s + ': syntax error in expression');
    return v;
  }
  /* ----- execution ----- */
  parseCached(src) { let a = this.astCache.get(src); if (!a) { a = parse(src); if (this.astCache.size > 400) this.astCache.clear(); this.astCache.set(src, a); } return a; }
  execSrc(src, ctx) { return this.execList(this.parseCached(src), ctx); }
  capture(src) {
    const buf = [], c = this.cur || { in: { s: '', p: 0 }, fd: { 2: { w() {} } } };
    const ctx = { in: c.in, fd: { 1: { w: s => buf.push(s) }, 2: c.fd[2] } };
    const st = this.subshell(() => this.execSrc(src, ctx)); this.subStatus = st; this.cur = c;
    return buf.join('');
  }
  subshell(fn) {
    const sv = { vars: this.vars, cwd: this.cwd, funcs: this.funcs, aliases: this.aliases, opts: this.opts, pos: this.pos, umask: this.umask, traps: this.traps, arg0: this.arg0 };
    this.vars = new Map(); for (const [k, v] of sv.vars) this.vars.set(k, { ...v, v: Array.isArray(v.v) ? v.v.slice() : (v.v && typeof v.v === 'object' ? { ...v.v } : v.v) });
    this.funcs = { ...sv.funcs }; this.aliases = { ...sv.aliases }; this.opts = { ...sv.opts }; this.traps = {};
    try { return fn(); } catch (e) { if (e instanceof ExitEx) return e.code; throw e; } finally { Object.assign(this, sv); }
  }
  step() { if (++this.steps > 60000) throw new Abort('^C  (sandbox stopped a runaway loop)'); }
  execList(list, ctx) {
    let st = 0;
    for (const it of list.items) {
      this.step();
      if (it.bg) { st = this.background(it.node, ctx); this.status = st; continue; }
      st = this.execNode(it.node, ctx); this.status = st;
    }
    return st;
  }
  errexit(st) { if (st && this.opts.e && !this.noErr) throw new ExitEx(st); return st; }
  execNode(n, ctx) {
    switch (n.k) {
      case 'andor': {
        this.noErr++; let st, lastRan = n.rest.length === 0;
        try { st = this.execNode(n.first, ctx); } finally { this.noErr--; }
        this.status = st;
        n.rest.forEach((r, i) => {
          if ((r.op === '&&') === (st === 0)) {
            const final = i === n.rest.length - 1; if (!final) this.noErr++;
            try { st = this.execNode(r.node, ctx); } finally { if (!final) this.noErr--; }
            this.status = st; lastRan = final;
          } else lastRan = false;
        });
        return lastRan ? this.errexit(st) : st;
      }
      case 'pipe': {
        let st; const sts = [];
        if (n.neg) this.noErr++;
        try {
          if (n.cmds.length === 1) { st = this.execCmd(n.cmds[0], ctx); sts.push(st); }
          else {
            let input = ctx.in;
            n.cmds.forEach((c, i) => {
              const last = i === n.cmds.length - 1, buf = [], sink = last ? ctx.fd[1] : { w: s => buf.push(s) };
              const c2 = { in: input, fd: { ...ctx.fd, 1: sink } }; if (c.errToo) c2.fd[2] = sink;
              st = this.subshell(() => this.execCmd(c, c2)); sts.push(st); input = { s: buf.join(''), p: 0 };
            });
            if (this.opts.pipefail) st = sts.reduce((a, b) => b || a, 0) && [...sts].reverse().find(x => x);
          }
        } finally { if (n.neg) this.noErr--; }
        this.vars.set('PIPESTATUS', { v: sts.map(String), x: false });
        if (n.time) ctx.fd[2].w('\nreal\t0m0.00' + (1 + n.cmds.length) + 's\nuser\t0m0.001s\nsys\t0m0.001s\n');
        if (n.neg) return st ? 0 : 1;
        return this.errexit(st || 0);
      }
      default: { const st = this.execCmd(n, ctx); if (n.k === 'simple' || n.k === 'arith' || n.k === 'sub') return this.errexit(st); return st; }
    }
  }
  srcOf(n) { if (n.k === 'simple') return [...n.assigns, ...n.words].join(' '); if (n.k === 'pipe') return n.cmds.map(c => this.srcOf(c)).join(' | '); if (n.k === 'andor') return this.srcOf(n.first) + n.rest.map(r => ' ' + r.op + ' ' + this.srcOf(r.node)).join(''); return '...'; }
  background(n, ctx) {
    const text = this.srcOf(n), pid = this.nextPid++, id = (this.jobs.reduce((a, j) => Math.max(a, j.id), 0)) + 1;
    const first = n.k === 'simple' ? n.words[0] : '';
    const long = /^(sleep|yes|ping|watch|top|cat|tail|nc|python3?|minicom|picocom)$/.test(first) && !(first === 'cat' && n.words.length > 1) && !(first === 'tail' && !n.words.includes('-f'));
    this.lastBg = pid; if (!this.quiet || true) ctx.fd[2].w('[' + id + '] ' + pid + '\n');
    if (long) { this.jobs.push({ id, pid, cmd: text, state: 'Running' }); this.procs.push({ pid, ppid: this.pid, user: this.users[this.uid], cmd: text, cpu: first === 'yes' ? 98.7 : 0, mem: 0.1, stat: first === 'yes' ? 'R' : 'S', tty: 'pts/0' }); return 0; }
    try { this.subshell(() => this.execNode(n, ctx)); } catch (e) { if (!(e instanceof BrkEx || e instanceof CntEx || e instanceof RetEx)) throw e; }
    ctx.fd[2].w('[' + id + ']+  Done                    ' + text + '\n');
    return 0;
  }
  openSink(p, append, ctx) {
    const a = this.abs(p);
    if (a === '/dev/stdout') return ctx.fd[1]; if (a === '/dev/stderr') return ctx.fd[2];
    const n = this.write(p, '', append);
    if (n.type === 'c') { if (n.dev === 'tty') return this.term || ctx.fd[1]; return { w() {} }; }
    return { w: s => { n.data += s; }, node: n };
  }
  applyRedirs(redirs, ctx) {
    if (!redirs || !redirs.length) return ctx;
    const c = { in: ctx.in, fd: { ...ctx.fd } };
    for (const r of redirs) {
      switch (r.op) {
        case '>': case '>>': c.fd[r.fd === null ? 1 : r.fd] = this.openSink(this.expStr(r.target), r.op === '>>', c); break;
        case '&>': case '&>>': c.fd[1] = c.fd[2] = this.openSink(this.expStr(r.target), r.op === '&>>', c); break;
        case '>&': { const t = this.expStr(r.target); if (/^\d+$/.test(t)) { if (!c.fd[+t]) throw new FsErr(t, 'Bad file descriptor'); c.fd[r.fd === null ? 1 : r.fd] = c.fd[+t]; } else if (t === '-') c.fd[r.fd === null ? 1 : r.fd] = { w() {} }; else c.fd[1] = c.fd[2] = this.openSink(t, false, c); break; }
        case '<': c.in = { s: this.read(this.expStr(r.target)), p: 0 }; break;
        case '<<': case '<<-': c.in = { s: r.quoted ? r.body : this.expDq(r.body), p: 0 }; break;
        case '<<<': c.in = { s: this.expStr(r.target) + '\n', p: 0 }; break;
      }
    }
    return c;
  }
  loop(fn) { try { fn(); } catch (e) { if (e instanceof BrkEx) { if (e.n > 1) throw new BrkEx(e.n - 1); return 'brk'; } if (e instanceof CntEx) { if (e.n > 1) throw new CntEx(e.n - 1); return 'cnt'; } throw e; } }
  cond(list, ctx) { this.noErr++; try { return this.execList(list, ctx); } finally { this.noErr--; } }
  execCmd(n, ctx0) {
    if (n.k === 'simple') return this.execSimple(n, ctx0);
    if (n.k === 'func') { this.funcs[n.name] = n.body; return 0; }
    let ctx; this.cur = ctx0;
    try { ctx = this.applyRedirs(n.redirs, ctx0); } catch (e) { if (e instanceof FsErr) { ctx0.fd[2].w('bash: ' + e.path + ': ' + e.msg + '\n'); return 1; } throw e; }
    switch (n.k) {
      case 'group': return this.execList(n.body, ctx);
      case 'sub': return this.subshell(() => this.execList(n.body, ctx));
      case 'arith': return this.arith(n.src) ? 0 : 1;
      case 'if': for (const c of n.clauses) { if (this.cond(c.cond, ctx) === 0) return this.execList(c.body, ctx); } return n.els ? this.execList(n.els, ctx) : 0;
      case 'while': { let st = 0; for (;;) { this.step(); const c = this.cond(n.cond, ctx); if ((c === 0) === n.until) break; const r = this.loop(() => { st = this.execList(n.body, ctx); }); if (r === 'brk') break; } return st; }
      case 'for': { let st = 0; const items = n.words ? n.words.flatMap(w => this.expand(w)) : this.pos.slice(); for (const it of items) { this.step(); this.setv(n.v, it); const r = this.loop(() => { st = this.execList(n.body, ctx); }); if (r === 'brk') break; } return st; }
      case 'cfor': { let st = 0; if (n.parts[0] && n.parts[0].trim()) this.arith(n.parts[0]); for (;;) { this.step(); if (n.parts[1] && n.parts[1].trim() && !this.arith(n.parts[1])) break; const r = this.loop(() => { st = this.execList(n.body, ctx); }); if (r === 'brk') break; if (n.parts[2] && n.parts[2].trim()) this.arith(n.parts[2]); } return st; }
      case 'case': { const w = this.expStr(n.word); for (const it of n.items) { if (it.pats.some(p => this.matchPat(w, this.expPat(p)))) return this.execList(it.body, ctx); } return 0; }
    }
    return 0;
  }
  assign(raw) {
    const m = /^([A-Za-z_]\w*)(?:\[([^\]]*)\])?(\+?)=([\s\S]*)$/.exec(raw); const name = m[1], k = m[2], app = m[3], val = m[4];
    if (val[0] === '(' && k === undefined) {
      const inner = val.slice(1, val.lastIndexOf(')')); const toks = lex(inner).filter(t => t.t === 'word'); const cur = this.vars.get(name);
      if (cur && cur.assoc) { const o = app ? cur.v : {}; for (const t of toks) { const mm = /^\[([^\]]*)\]=([\s\S]*)$/.exec(t.raw); if (mm) o[this.expStr(mm[1])] = this.expStr(mm[2]); } cur.v = o; return; }
      const vals = toks.flatMap(t => this.expand(t.raw));
      if (app && cur) { cur.v = (Array.isArray(cur.v) ? cur.v : [cur.v]).concat(vals); } else this.setv(name, vals);
      return;
    }
    let v = this.expStr(/['"\\]/.test(val) ? val : val.replace(/(^|:)~(?=\/|:|$)/g, (m, a) => a + (this.getv('HOME') || '~')));
    if (k !== undefined) { if (app) v = (this.arrGet(name, k) || '') + v; this.arrSet(name, k, v); return; }
    if (app) { const cur = this.vars.get(name); if (cur && Array.isArray(cur.v)) { cur.v.push(v); return; } if (cur && cur.int) v = '' + (this.arith(cur.v || '0') + this.arith(v)); else v = (this.getv(name) || '') + v; }
    this.setv(name, v);
  }
  mkio(ctx, name) {
    const sh = this;
    return {
      ctx, out: s => ctx.fd[1].w(s), err: s => ctx.fd[2].w(s), tty: !!ctx.fd[1].tty, inTty: !!ctx.in.tty,
      stdin() { const r = ctx.in.s.slice(ctx.in.p); ctx.in.p = ctx.in.s.length; return r; },
      readLine() { const i = ctx.in; if (i.p >= i.s.length) return null; let j = i.s.indexOf('\n', i.p); let ln; if (j < 0) { ln = i.s.slice(i.p); i.p = i.s.length; } else { ln = i.s.slice(i.p, j); i.p = j + 1; } return ln; },
      fail(msg, code) { ctx.fd[2].w(name + ': ' + msg + '\n'); return code === undefined ? 1 : code; }
    };
  }
  execSimple(n, ctx0) {
    this.cur = ctx0; this.subStatus = undefined; let words = [], raws = n.words;
    if (raws.length && Object.prototype.hasOwnProperty.call(this.aliases, raws[0]) && !n.noAlias) {
      const a = lex(this.aliases[raws[0]]).filter(t => t.t === 'word').map(t => t.raw); raws = a.concat(raws.slice(1));
    }
    let ctx;
    try {
      if (raws[0] === '[[') words = ['[[']; else for (const r of raws) words.push(...this.expand(r));
      ctx = this.applyRedirs(n.redirs, ctx0);
    } catch (e) { if (e instanceof FsErr) { ctx0.fd[2].w('bash: ' + e.path + ': ' + e.msg + '\n'); return 1; } throw e; }
    if (!words.length) { for (const a of n.assigns) this.assign(a); return this.subStatus === undefined ? 0 : this.subStatus; }
    const saved = [];
    for (const a of n.assigns) { const nm = /^[A-Za-z_]\w*/.exec(a)[0]; const old = this.vars.get(nm); saved.push([nm, old ? { ...old } : undefined]); this.assign(a); this.vars.get(nm).x = true; }
    try {
      if (this.opts.x) ctx.fd[2].w('+ ' + words.join(' ') + '\n');
      if (raws[0] === '[[') return this.evalCond(raws.slice(1), true);
      return this.invoke(words, ctx);
    } finally { for (const [nm, old] of saved) { if (old) this.vars.set(nm, old); else this.vars.delete(nm); } }
  }
  inPath(name) { for (const d of (this.getv('PATH') || '').split(':')) { if (!d) continue; const p = d + '/' + name, n = this.lookup(p); if (n && n.type === 'f' && (n.mode & 0o111)) return p; } return null; }
  invoke(words, ctx, noFunc) {
    const name = words[0];
    if (!noFunc && this.funcs[name]) return this.callFunc(name, words.slice(1), ctx);
    if (BUILTINS[name]) return this.runCmd(BUILTINS[name], name, words, ctx);
    if (name.includes('/')) return this.execFile(name, words, ctx);
    const p = this.inPath(name);
    if (!p) { ctx.fd[2].w('bash: ' + name + ': command not found\n'); return 127; }
    return this.execFile(p, words, ctx);
  }
  runCmd(fn, name, words, ctx) {
    try { const st = fn(words.slice(1), this.mkio(ctx, name), this, name); return st === undefined ? 0 : st; }
    catch (e) {
      if (e instanceof FsErr) { ctx.fd[2].w(name + ': ' + (e.path === '' ? '' : e.path + ': ') + e.msg + '\n'); return 1; }
      if (e instanceof Error && !(e instanceof Incomplete) && !(e instanceof SynErr) && !(e instanceof RangeError)) { ctx.fd[2].w(name + ': ' + e.message + '\n'); return 2; }
      throw e;
    }
  }
  callFunc(name, args, ctx) {
    const sv = this.pos, locals = this.locals; this.pos = args; this.locals = []; this.fdepth = (this.fdepth || 0) + 1;
    try { return this.execCmd(this.funcs[name], ctx); }
    catch (e) { if (e instanceof RetEx) return e.code; throw e; }
    finally { for (const [k, old] of this.locals.reverse()) { if (old) this.vars.set(k, old); else this.vars.delete(k); } this.pos = sv; this.locals = locals; this.fdepth--; }
  }
  execFile(path, words, ctx) {
    const n = this.lookup(path);
    if (!n) { ctx.fd[2].w('bash: ' + path + ': ' + this.err + '\n'); return 127; }
    if (n.type === 'd') { ctx.fd[2].w('bash: ' + path + ': Is a directory\n'); return 126; }
    if (!(n.mode & 0o111) || !this.can(n, 1)) { ctx.fd[2].w('bash: ' + path + ': Permission denied\n'); return 126; }
    if (n.bin) {
      if (!CMDS[n.bin]) { ctx.fd[2].w('bash: ' + path + ': cannot execute binary file\n'); return 126; }
      const setuid = (n.mode & 0o4000) && n.uid === 0;
      return this.runCmd(CMDS[n.bin], words[0].replace(/^.*\//, ''), words, ctx);
    }
    const m = /^#!\s*(\S+)(?:\s+(\S+))?/.exec(n.data);
    if (m && !/(sh|bash|dash|env)$/.test(m[1])) { ctx.fd[2].w('bash: ' + path + ': ' + m[1] + ': bad interpreter: No such file or directory\n'); return 126; }
    if (m && /env$/.test(m[1]) && m[2] && !/^(ba|da)?sh$/.test(m[2])) { ctx.fd[2].w('/usr/bin/env: \u2018' + m[2] + '\u2019: No such file or directory\n'); return 127; }
    return this.runScript(n.data, words.slice(1), path, ctx);
  }
  runScript(src, args, name, ctx) {
    if (this.depth > 40) { ctx.fd[2].w('bash: fork: retry: Resource temporarily unavailable\n'); return 254; }
    this.depth++;
    try {
      return this.subshell(() => {
        const ex = new Map(); for (const [k, v] of this.vars) if (v.x) ex.set(k, v); this.vars = ex; this.funcs = {}; this.aliases = {}; this.opts = {}; this.pos = args; this.arg0 = name; this.vars.set('OPTIND', { v: '1', x: false }); this.optpos = 1;
        let st = 0;
        try { st = this.execList(parse(src), ctx); }
        catch (e) {
          if (e instanceof ExitEx) st = e.code;
          else if (e instanceof Abort) { ctx.fd[2].w(name + ': ' + e.msg.replace(/^bash: /, '') + '\n'); st = 1; }
          else if (e instanceof SynErr || e instanceof Incomplete) { ctx.fd[2].w(name + ': ' + (e instanceof Incomplete ? 'syntax error: unexpected end of file' : e.message) + '\n'); st = 2; }
          else if (e instanceof RetEx) st = e.code; else if (e instanceof BrkEx || e instanceof CntEx) st = 0; else throw e;
        }
        if (this.traps.EXIT) { const t = this.traps.EXIT; this.traps = {}; this.status = st; try { this.execSrc(t, ctx); } catch (e) { if (!(e instanceof ExitEx)) throw e; st = e.code; } }
        return st;
      });
    } finally { this.depth--; }
  }
  /* ----- test / [[ ]] ----- */
  evalCond(args, dbl) {
    if (dbl) { if (args[args.length - 1] !== ']]') throw new SynErr("syntax error in conditional expression"); args = args.slice(0, -1); }
    let i = 0; const sh = this; const ex = r => dbl ? sh.expStr(r) : r;
    const fileT = (op, f) => { const n = sh.lookup(f, op !== 'L' && op !== 'h'); if (!n) return false; switch (op) { case 'e': return true; case 'f': return n.type === 'f'; case 'd': return n.type === 'd'; case 'L': case 'h': return n.type === 'l'; case 'r': return sh.can(n, 4); case 'w': return sh.can(n, 2); case 'x': return sh.can(n, 1) && !!(n.mode & 0o111 || n.type === 'd'); case 's': return n.type === 'f' && n.data.length > 0; case 'c': return n.type === 'c'; case 'b': return false; case 'u': return !!(n.mode & 0o4000); case 'g': return !!(n.mode & 0o2000); case 'k': return !!(n.mode & 0o1000); case 'O': return n.uid === sh.uid; } return false; };
    const num = v => { if (dbl) return sh.arith(v); if (!/^\s*-?\d+\s*$/.test(v)) throw new Abort('bash: [: ' + v + ': integer expression expected'); return parseInt(v, 10); };
    function prim() {
      const t = args[i];
      if (t === undefined) return false;
      if (t === '!') { i++; return !prim(); }
      if (t === '(') { i++; const v = or(); if (args[i] === ')') i++; return v; }
      const nx = args[i + 1], n2 = args[i + 2];
      const isBin = nx !== undefined && /^(=|==|!=|=~|<|>|-eq|-ne|-lt|-le|-gt|-ge|-nt|-ot|-ef)$/.test(nx) && n2 !== undefined;
      if (!isBin && /^-[a-zA-Z]$/.test(t) && nx !== undefined && !(dbl ? /^(&&|\|\|)$/ : /^(-a|-o)$/).test(nx)) {
        i += 2; const v = ex(nx);
        if (t === '-z') return v === ''; if (t === '-n') return v !== ''; if (t === '-v') return sh.vars.has(v); if (t === '-t') return true;
        return fileT(t[1], v);
      }
      if (isBin) {
        i += 3; const a = ex(t);
        if (nx === '=~') { let parts = [n2]; while (args[i] !== undefined && !/^(&&|\|\|)$/.test(args[i])) parts.push(args[i++]); const m = mkRe(parts.map(ex).join(''), true).exec(a); sh.vars.set('BASH_REMATCH', { v: m ? Array.from(m, x => x === undefined ? '' : x) : [], x: false }); return !!m; }
        if (nx === '=' || nx === '==' || nx === '!=') { const eq = dbl ? sh.matchPat(a, sh.expPat(n2)) : a === n2; return (nx === '!=') !== eq; }
        const b = ex(n2);
        switch (nx) {
          case '<': return a < b; case '>': return a > b;
          case '-eq': return num(a) === num(b); case '-ne': return num(a) !== num(b); case '-lt': return num(a) < num(b); case '-le': return num(a) <= num(b); case '-gt': return num(a) > num(b); case '-ge': return num(a) >= num(b);
          case '-nt': { const x = sh.lookup(a), y = sh.lookup(b); return !!x && (!y || x.mtime > y.mtime); } case '-ot': { const x = sh.lookup(a), y = sh.lookup(b); return !!y && (!x || x.mtime < y.mtime); }
          case '-ef': return !!sh.lookup(a) && sh.lookup(a) === sh.lookup(b);
        }
      }
      i++; return ex(t) !== '';
    }
    function and() { let v = prim(); while (args[i] === (dbl ? '&&' : '-a')) { i++; const r = prim(); v = v && r; } return v; }
    function or() { let v = and(); while (args[i] === (dbl ? '||' : '-o')) { i++; const r = and(); v = v || r; } return v; }
    const v = or();
    if (i < args.length) throw new Abort('bash: ' + (dbl ? '[[' : '[') + ': too many arguments');
    return v ? 0 : 1;
  }
  /* ----- top level ----- */
  histExpand(line) {
    if (!/!/.test(line) || !this.hist.length) return line;
    const last = this.hist[this.hist.length - 1]; let changed = false, out = '', i = 0, sq = false;
    while (i < line.length) {
      const c = line[i];
      if (c === "'") { sq = !sq; out += c; i++; continue; }
      if (c === '\\') { out += line.substr(i, 2); i += 2; continue; }
      if (!sq && c === '!' && line[i + 1] === '!') { out += last; i += 2; changed = true; continue; }
      if (!sq && c === '!' && line[i + 1] === '$') { let w = []; try { w = lex(last).filter(t => t.t === 'word'); } catch (e) {} out += w.length ? w[w.length - 1].raw : ''; i += 2; changed = true; continue; }
      if (!sq && c === '!' && line[i + 1] === '*') { let w = []; try { w = lex(last).filter(t => t.t === 'word'); } catch (e) {} out += w.slice(1).map(t => t.raw).join(' '); i += 2; changed = true; continue; }
      out += c; i++;
    }
    return changed ? out : line;
  }
  run(src, o = {}) {
    const out = []; let total = 0;
    const push = (s, e) => { total += s.length; if (total > 400000) throw new Abort('(output truncated by sandbox)'); const l = out[out.length - 1]; if (l && l.e === e) l.s += s; else out.push({ s, e }); };
    const o1 = { w: s => push(s, false), tty: true }, o2 = { w: s => push(s, true), tty: true }; this.term = o1;
    const ctx = { in: { s: o.stdin || '', p: 0, tty: true }, fd: { 1: o1, 2: o2 } };
    this.steps = 0; this.depth = 0; this.noErr = 0; let st, echo;
    try {
      let ast;
      if (o.history !== false) { const x = this.histExpand(src); if (x !== src) { echo = x; src = x; } }
      try { ast = parse(src); } catch (e) { if (e instanceof Incomplete) return { incomplete: true }; if (e instanceof SynErr) { if (o.history !== false && src.trim()) this.hist.push(src); return { out: [{ s: 'bash: ' + e.message + '\n', e: true }], status: 2, stdout: '', stderr: e.message }; } throw e; }
      if (o.history !== false && src.trim()) this.hist.push(src);
      st = this.execList(ast, ctx);
    } catch (e) {
      if (e instanceof ExitEx) { st = e.code; push('exit\n(the sandbox shell stays open)\n', true); }
      else if (e instanceof Abort) { push(e.msg + '\n', true); st = 1; }
      else if (e instanceof RetEx) { push('bash: return: can only `return\' from a function or sourced script\n', true); st = 1; }
      else if (e instanceof BrkEx || e instanceof CntEx) st = 0;
      else if (e instanceof RangeError) { push('bash: fork: retry: Resource temporarily unavailable\n', true); st = 254; }
      else if (e instanceof FsErr) { push('bash: ' + e.path + ': ' + e.msg + '\n', true); st = 1; }
      else if (e instanceof SynErr) { push('bash: ' + e.message + '\n', true); st = 2; }
      else if (e instanceof Incomplete) { push('bash: syntax error: unexpected end of file\n', true); st = 2; }
      else throw e;
    }
    this.status = st === undefined ? 0 : st;
    return { out, status: this.status, echo, stdout: out.filter(x => !x.e).map(x => x.s).join(''), stderr: out.filter(x => x.e).map(x => x.s).join('') };
  }
}

G.Sandbox = { Shell, CMDS, BUILTINS, MAN, mkNode, FsErr, ExitEx, RetEx, BrkEx, CntEx, Abort, Incomplete, SynErr, lex, parse, parseParts, braceExpand, globRe, reConv, mkRe, sprintf, unesc, fmtNum, reEsc, POSIX };
})(typeof window !== 'undefined' ? window : globalThis);
