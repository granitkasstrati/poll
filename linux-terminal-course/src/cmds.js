/* Sandbox commands: shell builtins and the core utilities. */
(function (G) {
'use strict';
const S = G.Sandbox, { CMDS, BUILTINS, MAN, mkNode, FsErr, ExitEx, RetEx, BrkEx, CntEx, Abort, sprintf, unesc, mkRe, reEsc } = S;
const C = (names, fn, man) => names.split(' ').forEach(n => { CMDS[n] = fn; if (man) MAN[n] = man; });
const B = (names, fn, man) => names.split(' ').forEach(n => { BUILTINS[n] = fn; if (man) MAN[n] = man; });
S.C = C; S.B = B;

function go(a, vals = '', long = {}) {
  const o = {}, r = []; let i = 0;
  for (; i < a.length; i++) {
    const x = a[i];
    if (x === '--') { r.push(...a.slice(i + 1)); break; }
    if (x.startsWith('--') && x.length > 2) {
      const eq = x.indexOf('='), name = eq < 0 ? x.slice(2) : x.slice(2, eq); const k = long[name] || name;
      if (eq >= 0) o[k] = x.slice(eq + 1); else if (k.length === 1 && vals.includes(k)) o[k] = a[++i]; else o[k] = true;
    } else if (x[0] === '-' && x.length > 1) {
      for (let j = 1; j < x.length; j++) {
        const f = x[j];
        if (vals.includes(f)) { o[f] = j + 1 < x.length ? x.slice(j + 1) : a[++i]; break; }
        o[f] = true;
      }
    } else r.push(x);
  }
  return { o, r };
}
S.go = go;
const lines = s => { if (s === '') return []; const l = s.split('\n'); if (l[l.length - 1] === '') l.pop(); return l; };
function src(files, io, sh) {
  if (!files.length) { if (io.inTty) io.err('(sandbox: no interactive stdin here; pipe or redirect input instead)\n'); return io.stdin(); }
  return files.map(f => f === '-' ? io.stdin() : sh.read(f)).join('');
}
function each(files, io, sh, name, fn) {
  let st = 0; if (!files.length) files = ['-'];
  for (const f of files) { try { fn(f === '-' ? io.stdin() : sh.read(f), f); } catch (e) { if (!(e instanceof FsErr)) throw e; io.err(name + ': ' + e.path + ': ' + e.msg + '\n'); st = 1; } }
  return st;
}
const human = n => { if (n < 1024) return '' + n; const u = 'KMGT'; let i = -1; do { n /= 1024; i++; } while (n >= 1024 && i < 3); return (n < 10 ? (Math.ceil(n * 10) / 10).toFixed(1) : '' + Math.ceil(n)) + u[i]; };
const modeStr = n => {
  const t = { d: 'd', l: 'l', c: 'c', f: '-' }[n.type], m = n.mode; let s = '';
  for (let i = 2; i >= 0; i--) { const b = (m >> (i * 3)) & 7, sp = (m >> 9) & (1 << i); s += (b & 4 ? 'r' : '-') + (b & 2 ? 'w' : '-') + (sp ? (i === 0 ? (b & 1 ? 't' : 'T') : (b & 1 ? 's' : 'S')) : (b & 1 ? 'x' : '-')); }
  return t + s;
};
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], DAY = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const p2 = n => String(n).padStart(2, '0');
const lsDate = t => { const d = new Date(t); return MON[d.getUTCMonth()] + ' ' + String(d.getUTCDate()).padStart(2) + ' ' + p2(d.getUTCHours()) + ':' + p2(d.getUTCMinutes()); };
const sizeOf = n => n.type === 'f' ? n.data.length : n.type === 'd' ? 4096 : n.type === 'l' ? n.target.length : 0;
const uname = (sh, id) => sh.users[id] !== undefined ? sh.users[id] : '' + id;
const gname = (sh, id) => sh.groupNames[id] !== undefined ? sh.groupNames[id] : '' + id;
const uidOf = (sh, name) => { const k = Object.keys(sh.users).find(k => sh.users[k] === name); return k === undefined ? (/^\d+$/.test(name) ? +name : null) : +k; };
const gidOf = (sh, name) => { const k = Object.keys(sh.groupNames).find(k => sh.groupNames[k] === name); return k === undefined ? (/^\d+$/.test(name) ? +name : null) : +k; };
const join = (a, b) => a === '/' ? '/' + b : a.replace(/\/$/, '') + '/' + b;
const base = p => p.replace(/\/+$/, '').replace(/^.*\//, '') || '/';
Object.assign(S, { lines, src, human, modeStr, lsDate, sizeOf, uname, gname, uidOf, gidOf, join, base });

/* ================= builtins ================= */
B(': true', () => 0); B('false', () => 1);
B('echo', (a, io) => {
  let nl = true, esc = false;
  while (a.length && /^-[neE]+$/.test(a[0])) { const f = a.shift(); if (f.includes('n')) nl = false; if (f.includes('e')) esc = true; if (f.includes('E')) esc = false; }
  let s = a.join(' '); if (esc) s = unesc(s); io.out(s + (nl ? '\n' : ''));
}, 'echo [-ne] [arg...] — print arguments. -n: no trailing newline, -e: interpret \\n \\t escapes');
B('printf', (a, io, sh) => {
  let v = null; if (a[0] === '-v') { v = a[1]; a = a.slice(2); } if (a[0] === '--') a = a.slice(1);
  if (!a.length) return io.fail('usage: printf [-v var] format [arguments]', 2);
  const s = sprintf(unesc(a[0].replace(/%%/g, '\u0001')).replace(/\u0001/g, '%%'), a.slice(1), true);
  if (v) sh.setv(v, s); else io.out(s);
}, 'printf FORMAT [ARG...] — formatted output (%s %d %x %05.2f ...). The format is reused until all args are consumed');
B('pwd', (a, io, sh) => io.out(sh.cwd + '\n'), 'pwd — print the working directory');
B('cd', (a, io, sh) => {
  a = a.filter(x => x !== '-P' && x !== '-L' && x !== '--');
  let t = a[0]; let show = false;
  if (t === undefined) t = sh.getv('HOME'); else if (t === '-') { t = sh.getv('OLDPWD'); if (!t) return io.fail('OLDPWD not set'); show = true; }
  if (t === undefined || t === '') return io.fail('HOME not set');
  let n = sh.lookup(t), path = t;
  if (!n && !/^[./]/.test(t) && sh.getv('CDPATH')) for (const d of sh.getv('CDPATH').split(':')) { const p = join(d || '.', t); if (sh.lookup(p)) { n = sh.lookup(p); path = p; show = true; break; } }
  if (!n) { sh.lookup(t); return io.fail(t + ': ' + sh.err); }
  if (n.type !== 'd') return io.fail(t + ': Not a directory');
  if (!sh.can(n, 1)) return io.fail(t + ': Permission denied');
  sh.setv('OLDPWD', sh.cwd); sh.cwd = sh.abs(path); if (show) io.out(sh.cwd + '\n');
}, 'cd [DIR] — change directory. `cd` alone goes home, `cd -` returns to the previous directory');
B('pushd', (a, io, sh) => { if (!a[0]) return io.fail('no other directory'); const old = sh.cwd; const st = BUILTINS.cd([a[0]], io, sh); if (st) return st; sh.dirstack.unshift(old); io.out([sh.cwd, ...sh.dirstack].join(' ') + '\n'); }, 'pushd DIR — cd to DIR and remember where you were (see popd)');
B('popd', (a, io, sh) => { if (!sh.dirstack.length) return io.fail('directory stack empty'); const d = sh.dirstack.shift(); BUILTINS.cd([d], io, sh); io.out([sh.cwd, ...sh.dirstack].join(' ') + '\n'); }, 'popd — return to the directory saved by pushd');
B('dirs', (a, io, sh) => io.out([sh.cwd, ...sh.dirstack].join(' ') + '\n'));
B('export', (a, io, sh) => {
  if (!a.length || a[0] === '-p') { for (const [k, v] of [...sh.vars].sort()) if (v.x && typeof v.v === 'string') io.out('declare -x ' + k + '="' + v.v + '"\n'); return; }
  let un = false;
  for (const x of a) { if (x === '-n') { un = true; continue; } const m = /^([A-Za-z_]\w*)(?:=([\s\S]*))?$/.exec(x); if (!m) return io.fail("`" + x + "': not a valid identifier"); if (m[2] !== undefined) sh.setv(m[1], m[2]); let v = sh.vars.get(m[1]); if (!v) { v = { v: '', x: true, unsetX: true }; sh.vars.set(m[1], v); } v.x = !un; }
}, 'export NAME[=VALUE]... — mark variables for inheritance by child processes');
B('unset', (a, io, sh) => { let fn = false; for (const x of a) { if (x === '-f') { fn = true; continue; } if (x === '-v') continue; if (fn) delete sh.funcs[x]; else { const m = /^(\w+)\[(.+)\]$/.exec(x); if (m) { const v = sh.vars.get(m[1]); if (v && Array.isArray(v.v)) delete v.v[sh.arith(m[2])]; else if (v && typeof v.v === 'object') delete v.v[m[2]]; } else if (sh.vars.get(x) && sh.vars.get(x).ro) return io.fail(x + ': cannot unset: readonly variable'); else sh.vars.delete(x); } } }, 'unset [-f] NAME... — remove variables (or functions with -f)');
B('readonly', (a, io, sh) => { for (const x of a) { const m = /^([A-Za-z_]\w*)(?:=([\s\S]*))?$/.exec(x); if (!m) continue; if (m[2] !== undefined) sh.setv(m[1], m[2]); else if (!sh.vars.has(m[1])) sh.setv(m[1], ''); sh.vars.get(m[1]).ro = true; } });
B('local declare typeset', (a, io, sh, name) => {
  const fl = {}; const rest = [];
  for (const x of a) { if (/^[-+][a-zA-Z]+$/.test(x)) for (const c of x.slice(1)) fl[c] = x[0] === '-'; else rest.push(x); }
  if (name !== 'local' && !rest.length) {
    for (const [k, v] of [...sh.vars].sort()) { if (fl.x && !v.x) continue; if (fl.f) continue; if (Array.isArray(v.v)) io.out('declare -a ' + k + '=(' + v.v.map((x, i) => '[' + i + ']="' + x + '"').join(' ') + ')\n'); else if (typeof v.v === 'object') io.out('declare -A ' + k + '=(' + Object.entries(v.v).map(([a, b]) => '[' + a + ']="' + b + '"').join(' ') + ' )\n'); else io.out('declare -' + (v.x ? 'x' : '-') + ' ' + k + '="' + v.v + '"\n'); }
    if (fl.f) for (const f of Object.keys(sh.funcs)) io.out('declare -f ' + f + '\n'); return;
  }
  if (name === 'local' && !sh.fdepth) return io.fail('can only be used in a function');
  for (const x of rest) {
    const m = /^([A-Za-z_]\w*)(\+?=[\s\S]*)?$/.exec(x); if (!m) return io.fail("`" + x + "': not a valid identifier");
    if (sh.fdepth && !fl.g) { const old = sh.vars.get(m[1]); sh.locals.push([m[1], old ? { ...old } : undefined]); if (m[2] === undefined) sh.vars.set(m[1], { v: fl.a ? [] : fl.A ? {} : '', x: false }); }
    let v = sh.vars.get(m[1]);
    if (!v) { v = { v: fl.A ? {} : fl.a ? [] : '', x: false }; sh.vars.set(m[1], v); }
    if (fl.A) { v.assoc = true; if (typeof v.v !== 'object' || Array.isArray(v.v)) v.v = {}; }
    if (fl.i) v.int = true;
    if (m[2] !== undefined) sh.assign(x);
    v = sh.vars.get(m[1]); if (fl.x) v.x = true; if (fl.r) v.ro = true;
  }
}, 'declare [-aAirx] NAME[=VALUE] — declare variables: -a array, -A associative array, -i integer, -r readonly, -x export');
B('set', (a, io, sh) => {
  if (!a.length) { for (const [k, v] of [...sh.vars].sort()) if (typeof v.v === 'string') io.out(k + '=' + (/[^\w\/.:-]/.test(v.v) || v.v === '' ? "'" + v.v + "'" : v.v) + '\n'); return; }
  for (let i = 0; i < a.length; i++) {
    const x = a[i];
    if (x === '--') { sh.pos = a.slice(i + 1); return; }
    if (x === '-o' || x === '+o') { const n = a[++i]; if (n === undefined) { for (const k of ['errexit', 'nounset', 'pipefail', 'xtrace', 'noglob', 'noclobber']) io.out(k.padEnd(16) + (sh.opts[{ errexit: 'e', nounset: 'u', xtrace: 'x', noglob: 'f', noclobber: 'C' }[k] || k] ? 'on' : 'off') + '\n'); return; } const k = { errexit: 'e', nounset: 'u', xtrace: 'x', noglob: 'f', noclobber: 'C', allexport: 'a' }[n] || n; sh.opts[k] = x[0] === '-'; continue; }
    if (/^[-+][a-zA-Z]+$/.test(x)) { for (const c of x.slice(1)) { if (c === 'o') { const n = a[++i]; const k = { errexit: 'e', nounset: 'u', xtrace: 'x', noglob: 'f', noclobber: 'C', allexport: 'a' }[n] || n; if (k) sh.opts[k] = x[0] === '-'; } else sh.opts[c] = x[0] === '-'; } continue; }
    sh.pos = a.slice(i); return;
  }
}, 'set [-euxo pipefail] — shell options. -e exit on error, -u error on unset variables, -x trace, -o pipefail. `set --` replaces $1 $2 ...');
B('shopt', () => 0, 'shopt — bash-specific options (accepted but ignored in the sandbox)');
B('shift', (a, io, sh) => { const n = a[0] ? +a[0] : 1; if (n > sh.pos.length) return 1; sh.pos = sh.pos.slice(n); }, 'shift [N] — drop the first N positional parameters');
B('exit', (a, io, sh) => { throw new ExitEx(a[0] !== undefined ? (+a[0] & 255) : sh.status); }, 'exit [N] — leave the shell or script with status N');
B('return', (a, io, sh) => { throw new RetEx(a[0] !== undefined ? (+a[0] & 255) : sh.status); }, 'return [N] — return from a function with status N');
B('break', a => { throw new BrkEx(+a[0] || 1); }); B('continue', a => { throw new CntEx(+a[0] || 1); });
B('test [', (a, io, sh, name) => { if (name === '[') { if (a[a.length - 1] !== ']') return io.fail("missing `]'", 2); a = a.slice(0, -1); } return sh.evalCond(a, false); }, 'test EXPR / [ EXPR ] — file tests (-e -f -d -r -w -x -s), strings (-z -n = !=), integers (-eq -ne -lt -le -gt -ge)');
B('let', (a, io, sh) => { let v = 0; for (const x of a) v = sh.arith(x); return v ? 0 : 1; });
B('read', (a, io, sh) => {
  const { o, r } = go(a, 'pdnatu');
  const line = io.readLine(); if (o.p && io.inTty) io.err(o.p);
  if (line === null) { for (const v of r) sh.setv(v, ''); return 1; }
  if (o.a) { sh.setv(o.a, line.trim().split(/\s+/).filter(Boolean)); return 0; }
  if (!r.length) { sh.setv('REPLY', line); return 0; }
  let ifs = sh.getv('IFS'); if (ifs === undefined) ifs = ' \t\n';
  const ws = [...ifs].filter(c => ' \t\n'.includes(c)).map(reEsc).join(''), nws = [...ifs].filter(c => !' \t\n'.includes(c)).map(reEsc).join('');
  let s = ws ? line.replace(new RegExp('^[' + ws + ']+|[' + ws + ']+$', 'g'), '') : line;
  const sep = ifs === '' ? null : new RegExp(ws && nws ? '[' + ws + ']*[' + nws + '][' + ws + ']*|[' + ws + ']+' : nws ? '[' + nws + ']' : '[' + ws + ']+');
  r.forEach((v, i) => {
    if (i === r.length - 1 || !sep) { sh.setv(v, s); s = ''; return; }
    const m = sep.exec(s); if (!m) { sh.setv(v, s); s = ''; } else { sh.setv(v, s.slice(0, m.index)); s = s.slice(m.index + m[0].length); }
  });
  return 0;
}, 'read [-r] [-a ARRAY] [NAME...] — read one line from stdin and split it into variables using IFS');
B('alias', (a, io, sh) => { if (!a.length) { for (const k of Object.keys(sh.aliases).sort()) io.out("alias " + k + "='" + sh.aliases[k] + "'\n"); return; } let st = 0; for (const x of a) { const i = x.indexOf('='); if (i < 0) { if (sh.aliases[x] !== undefined) io.out("alias " + x + "='" + sh.aliases[x] + "'\n"); else st = io.fail(x + ': not found'); } else sh.aliases[x.slice(0, i)] = x.slice(i + 1); } return st; }, "alias NAME='COMMAND' — define a shortcut; `alias` alone lists them");
B('unalias', (a, io, sh) => { for (const x of a) delete sh.aliases[x]; });
const KW = ['if', 'then', 'else', 'elif', 'fi', 'for', 'while', 'until', 'do', 'done', 'case', 'esac', 'function', 'time', '[[', '{', '}', '!', 'in'];
B('type', (a, io, sh) => {
  const { o, r } = go(a); let st = 0;
  for (const n of r) {
    const res = [];
    if (sh.aliases[n] !== undefined) res.push(o.t ? 'alias' : n + " is aliased to `" + sh.aliases[n] + "'");
    if (KW.includes(n)) res.push(o.t ? 'keyword' : n + ' is a shell keyword');
    if (sh.funcs[n]) res.push(o.t ? 'function' : n + ' is a function');
    if (BUILTINS[n]) res.push(o.t ? 'builtin' : n + ' is a shell builtin');
    for (const d of (sh.getv('PATH') || '').split(':')) { const f = sh.lookup(d + '/' + n); if (d && f && f.type === 'f' && (f.mode & 0o111)) res.push(o.t ? 'file' : o.p ? d + '/' + n : n + ' is ' + d + '/' + n); }
    if (!res.length) { io.err('bash: type: ' + n + ': not found\n'); st = 1; } else io.out((o.a ? res : res.slice(0, 1)).join('\n') + '\n');
  }
  return st;
}, 'type [-at] NAME — how the shell would interpret NAME: alias, keyword, function, builtin or file');
B('command', (a, io, sh) => {
  if (a[0] === '-v' || a[0] === '-V') { let st = 0; for (const n of a.slice(1)) { if (sh.aliases[n] !== undefined) io.out("alias " + n + "='" + sh.aliases[n] + "'\n"); else if (sh.funcs[n] || BUILTINS[n] || KW.includes(n)) io.out(n + '\n'); else { const p = sh.inPath(n); if (p) io.out(p + '\n'); else st = 1; } } return st; }
  if (!a.length) return 0; return sh.invoke(a, io.ctx, true);
}, 'command [-v] NAME — run NAME ignoring functions and aliases; -v prints how it resolves (portable `which`)');
B('builtin', (a, io, sh) => BUILTINS[a[0]] ? sh.runCmd(BUILTINS[a[0]], a[0], a, io.ctx) : io.fail(a[0] + ': not a shell builtin'));
B('hash', () => 0);
B('eval', (a, io, sh) => sh.execSrc(a.join(' '), io.ctx), 'eval ARGS — join the arguments and run the result as shell code (rarely the right tool)');
B('exec', (a, io, sh) => a.length ? sh.invoke(a, io.ctx) : 0);
B('source .', (a, io, sh) => { if (!a[0]) return io.fail('filename argument required', 2); const data = sh.read(a[0]); const sv = sh.pos; if (a.length > 1) sh.pos = a.slice(1); try { return sh.execList(S.parse(data), io.ctx); } catch (e) { if (e instanceof RetEx) return e.code; throw e; } finally { sh.pos = sv; } }, 'source FILE (or . FILE) — run FILE in the current shell, so its variables and functions stay');
B('trap', (a, io, sh) => { if (!a.length || a[0] === '-p') { for (const k of Object.keys(sh.traps)) io.out("trap -- '" + sh.traps[k] + "' " + k + '\n'); return; } if (a[0] === '-l') { io.out(' 1) SIGHUP  2) SIGINT  3) SIGQUIT  9) SIGKILL  15) SIGTERM  17) SIGCHLD  18) SIGCONT  19) SIGSTOP  20) SIGTSTP\n'); return; } const act = a[0]; for (const s of a.slice(1)) { const k = s.replace(/^SIG/, '').replace(/^0$/, 'EXIT'); if (act === '-' || act === '') delete sh.traps[k]; else sh.traps[k] = act; } }, "trap 'COMMANDS' SIGNAL... — run COMMANDS when the shell receives SIGNAL. EXIT fires when the script ends for any reason");
B('umask', (a, io, sh) => { if (!a.length) { io.out(sh.umask.toString(8).padStart(4, '0') + '\n'); return; } if (a[0] === '-S') { const m = 0o777 & ~sh.umask; io.out('u=' + 'rwx'.split('').filter((c, i) => m & (0o400 >> i)).join('') + ',g=' + 'rwx'.split('').filter((c, i) => m & (0o40 >> i)).join('') + ',o=' + 'rwx'.split('').filter((c, i) => m & (0o4 >> i)).join('') + '\n'); return; } if (!/^[0-7]{1,4}$/.test(a[0])) return io.fail(a[0] + ': octal number out of range'); sh.umask = parseInt(a[0], 8); }, 'umask [MODE] — permission bits removed from newly created files (022 gives 644 files and 755 directories)');
B('history', (a, io, sh) => { if (a[0] === '-c') { sh.hist.length = 0; return; } const n = a[0] ? +a[0] : sh.hist.length; sh.hist.slice(-n).forEach((h, i) => io.out(String(sh.hist.length - Math.min(n, sh.hist.length) + i + 1).padStart(5) + '  ' + h + '\n')); }, 'history [N] — list previous commands. `!!` repeats the last one, `!$` is its last argument');
B('getopts', (a, io, sh) => {
  const spec = a[0], name = a[1], args = a.length > 2 ? a.slice(2) : sh.pos; let ind = +(sh.getv('OPTIND') || 1); let cp = sh.optpos || 1;
  const silent = spec[0] === ':'; const cur = args[ind - 1];
  if (cur === undefined || cur[0] !== '-' || cur === '-' ) { sh.setv(name, '?'); return 1; }
  if (cur === '--') { sh.setv('OPTIND', '' + (ind + 1)); sh.setv(name, '?'); return 1; }
  const c = cur[cp]; const i = spec.indexOf(c, silent ? 1 : 0); const adv = () => { if (cp + 1 < cur.length) sh.optpos = cp + 1; else { sh.optpos = 1; ind++; } };
  sh.vars.delete('OPTARG');
  if (i < 0 || c === ':') { adv(); sh.setv('OPTIND', '' + ind); sh.setv(name, '?'); if (silent) sh.setv('OPTARG', c); else io.err(sh.arg0 + ': illegal option -- ' + c + '\n'); return 0; }
  if (spec[i + 1] === ':') {
    let val; if (cp + 1 < cur.length) { val = cur.slice(cp + 1); ind++; } else { val = args[ind]; ind += 2; }
    sh.optpos = 1; sh.setv('OPTIND', '' + ind);
    if (val === undefined) { if (silent) { sh.setv(name, ':'); sh.setv('OPTARG', c); } else { sh.setv(name, '?'); io.err(sh.arg0 + ': option requires an argument -- ' + c + '\n'); } return 0; }
    sh.setv('OPTARG', val);
  } else { adv(); sh.setv('OPTIND', '' + ind); }
  sh.setv(name, c); return 0;
}, 'getopts OPTSTRING NAME — parse short options in a while loop; a colon after a letter means it takes an argument ($OPTARG)');
B('argv', (a, io) => { io.out('argc = ' + a.length + '\n'); a.forEach((x, i) => io.out('  argv[' + (i + 1) + '] = <' + x + '>\n')); }, 'argv ARGS... — (sandbox helper) show exactly which arguments a command would receive after all shell expansions');
B('wait', () => 0, 'wait [PID|%JOB] — block until background jobs finish');
B('jobs', (a, io, sh) => { sh.jobs.forEach((j, i) => io.out('[' + j.id + ']' + (i === sh.jobs.length - 1 ? '+' : i === sh.jobs.length - 2 ? '-' : ' ') + '  ' + (a.includes('-l') ? j.pid + ' ' : '') + j.state.padEnd(24) + j.cmd + (j.state === 'Running' ? ' &' : '') + '\n')); }, 'jobs [-l] — list background and stopped jobs of this shell');
const jobOf = (sh, spec) => { if (!sh.jobs.length) return null; if (spec === undefined || spec === '%%' || spec === '%+') return sh.jobs[sh.jobs.length - 1]; const m = /^%?(\d+)$/.exec(spec); if (m) return sh.jobs.find(j => j.id === +m[1]) || null; return sh.jobs.find(j => j.cmd.startsWith(spec.replace(/^%/, ''))) || null; };
B('fg', (a, io, sh) => { const j = jobOf(sh, a[0]); if (!j) return io.fail((a[0] || 'current') + ': no such job'); io.out(j.cmd + '\n'); io.err('^C  (sandbox: a foreground job would block here until it ends; treated as interrupted)\n'); sh.jobs = sh.jobs.filter(x => x !== j); sh.procs = sh.procs.filter(p => p.pid !== j.pid); return 130; }, 'fg [%JOB] — bring a job to the foreground');
B('bg', (a, io, sh) => { const j = jobOf(sh, a[0]); if (!j) return io.fail((a[0] || 'current') + ': no such job'); j.state = 'Running'; const p = sh.procs.find(p => p.pid === j.pid); if (p) p.stat = 'S'; io.out('[' + j.id + ']+ ' + j.cmd + ' &\n'); }, 'bg [%JOB] — resume a stopped job in the background');
B('disown', (a, io, sh) => { const j = jobOf(sh, a.filter(x => x[0] !== '-')[0]); if (!j) return io.fail('current: no such job'); sh.jobs = sh.jobs.filter(x => x !== j); }, 'disown [%JOB] — remove a job from the shell\'s table so it is not sent SIGHUP on logout');
const SIGS = { HUP: 1, INT: 2, QUIT: 3, KILL: 9, USR1: 10, SEGV: 11, USR2: 12, PIPE: 13, ALRM: 14, TERM: 15, CHLD: 17, CONT: 18, STOP: 19, TSTP: 20 };
function signal(sh, io, p, sig, who) {
  if (sh.uid !== 0 && p.user !== sh.users[sh.uid]) { io.err(who + ': (' + p.pid + ') - Operation not permitted\n'); return 1; }
  if (sig === 0) return 0;
  const j = sh.jobs.find(j => j.pid === p.pid);
  if (sig === 19 || sig === 20) { p.stat = 'T'; if (j) { j.state = 'Stopped'; io.err('[' + j.id + ']+  Stopped                 ' + j.cmd + '\n'); } return 0; }
  if (sig === 18) { p.stat = 'S'; if (j) j.state = 'Running'; return 0; }
  if (p.pid === 1 || p.pid === sh.pid) return 0;
  if (sig !== 9 && p.ignoreTerm && [1, 2, 15].includes(sig)) return 0;
  if (sig === 17 || sig === 10 || sig === 12) return 0;
  if (p.respawn) { io.err('(pid ' + p.pid + ' died; its supervisor restarted the service)\n'); p.pid = sh.nextPid++; sh.world.restarts = (sh.world.restarts || 0) + 1; return 0; }
  sh.procs = sh.procs.filter(x => x !== p);
  if (j) { sh.jobs = sh.jobs.filter(x => x !== j); io.err('[' + j.id + ']+  ' + (sig === 9 ? 'Killed' : 'Terminated').padEnd(24) + j.cmd + '\n'); }
  return 0;
}
S.signal = signal; S.SIGS = SIGS;
const parseSig = s => { s = s.replace(/^-/, '').replace(/^SIG/i, '').toUpperCase(); if (/^\d+$/.test(s)) return +s; return SIGS[s]; };
B('kill', (a, io, sh) => {
  if (a[0] === '-l' || a[0] === '-L') { io.out(Object.entries(SIGS).map(([k, v]) => String(v).padStart(2) + ') SIG' + k).join('\n') + '\n'); return; }
  let sig = 15; if (a[0] === '-s' || a[0] === '-n') { sig = parseSig(a[1]); a = a.slice(2); } else if (a[0] && /^-\w+$/.test(a[0])) { sig = parseSig(a[0]); a = a.slice(1); }
  if (sig === undefined) return io.fail('invalid signal specification');
  if (!a.length) return io.fail('usage: kill [-s sigspec | -n signum | -sigspec] pid | jobspec ...', 2);
  let st = 0;
  for (const t of a) {
    let pid; if (t[0] === '%') { const j = jobOf(sh, t); if (!j) { st = io.fail(t + ': no such job'); continue; } pid = j.pid; } else pid = +t;
    const p = sh.procs.find(p => p.pid === pid); if (!p) { io.err('bash: kill: (' + t + ') - No such process\n'); st = 1; continue; }
    st = signal(sh, io, p, sig, 'bash: kill') || st;
  }
  return st;
}, 'kill [-SIGNAL] PID|%JOB... — send a signal (default TERM). -9/KILL cannot be caught; `kill -l` lists signals');
B('help', (a, io) => {
  if (a[0]) { io.out((MAN[a[0]] || ('no help for ' + a[0])) + '\n'); return MAN[a[0]] ? 0 : 1; }
  io.out('Sandbox shell: a bash-compatible interpreter running in your browser.\nBuiltins:  ' + Object.keys(BUILTINS).sort().join(' ') + '\n\nPrograms:  ' + Object.keys(CMDS).sort().join(' ') + '\n\nTry `man NAME` for a one-line summary, `argv ARGS...` to inspect expansion, and Tab to complete.\n');
}, 'help [NAME] — list sandbox commands or describe one');

/* ================= file utilities ================= */
C('ls', (a, io, sh) => {
  const { o, r } = go(a, '', { all: 'a', 'human-readable': 'h', recursive: 'R', reverse: 'r', directory: 'd', inode: 'i' }); let st = 0;
  const fmt = (name, n, path) => {
    let nm = name; if (o.F || o.p) nm += n.type === 'd' ? '/' : (o.F && n.type === 'l') ? '@' : (o.F && n.type === 'f' && n.mode & 0o111) ? '*' : '';
    if (!o.l && !o.n) return (o.i ? n.ino + ' ' : '') + nm;
    return (o.i ? n.ino + ' ' : '') + modeStr(n);
  };
  const long = entries => {
    const rows = entries.map(([name, n]) => [o.i ? '' + n.ino : null, modeStr(n), '' + n.nlink, o.n ? '' + n.uid : uname(sh, n.uid), o.n ? '' + n.gid : gname(sh, n.gid), n.type === 'c' ? n.rdev || '1, 3' : (o.h ? human(sizeOf(n)) : '' + sizeOf(n)), lsDate(n.mtime), name + (n.type === 'l' ? ' -> ' + n.target : (o.F && n.type === 'd' ? '/' : ''))]);
    const w = [0, 1, 2, 3, 4, 5].map(i => Math.max(0, ...rows.map(r => r[i] === null ? 0 : r[i].length)));
    return rows.map(r => (r[0] !== null ? r[0].padStart(w[0]) + ' ' : '') + r[1] + ' ' + r[2].padStart(w[2]) + ' ' + r[3].padEnd(w[3]) + ' ' + r[4].padEnd(w[4]) + ' ' + r[5].padStart(w[5]) + ' ' + r[6] + ' ' + r[7]);
  };
  const order = es => { es.sort((x, y) => o.t ? y[1].mtime - x[1].mtime : o.S ? sizeOf(y[1]) - sizeOf(x[1]) : (x[0].replace(/^\./, '').toLowerCase() < y[0].replace(/^\./, '').toLowerCase() ? -1 : 1)); if (o.r) es.reverse(); return es; };
  const show = es => { if (o.l || o.n) io.out(long(es).map(l => l + '\n').join('')); else if (!es.length) { /* nothing */ } else io.out(es.map(([name, n]) => fmt(name, n)).join(io.tty && !o['1'] ? '  ' : '\n') + '\n'); };
  const listDir = (p, n, hdr) => {
    if (!sh.can(n, 4)) { io.err("ls: cannot open directory '" + p + "': Permission denied\n"); st = 2; return; }
    let es = [...n.kids.entries()]; if (!o.a && !o.A) es = es.filter(([k]) => k[0] !== '.');
    es = order(es); if (o.a) es = [['.', n], ['..', sh.lookup(p + '/..') || n], ...es];
    if (hdr) io.out(p + ':\n');
    if (o.l || o.n) io.out('total ' + es.reduce((s, [, x]) => s + (x.type === 'f' ? Math.ceil(x.data.length / 4096) * 4 : x.type === 'd' ? 4 : 0), 0) + '\n');
    show(es);
    if (o.R) for (const [k, c] of es) if (c.type === 'd' && k !== '.' && k !== '..') { io.out('\n'); listDir(join(p, k), c, true); }
  };
  const targets = r.length ? r : ['.'], files = [], dirs = [];
  for (const t of targets) { const n = sh.lookup(t, !(o.l || o.d || o.F)) || null; const n2 = n && n.type === 'l' && /\/$/.test(t) ? sh.lookup(t) : n; if (!n2) { io.err("ls: cannot access '" + t + "': " + sh.err + '\n'); st = 2; continue; } (n2.type === 'd' && !o.d ? dirs : files).push([t, n2]); }
  if (files.length) show(order(files));
  dirs.forEach(([t, n], i) => { if (files.length || i) io.out('\n'); listDir(t, n, targets.length > 1 || o.R); });
  return st;
}, 'ls [-laAhdRtSr1iF] [PATH...] — list directory contents. -l long, -a hidden, -h human sizes, -t by time, -S by size, -d the directory itself');
C('cat', (a, io, sh) => {
  const { o, r } = go(a); let n = 1;
  return each(r, io, sh, 'cat', d => { if (o.n || o.b) d = d.replace(/^(.*)$/gm, (m, l, off) => (off >= d.length && l === '') ? '' : (o.b && l === '' ? '' : String(n++).padStart(6) + '\t' + l)); if (o.A || o.E || o.T || o.v) { if (o.A || o.T) d = d.replace(/\t/g, '^I'); if (o.A || o.v) d = d.replace(/\r/g, '^M'); if (o.A || o.E) d = d.replace(/\n/g, '$\n'); } io.out(d); });
}, 'cat [-nA] [FILE...] — concatenate files to stdout. -n number lines, -A show tabs (^I), CRs (^M) and line ends ($)');
C('tac', (a, io, sh) => io.out(lines(src(a, io, sh)).reverse().map(l => l + '\n').join('')), 'tac — cat backwards, last line first');
C('rev', (a, io, sh) => io.out(lines(src(a, io, sh)).map(l => [...l].reverse().join('') + '\n').join('')), 'rev — reverse the characters of each line');
C('less more', (a, io, sh) => { io.out(src(a.filter(x => x[0] !== '-'), io, sh)); if (io.tty) io.err('(sandbox: pager shows everything at once; in a real terminal use / to search and q to quit)\n'); }, 'less FILE — pager. / search, n next, g/G top/bottom, F follow, q quit');
function headTail(tail) {
  return (a, io, sh) => {
    let n = 10, bytes = false, plus = false; const files = [];
    for (let i = 0; i < a.length; i++) {
      const x = a[i]; let m;
      if ((m = /^-(\d+)$/.exec(x))) n = +m[1];
      else if ((m = /^-([nc])(.*)$/.exec(x)) || (m = /^--(lines|bytes)=(.*)$/.exec(x))) { let v = m[2] || a[++i]; bytes = m[1][0] === 'c' || m[1][0] === 'b'; if (v[0] === '+') { plus = true; v = v.slice(1); } else if (v[0] === '-') { if (!tail) plus = true; v = v.slice(1); } const mm = /^(\d+)([kKMG]?)/.exec(v); n = +mm[1] * ({ k: 1024, K: 1024, M: 1048576, G: 1073741824 }[mm[2]] || 1); }
      else if (x === '-f' || x === '-F' || x === '-q') { if (x !== '-q' && io.tty) io.err('(sandbox: -f would keep following the file; showing the current tail)\n'); }
      else files.push(x);
    }
    let first = true;
    return each(files, io, sh, tail ? 'tail' : 'head', (d, f) => {
      if (files.length > 1) { io.out((first ? '' : '\n') + '==> ' + f + ' <==\n'); first = false; }
      if (bytes) { io.out(tail ? (plus ? d.slice(n - 1) : d.slice(Math.max(0, d.length - n))) : (plus ? d.slice(0, Math.max(0, d.length - n)) : d.slice(0, n))); return; }
      const l = lines(d); const sel = tail ? (plus ? l.slice(Math.max(0, n - 1)) : (n ? l.slice(-n) : [])) : (plus ? l.slice(0, Math.max(0, l.length - n)) : l.slice(0, n));
      io.out(sel.map(x => x + '\n').join(''));
    });
  };
}
C('head', headTail(false), 'head [-n N | -c N] [FILE] — first N lines (default 10) or bytes. -n -N: all but the last N');
C('tail', headTail(true), 'tail [-n N | -n +N | -c N] [-f] [FILE] — last N lines; +N starts at line N; -f follows growth');
C('wc', (a, io, sh) => {
  const { o, r } = go(a, '', { lines: 'l', words: 'w', bytes: 'c', chars: 'm' }); const all = !o.l && !o.w && !o.c && !o.m; const rows = [];
  const st = each(r, io, sh, 'wc', (d, f) => { const c = []; if (o.l || all) c.push((d.match(/\n/g) || []).length); if (o.w || all) c.push((d.match(/\S+/g) || []).length); if (o.c || o.m || all) c.push(d.length); rows.push([c, r.length ? f : '']); });
  if (rows.length > 1) rows.push([rows[0][0].map((_, i) => rows.reduce((s, x) => s + x[0][i], 0)), 'total']);
  const multi = rows.length > 1 || (rows[0] && rows[0][0].length > 1); const w = !multi ? 1 : Math.max(r.length ? 1 : 7, ...rows.flatMap(x => x[0].map(n => ('' + n).length)));
  for (const [c, f] of rows) io.out(c.map(n => ('' + n).padStart(w)).join(' ') + (f ? ' ' + f : '') + '\n');
  return st;
}, 'wc [-lwc] [FILE...] — count lines, words, bytes');
C('tee', (a, io, sh) => { const { o, r } = go(a); const d = io.stdin(); for (const f of r) sh.write(f, d, !!o.a); io.out(d); }, 'tee [-a] FILE... — copy stdin to stdout and to each FILE (-a appends). `cmd | sudo tee /etc/x` writes as root');
C('touch', (a, io, sh) => { const { r } = go(a, 'dtr'); for (const f of r) { const n = sh.lookup(f); if (n) { if (!sh.can(n, 2) && n.uid !== sh.uid) throw new FsErr("cannot touch '" + f + "'", 'Permission denied'); n.mtime = Date.now() + (sh.tick++); } else sh.write(f, ''); } }, 'touch FILE... — create empty files or update timestamps');
C('mkdir', (a, io, sh) => { const { o, r } = go(a, 'm', { parents: 'p', mode: 'm', verbose: 'v' }); if (!r.length) return io.fail('missing operand'); let st = 0; for (const d of r) { try { sh.mkdir(d, !!o.p, o.m ? parseInt(o.m, 8) : undefined); if (o.v) io.out("mkdir: created directory '" + d + "'\n"); } catch (e) { if (!(e instanceof FsErr)) throw e; io.err("mkdir: cannot create directory \u2018" + d + "\u2019: " + e.msg + '\n'); st = 1; } } return st; }, 'mkdir [-p] [-m MODE] DIR... — create directories; -p creates parents and ignores existing');
C('rmdir', (a, io, sh) => { let st = 0; for (const d of go(a).r) { const n = sh.lookup(d, false); if (!n) { io.err("rmdir: failed to remove '" + d + "': " + sh.err + '\n'); st = 1; } else if (n.type !== 'd') { io.err("rmdir: failed to remove '" + d + "': Not a directory\n"); st = 1; } else if (n.kids.size) { io.err("rmdir: failed to remove '" + d + "': Directory not empty\n"); st = 1; } else sh.unlink(d); } return st; }, 'rmdir DIR... — remove empty directories');
C('rm', (a, io, sh) => {
  const { o, r } = go(a, '', { recursive: 'r', force: 'f', verbose: 'v' }); const rec = o.r || o.R; let st = 0;
  if (!r.length && !o.f) return io.fail('missing operand');
  const del = p => { const n = sh.lookup(p, false); if (n.type === 'd') { if (!sh.can(n, 2) && n.kids.size) throw new FsErr("cannot remove '" + p + "'", 'Permission denied'); for (const k of [...n.kids.keys()]) del(join(p, k)); } sh.unlink(p); if (o.v) io.out("removed " + (n.type === 'd' ? 'directory ' : '') + "'" + p + "'\n"); };
  for (const p of r) {
    try {
      if (rec && sh.abs(p) === '/') { io.err("rm: it is dangerous to operate recursively on '/'\nrm: use --no-preserve-root to override this failsafe\n"); st = 1; continue; }
      const n = sh.lookup(p, false);
      if (!n) { if (!o.f) { io.err("rm: cannot remove '" + p + "': " + sh.err + '\n'); st = 1; } continue; }
      if (n.type === 'd' && !rec) { io.err("rm: cannot remove '" + p + "': Is a directory\n"); st = 1; continue; }
      del(p);
    } catch (e) { if (!(e instanceof FsErr)) throw e; io.err('rm: ' + (/^cannot/.test(e.path) ? e.path : "cannot remove '" + e.path + "'") + ': ' + e.msg + '\n'); st = 1; }
  }
  return st;
}, 'rm [-rf] PATH... — remove files; -r recurses into directories, -f ignores missing files. There is no undo');
function copyNode(sh, n, keep) { const c = structuredClone(n); const fix = x => { x.ino = S.mkNode('f', 0).ino; if (!keep) { x.uid = sh.uid; x.gid = sh.gid; x.mtime = Date.now() + (sh.tick++); x.mode &= 0o777; } if (x.type !== 'd') x.nlink = 1; if (x.kids) for (const k of x.kids.values()) fix(k); }; fix(c); return c; }
function place(sh, node, dst, srcName, cmd) {
  const d = sh.lookup(dst); let dir, name;
  if (d && d.type === 'd') { dir = d; name = srcName; } else { const p = sh.parentOf(dst); dir = p.d; name = p.name; }
  if (!sh.can(dir, 2)) throw new FsErr(dst, 'Permission denied');
  const ex = dir.kids.get(name);
  if (ex && ex.type === 'd' && node.type !== 'd') throw new FsErr(dst, 'cannot overwrite directory with non-directory');
  if (ex && ex.type !== 'd' && node.type !== 'd' && cmd === 'cp') { if (!sh.can(ex, 2)) throw new FsErr(dst, 'Permission denied'); ex.data = node.data; ex.mtime = node.mtime; return; }
  if (ex && ex.type === 'd' && node.type === 'd' && cmd === 'cp') { for (const [k, v] of node.kids) ex.kids.set(k, v); return; }
  dir.kids.set(name, node);
}
C('cp', (a, io, sh) => {
  const { o, r } = go(a, 't', { recursive: 'r', archive: 'a', verbose: 'v', preserve: 'p' }); if (r.length < 2) return io.fail(r.length ? "missing destination file operand after '" + r[0] + "'" : 'missing file operand');
  const dst = r.pop(); const dn = sh.lookup(dst); let st = 0;
  if (r.length > 1 && !(dn && dn.type === 'd')) return io.fail("target '" + dst + "' is not a directory");
  for (const s of r) {
    try {
      const n = sh.stat(s, !(o.a || o.P)); if (n.type === 'd' && !(o.r || o.R || o.a)) { io.err("cp: -r not specified; omitting directory '" + s + "'\n"); st = 1; continue; }
      if (n.type !== 'd' && !sh.can(n, 4)) throw new FsErr(s, 'Permission denied');
      place(sh, copyNode(sh, n, o.a || o.p), dst, base(s), 'cp'); if (o.v) io.out("'" + s + "' -> '" + (dn && dn.type === 'd' ? join(dst, base(s)) : dst) + "'\n");
    } catch (e) { if (!(e instanceof FsErr)) throw e; io.err("cp: cannot " + (e.path === s ? "stat" : "create regular file") + " '" + e.path + "': " + e.msg + '\n'); st = 1; }
  }
  return st;
}, 'cp [-rav] SRC... DST — copy. -r directories, -a archive (recursive, keeps owner, mode, times and links)');
C('mv', (a, io, sh) => {
  const { o, r } = go(a); if (r.length < 2) return io.fail('missing file operand'); const dst = r.pop(); const dn = sh.lookup(dst); let st = 0;
  if (r.length > 1 && !(dn && dn.type === 'd')) return io.fail("target '" + dst + "' is not a directory");
  for (const s of r) {
    try { const n = sh.stat(s, false); const p = sh.parentOf(s); if (!sh.can(p.d, 2)) throw new FsErr(s, 'Permission denied'); if (o.n && sh.lookup(dn && dn.type === 'd' ? join(dst, base(s)) : dst)) continue; p.d.kids.delete(p.name); try { place(sh, n, dst, base(s), 'mv'); } catch (e) { p.d.kids.set(p.name, n); throw e; } if (o.v) io.out("renamed '" + s + "' -> '" + dst + "'\n"); }
    catch (e) { if (!(e instanceof FsErr)) throw e; io.err("mv: cannot move '" + s + "': " + e.msg + '\n'); st = 1; }
  }
  return st;
}, 'mv SRC... DST — move or rename (atomic within one filesystem)');
C('ln', (a, io, sh) => {
  const { o, r } = go(a, '', { symbolic: 's', force: 'f' }); if (r.length < 1) return io.fail('missing file operand'); let dst = r.length > 1 ? r.pop() : '.';
  for (const s of r) {
    let target = dst; const dn = sh.lookup(dst); if (dn && dn.type === 'd' && !o.T) target = join(dst, base(s));
    const p = sh.parentOf(target); if (!sh.can(p.d, 2)) throw new FsErr("failed to create " + (o.s ? 'symbolic' : 'hard') + " link '" + target + "'", 'Permission denied');
    if (p.d.kids.has(p.name)) { if (!o.f) throw new FsErr("failed to create " + (o.s ? 'symbolic' : 'hard') + " link '" + target + "'", 'File exists'); p.d.kids.delete(p.name); }
    if (o.s) p.d.kids.set(p.name, mkNode('l', 0o777, sh.uid, sh.gid, { target: s }));
    else { const n = sh.stat(s); if (n.type === 'd') throw new FsErr(s, 'hard link not allowed for directory'); n.nlink++; p.d.kids.set(p.name, n); }
  }
}, 'ln [-s] TARGET LINK — create a hard link, or a symbolic link with -s');
C('readlink', (a, io, sh) => { const { o, r } = go(a); for (const p of r) { if (o.f || o.e || o.m) { io.out(real(sh, p) + '\n'); continue; } const n = sh.lookup(p, false); if (!n || n.type !== 'l') return 1; io.out(n.target + '\n'); } }, 'readlink [-f] LINK — print where a symlink points; -f resolves the whole chain');
function real(sh, p, d = 0) { const parts = sh.abs(p).split('/').filter(Boolean); let cur = ''; for (let i = 0; i < parts.length; i++) { const n = sh.lookup(cur + '/' + parts[i], false); if (n && n.type === 'l' && d < 20) { const t = n.target[0] === '/' ? n.target : (cur || '') + '/' + n.target; return real(sh, t + (i < parts.length - 1 ? '/' + parts.slice(i + 1).join('/') : ''), d + 1); } cur += '/' + parts[i]; } return cur || '/'; }
C('realpath', (a, io, sh) => { for (const p of go(a).r) { if (!sh.lookup(p)) return io.fail(p + ': ' + sh.err); io.out(real(sh, p) + '\n'); } }, 'realpath PATH — absolute path with symlinks resolved');
C('basename', (a, io) => { const { o, r } = go(a, 's'); if (!r.length) return io.fail('missing operand'); const suf = o.s || (o.a ? '' : r[1]) || ''; for (const p of (o.a || o.s ? r : [r[0]])) { let b = base(p); if (suf && b.endsWith(suf) && b !== suf) b = b.slice(0, -suf.length); io.out(b + '\n'); } }, 'basename PATH [SUFFIX] — strip directory (and optional suffix)');
C('dirname', (a, io) => { for (const p of a) { const t = p.replace(/\/+$/, ''); const i = t.lastIndexOf('/'); io.out((i < 0 ? '.' : i === 0 ? '/' : t.slice(0, i)) + '\n'); } }, 'dirname PATH — strip the last component');
C('mktemp', (a, io, sh) => { const { o, r } = go(a, 'pt'); const rnd = () => Array.from({ length: 10 }, () => 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'[Math.floor(Math.random() * 62)]).join(''); let t = r[0] || 'tmp.XXXXXXXXXX'; if (!t.includes('/')) t = (o.p || '/tmp') + '/' + t; const p = t.replace(/X{3,}$/, m => rnd().slice(0, m.length)); if (o.d) sh.mkdir(p, false, 0o700); else sh.write(p, '').mode = 0o600; io.out(p + '\n'); }, 'mktemp [-d] [TEMPLATE] — safely create a unique temp file (or directory) and print its name');
function parseMode(spec, n, umask) {
  if (/^[0-7]{1,4}$/.test(spec)) return parseInt(spec, 8);
  let mode = n.mode & 0o7777;
  for (const cl of spec.split(',')) {
    const m = /^([ugoa]*)([-+=])([rwxXst]*)$/.exec(cl); if (!m) return null;
    let who = m[1] || 'a'; if (who.includes('a')) who = 'ugo';
    let bits = 0, sp = 0;
    for (const c of m[3]) { if (c === 'r') bits |= 4; else if (c === 'w') bits |= 2; else if (c === 'x' || (c === 'X' && (n.type === 'd' || mode & 0o111))) bits |= 1; else if (c === 's') sp |= (who.includes('u') ? 0o4000 : 0) | (who.includes('g') ? 0o2000 : 0); else if (c === 't') sp |= 0o1000; }
    let mask = 0, full = 0; for (const w of who) { const sh = { u: 6, g: 3, o: 0 }[w]; mask |= bits << sh; full |= 7 << sh; }
    if (!m[1]) mask &= ~umask;
    if (m[2] === '+') mode |= mask | sp; else if (m[2] === '-') mode &= ~(mask | sp); else mode = (mode & ~full & ~(who.includes('u') ? 0o4000 : 0) & ~(who.includes('g') ? 0o2000 : 0)) | mask | sp;
  }
  return mode;
}
function walk(sh, p, fn) { const n = sh.lookup(p, false); if (!n) return; fn(p, n); if (n.type === 'd') for (const k of [...n.kids.keys()].sort()) walk(sh, join(p, k), fn); }
S.walk = walk;
C('chmod', (a, io, sh) => {
  const rec = a.includes('-R') || a.includes('--recursive'); const verbose = a.includes('-v'); a = a.filter(x => !/^(-R|-v|--recursive|-c)$/.test(x));
  if (a.length < 2) return io.fail(a.length ? "missing operand after '" + a[0] + "'" : 'missing operand'); const spec = a[0]; let st = 0;
  for (const f of a.slice(1)) {
    const top = sh.lookup(f); if (!top) { io.err("chmod: cannot access '" + f + "': " + sh.err + '\n'); st = 1; continue; }
    const ap = (p, n) => { if (n.type === 'l') return; if (sh.uid !== 0 && n.uid !== sh.uid) { io.err("chmod: changing permissions of '" + p + "': Operation not permitted\n"); st = 1; return; } const m = parseMode(spec, n, sh.umask); if (m === null) { st = 1; return; } n.mode = m; if (verbose) io.out("mode of '" + p + "' changed to " + m.toString(8).padStart(4, '0') + ' (' + modeStr(n).slice(1) + ')\n'); };
    if (parseMode(spec, top, 0) === null) return io.fail("invalid mode: \u2018" + spec + "\u2019");
    if (rec) walk(sh, f, ap); else ap(f, top);
  }
  return st;
}, 'chmod [-R] MODE FILE... — change permission bits. Octal (644, 2775) or symbolic (u+x, go-w, a=r)');
C('chown chgrp', (a, io, sh, name) => {
  const rec = a.includes('-R'); a = a.filter(x => !/^-[Rvh]$/.test(x)); if (a.length < 2) return io.fail('missing operand'); let [u, g] = name === 'chgrp' ? [undefined, a[0]] : a[0].split(/[:.]/); let st = 0;
  const uid = u ? uidOf(sh, u) : undefined, gid = g ? gidOf(sh, g) : undefined;
  if (u && uid === null) return io.fail("invalid user: \u2018" + a[0] + "\u2019"); if (g && gid === null) return io.fail("invalid group: \u2018" + a[0] + "\u2019");
  for (const f of a.slice(1)) {
    if (!sh.lookup(f)) { io.err(name + ": cannot access '" + f + "': " + sh.err + '\n'); st = 1; continue; }
    const ap = (p, n) => { if (sh.uid !== 0 && (uid !== undefined && uid !== n.uid || n.uid !== sh.uid || (gid !== undefined && !sh.groups.includes(gid)))) { io.err(name + ": changing " + (name === 'chgrp' ? 'group' : 'ownership') + " of '" + p + "': Operation not permitted\n"); st = 1; return; } if (uid !== undefined) n.uid = uid; if (gid !== undefined) n.gid = gid; };
    if (rec) walk(sh, f, ap); else ap(f, sh.lookup(f));
  }
  return st;
}, 'chown [-R] USER[:GROUP] FILE... — change owner (root only). chgrp GROUP FILE changes just the group');
const ftype = n => ({ f: n.data !== undefined && n.data.length === 0 ? 'regular empty file' : 'regular file', d: 'directory', l: 'symbolic link', c: 'character special file' })[n.type];
C('stat', (a, io, sh) => {
  const { o, r } = go(a, 'c', { format: 'c', printf: 'c' }); let st = 0;
  for (const f of r) {
    const n = sh.lookup(f, !!o.L); if (!n) { io.err("stat: cannot statx '" + f + "': " + sh.err + '\n'); st = 1; continue; }
    const d = new Date(n.mtime).toISOString().replace('T', ' ').replace('Z', '000000 +0000');
    if (o.c) { io.out(unesc(o.c).replace(/%([aAUGugsnNihFyYxzf])/g, (m, c) => ({ a: (n.mode & 0o7777).toString(8), A: modeStr(n), U: uname(sh, n.uid), G: gname(sh, n.gid), u: n.uid, g: n.gid, s: sizeOf(n), n: f, N: "'" + f + "'" + (n.type === 'l' ? " -> '" + n.target + "'" : ''), i: n.ino, h: n.nlink, F: ftype(n), y: d, x: d, z: d, Y: Math.floor(n.mtime / 1000), f: n.mode.toString(16) })[c]) + (a.some(x => x.startsWith('--printf')) ? '' : '\n')); continue; }
    io.out('  File: ' + f + (n.type === 'l' ? ' -> ' + n.target : '') + '\n  Size: ' + String(sizeOf(n)).padEnd(10) + '\tBlocks: ' + String(Math.ceil(sizeOf(n) / 4096) * 8).padEnd(10) + ' IO Block: 4096   ' + ftype(n) + '\nDevice: 259,2\tInode: ' + String(n.ino).padEnd(11) + ' Links: ' + n.nlink + '\nAccess: (' + (n.mode & 0o7777).toString(8).padStart(4, '0') + '/' + modeStr(n) + ')  Uid: (' + String(n.uid).padStart(5) + '/' + uname(sh, n.uid).padStart(8) + ')   Gid: (' + String(n.gid).padStart(5) + '/' + gname(sh, n.gid).padStart(8) + ')\nModify: ' + d + '\n');
  }
  return st;
}, "stat [-c FORMAT] FILE — inode details. Formats: %a octal mode, %A rwx mode, %U owner, %G group, %s size, %i inode, %h links, %n name, %F type");
function magic(n) {
  if (n.type === 'd') return 'directory'; if (n.type === 'l') return 'symbolic link to ' + n.target; if (n.type === 'c') return 'character special';
  const d = n.data; if (!d.length) return 'empty';
  if (d.startsWith('\x7fELF')) return 'ELF ' + (d.charCodeAt(4) === 2 ? '64' : '32') + '-bit LSB ' + (d.charCodeAt(16) === 3 ? 'pie executable' : 'executable') + ', ' + ({ 0x3e: 'x86-64', 0x28: 'ARM', 0x5e: 'Tensilica Xtensa', 0xf3: 'UCB RISC-V' }[d.charCodeAt(18)] || 'unknown arch') + ', version 1 (SYSV), dynamically linked, stripped';
  if (d.startsWith('\x1f\x8b')) return 'gzip compressed data, from Unix'; if (d.startsWith('TARSIM\0')) return 'POSIX tar archive (GNU)';
  if (d.startsWith('hsqs')) return 'Squashfs filesystem, little endian, version 4.0'; if (d.startsWith('\x27\x05\x19\x56')) return 'u-boot legacy uImage';
  if (d.charCodeAt(0) === 0xe9 && d.length > 24 && d.charCodeAt(1) < 17) return 'ESP-IDF application image for ESP32, entry address 0x' + [7, 6, 5, 4].map(i => d.charCodeAt(i).toString(16).padStart(2, '0')).join('');
  if (d.startsWith('\x89PNG')) return 'PNG image data'; if (d.startsWith('-----BEGIN')) return 'PEM ' + (/BEGIN ([A-Z ]+)-/.exec(d) || [, 'data'])[1].toLowerCase();
  const m = /^#!\s*(\S+)(?:\s+(\S+))?/.exec(d); if (m) return (/(ba)?sh$/.test(m[1]) || /^(ba)?sh$/.test(m[2] || '') ? 'Bourne-Again shell script' : /python/.test(m[0]) ? 'Python script' : 'a ' + m[1] + ' script') + ', ASCII text executable';
  if (/[\x00-\x08\x0e-\x1f\x7f-\xff]/.test(d.slice(0, 2048))) return 'data';
  if (/^\s*[{[]/.test(d) && (() => { try { JSON.parse(d); return true; } catch (e) { return false; } })()) return 'JSON text data';
  return (/^.*,.*\n.*,/.test(d) && d.split('\n')[0].split(',').length > 2 ? 'CSV text' : 'ASCII text') + (/\r\n/.test(d) ? ', with CRLF line terminators' : '');
}
S.magic = magic;
C('file', (a, io, sh) => { const { o, r } = go(a); let st = 0; for (const f of r) { const n = sh.lookup(f, !!o.L); if (!n) { io.out(f + ': cannot open `' + f + "' (" + sh.err + ')\n'); st = 1; continue; } io.out((o.b ? '' : f + ': ') + magic(n) + '\n'); } return st; }, 'file FILE... — identify a file by its magic bytes, not its name');
C('du', (a, io, sh) => {
  const { o, r } = go(a, 'd', { 'max-depth': 'd', summarize: 's', 'human-readable': 'h', all: 'a', total: 'c' }); const maxd = o.s ? 0 : o.d !== undefined ? +o.d : Infinity; let tot = 0, st = 0;
  const fmt = k => o.h ? human(k * 1024) : (o.b ? k * 1024 : k);
  const rec = (p, n, depth) => { let k = n.type === 'f' ? Math.ceil(n.data.length / 1024 / 4) * 4 : n.type === 'd' ? 4 : 0; if (n.type === 'd') { if (!sh.can(n, 4)) { io.err("du: cannot read directory '" + p + "': Permission denied\n"); st = 1; } else for (const name of [...n.kids.keys()].sort()) k += rec(join(p, name), n.kids.get(name), depth + 1); } if ((n.type === 'd' || o.a || depth === 0) && depth <= maxd) io.out(fmt(k) + '\t' + p + '\n'); return k; };
  for (const p of (r.length ? r : ['.'])) { const n = sh.lookup(p, false); if (!n) { io.err("du: cannot access '" + p + "': " + sh.err + '\n'); st = 1; continue; } tot += rec(p, n, 0); }
  if (o.c) io.out(fmt(tot) + '\ttotal\n'); return st;
}, 'du [-sh] [-d N] [PATH...] — disk usage. -s summary only, -h human units, -d N depth limit');
C('tree', (a, io, sh) => {
  const { o, r } = go(a, 'L'); const maxd = o.L ? +o.L : Infinity; let nd = 0, nf = 0;
  for (const p of (r.length ? r : ['.'])) {
    const n = sh.lookup(p); if (!n) { io.out(p + '  [error opening dir]\n'); continue; } io.out(p + '\n');
    const rec = (n, pre, d) => { if (d >= maxd || n.type !== 'd') return; let es = [...n.kids.entries()].sort((x, y) => x[0] < y[0] ? -1 : 1); if (!o.a) es = es.filter(([k]) => k[0] !== '.'); if (o.d) es = es.filter(([, c]) => c.type === 'd'); es.forEach(([k, c], i) => { const last = i === es.length - 1; io.out(pre + (last ? '`-- ' : '|-- ') + k + (c.type === 'l' ? ' -> ' + c.target : '') + '\n'); if (c.type === 'd') { nd++; rec(c, pre + (last ? '    ' : '|   '), d + 1); } else nf++; }); };
    rec(n, '', 0);
  }
  io.out('\n' + nd + ' directories' + (o.d ? '' : ', ' + nf + ' files') + '\n');
}, 'tree [-L DEPTH] [-a] [-d] [DIR] — draw a directory tree');
C('find', (a, io, sh) => {
  const paths = []; let i = 0; while (i < a.length && !/^[-!(]/.test(a[i])) paths.push(a[i++]); if (!paths.length) paths.push('.');
  const groups = [[]]; let maxd = Infinity, mind = 0, neg = false, action = null, st = 0; const execs = [];
  const add = t => { groups[groups.length - 1].push(neg ? (p, n, d) => !t(p, n, d) : t); neg = false; };
  const globT = (pat, ci) => new RegExp('^(?:' + S.globRe(pat, true) + ')$', ci ? 'i' : '');
  for (; i < a.length; i++) {
    const t = a[i], v = () => { if (a[i + 1] === undefined) throw new Abort("find: missing argument to `" + t + "'"); return a[++i]; };
    switch (t) {
      case '!': case '-not': neg = !neg; break; case '-a': case '-and': case '(': case ')': break; case '-o': case '-or': groups.push([]); break;
      case '-name': case '-iname': { const re = globT(v(), t === '-iname'); add(p => re.test(base(p))); break; }
      case '-path': case '-wholename': { const re = globT(v()); add(p => re.test(p)); break; }
      case '-regex': { const re = new RegExp('^(?:' + S.reConv(v(), true) + ')$'); add(p => re.test(p)); break; }
      case '-type': { const ty = v(); add((p, n) => ty.split(',').includes(n.type)); break; }
      case '-maxdepth': maxd = +v(); break; case '-mindepth': mind = +v(); break;
      case '-size': { const m = /^([+-]?)(\d+)([ckMGb]?)$/.exec(v()); if (!m) throw new Abort('find: invalid -size'); const unit = { c: 1, k: 1024, M: 1048576, G: 1073741824, b: 512, '': 512 }[m[3]]; add((p, n) => { const s = Math.ceil(sizeOf(n) / unit); return m[1] === '+' ? s > +m[2] : m[1] === '-' ? s < +m[2] : s === +m[2]; }); break; }
      case '-perm': { const x = v(), m = parseInt(x.replace(/^[-\/]/, ''), 8); add((p, n) => x[0] === '-' ? (n.mode & m) === m : x[0] === '/' ? (n.mode & m) !== 0 : (n.mode & 0o7777) === m); break; }
      case '-user': { const u = uidOf(sh, v()); add((p, n) => n.uid === u); break; } case '-group': { const g = gidOf(sh, v()); add((p, n) => n.gid === g); break; }
      case '-empty': add((p, n) => n.type === 'f' ? !n.data.length : n.type === 'd' && !n.kids.size); break;
      case '-newer': { const ref = sh.stat(v()); add((p, n) => n.mtime > ref.mtime); break; }
      case '-mtime': case '-mmin': { const x = v(), k = +x.replace(/^[+-]/, ''), unit = t === '-mtime' ? 86400000 : 60000; add((p, n) => { const age = Math.floor((Date.now() - n.mtime) / unit); return x[0] === '+' ? age > k : x[0] === '-' ? age < k : age === k; }); break; }
      case '-links': { const k = +v(); add((p, n) => n.nlink === k); break; }
      case '-executable': add((p, n) => sh.can(n, 1) && !!(n.mode & 0o111)); break; case '-readable': add((p, n) => sh.can(n, 4)); break; case '-writable': add((p, n) => sh.can(n, 2)); break;
      case '-print': action = action || 'print'; break; case '-print0': action = 'print0'; break; case '-delete': action = 'delete'; break; case '-ls': action = 'ls'; break; case '-quit': break; case '-depth': break;
      case '-exec': case '-execdir': case '-ok': { const w = []; i++; while (i < a.length && a[i] !== ';' && !(a[i] === '+' && w[w.length - 1] === '{}')) w.push(a[i++]); if (i >= a.length) throw new Abort("find: missing argument to `-exec'"); execs.push({ w, plus: a[i] === '+' }); action = 'exec'; break; }
      default: throw new Abort("find: unknown predicate `" + t + "'");
    }
  }
  const hits = [];
  const rec = (p, n, d) => {
    if (d >= mind && groups.some(g => g.every(t => t(p, n, d)))) hits.push([p, n]);
    if (n.type === 'd' && d < maxd) { if (!sh.can(n, 4) || !sh.can(n, 1)) { io.err("find: \u2018" + p + "\u2019: Permission denied\n"); st = 1; return; } for (const k of [...n.kids.keys()].sort()) rec(join(p, k), n.kids.get(k), d + 1); }
  };
  for (const p of paths) { const n = sh.lookup(p, false); const n2 = n && n.type === 'l' ? sh.lookup(p) || n : n; if (!n2) { io.err("find: \u2018" + p + "\u2019: " + sh.err + '\n'); st = 1; continue; } rec(p, n2, 0); }
  if (action === 'delete') { for (const [p] of hits.reverse()) { try { sh.unlink(p); } catch (e) { if (!(e instanceof FsErr)) throw e; io.err("find: cannot delete \u2018" + p + "\u2019: " + e.msg + '\n'); st = 1; } } }
  else if (action === 'exec') { for (const ex of execs) { if (ex.plus) { if (hits.length) st = sh.invoke(ex.w.flatMap(x => x === '{}' ? hits.map(h => h[0]) : [x]), io.ctx) || st; } else for (const [p] of hits) st = sh.invoke(ex.w.map(x => x.replace(/\{\}/g, p)), io.ctx) ? 1 : st; } }
  else if (action === 'print0') io.out(hits.map(h => h[0] + '\0').join(''));
  else if (action === 'ls') for (const [p, n] of hits) io.out(String(n.ino).padStart(8) + ' ' + String(Math.ceil(sizeOf(n) / 1024)).padStart(6) + ' ' + modeStr(n) + ' ' + String(n.nlink).padStart(3) + ' ' + uname(sh, n.uid).padEnd(8) + ' ' + gname(sh, n.gid).padEnd(8) + ' ' + String(sizeOf(n)).padStart(8) + ' ' + lsDate(n.mtime) + ' ' + p + '\n');
  else io.out(hits.map(h => h[0] + '\n').join(''));
  return st;
}, "find [PATH...] [TESTS] [ACTION] — walk a tree. Tests: -name 'GLOB' -iname -type f|d|l -size +10k -perm -4000 -user U -newer F -mtime -7 -empty -maxdepth N, ! negates, -o is OR. Actions: -print -print0 -delete -exec CMD {} \\; or {} +");
C('xargs', (a, io, sh) => {
  let n = Infinity, I = null, zero = false, delim = null, trace = false, noEmpty = false; let i = 0;
  for (; i < a.length; i++) { const x = a[i]; if (x === '-n') n = +a[++i]; else if (/^-n\d+$/.test(x)) n = +x.slice(2); else if (x === '-I') I = a[++i]; else if (/^-I.+/.test(x)) I = x.slice(2); else if (x === '-i') I = '{}'; else if (x === '-0' || x === '--null') zero = true; else if (x === '-d') delim = unesc(a[++i]); else if (x === '-t') trace = true; else if (x === '-r' || x === '--no-run-if-empty') noEmpty = true; else if (x === '-P' || x === '-L') { if (x === '-L') { I = I; n = Infinity; delim = '\n'; } i++; } else if (/^-P\d+$/.test(x)) { /* parallelism ignored */ } else break; }
  const cmd = a.slice(i).length ? a.slice(i) : ['echo']; const data = io.stdin();
  let items;
  if (zero) items = data.split('\0'); else if (delim !== null) items = data.split(delim); else if (I) items = data.split('\n').map(s => s.trim());
  else { items = []; data.replace(/"([^"]*)"|'([^']*)'|((?:\\.|[^\s"'\\])+)/g, (m, d, s, w) => { items.push(d !== undefined ? d : s !== undefined ? s : w.replace(/\\(.)/g, '$1')); return ''; }); }
  if (zero || delim !== null || I) { if (items[items.length - 1] === '') items.pop(); if (I) items = items.filter(x => x !== ''); }
  let st = 0; const run = w => { if (trace) io.err(w.join(' ') + '\n'); const s = sh.invoke(w, { in: { s: '', p: 0 }, fd: io.ctx.fd }); if (s) st = s === 127 ? 127 : 123; };
  if (I) { for (const it of items) run(cmd.map(x => x.split(I).join(it))); return st; }
  if (!items.length) { if (!noEmpty && !(zero || delim !== null) ) run(cmd); else if (!noEmpty) run(cmd); return st; }
  for (let k = 0; k < items.length; k += n === Infinity ? items.length : n) run(cmd.concat(items.slice(k, n === Infinity ? undefined : k + n)));
  return st;
}, 'xargs [-n N] [-I {}] [-0] [-r] CMD... — build command lines from stdin. -0 pairs with find -print0 for names with spaces; -I {} runs once per line');

/* ================= text utilities ================= */
C('grep egrep fgrep', (a, io, sh, name) => {
  const { o, r } = go(a, 'eAfBCm', { 'ignore-case': 'i', 'invert-match': 'v', count: 'c', 'line-number': 'n', 'only-matching': 'o', 'extended-regexp': 'E', 'fixed-strings': 'F', 'perl-regexp': 'P', recursive: 'r', 'files-with-matches': 'l', 'word-regexp': 'w', quiet: 'q', 'no-filename': 'h', 'with-filename': 'H', 'line-regexp': 'x', regexp: 'e', 'max-count': 'm', 'files-without-match': 'L', include: 'include' });
  let pat = o.e !== undefined ? o.e : r.shift(); if (pat === undefined) return io.fail('usage: grep [OPTION]... PATTERNS [FILE]...', 2);
  const ere = o.E || name === 'egrep', fixed = o.F || name === 'fgrep';
  let rs = pat.split('\n').map(p => fixed ? reEsc(p) : o.P ? p : S.reConv(p, ere)).join('|');
  if (o.w) rs = '\\b(?:' + rs + ')\\b'; if (o.x) rs = '^(?:' + rs + ')$';
  let re; try { re = new RegExp(rs, (o.i || o.y ? 'i' : '') + 'g'); } catch (e) { return io.fail('Invalid regular expression', 2); }
  let files = r, rec = o.r || o.R; if (rec && !files.length) files = ['.'];
  const list = [];
  for (const f of files) { if (rec) { const n = sh.lookup(f); if (!n) { io.err('grep: ' + f + ': ' + sh.err + '\n'); continue; } walk(sh, f, (p, x) => { if (x.type === 'f' && (!o.include || new RegExp('^(?:' + S.globRe(o.include, true) + ')$').test(base(p)))) list.push(p); }); } else list.push(f); }
  const showName = !o.h && (o.H || list.length > 1 || rec); let any = false, st = 0;
  const A = o.C !== undefined ? +o.C : +(o.A || 0), Bf = o.C !== undefined ? +o.C : +(o.B || 0); const max = o.m !== undefined ? +o.m : Infinity;
  const doFile = (data, f) => {
    const pre = showName ? f + ':' : ''; let cnt = 0;
    if (/\0/.test(data.slice(0, 4096)) && !o.a && !o.c && !o.q && !o.l) { re.lastIndex = 0; if (re.test(data)) { any = true; io.out('Binary file ' + (f === '-' ? '(standard input)' : f) + ' matches\n'); } return; }
    const ls = lines(data); let lastPrinted = -1, after = 0;
    for (let k = 0; k < ls.length && cnt < max; k++) {
      re.lastIndex = 0; const hit = re.test(ls[k]) !== !!o.v;
      if (hit) {
        cnt++; any = true; if (o.q || o.c || o.l || o.L) { if (o.q || o.l) break; continue; }
        if (Bf) for (let b = Math.max(lastPrinted + 1, k - Bf); b < k; b++) { if (lastPrinted >= 0 && b > lastPrinted + 1 && b === Math.max(lastPrinted + 1, k - Bf)) io.out('--\n'); io.out((showName ? f + '-' : '') + (o.n ? (b + 1) + '-' : '') + ls[b] + '\n'); }
        else if ((A) && lastPrinted >= 0 && k > lastPrinted + 1) io.out('--\n');
        if (o.o && !o.v) { re.lastIndex = 0; let m; while ((m = re.exec(ls[k]))) { if (m[0] === '') { re.lastIndex++; continue; } io.out(pre + (o.n ? (k + 1) + ':' : '') + m[0] + '\n'); } }
        else io.out(pre + (o.n ? (k + 1) + ':' : '') + ls[k] + '\n');
        lastPrinted = k; after = A;
      } else if (after > 0) { io.out((showName ? f + '-' : '') + (o.n ? (k + 1) + '-' : '') + ls[k] + '\n'); lastPrinted = k; after--; }
    }
    if (o.c) io.out(pre + cnt + '\n'); if (o.l && cnt) io.out(f + '\n'); if (o.L && !cnt) io.out(f + '\n');
  };
  if (!list.length) doFile(io.stdin(), '(standard input)');
  else for (const f of list) { try { const n = sh.stat(f); if (n.type === 'd') { io.err('grep: ' + f + ': Is a directory\n'); continue; } doFile(sh.read(f), f); } catch (e) { if (!(e instanceof FsErr)) throw e; if (!o.s) io.err('grep: ' + e.path + ': ' + e.msg + '\n'); st = 2; } }
  return any ? 0 : (st || 1);
}, "grep [-ivncolwrEFP] [-A N] [-B N] PATTERN [FILE...] — print lines matching a regex. -E extended, -o only the match, -c count, -v invert, -r recursive, -l file names. Exit 0 if anything matched");
C('sort', (a, io, sh) => {
  const { o, r } = go(a, 'kto', { reverse: 'r', numeric: 'n', unique: 'u', key: 'k', 'field-separator': 't', 'human-numeric-sort': 'h', 'ignore-case': 'f', 'version-sort': 'V' });
  const keys = []; for (let i = 0; i < a.length; i++) { let m; if (a[i] === '-k' || a[i] === '--key') keys.push(a[i + 1]); else if ((m = /^-k(.+)$/.exec(a[i])) || (m = /^--key=(.+)$/.exec(a[i]))) keys.push(m[1]); }
  const ks = keys.map(k => { const m = /^(\d+)(?:\.\d+)?([a-zA-Z]*)(?:,(\d+)(?:\.\d+)?([a-zA-Z]*))?$/.exec(k); if (!m) throw new Abort('sort: invalid key ' + k); const fl = m[2] + (m[4] || ''); return { a: +m[1], b: m[3] ? +m[3] : Infinity, n: fl.includes('n') || (!fl && o.n), h: fl.includes('h') || (!fl && o.h), r: fl.includes('r') || (!fl && o.r), f: fl.includes('f') || o.f, V: fl.includes('V') || (!fl && o.V) }; });
  if (!ks.length) ks.push({ a: 1, b: Infinity, n: o.n, h: o.h, r: o.r, f: o.f, V: o.V, whole: true });
  const hn = s => { const m = /^\s*(-?[\d.]+)([KMGTkmgt]?)/.exec(s); return m ? parseFloat(m[1]) * Math.pow(1024, ' KMGT'.indexOf(m[2].toUpperCase())) : 0; };
  const fields = l => o.t ? l.split(o.t) : (l.match(/\s*\S+/g) || []);
  const key = (l, k) => k.whole ? l : fields(l).slice(k.a - 1, k.b === Infinity ? undefined : k.b).join(o.t || '').replace(/^\s+/, '');
  const vcmp = (x, y) => { const xa = x.split(/(\d+)/), ya = y.split(/(\d+)/); for (let i = 0; i < Math.max(xa.length, ya.length); i++) { const p = xa[i] || '', q = ya[i] || ''; if (p === q) continue; if (i % 2) return +p - +q; return p < q ? -1 : 1; } return 0; };
  const cmp = (x, y) => {
    for (const k of ks) { let p = key(x, k), q = key(y, k), c; if (k.n) c = (parseFloat(p) || 0) - (parseFloat(q) || 0); else if (k.h) c = hn(p) - hn(q); else if (k.V) c = vcmp(p, q); else { if (k.f) { p = p.toUpperCase(); q = q.toUpperCase(); } c = p < q ? -1 : p > q ? 1 : 0; } if (c) return k.r ? -c : c; }
    return 0;
  };
  let ls = lines(src(r, io, sh)); const full = (x, y) => cmp(x, y) || (o.s || o.u ? 0 : (x < y ? -1 : x > y ? 1 : 0) * (o.r ? -1 : 1));
  ls = ls.map((l, i) => [l, i]).sort((x, y) => full(x[0], y[0]) || x[1] - y[1]).map(x => x[0]);
  if (o.u) ls = ls.filter((l, i) => i === 0 || cmp(ls[i - 1], l) !== 0);
  const out = ls.map(l => l + '\n').join(''); if (o.o) sh.write(o.o, out); else io.out(out);
}, 'sort [-nrhuVf] [-t SEP] [-k N[,M]] [FILE] — sort lines. -n numeric, -h human sizes (2K 1G), -r reverse, -u unique, -k field, -t field separator');
C('uniq', (a, io, sh) => {
  const { o, r } = go(a, 'fsw'); const ls = lines(src(r.slice(0, 1), io, sh)); const keyf = l => { let k = l; if (o.f) k = (k.match(/\s*\S+/g) || []).slice(+o.f).join(''); if (o.s) k = k.slice(+o.s); if (o.w) k = k.slice(0, +o.w); return o.i ? k.toLowerCase() : k; };
  const groups = []; for (const l of ls) { const g = groups[groups.length - 1]; if (g && keyf(g[0]) === keyf(l)) g[1]++; else groups.push([l, 1]); }
  io.out(groups.filter(g => o.d ? g[1] > 1 : o.u ? g[1] === 1 : true).map(g => (o.c ? String(g[1]).padStart(7) + ' ' : '') + g[0] + '\n').join(''));
}, 'uniq [-cdui] — collapse ADJACENT duplicate lines (sort first). -c prefix counts, -d only duplicates, -u only uniques');
function ranges(spec) { return spec.split(',').map(s => { const m = /^(\d*)(-?)(\d*)$/.exec(s); if (!m || s === '' || s === '-') throw new Abort('cut: invalid field value'); return [m[1] ? +m[1] : 1, m[2] ? (m[3] ? +m[3] : Infinity) : +m[1]]; }); }
C('cut', (a, io, sh) => {
  const { o, r } = go(a, 'dfcb', { delimiter: 'd', fields: 'f', characters: 'c', 'only-delimited': 's' }); const spec = o.f || o.c || o.b; if (!spec) return io.fail('you must specify a list of bytes, characters, or fields');
  const rg = ranges(spec), d = o.d === undefined ? '\t' : o.d, od = o['output-delimiter'] !== undefined ? o['output-delimiter'] : d; const inR = i => rg.some(([x, y]) => i >= x && i <= y) !== !!o.complement;
  io.out(lines(src(r, io, sh)).map(l => { if (o.f) { if (!l.includes(d)) return o.s ? null : l; return l.split(d).filter((_, i) => inR(i + 1)).join(od); } return [...l].filter((_, i) => inR(i + 1)).join(''); }).filter(x => x !== null).map(l => l + '\n').join(''));
}, 'cut -d SEP -f LIST | -c LIST [FILE] — select fields or character columns. LIST: 1,3 or 2-4 or 3-');
function trSet(s) {
  s = unesc(s).replace(/\[:(\w+):\]/g, (m, n) => ({ upper: 'A-Z', lower: 'a-z', digit: '0-9', alpha: 'a-zA-Z', alnum: 'a-zA-Z0-9', space: ' \t\n\r\f\v', blank: ' \t', punct: '!-/:-@[-`{-~', xdigit: '0-9a-fA-F', cntrl: '\x00-\x1f', print: ' -~' })[n] || '');
  let out = ''; for (let i = 0; i < s.length; i++) { if (s[i + 1] === '-' && i + 2 < s.length) { for (let c = s.charCodeAt(i); c <= s.charCodeAt(i + 2); c++) out += String.fromCharCode(c); i += 2; } else out += s[i]; } return out;
}
C('tr', (a, io) => {
  const { o, r } = go(a); if (!r.length) return io.fail('missing operand'); let s1 = trSet(r[0]); const s2 = r[1] !== undefined ? trSet(r[1]) : ''; const data = io.stdin(); let out = '';
  const comp = o.c || o.C; const in1 = c => s1.includes(c) !== !!comp;
  if (o.d) { for (const c of data) if (!in1(c)) out += c; if (o.s && s2) out = out.replace(new RegExp('([' + [...s2].map(reEsc).join('') + '])\\1+', 'g'), '$1'); }
  else if (r.length < 2) { if (!o.s) return io.fail("missing operand after '" + r[0] + "'"); let prev = ''; for (const c of data) { if (in1(c) && c === prev) continue; out += c; prev = c; } }
  else { let prev = null; for (const c of data) { let t = c; if (in1(c)) { const i = comp ? s2.length - 1 : Math.min(s1.indexOf(c), s2.length - 1); t = s2[i]; if (o.s && t === prev) continue; prev = t; } else prev = null; out += t; } }
  io.out(out);
}, "tr [-dsc] SET1 [SET2] — translate, delete (-d) or squeeze (-s) characters from stdin. Sets: a-z, [:upper:], '\\n'");
C('paste', (a, io, sh) => {
  const { o, r } = go(a, 'd'); const d = o.d !== undefined ? unesc(o.d) : '\t'; const cols = (r.length ? r : ['-']).map(f => f === '-' ? null : lines(sh.read(f))); const stdin = lines(cols.includes(null) ? io.stdin() : ''); let si = 0;
  if (o.s) { io.out(cols.map(c => (c || stdin).join(d[0]) + '\n').join('')); return; }
  const out = []; for (let i = 0; ; i++) { let any = false; const row = cols.map(c => { if (c === null) { if (si < stdin.length) { any = true; return stdin[si++]; } return ''; } if (i < c.length) { any = true; return c[i]; } return ''; }); if (!any) break; out.push(row.map((x, k) => x + (k < row.length - 1 ? d[k % d.length] : '')).join('')); }
  io.out(out.map(l => l + '\n').join(''));
}, 'paste [-d SEP] [-s] FILE... — join files line by line into columns; -s joins all lines of one file');
C('join', (a, io, sh) => {
  const { o, r } = go(a, 't12ajeo'); if (r.length < 2) return io.fail('missing operand'); const f1 = +(o['1'] || o.j || 1) - 1, f2 = +(o['2'] || o.j || 1) - 1; const sp = l => o.t ? l.split(o.t) : l.trim().split(/\s+/); const sep = o.t || ' ';
  const A = lines(r[0] === '-' ? io.stdin() : sh.read(r[0])).map(sp), Bq = lines(r[1] === '-' ? io.stdin() : sh.read(r[1])).map(sp); const out = [];
  for (const x of A) { const ms = Bq.filter(y => y[f2] === x[f1]); for (const y of ms) out.push([x[f1], ...x.filter((_, i) => i !== f1), ...y.filter((_, i) => i !== f2)].join(sep)); if (!ms.length && o.a === '1') out.push(x.join(sep)); }
  if (o.a === '2') for (const y of Bq) if (!A.some(x => x[f1] === y[f2])) out.push(y.join(sep));
  io.out(out.map(l => l + '\n').join(''));
}, 'join [-t SEP] [-1 N] [-2 N] FILE1 FILE2 — relational join of two sorted files on a common field');
C('comm', (a, io, sh) => {
  const { o, r } = go(a); if (r.length < 2) return io.fail('missing operand'); const A = lines(r[0] === '-' ? io.stdin() : sh.read(r[0])), Bq = lines(r[1] === '-' ? io.stdin() : sh.read(r[1])); let i = 0, j = 0; const out = [];
  const emit = (col, s) => { if (o['' + col]) return; let tabs = 0; for (let c = 1; c < col; c++) if (!o['' + c]) tabs++; out.push('\t'.repeat(tabs) + s); };
  while (i < A.length || j < Bq.length) { if (j >= Bq.length || (i < A.length && A[i] < Bq[j])) emit(1, A[i++]); else if (i >= A.length || Bq[j] < A[i]) emit(2, Bq[j++]); else { emit(3, A[i]); i++; j++; } }
  io.out(out.map(l => l + '\n').join(''));
}, 'comm [-123] FILE1 FILE2 — compare two SORTED files: column 1 only in FILE1, 2 only in FILE2, 3 in both. -23 shows lines unique to FILE1');
C('column', (a, io, sh) => {
  const { o, r } = go(a, 'sco'); const ls = lines(src(r, io, sh)); if (!o.t) { io.out(ls.map(l => l + '\n').join('')); return; }
  const rows = ls.filter(l => l.trim() !== '').map(l => o.s ? l.split(new RegExp('[' + reEsc(o.s) + ']')) : l.trim().split(/\s+/)); const w = []; rows.forEach(rw => rw.forEach((c, i) => { w[i] = Math.max(w[i] || 0, c.length); }));
  io.out(rows.map(rw => rw.map((c, i) => i === rw.length - 1 ? c : c.padEnd(w[i])).join(o.o !== undefined ? o.o : '  ') + '\n').join(''));
}, 'column -t [-s SEP] — align input into a table');
C('nl', (a, io, sh) => { const { o, r } = go(a, 'bw'); let n = 1; io.out(lines(src(r, io, sh)).map(l => (l === '' && o.b !== 'a' ? '       ' : String(n++).padStart(6) + '\t') + l + '\n').join('')); }, 'nl [-ba] — number lines');
C('seq', (a, io) => { const { o, r } = go(a.filter(x => !/^-\d/.test(x)).concat(), 'sf'); const nums = a.filter(x => /^-?[\d.]+$/.test(x)).map(Number); let [f, inc, l] = nums.length === 1 ? [1, 1, nums[0]] : nums.length === 2 ? [nums[0], 1, nums[1]] : nums; if (l === undefined) return io.fail('missing operand'); const out = []; const w = o.w ? Math.max(('' + f).length, ('' + l).length) : 0; for (let x = f; inc > 0 ? x <= l : x >= l; x += inc) { if (out.length > 100000 || !inc) break; let s = o.f ? sprintf(o.f, [x]) : S.fmtNum(Number(x.toFixed(10))); if (w) s = s.padStart(w, '0'); out.push(s); } io.out(out.join(o.s !== undefined ? unesc(o.s) : '\n') + (out.length ? '\n' : '')); }, 'seq [FIRST [STEP]] LAST — print a sequence of numbers. -w pads with zeros, -s SEP');
C('yes', (a, io) => { io.out(((a.join(' ') || 'y') + '\n').repeat(2000)); }, 'yes [STRING] — print STRING forever (the sandbox stops after 2000 lines)');
C('sleep', (a, io) => { if (!a.length) return io.fail('missing operand'); }, 'sleep SECONDS — wait (instant in the sandbox; with & it becomes a background job you can practise on)');
C('date', (a, io) => {
  const { r } = go(a, 'dr'); const d = new Date(); const f = r.find(x => x[0] === '+');
  const out = (f ? f.slice(1) : '%a %b %e %H:%M:%S %Z %Y').replace(/%([a-zA-Z%])/g, (m, c) => ({ Y: d.getUTCFullYear(), m: p2(d.getUTCMonth() + 1), d: p2(d.getUTCDate()), e: String(d.getUTCDate()).padStart(2), H: p2(d.getUTCHours()), M: p2(d.getUTCMinutes()), S: p2(d.getUTCSeconds()), F: d.toISOString().slice(0, 10), T: d.toISOString().slice(11, 19), s: Math.floor(d / 1000), a: DAY[d.getUTCDay()], b: MON[d.getUTCMonth()], Z: 'UTC', z: '+0000', y: p2(d.getUTCFullYear() % 100), j: String(Math.floor((d - Date.UTC(d.getUTCFullYear(), 0, 0)) / 864e5)).padStart(3, '0'), N: String(d.getUTCMilliseconds()).padStart(3, '0') + '000000', u: d.getUTCDay() || 7, R: d.toISOString().slice(11, 16), n: '\n', t: '\t', '%': '%' })[c] ?? m);
  io.out(out + '\n');
}, "date [+FORMAT] — current time. `date +%F` is 2026-11-10 style, `date +%s` is epoch seconds, `date +%Y%m%d-%H%M%S` makes a good file-name stamp");
C('whoami', (a, io, sh) => io.out(uname(sh, sh.uid) + '\n'), 'whoami — effective user name');
C('id', (a, io, sh) => {
  const { o, r } = go(a); let uid = sh.uid, gid = sh.gid, groups = sh.groups;
  if (r[0]) { uid = uidOf(sh, r[0]); if (uid === null || sh.users[uid] === undefined) return io.fail("\u2018" + r[0] + "\u2019: no such user"); const g = (sh.world.userGroups || {})[r[0]] || [uid]; gid = g[0]; groups = uid === 1000 ? (sh.world.opGroups || g) : g; }
  if (o.u) { io.out((o.n ? uname(sh, uid) : uid) + '\n'); return; } if (o.g) { io.out((o.n ? gname(sh, gid) : gid) + '\n'); return; } if (o.G) { io.out(groups.map(g => o.n ? gname(sh, g) : g).join(' ') + '\n'); return; }
  io.out('uid=' + uid + '(' + uname(sh, uid) + ') gid=' + gid + '(' + gname(sh, gid) + ') groups=' + groups.map(g => g + '(' + gname(sh, g) + ')').join(',') + '\n');
}, 'id [USER] — numeric and named user, group and supplementary groups');
C('groups', (a, io, sh) => io.out((a[0] && a[0] !== uname(sh, sh.uid) ? ((sh.world.userGroups || {})[a[0]] || []) : sh.groups).map(g => gname(sh, g)).join(' ') + '\n'), 'groups [USER] — group memberships');
C('hostname', (a, io, sh) => io.out(sh.read('/etc/hostname')), 'hostname — the machine name');
C('uname', (a, io) => { const { o } = go(a); const f = { s: 'Linux', n: 'bench', r: '6.17.7-arch1-1', v: '#1 SMP PREEMPT_DYNAMIC Sun, 02 Nov 2026 17:01:33 +0000', m: 'x86_64', o: 'GNU/Linux' }; if (o.a) { io.out([f.s, f.n, f.r, f.v, f.m, f.o].join(' ') + '\n'); return; } const sel = 'snrvmo'.split('').filter(k => o[k]); io.out((sel.length ? sel : ['s']).map(k => f[k]).join(' ') + '\n'); }, 'uname [-a|-r|-m] — kernel name, release, architecture');
C('env printenv', (a, io, sh, name) => {
  if (name === 'printenv' && a.length) { let st = 0; for (const k of a) { const v = sh.vars.get(k); if (v && v.x) io.out(v.v + '\n'); else st = 1; } return st; }
  const extra = []; let i = 0; let clear = false; for (; i < a.length; i++) { if (a[i] === '-i') clear = true; else if (a[i] === '-u') i++; else if (/^[A-Za-z_]\w*=/.test(a[i])) extra.push(a[i]); else break; }
  if (i >= a.length) { const e = clear ? {} : sh.env(); for (const x of extra) { const k = x.indexOf('='); e[x.slice(0, k)] = x.slice(k + 1); } io.out(Object.entries(e).map(([k, v]) => k + '=' + v + '\n').join('')); return; }
  return sh.subshell(() => { for (const x of extra) { const k = x.indexOf('='); sh.setv(x.slice(0, k), x.slice(k + 1), true); } return sh.invoke(a.slice(i), io.ctx); });
}, 'env [NAME=VALUE...] [CMD] — print the environment, or run CMD with extra variables');
C('which', (a, io, sh) => { const { o, r } = go(a); let st = 0; for (const n of r) { const hits = (sh.getv('PATH') || '').split(':').filter(d => { const f = d && sh.lookup(d + '/' + n); return f && f.type === 'f' && (f.mode & 0o111); }).map(d => d + '/' + n); if (!hits.length) { io.err('which: no ' + n + ' in (' + (sh.getv('PATH') || '') + ')\n'); st = 1; } else io.out((o.a ? hits : hits.slice(0, 1)).join('\n') + '\n'); } return st; }, 'which NAME — first matching executable in $PATH (does not know about builtins or aliases; `type` does)');
C('man', (a, io) => { const n = a.filter(x => !/^(-|\d$)/.test(x))[0]; if (!n) { io.err('What manual page do you want?\nFor example, try \'man man\'.\n'); return 1; } if (n === 'man') { io.out('man [SECTION] NAME — manual pages. Sections: 1 commands, 2 syscalls, 3 library, 4 devices, 5 file formats, 7 overviews, 8 admin. `man -k WORD` searches.\n'); return; } if (a.includes('-k')) { const hits = Object.entries(MAN).filter(([k, v]) => (k + v).toLowerCase().includes(n.toLowerCase())); io.out(hits.map(([k, v]) => k.padEnd(12) + '- ' + v.split(' — ')[1] + '\n').join('') || n + ': nothing appropriate.\n'); return hits.length ? 0 : 16; } if (!MAN[n]) { io.err('No manual entry for ' + n + '\n'); return 16; } io.out(n.toUpperCase() + '(1)  sandbox summary\n\n    ' + MAN[n] + '\n\n(The real page is much longer: run `man ' + n + '` on your own machine.)\n'); }, 'man NAME — read the manual');
C('clear reset', (a, io, sh) => { sh.uiClear = true; }, 'clear — clear the terminal (Ctrl-L does the same)');
C('edit nano vim vi nvim', (a, io, sh, name) => {
  const f = a.filter(x => x[0] !== '-' && x[0] !== '+')[0]; if (!f) return io.fail('sandbox editor needs a file name: ' + name + ' FILE');
  const n = sh.lookup(f); if (n && n.type === 'd') return io.fail(f + ': Is a directory'); if (n && !sh.can(n, 4)) return io.fail(f + ': Permission denied');
  if (!n) { const p = sh.parentOf(f); if (!sh.can(p.d, 2)) return io.fail(f + ': Permission denied'); } else if (!sh.can(n, 2)) io.err('(warning: ' + f + ' is read-only for you; saving will fail without sudo)\n');
  sh.uiEdit = { path: sh.abs(f), data: n ? n.data : '', uid: sh.uid, gid: sh.gid, groups: sh.groups.slice() };
  if (!sh.ui) io.err('(sandbox: editor opens in the page UI)\n');
}, 'edit FILE — open the sandbox editor (nano, vi and vim are aliases for it here)');
C('sudo', (a, io, sh) => {
  let i = 0, user = 'root'; while (i < a.length && a[i][0] === '-') { if (a[i] === '-u') user = a[++i]; else if (a[i] === '-l') { io.out('User op may run the following commands on bench:\n    (ALL : ALL) ALL\n'); return; } else if (a[i] === '-v' || a[i] === '-k') return 0; i++; }
  if (sh.uid !== 0 && !sh.groups.includes(998)) { io.err(uname(sh, sh.uid) + ' is not in the sudoers file.\n'); return 1; }
  if (i >= a.length) { io.err('usage: sudo [-u user] command\n'); return 1; }
  const uid = uidOf(sh, user); if (uid === null) { io.err('sudo: unknown user ' + user + '\n'); return 1; }
  const sv = { uid: sh.uid, gid: sh.gid, groups: sh.groups }; sh.uid = uid; sh.gid = uid; sh.groups = uid === 0 ? [0] : ((sh.world.userGroups || {})[user] || [uid]);
  sh.world.sudoUsed = (sh.world.sudoUsed || 0) + 1;
  try { return sh.invoke(a.slice(i), io.ctx, true); } finally { if (sh.world.groupsChanged) { sv.groups = sh.world.groupsChanged; delete sh.world.groupsChanged; } Object.assign(sh, sv); }
}, 'sudo [-u USER] CMD — run one command as root. Redirections are still opened by YOUR shell: use `cmd | sudo tee FILE` to write as root');
C('nohup nice ionice stdbuf setsid', (a, io, sh, name) => { let i = 0; while (i < a.length && (a[i][0] === '-' || (name !== 'nohup' && /^\d+$/.test(a[i]) && a[i - 1] === '-n'))) i++; if (i >= a.length) return name === 'nice' ? (io.out('0\n'), 0) : io.fail('missing operand'); return sh.invoke(a.slice(i), io.ctx); }, 'nohup CMD & — keep CMD running after the terminal closes (ignores SIGHUP). nice -n N CMD lowers CPU priority');
C('watch', (a, io, sh) => { let i = 0; while (i < a.length && a[i][0] === '-') { if (a[i] === '-n') i++; i++; } io.out('Every 2.0s: ' + a.slice(i).join(' ') + '\n\n'); const st = sh.execSrc(a.slice(i).join(' '), io.ctx); io.err('(sandbox: watch would repeat this until Ctrl-C)\n'); return st; }, 'watch [-n SECS] CMD — rerun CMD periodically and show the latest output');
C('timeout', (a, io, sh) => { let i = 0; while (i < a.length && a[i][0] === '-') { if (a[i] === '-s' || a[i] === '-k') i++; i++; } return sh.invoke(a.slice(i + 1), io.ctx); }, 'timeout DURATION CMD — kill CMD if it runs longer than DURATION (exit status 124)');
C('bash sh dash', (a, io, sh, name) => {
  const opt = {}; let i = 0; while (i < a.length && /^[-+]/.test(a[i]) && a[i] !== '-c') { if (a[i] === '-o') { opt[a[++i]] = true; } else for (const c of a[i].slice(1)) opt[c] = true; i++; }
  const pre = (opt.e ? 'set -e\n' : '') + (opt.u ? 'set -u\n' : '') + (opt.x ? 'set -x\n' : '') + (opt.pipefail ? 'set -o pipefail\n' : '');
  if (a[i] === '-c') { if (a[i + 1] === undefined) return io.fail('-c: option requires an argument', 2); return sh.runScript(pre + a[i + 1], a.slice(i + 3), a[i + 2] || name, io.ctx); }
  if (a[i] === undefined) { const d = io.stdin(); if (d) return sh.runScript(pre + d, [], name, io.ctx); io.err('(sandbox: you are already in bash; nested interactive shells are not simulated)\n'); return 0; }
  if (opt.n) { try { S.parse(sh.read(a[i])); return 0; } catch (e) { if (e instanceof FsErr) throw e; io.err(a[i] + ': ' + (e.message || 'syntax error: unexpected end of file') + '\n'); return 2; } }
  const n = sh.lookup(a[i]); if (!n) { io.err(name + ': ' + a[i] + ': No such file or directory\n'); return 127; }
  return sh.runScript(pre + sh.read(a[i]), a.slice(i + 1), a[i], io.ctx);
}, 'bash [-eux] [-c STRING | FILE] [ARGS] — run a script in a child shell. -n only checks syntax, -x traces every command');

/* ---------- sed ---------- */
C('sed', (a, io, sh) => {
  let quiet = false, ere = false, inplace = null; const scripts = [], files = [];
  for (let i = 0; i < a.length; i++) { const x = a[i]; if (x === '-n' || x === '--quiet') quiet = true; else if (x === '-E' || x === '-r' || x === '--regexp-extended') ere = true; else if (x === '-e') scripts.push(a[++i]); else if (/^-i/.test(x) || /^--in-place/.test(x)) inplace = x.replace(/^(-i|--in-place=?)/, ''); else if (x === '-s' || x === '--posix' || x === '-u') { /* ignore */ } else if (/^-[nEr]+$/.test(x)) { if (x.includes('n')) quiet = true; if (/[Er]/.test(x)) ere = true; } else if (!scripts.length && !a.includes('-e')) scripts.push(x); else files.push(x); }
  if (!scripts.length) return io.fail('usage: sed [OPTION]... {script} [input-file]...', 1);
  const prog = [], s = scripts.join('\n'); let p = 0;
  const ws = () => { while (p < s.length && /[ \t]/.test(s[p])) p++; };
  const delimited = d => { let out = ''; while (p < s.length && s[p] !== d) { if (s[p] === '\\' && p + 1 < s.length) { if (s[p + 1] === d) { out += d; p += 2; continue; } if (s[p + 1] === 'n' ) { out += '\\n'; p += 2; continue; } out += s[p] + s[p + 1]; p += 2; continue; } out += s[p++]; } if (p >= s.length) throw new Abort("sed: -e expression #1, char " + p + ": unterminated `s' command"); p++; return out; };
  const addr = () => { ws(); if (/\d/.test(s[p])) { let n = ''; while (/\d/.test(s[p])) n += s[p++]; if (s[p] === '~') { p++; let st = ''; while (/\d/.test(s[p])) st += s[p++]; return { step: [+n, +st] }; } return { n: +n }; } if (s[p] === '$') { p++; return { last: true }; } if (s[p] === '/') { p++; const re = delimited('/'); let fl = ''; if (s[p] === 'I') { fl = 'i'; p++; } return { re: mkRe(re, ere, fl) }; } if (s[p] === '\\') { const d = s[p + 1]; p += 2; return { re: mkRe(delimited(d), ere) }; } return null; };
  const parseCmds = stop => {
    const out = [];
    for (;;) {
      while (p < s.length && /[\s;]/.test(s[p])) p++; if (p >= s.length) break; if (s[p] === '}') { if (stop) { p++; return out; } throw new Abort("sed: unexpected `}'"); } if (s[p] === '#') { while (p < s.length && s[p] !== '\n') p++; continue; }
      const c = { a1: addr() }; if (c.a1) { ws(); if (s[p] === ',') { p++; ws(); if (s[p] === '+') { p++; let n = ''; while (/\d/.test(s[p])) n += s[p++]; c.a2 = { plus: +n }; } else c.a2 = addr(); } } ws(); if (s[p] === '!') { c.neg = true; p++; ws(); }
      c.c = s[p++];
      switch (c.c) {
        case '{': c.block = parseCmds(true); break;
        case 's': { const d = s[p++]; const re = delimited(d); let rep = ''; while (p < s.length && s[p] !== d) { if (s[p] === '\\' && p + 1 < s.length) { rep += s[p] + s[p + 1]; p += 2; continue; } rep += s[p++]; } if (p >= s.length) throw new Abort("sed: -e expression #1, char " + p + ": unterminated `s' command"); p++; let fl = ''; while (p < s.length && /[gpiIme0-9]/.test(s[p])) fl += s[p++]; if (s[p] === 'w') { while (p < s.length && s[p] !== '\n') p++; } c.re = mkRe(re, ere, (/[iI]/.test(fl) ? 'i' : '') + (fl.includes('g') ? 'g' : '')); c.g = fl.includes('g'); c.p = fl.includes('p'); c.nth = +(/\d+/.exec(fl) || [0])[0]; c.rep = rep; break; }
        case 'y': { const d = s[p++]; const x = unesc(delimited(d)), y = unesc(delimited(d)); c.map = [x, y]; break; }
        case 'a': case 'i': case 'c': { if (s[p] === '\\') p++; ws(); if (s[p] === '\n') p++; let t = ''; while (p < s.length && s[p] !== '\n') { if (s[p] === '\\' && s[p + 1] === '\n') { t += '\n'; p += 2; continue; } t += s[p++]; } c.text = t.replace(/\\n/g, '\n').replace(/\\t/g, '\t'); break; }
        case 'q': case 'Q': { ws(); let n = ''; while (/\d/.test(s[p] || '')) n += s[p++]; c.code = +n || 0; break; }
        case 'r': case 'w': { ws(); let f = ''; while (p < s.length && s[p] !== '\n') f += s[p++]; c.file = f; break; }
        case 'p': case 'd': case '=': case 'n': case 'N': case 'D': case 'P': case 'h': case 'H': case 'g': case 'G': case 'x': case 'l': break;
        case 'b': case 't': { ws(); while (p < s.length && !/[;\n}]/.test(s[p])) p++; c.c = 'b-end'; break; }
        default: throw new Abort("sed: -e expression #1, char " + p + ": unknown command: `" + c.c + "'");
      }
      out.push(c);
    }
    if (stop) throw new Abort("sed: unmatched `{'");
    return out;
  };
  prog.push(...parseCmds(false));
  const rep = (r, m) => { let out = ''; for (let i = 0; i < r.length; i++) { const c = r[i]; if (c === '\\' && i + 1 < r.length) { const n = r[++i]; if (/\d/.test(n)) out += m[+n] === undefined ? '' : m[+n]; else if (n === 'n') out += '\n'; else if (n === 't') out += '\t'; else out += n; } else if (c === '&') out += m[0]; else out += c; } return out; };
  const runOn = (data) => {
    const ls = lines(data); const out = []; let quit = false, hold = ''; const flat = []; const number = cs => cs.forEach(c => { c.id = flat.length; flat.push(c); if (c.block) number(c.block); }); number(prog); const act = flat.map(() => 0);
    const match = (ad, ps, i) => ad.n !== undefined ? i + 1 === ad.n : ad.last ? i === ls.length - 1 : ad.step ? (ad.step[1] ? (i + 1 >= ad.step[0] && (i + 1 - ad.step[0]) % ad.step[1] === 0) : i + 1 === ad.step[0]) : (ad.re.lastIndex = 0, ad.re.test(ps));
    for (let i = 0; i < ls.length && !quit; i++) {
      let ps = ls[i], del = false; const post = [];
      const exec = cs => {
        for (const c of cs) {
          if (del || quit) return; let sel = true;
          if (c.a1) {
            if (c.a2) { if (act[c.id]) { sel = true; if (c.a2.plus !== undefined ? i >= act[c.id] - 1 + c.a2.plus : c.a2.n !== undefined ? i + 1 >= c.a2.n : match(c.a2, ps, i)) act[c.id] = 0; } else if (match(c.a1, ps, i)) { sel = true; act[c.id] = i + 1; if (c.a2.n !== undefined && c.a2.n <= i + 1) act[c.id] = 0; if (c.a2.plus === 0) act[c.id] = 0; } else sel = false; }
            else sel = match(c.a1, ps, i);
          }
          if (sel === !!c.neg) continue;
          switch (c.c) {
            case '{': exec(c.block); break;
            case 's': { let k = 0, did = false; c.re.lastIndex = 0; const src2 = ps; if (c.g || c.nth) { const re = new RegExp(c.re.source, c.re.flags.includes('g') ? c.re.flags : c.re.flags + 'g'); ps = src2.replace(re, (...m) => { k++; if (c.nth && (c.g ? k < c.nth : k !== c.nth)) return m[0]; did = true; return rep(c.rep, m); }); } else { const m = c.re.exec(src2); if (m) { did = true; ps = src2.slice(0, m.index) + rep(c.rep, m) + src2.slice(m.index + m[0].length); } } if (did && c.p) out.push(ps); break; }
            case 'y': ps = [...ps].map(ch => { const k = c.map[0].indexOf(ch); return k < 0 ? ch : c.map[1][k]; }).join(''); break;
            case 'p': out.push(ps); break; case 'P': out.push(ps.split('\n')[0]); break;
            case 'd': del = true; break;
            case '=': out.push('' + (i + 1)); break;
            case 'a': post.push(c.text); break; case 'i': out.push(c.text); break;
            case 'c': if (!c.a2 || !act[c.id]) out.push(c.text); del = true; break;
            case 'q': quit = true; break; case 'Q': quit = true; del = true; break;
            case 'n': if (!quiet) out.push(ps); if (i + 1 < ls.length) ps = ls[++i]; else { del = true; quit = true; } break;
            case 'N': if (i + 1 < ls.length) ps += '\n' + ls[++i]; else { quit = true; } break;
            case 'D': if (ps.includes('\n')) { ps = ps.slice(ps.indexOf('\n') + 1); } del = true; break;
            case 'h': hold = ps; break; case 'H': hold += '\n' + ps; break; case 'g': ps = hold; break; case 'G': ps += '\n' + hold; break; case 'x': { const t = ps; ps = hold; hold = t; break; }
            case 'l': out.push(ps.replace(/\t/g, '\\t') + '$'); break;
            case 'r': try { post.push(sh.read(c.file).replace(/\n$/, '')); } catch (e) { /* ignore */ } break;
            case 'w': sh.write(c.file, ps + '\n', true); break;
          }
        }
      };
      exec(prog);
      if (!del && !quiet) out.push(ps); out.push(...post);
    }
    return out.map(l => l + '\n').join('');
  };
  if (inplace !== null) { if (!files.length) return io.fail('no input files'); for (const f of files) { const d = sh.read(f); if (inplace) sh.write(f + inplace, d); sh.write(f, runOn(d)); } return 0; }
  io.out(runOn(src(files, io, sh)));
}, "sed [-n] [-E] [-i[SUFFIX]] 'SCRIPT' [FILE] — stream editor. s/RE/REP/g substitute, Np print line N, /RE/d delete, A,B ranges, -n with p prints only selected lines, -i edits the file in place");

/* ---------- binary tools ---------- */
const hex2 = c => c.toString(16).padStart(2, '0'); const pr = c => c >= 32 && c < 127 ? String.fromCharCode(c) : '.';
const num = v => /^0x/i.test(v) ? parseInt(v, 16) : parseInt(v, 10);
C('xxd', (a, io, sh) => {
  const { o, r } = go(a, 'lsc g'.replace(' ', '')); let d = src(r.slice(0, 1), io, sh);
  if (o.r) { const bytes = o.p ? d.replace(/\s+/g, '') : lines(d).map(l => l.replace(/^[0-9a-f]+:\s*/i, '').split('  ')[0].replace(/\s+/g, '')).join(''); let out = ''; for (let i = 0; i + 1 < bytes.length; i += 2) out += String.fromCharCode(parseInt(bytes.substr(i, 2), 16)); if (r[1]) sh.write(r[1], out); else io.out(out); return; }
  const skip = o.s ? num(o.s) : 0, len = o.l !== undefined ? num(o.l) : Infinity, cols = o.c ? num(o.c) : (o.p ? 30 : o.b ? 6 : 16), grp = o.g !== undefined ? num(o.g) : (o.b ? 1 : 2);
  d = d.slice(skip < 0 ? d.length + skip : skip); if (len !== Infinity) d = d.slice(0, len); const off0 = skip < 0 ? 0 : skip; let out = '';
  if (o.p) { for (let i = 0; i < d.length; i += cols) out += [...d.slice(i, i + cols)].map(c => hex2(c.charCodeAt(0))).join('') + '\n'; io.out(out); return; }
  if (o.i) { out = 'unsigned char ' + (r[0] || 'stdin').replace(/\W/g, '_') + '[] = {\n'; for (let i = 0; i < d.length; i += 12) out += '  ' + [...d.slice(i, i + 12)].map(c => '0x' + hex2(c.charCodeAt(0))).join(', ') + (i + 12 < d.length ? ',' : '') + '\n'; io.out(out + '};\nunsigned int ' + (r[0] || 'stdin').replace(/\W/g, '_') + '_len = ' + d.length + ';\n'); return; }
  for (let i = 0; i < d.length; i += cols) { const ch = [...d.slice(i, i + cols)].map(c => c.charCodeAt(0)); let hx = ''; ch.forEach((c, k) => { hx += (o.b ? c.toString(2).padStart(8, '0') : (o.u ? hex2(c).toUpperCase() : hex2(c))) + ((grp && (k + 1) % grp === 0) ? ' ' : ''); }); const full = cols * (o.b ? 8 : 2) + (grp ? Math.ceil(cols / grp) : 0); out += (off0 + i).toString(16).padStart(8, '0') + ': ' + hx.padEnd(full) + ' ' + ch.map(pr).join('') + '\n'; }
  io.out(out);
}, 'xxd [-l LEN] [-s OFFSET] [-c COLS] [-p] [-r] [FILE] — hex dump. -p plain hex, -r reverse (hex back to binary), -i C array. Offsets accept 0x');
C('hexdump hd', (a, io, sh, name) => {
  const { o, r } = go(a, 'nse'); let d = src(r, io, sh); const skip = o.s ? num(o.s) : 0; d = d.slice(skip); if (o.n !== undefined) d = d.slice(0, num(o.n)); let out = '', prev = null, star = false;
  const canon = o.C || name === 'hd';
  for (let i = 0; i < d.length; i += 16) {
    const chunk = d.slice(i, i + 16); if (chunk === prev && chunk.length === 16 && !o.v) { if (!star) { out += '*\n'; star = true; } continue; } prev = chunk; star = false; const ch = [...chunk].map(c => c.charCodeAt(0));
    if (canon) out += (skip + i).toString(16).padStart(8, '0') + '  ' + (ch.slice(0, 8).map(hex2).join(' ').padEnd(23) + '  ' + ch.slice(8).map(hex2).join(' ')).padEnd(48) + '  |' + ch.map(pr).join('') + '|\n';
    else { let w = ''; for (let k = 0; k < ch.length; k += 2) w += ' ' + hex2(ch[k + 1] || 0) + hex2(ch[k]); out += (skip + i).toString(16).padStart(7, '0') + w + '\n'; }
  }
  io.out(out + (skip + d.length).toString(16).padStart(canon ? 8 : 7, '0') + '\n');
}, 'hexdump [-C] [-n LEN] [-s OFFSET] [FILE] — hex dump. -C is the canonical hex+ASCII view; without it you get 16-bit little-endian words (bytes look swapped)');
C('strings', (a, io, sh) => { const { o, r } = go(a, 'nt'); const min = +(o.n || a.map(x => /^-(\d+)$/.exec(x)).filter(Boolean).map(m => m[1])[0] || 4); return each(r.filter(x => !/^-\d+$/.test(x)), io, sh, 'strings', d => { const re = new RegExp('[\\x20-\\x7e\\t]{' + min + ',}', 'g'); let m, out = ''; while ((m = re.exec(d))) out += (o.t ? (o.t === 'x' ? m.index.toString(16) : '' + m.index).padStart(7) + ' ' : '') + m[0] + '\n'; io.out(out); }); }, 'strings [-n MIN] [-t x] FILE — printable character runs in a binary (default 4+). -t x prefixes the hex offset');
C('base64', (a, io, sh) => { const { o, r } = go(a, 'w'); const d = src(r, io, sh); if (o.d || o.D || o.decode) { try { io.out(atob(d.replace(/\s+/g, ''))); } catch (e) { return io.fail('invalid input'); } } else { const b = btoa(d), w = o.w !== undefined ? +o.w : 76; io.out((w ? (b.match(new RegExp('.{1,' + w + '}', 'g')) || []).join('\n') : b) + (w || b ? '\n' : '')); } }, 'base64 [-d] [FILE] — encode to (or -d decode from) base64');
function sha256(s) {
  const K = [], H = []; let n = 2, c = 0; const frac = x => ((x - Math.floor(x)) * 4294967296) | 0;
  for (; c < 64; n++) { let p = true; for (let i = 2; i * i <= n; i++) if (n % i === 0) { p = false; break; } if (p) { if (c < 8) H[c] = frac(Math.pow(n, 0.5)); K[c++] = frac(Math.pow(n, 1 / 3)); } }
  const b = [...s].map(ch => ch.charCodeAt(0) & 255), l = b.length; b.push(0x80); while (b.length % 64 !== 56) b.push(0); const bits = l * 8; b.push(0, 0, 0, Math.floor(bits / 4294967296) & 255, (bits >>> 24) & 255, (bits >>> 16) & 255, (bits >>> 8) & 255, bits & 255);
  const rr = (x, k) => (x >>> k) | (x << (32 - k)); const w = new Array(64);
  for (let i = 0; i < b.length; i += 64) {
    for (let t = 0; t < 16; t++) w[t] = (b[i + 4 * t] << 24) | (b[i + 4 * t + 1] << 16) | (b[i + 4 * t + 2] << 8) | b[i + 4 * t + 3];
    for (let t = 16; t < 64; t++) { const s0 = rr(w[t - 15], 7) ^ rr(w[t - 15], 18) ^ (w[t - 15] >>> 3), s1 = rr(w[t - 2], 17) ^ rr(w[t - 2], 19) ^ (w[t - 2] >>> 10); w[t] = (w[t - 16] + s0 + w[t - 7] + s1) | 0; }
    let [a, bb, cc, d, e, f, g, h] = H;
    for (let t = 0; t < 64; t++) { const S1 = rr(e, 6) ^ rr(e, 11) ^ rr(e, 25), ch = (e & f) ^ (~e & g), t1 = (h + S1 + ch + K[t] + w[t]) | 0, S0 = rr(a, 2) ^ rr(a, 13) ^ rr(a, 22), mj = (a & bb) ^ (a & cc) ^ (bb & cc), t2 = (S0 + mj) | 0; h = g; g = f; f = e; e = (d + t1) | 0; d = cc; cc = bb; bb = a; a = (t1 + t2) | 0; }
    H[0] = (H[0] + a) | 0; H[1] = (H[1] + bb) | 0; H[2] = (H[2] + cc) | 0; H[3] = (H[3] + d) | 0; H[4] = (H[4] + e) | 0; H[5] = (H[5] + f) | 0; H[6] = (H[6] + g) | 0; H[7] = (H[7] + h) | 0;
  }
  return H.map(x => (x >>> 0).toString(16).padStart(8, '0')).join('');
}
S.sha256 = sha256;
C('sha256sum', (a, io, sh) => {
  const { o, r } = go(a);
  if (o.c || o.check) { let bad = 0; for (const f of r) for (const l of lines(sh.read(f))) { const m = /^([0-9a-f]{64})\s+\*?(.+)$/.exec(l); if (!m) continue; let ok = false; try { ok = sha256(sh.read(join(f.includes('/') ? f.replace(/\/[^/]*$/, '') : '.', m[2]).replace(/^\.\//, ''))) === m[1]; } catch (e) { io.err('sha256sum: ' + m[2] + ': No such file or directory\n'); io.out(m[2] + ': FAILED open or read\n'); bad++; continue; } io.out(m[2] + ': ' + (ok ? 'OK' : 'FAILED') + '\n'); if (!ok) bad++; } if (bad) io.err('sha256sum: WARNING: ' + bad + ' computed checksum' + (bad > 1 ? 's' : '') + ' did NOT match\n'); return bad ? 1 : 0; }
  return each(r, io, sh, 'sha256sum', (d, f) => io.out(sha256(d) + '  ' + f + '\n'));
}, 'sha256sum [FILE...] | sha256sum -c SUMS — compute or verify SHA-256 digests');
C('cmp', (a, io, sh) => {
  const { o, r } = go(a, 'n'); if (r.length < 2) return io.fail('missing operand'); const x = sh.read(r[0]), y = sh.read(r[1]); const n = Math.min(x.length, y.length); let diff = false, out = '';
  for (let i = 0; i < n; i++) if (x[i] !== y[i]) { diff = true; if (o.l) out += String(i + 1).padStart(Math.max(1, ('' + n).length)) + ' ' + x.charCodeAt(i).toString(8).padStart(3) + ' ' + y.charCodeAt(i).toString(8).padStart(3) + '\n'; else { if (!o.s) io.out(r[0] + ' ' + r[1] + ' differ: byte ' + (i + 1) + ', line ' + (x.slice(0, i).split('\n').length) + '\n'); return 1; } }
  io.out(out); if (x.length !== y.length) { if (!o.s) io.err('cmp: EOF on ' + (x.length < y.length ? r[0] : r[1]) + ' after byte ' + n + '\n'); return 1; } return diff ? 1 : 0;
}, 'cmp [-l] FILE1 FILE2 — compare byte by byte. Default: first difference. -l: every differing byte as OFFSET(decimal, 1-based) and the two byte values in octal');
C('diff', (a, io, sh) => {
  const { o, r } = go(a, 'U'); if (r.length < 2) return io.fail('missing operand'); const rd = f => f === '-' ? io.stdin() : sh.read(f); const A = lines(rd(r[0])), Bq = lines(rd(r[1])); const n = A.length, m = Bq.length;
  if (o.q) { if (A.join('\n') !== Bq.join('\n')) { io.out('Files ' + r[0] + ' and ' + r[1] + ' differ\n'); return 1; } return 0; }
  const L = Array.from({ length: n + 1 }, () => new Int32Array(m + 1)); for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = A[i] === Bq[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const ops = []; let i = 0, j = 0; while (i < n || j < m) { if (i < n && j < m && A[i] === Bq[j]) { ops.push(['=', i++, j++]); } else if (j < m && (i >= n || L[i][j + 1] >= L[i + 1][j])) ops.push(['+', i, j++]); else ops.push(['-', i++, j]); }
  if (!ops.some(x => x[0] !== '=')) return 0;
  if (o.u || o.U !== undefined) {
    const ctx = o.U !== undefined ? +o.U : 3; let out = '--- ' + r[0] + '\n+++ ' + r[1] + '\n'; let k = 0;
    while (k < ops.length) { while (k < ops.length && ops[k][0] === '=') k++; if (k >= ops.length) break; let s = Math.max(0, k - ctx), e = k, lastChg = k; while (e < ops.length && e - lastChg <= ctx * 2) { if (ops[e][0] !== '=') lastChg = e; e++; } e = Math.min(ops.length, lastChg + ctx + 1); const hunk = ops.slice(s, e); const la = hunk.filter(x => x[0] !== '+').length, lb = hunk.filter(x => x[0] !== '-').length; out += '@@ -' + (la ? hunk[0][1] + 1 : hunk[0][1]) + (la === 1 ? '' : ',' + la) + ' +' + (lb ? hunk[0][2] + 1 : hunk[0][2]) + (lb === 1 ? '' : ',' + lb) + ' @@\n' + hunk.map(x => (x[0] === '=' ? ' ' + A[x[1]] : x[0] === '-' ? '-' + A[x[1]] : '+' + Bq[x[2]]) + '\n').join(''); k = e; }
    io.out(out); return 1;
  }
  let out = '', k = 0; const rg = (s, c) => c === 0 ? '' + s : c === 1 ? '' + (s + 1) : (s + 1) + ',' + (s + c);
  while (k < ops.length) { if (ops[k][0] === '=') { k++; continue; } const st = k; while (k < ops.length && ops[k][0] !== '=') k++; const del = ops.slice(st, k).filter(x => x[0] === '-'), ins = ops.slice(st, k).filter(x => x[0] === '+'); const ai = ops[st][1], bj = ops[st][2]; out += rg(ai, del.length) + (del.length && ins.length ? 'c' : del.length ? 'd' : 'a') + rg(bj, ins.length) + '\n' + del.map(x => '< ' + A[x[1]] + '\n').join('') + (del.length && ins.length ? '---\n' : '') + ins.map(x => '> ' + Bq[x[2]] + '\n').join(''); }
  io.out(out); return 1;
}, 'diff [-u] [-q] FILE1 FILE2 — line differences. -u unified format (what patches and git use). Exit 0 same, 1 different');
C('dd', (a, io, sh) => {
  const o = {}; for (const x of a) { const i = x.indexOf('='); if (i > 0) o[x.slice(0, i)] = x.slice(i + 1); }
  const sz = v => { const m = /^(0x[0-9a-f]+|\d+)([kKMGb]?)(B?)$/i.exec(v); if (!m) throw new Abort("dd: invalid number: \u2018" + v + "\u2019"); return num(m[1]) * ({ k: 1024, K: 1024, M: 1048576, G: 1073741824, b: 512 }[m[2]] || 1); };
  const bs = o.bs ? sz(o.bs) : 512, ibs = o.ibs ? sz(o.ibs) : bs, obs = o.obs ? sz(o.obs) : bs; let d = o.if ? sh.read(o.if) : io.stdin();
  if (o.if && sh.lookup(o.if).type === 'c' && o.count) { const need = sz(o.count) * ibs; while (d.length < need && d.length) d += sh.read(o.if); }
  const flagB = (o.iflag || '').includes('skip_bytes'), flagC = (o.iflag || '').includes('count_bytes');
  if (o.skip) d = d.slice(sz(o.skip) * (flagB ? 1 : ibs)); if (o.count !== undefined) d = d.slice(0, sz(o.count) * (flagC ? 1 : ibs));
  if (o.of) { const seek = o.seek ? sz(o.seek) * obs : 0; if (seek || (o.conv || '').includes('notrunc')) { let old = ''; try { old = sh.read(o.of); } catch (e) { /* new */ } const head = old.slice(0, seek).padEnd(seek, '\0'); sh.write(o.of, head + d + ((o.conv || '').includes('notrunc') ? old.slice(seek + d.length) : '')); } else sh.write(o.of, d); } else io.out(d);
  if (o.status !== 'none') io.err(Math.floor(d.length / ibs) + '+' + (d.length % ibs ? 1 : 0) + ' records in\n' + Math.floor(d.length / obs) + '+' + (d.length % obs ? 1 : 0) + ' records out\n' + d.length + ' bytes copied, 0.000' + (1 + d.length % 9) + ' s\n');
}, 'dd if=IN of=OUT bs=SIZE skip=N count=N [seek=N] [conv=notrunc] [status=none] — copy blocks. skip/count are in units of bs, so bs=1 lets you carve exact byte ranges');
const GZ = '\x1f\x8b\x08\x00'; const xor = d => [...d].map(c => String.fromCharCode(c.charCodeAt(0) ^ 0xa5)).join('');
const gz = d => GZ + String.fromCharCode(d.length & 255, (d.length >> 8) & 255, (d.length >> 16) & 255, 0) + '\x00\x03' + xor(d);
const gunz = d => { if (!d.startsWith('\x1f\x8b')) return null; const n = d.charCodeAt(4) | (d.charCodeAt(5) << 8) | (d.charCodeAt(6) << 16); gunz.trailing = d.length > 10 + n; return xor(d.slice(10, 10 + n)); };
Object.assign(S, { gz, gunz });
C('gzip gunzip zcat', (a, io, sh, name) => {
  const { o, r } = go(a); const dec = name !== 'gzip' || o.d; const toOut = name === 'zcat' || o.c || !r.length; let st = 0;
  for (const f of (r.length ? r : ['-'])) {
    const d = f === '-' ? io.stdin() : sh.read(f); let res;
    if (dec) { res = gunz(d); if (res === null) { io.err('gzip: ' + (f === '-' ? 'stdin' : f) + ': not in gzip format\n'); st = 1; continue; } if (gunz.trailing) { io.err('gzip: ' + (f === '-' ? 'stdin' : f) + ': decompression OK, trailing garbage ignored\n'); st = 2; } } else res = gz(d);
    if (toOut) io.out(res); else { const nf = dec ? f.replace(/\.gz$/, '') : f + '.gz'; if (dec && nf === f) { io.err('gzip: ' + f + ': unknown suffix -- ignored\n'); st = 2; continue; } sh.write(nf, res); if (!o.k) sh.unlink(f); }
  }
  return st;
}, 'gzip [-dkc] FILE / gunzip FILE / zcat FILE — compress, decompress, or decompress to stdout. -k keeps the original, -c writes to stdout');
C('tar', (a, io, sh) => {
  if (a[0] && a[0][0] !== '-') a = ['-' + a[0], ...a.slice(1)]; const { o, r } = go(a, 'fC', { file: 'f', directory: 'C', create: 'c', extract: 'x', list: 't', gzip: 'z', verbose: 'v' });
  const f = o.f; if (!f) return io.fail('Refusing to read archive contents from terminal (missing -f option?)', 2);
  if (o.c) {
    const ents = []; const cwd = sh.cwd; if (o.C) sh.cwd = sh.abs(o.C);
    try { for (const p of r) { if (!sh.lookup(p)) { io.err('tar: ' + p + ': Cannot stat: No such file or directory\n'); continue; } walk(sh, p.replace(/\/$/, ''), (q, n) => { ents.push({ p: q.replace(/^\//, '') + (n.type === 'd' ? '/' : ''), t: n.type, m: n.mode, u: n.uid, g: n.gid, d: n.type === 'f' ? btoa(n.data) : undefined, l: n.target }); if (o.v) io.out(q + (n.type === 'd' ? '/' : '') + '\n'); }); } } finally { sh.cwd = cwd; }
    let d = 'TARSIM\0' + JSON.stringify(ents); if (o.z || /\.t?gz$/.test(f)) d = gz(d); if (f === '-') io.out(d); else sh.write(f, d); return 0;
  }
  let d = f === '-' ? io.stdin() : sh.read(f); if (d.startsWith('\x1f\x8b')) d = gunz(d); if (!d.startsWith('TARSIM\0')) return io.fail('This does not look like a tar archive', 2);
  const ents = JSON.parse(d.slice(7)).filter(e => !r.length || r.some(p => e.p === p || e.p.startsWith(p.replace(/\/?$/, '/'))));
  if (o.t) { io.out(ents.map(e => (o.v ? modeStr({ type: e.t, mode: e.m }) + ' ' + uname(sh, e.u) + '/' + gname(sh, e.g) + ' ' + String(e.d ? atob(e.d).length : 0).padStart(8) + ' ' : '') + e.p + '\n').join('')); return 0; }
  if (o.x) { const dest = o.C || '.'; for (const e of ents) { const p = join(dest, e.p.replace(/\/$/, '')); if (e.t === 'd') sh.mkdir(p, true); else { sh.mkdir(p.replace(/\/[^/]*$/, '') || '.', true); if (e.t === 'l') { const q = sh.parentOf(p); q.d.kids.set(q.name, mkNode('l', 0o777, sh.uid, sh.gid, { target: e.l })); } else sh.write(p, atob(e.d)).mode = e.m; } if (o.v) io.out(e.p + '\n'); } return 0; }
  return io.fail("You must specify one of the '-ctx' options", 2);
}, 'tar -czf OUT.tar.gz PATHS (create) | -xzf FILE [-C DIR] (extract) | -tzf FILE (list) — archives. c/x/t pick the mode, z is gzip, v verbose, f FILE must come last in the flag cluster');
C('jq', (a, io, sh) => {
  const { o, r } = go(a); const filt = r[0] === undefined ? '.' : r[0]; let data; const txt = src(r.slice(1), io, sh);
  try { data = JSON.parse(txt); } catch (e) { return io.fail('error (at <stdin>:0): Cannot parse input as JSON', 2); }
  const step = (vals, f) => {
    f = f.trim(); if (f === '.' || f === '') return vals; if (f === 'length') return vals.map(v => v === null ? 0 : typeof v === 'object' ? Object.keys(v).length : String(v).length); if (f === 'keys') return vals.map(v => Object.keys(v).sort());
    let m; if ((m = /^select\((.+?)\s*(==|!=|>=|<=|>|<)\s*(.+)\)$/.exec(f))) return vals.filter(v => { const l = step([v], m[1])[0], rr = JSON.parse(m[3]); return m[2] === '==' ? l === rr : m[2] === '!=' ? l !== rr : m[2] === '>' ? l > rr : m[2] === '<' ? l < rr : m[2] === '>=' ? l >= rr : l <= rr; });
    const re = /\.([A-Za-z_]\w*)|\.?\[(\d+)\]|\.?\[\]|\.\["([^"]+)"\]/y; let pos = 0, cur = vals;
    while (pos < f.length) { re.lastIndex = pos; const t = re.exec(f); if (!t) throw new Abort('jq: error: syntax error in filter: ' + f); pos = re.lastIndex; if (t[1] !== undefined || t[3] !== undefined) cur = cur.map(v => v === null || v === undefined ? null : (v[t[1] || t[3]] === undefined ? null : v[t[1] || t[3]])); else if (t[2] !== undefined) cur = cur.map(v => v == null ? null : v[+t[2]] === undefined ? null : v[+t[2]]); else cur = cur.flatMap(v => Array.isArray(v) ? v : v && typeof v === 'object' ? Object.values(v) : (() => { throw new Abort('jq: error: Cannot iterate over ' + typeof v); })()); if (f[pos] === '?') pos++; }
    return cur;
  };
  let vals = [data]; for (const part of filt.split('|')) vals = step(vals, part);
  io.out(vals.map(v => (typeof v === 'string' && (o.r || o.j) ? v : JSON.stringify(v, null, o.c ? 0 : 2)) + '\n').join(''));
}, "jq [-r] [-c] 'FILTER' [FILE] — query JSON. .key, .a.b, .[0], .[] (each element), .[] | .name, select(.x == 1), length, keys. -r prints raw strings");
})(typeof window !== 'undefined' ? window : globalThis);
