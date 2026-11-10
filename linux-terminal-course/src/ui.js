/* Page behaviour: navigation, the terminal, mission grading, quizzes and the small interactive widgets. */
(function () {
'use strict';
const S = window.Sandbox, M = window.SandboxMissions, W = window.SandboxWorld;
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
const store = { get(k, d) { try { const v = localStorage.getItem('shellcraft.' + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } }, set(k, v) { try { localStorage.setItem('shellcraft.' + k, JSON.stringify(v)); } catch (e) { /* storage unavailable */ } } };
const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const md = s => esc(s).replace(/`([^`]+)`/g, '<code>$1</code>');
let sh = W.build(); sh.ui = true;
let done = store.get('done', {});
const mods = $$('.module'); let cur = null;
const total = Object.values(M).reduce((a, l) => a + l.length, 0);
const countDone = id => (M[id] || []).filter((m, i) => done[id + '.' + i]).length;

/* ---------- lesson chrome ---------- */
mods.forEach((s, i) => {
  const n = String(i).padStart(2, '0');
  s.insertBefore(el('p', 'eyebrow', 'Module ' + n + ' · ' + s.dataset.part + ' · about ' + s.dataset.min + ' min'), s.firstChild);
  const foot = el('div', 'foot'); const prev = el('button', 'btn', '← Previous'), next = el('button', 'btn primary', i === mods.length - 1 ? 'Back to the start' : 'Next: ' + (mods[i + 1] ? mods[i + 1].dataset.title : ''));
  prev.disabled = i === 0; prev.onclick = () => go(mods[i - 1].id); next.onclick = () => go(mods[(i + 1) % mods.length].id); foot.append(prev, next); s.appendChild(foot);
  s.hidden = true;
});
const toc = $('#toc'); let part = '';
mods.forEach((s, i) => {
  if (s.dataset.part !== part) { part = s.dataset.part; toc.appendChild(el('li', 'part', part)); }
  const li = el('li'), a = el('a'); a.href = '#' + s.id; a.dataset.id = s.id;
  a.append(el('span', 'n', String(i).padStart(2, '0')), el('span', '', s.dataset.title), el('span', 'ct', ''));
  li.appendChild(a); toc.appendChild(li);
});
$('#navtoggle').onclick = e => { const o = toc.dataset.open !== 'true'; toc.dataset.open = o; e.target.setAttribute('aria-expanded', o); e.target.textContent = o ? 'Hide modules' : 'Show all modules'; };
function progress() {
  const d = Object.keys(M).reduce((a, id) => a + countDone(id), 0);
  $('#barfill').style.width = (100 * d / total) + '%'; $('#progtext').textContent = d + ' of ' + total + ' missions';
  $$('#toc a').forEach(a => { const id = a.dataset.id, n = (M[id] || []).length; a.querySelector('.ct').textContent = n ? countDone(id) + '/' + n : ''; a.classList.toggle('done', n > 0 && countDone(id) === n); });
}
function go(id) { if (location.hash !== '#' + id) { try { location.hash = id; } catch (e) { /* ignore */ } } show(id); }
function show(id) {
  const s = document.getElementById(id) && document.getElementById(id).classList.contains('module') ? document.getElementById(id) : mods[0];
  cur = s.id; mods.forEach(m => { m.hidden = m !== s; });
  $$('#toc a').forEach(a => a.setAttribute('aria-current', a.dataset.id === cur));
  store.set('last', cur); toc.dataset.open = 'false'; $('#navtoggle').textContent = 'Show all modules';
  window.scrollTo(0, 0); renderMissions(); ticker();
}
window.addEventListener('hashchange', () => show(location.hash.slice(1)));

/* ---------- example blocks ---------- */
$$('pre.t').forEach(pre => {
  const live = pre.classList.contains('live'); const src = pre.textContent.replace(/^\n/, '').replace(/\n\s*$/, ''); pre.textContent = '';
  src.split('\n').forEach((ln, i, arr) => {
    const m = /^([$#]) (.*)$/.exec(ln);
    if (m) {
      const k = m[2].search(/ {2,}# /); const cmd = k < 0 ? m[2] : m[2].slice(0, k), com = k < 0 ? '' : m[2].slice(k);
      const row = el('span', 'cl'); row.append(el('span', 'p', m[1] + ' '), el('span', 'c', cmd)); if (com) row.appendChild(el('span', 'h', com));
      if (live) { row.tabIndex = 0; row.setAttribute('role', 'button'); row.title = 'Put this command in the terminal'; row.dataset.cmd = cmd; }
      pre.appendChild(row);
    } else if (/^> /.test(ln)) { const row = el('span'); row.append(el('span', 'p', '> '), el('span', 'c', ln.slice(2))); pre.appendChild(row); }
    else pre.appendChild(el('span', '', ln));
    if (i < arr.length - 1) pre.appendChild(document.createTextNode('\n'));
  });
});
document.addEventListener('click', e => { const r = e.target.closest('pre.t.live .cl'); if (r) stage(r.dataset.cmd); });
document.addEventListener('keydown', e => { if ((e.key === 'Enter' || e.key === ' ') && e.target.matches && e.target.matches('pre.t.live .cl')) { e.preventDefault(); stage(e.target.dataset.cmd); } });
function stage(cmd) { openBench(true); inp.value = cmd; inp.focus(); inp.setSelectionRange(cmd.length, cmd.length); }

/* ---------- terminal ---------- */
const out = $('#out'), inp = $('#cmdline'), plabel = $('#prompt'); let pending = '', hidx = -1, draft = '', rsearch = -1;
function promptText() { const home = sh.getv('HOME'); let p = sh.cwd; if (home && (p === home || p.startsWith(home + '/'))) p = '~' + p.slice(home.length); return sh.users[sh.uid] + '@bench:' + p + (sh.uid === 0 ? '#' : '$'); }
function refresh() { plabel.textContent = ''; if (pending) { plabel.textContent = '>'; return; } if (sh.status) plabel.appendChild(el('span', 'st', '[' + sh.status + '] ')); plabel.appendChild(document.createTextNode(promptText())); }
const clean = s => s.replace(/\r\n/g, '\n').replace(/\r/g, '').replace(/[\x00-\x08\x0b-\x1f\x7f]/g, '·');
function print(text, cls) { if (text === '') return; out.appendChild(el('span', cls, clean(text))); while (out.childNodes.length > 900) out.removeChild(out.firstChild); out.scrollTop = out.scrollHeight; }
function exec(line, quietEcho) {
  const full = pending ? pending + '\n' + line : line;
  if (!quietEcho) { const row = el('span', 'cmd'); row.append(el('span', 'p', (pending ? '>' : promptText()) + ' '), document.createTextNode(line + '\n')); out.appendChild(row); }
  if (!full.trim()) { pending = ''; refresh(); out.scrollTop = out.scrollHeight; return; }
  let pre, res;
  try { pre = sh.clone(); res = sh.run(full); }
  catch (e) { print('sandbox error: ' + (e && e.message || e) + '\n', 'e'); pending = ''; refresh(); return; }
  if (res.incomplete) { pending = full; refresh(); out.scrollTop = out.scrollHeight; return; }
  pending = ''; hidx = -1; rsearch = -1;
  if (res.echo) print(res.echo + '\n', 'sys');
  if (sh.uiClear) { out.textContent = ''; sh.uiClear = false; }
  let last = ''; for (const o of res.out) { print(o.s, o.e ? 'e' : 'o'); last = o.s; }
  if (last && !/\n$/.test(last)) print('\n', 'o');
  if (sh.uiEdit) { openEditor(sh.uiEdit); sh.uiEdit = null; }
  grade({ sh, line: full, res, ref: c => pre.clone().run(c, { history: false }).stdout, probe: c => sh.clone().run(c, { history: false }) });
  refresh();
}
function complete() {
  const v = inp.value, pos = inp.selectionStart, left = v.slice(0, pos); const m = /(?:^|[\s;|&(<>=])((?:\\.|[^\s;|&(<>=])*)$/.exec(left); const word = m ? m[1] : ''; const start = pos - word.length;
  const before = left.slice(0, start); const isCmd = /(^|[;|&(]\s*|\b(sudo|man|type|which|command|xargs|watch|nohup|time|strace|help)\s+)$/.test(before) && !word.includes('/'); let cands = [];
  if (isCmd) { const names = new Set([...Object.keys(S.BUILTINS), ...Object.keys(sh.aliases), ...Object.keys(sh.funcs)]); for (const d of (sh.getv('PATH') || '').split(':')) { const n = d && sh.lookup(d); if (n && n.type === 'd') for (const [k, f] of n.kids) if (f.mode & 0o111) names.add(k); } cands = [...names].filter(n => n.startsWith(word) && /^[\w.]/.test(n)).sort().map(n => n + ' '); }
  else if (word[0] === '$') cands = [...sh.vars.keys()].filter(k => ('$' + k).startsWith(word)).sort().map(k => '$' + k);
  else { const raw = word.replace(/\\(.)/g, '$1'); const i = raw.lastIndexOf('/'); const dirp = i < 0 ? '' : raw.slice(0, i + 1), basep = raw.slice(i + 1); const look = (dirp || './').replace(/^~(?=\/)/, sh.getv('HOME') || '~'); const d = sh.lookup(look); if (d && d.type === 'd' && sh.can(d, 4)) cands = [...d.kids.keys()].filter(k => k.startsWith(basep) && (basep[0] === '.' || k[0] !== '.')).sort().map(k => { const n = sh.lookup(look + k); return (dirp + k).replace(/([ '"()&;|<>*?$!#\\])/g, '\\$1') + (n && n.type === 'd' ? '/' : ' '); }); }
  if (!cands.length) return;
  let fill = cands[0]; if (cands.length > 1) { let k = 0; while (cands.every(c => c[k] !== undefined && c[k] === cands[0][k])) k++; fill = cands[0].slice(0, k); if (fill.length <= word.length) { print(promptText() + ' ' + v + '\n', 'cmd'); print(cands.map(c => c.trim().replace(/^.*\/(?=.)/, '')).join('  ') + '\n', 'sys'); return; } }
  inp.value = v.slice(0, start) + fill + v.slice(pos); const np = start + fill.length; inp.setSelectionRange(np, np);
}
inp.addEventListener('keydown', e => {
  const H = sh.hist;
  if (e.key === 'Enter') { e.preventDefault(); const v = inp.value; inp.value = ''; exec(v); return; }
  if (e.key === 'Tab') { e.preventDefault(); complete(); return; }
  if (e.key === 'ArrowUp') { e.preventDefault(); if (!H.length) return; if (hidx < 0) { draft = inp.value; hidx = H.length; } if (hidx > 0) hidx--; inp.value = H[hidx].split('\n')[0]; return; }
  if (e.key === 'ArrowDown') { e.preventDefault(); if (hidx < 0) return; hidx++; if (hidx >= H.length) { hidx = -1; inp.value = draft; } else inp.value = H[hidx].split('\n')[0]; return; }
  if (e.ctrlKey && !e.altKey && !e.metaKey) {
    const k = e.key.toLowerCase();
    if (k === 'l') { e.preventDefault(); out.textContent = ''; }
    else if (k === 'c' && inp.selectionStart === inp.selectionEnd) { e.preventDefault(); print((pending ? '>' : promptText()) + ' ' + inp.value + '^C\n', 'cmd'); inp.value = ''; pending = ''; hidx = -1; refresh(); }
    else if (k === 'u') { e.preventDefault(); const p = inp.selectionStart; inp.value = inp.value.slice(p); inp.setSelectionRange(0, 0); }
    else if (k === 'k') { e.preventDefault(); inp.value = inp.value.slice(0, inp.selectionStart); }
    else if (k === 'a') { e.preventDefault(); inp.setSelectionRange(0, 0); }
    else if (k === 'e') { e.preventDefault(); inp.setSelectionRange(inp.value.length, inp.value.length); }
    else if (k === 'd' && inp.value === '') { e.preventDefault(); exec('exit'); }
    else if (k === 'r') { e.preventDefault(); if (rsearch < 0) { draft = inp.value; rsearch = H.length; } for (let i = rsearch - 1; i >= 0; i--) if (H[i].includes(draft)) { rsearch = i; inp.value = H[i].split('\n')[0]; return; } }
  }
});
out.addEventListener('click', () => { if (!String(window.getSelection())) inp.focus(); });
$('#b-clear').onclick = () => { out.textContent = ''; inp.focus(); };
let armed = 0;
$('#b-reset').onclick = e => { if (Date.now() - armed > 3000) { armed = Date.now(); e.target.textContent = 'click again to confirm'; setTimeout(() => { e.target.textContent = 'reset machine'; }, 3000); return; } armed = 0; e.target.textContent = 'reset machine'; sh = W.build(); sh.ui = true; pending = ''; out.textContent = ''; print('Machine rebuilt: files, processes and services are back to their starting state. Completed missions stay ticked.\n', 'sys'); refresh(); };
function openBench(o) { const b = $('#bench'); b.dataset.open = o; document.body.dataset.bench = o; $('#b-fold').textContent = o ? 'hide' : 'show terminal'; $('#b-fold').setAttribute('aria-expanded', o); }
$('#b-fold').onclick = () => openBench($('#bench').dataset.open !== 'true');

/* ---------- editor ---------- */
const ed = $('#editor'), edText = $('#ed-text'); let edCtx = null;
function openEditor(ctx) { edCtx = ctx; $('#ed-name').textContent = ctx.path + (ctx.uid === 0 ? '  (as root)' : ''); edText.value = ctx.data; $('#ed-msg').textContent = ''; ed.hidden = false; edText.focus(); }
function closeEditor() { ed.hidden = true; edCtx = null; inp.focus(); }
function saveEditor() {
  const sv = { uid: sh.uid, gid: sh.gid, groups: sh.groups }; let text = edText.value; if (text && !/\n$/.test(text)) text += '\n';
  const pre = sh.clone();
  try { Object.assign(sh, { uid: edCtx.uid, gid: edCtx.gid, groups: edCtx.groups }); sh.write(edCtx.path, text); }
  catch (e) { $('#ed-msg').textContent = 'Cannot write ' + edCtx.path + ': ' + (e.msg || e.message) + (/Permission/.test(e.msg || '') ? '. Cancel and reopen with sudo edit ...' : ''); return; }
  finally { Object.assign(sh, sv); }
  print('"' + edCtx.path + '" ' + text.split('\n').length + 'L, ' + text.length + 'B written\n', 'sys'); closeEditor();
  grade({ sh, line: 'edit', res: { stdout: '', stderr: '', status: 0, out: [] }, ref: c => pre.clone().run(c, { history: false }).stdout, probe: c => sh.clone().run(c, { history: false }) });
}
$('#ed-save').onclick = saveEditor; $('#ed-cancel').onclick = closeEditor;
edText.addEventListener('keydown', e => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); saveEditor(); } else if (e.key === 'Escape') { e.preventDefault(); closeEditor(); } else if (e.key === 'Tab') { e.preventDefault(); const p = edText.selectionStart; edText.setRangeText('    ', p, edText.selectionEnd, 'end'); } });

/* ---------- missions ---------- */
function renderMissions() {
  const s = document.getElementById(cur), box = s.querySelector('.missions'), list = M[cur] || []; if (!box) return; box.textContent = ''; if (!list.length) { box.hidden = true; return; }
  const hd = el('header'); hd.append(el('h3', '', 'Missions'), el('span', '', countDone(cur) + ' / ' + list.length + ' complete')); box.appendChild(hd);
  const firstOpen = list.findIndex((m, i) => !done[cur + '.' + i]);
  list.forEach((m, i) => {
    const row = el('div', 'mission' + (done[cur + '.' + i] ? ' done' : '') + (i === firstOpen ? ' active' : '')); const body = el('div'); const p = el('p'); p.innerHTML = md(m.t); body.appendChild(p);
    const acts = el('div', 'acts'), rev = el('div', 'reveal'); rev.hidden = true;
    const bh = el('button', '', 'Hint'), bs = el('button', '', 'Solution');
    bh.onclick = () => { rev.hidden = false; rev.innerHTML = md(m.hint); };
    bs.onclick = () => { rev.hidden = false; rev.textContent = 'One way to do it:'; const lines = [].concat(m.sol); rev.appendChild(el('pre', '', lines.join('\n'))); const run = el('button', 'chip', 'Run it in the terminal'); run.onclick = () => { openBench(true); for (const l of lines) { l.split('\n').forEach(x => exec(x)); } inp.focus(); }; rev.appendChild(run); };
    acts.append(bh, bs); body.append(acts, rev); row.append(el('span', 'box', '✓'), body); box.appendChild(row);
  });
}
function ticker() {
  const list = M[cur] || [], i = list.findIndex((m, k) => !done[cur + '.' + k]), t = $('#ticker'), tx = $('#ticktext'); t.classList.toggle('alldone', i < 0);
  if (!list.length) { t.querySelector('.tag').textContent = 'Free play'; tx.textContent = 'No missions in this module. Try anything.'; return; }
  if (i < 0) { t.querySelector('.tag').textContent = 'Done'; tx.textContent = 'All ' + list.length + ' missions in this module are complete.'; return; }
  t.querySelector('.tag').textContent = 'Mission ' + (i + 1) + '/' + list.length; tx.innerHTML = md(list[i].t);
}
function grade(c) {
  const list = M[cur] || []; let any = false;
  list.forEach((m, i) => { const k = cur + '.' + i; if (done[k]) return; let okk = false; try { okk = !!m.check(c); } catch (e) { okk = false; } if (okk) { done[k] = true; any = true; print('✓ mission ' + (i + 1) + ' complete\n', 'win'); } });
  if (any) { store.set('done', done); progress(); renderMissions(); ticker(); if (countDone(cur) === list.length) print('Module cleared: all ' + list.length + ' missions done.\n', 'win'); }
}

/* ---------- quizzes ---------- */
$$('.quiz').forEach(qz => {
  const qs = [...qz.querySelectorAll('.q')]; let right = 0, ans = 0; const score = el('p', 'score', ''); qz.appendChild(score);
  qs.forEach(q => { const why = q.querySelector('.why'); if (why) why.hidden = true; const bs = [...q.querySelectorAll('button')]; bs.forEach(b => { b.onclick = () => { bs.forEach(x => { x.disabled = true; if (x.hasAttribute('data-ok')) x.classList.add('right'); }); if (b.hasAttribute('data-ok')) right++; else b.classList.add('wrong'); ans++; if (why) why.hidden = false; score.textContent = right + ' of ' + ans + ' correct' + (ans === qs.length ? (right === qs.length ? '. Clean sweep.' : '. Reread the explanations for the ones you missed.') : ''); }; }); });
});

/* ---------- widgets ---------- */
$$('[data-widget="chmod"]').forEach(w => {
  w.innerHTML = '<h4>Permission calculator</h4><div class="permgrid"><span></span><span>read (4)</span><span>write (2)</span><span>execute (1)</span></div><div class="permgrid sp"></div><div class="permout"><label>octal <input type="text" inputmode="numeric" maxlength="4" value="0754" aria-label="Octal mode"></label><span>symbolic <b class="sym"></b></span></div><p class="rx-meta"></p>';
  const g = w.querySelector('.permgrid'), sp = w.querySelector('.sp'), box = {};
  ['user', 'group', 'other'].forEach((who, r) => { g.appendChild(el('span', '', who)); [4, 2, 1].forEach(b => { const l = el('label'), c = el('input'); c.type = 'checkbox'; c.setAttribute('aria-label', who + ' ' + { 4: 'read', 2: 'write', 1: 'execute' }[b]); box[r + '.' + b] = c; l.appendChild(c); l.appendChild(document.createTextNode('rwx'[[4, 2, 1].indexOf(b)])); g.appendChild(l); c.onchange = fromBoxes; }); });
  sp.appendChild(el('span', '', 'special')); [[4, 'setuid'], [2, 'setgid'], [1, 'sticky']].forEach(([b, n]) => { const l = el('label'), c = el('input'); c.type = 'checkbox'; box['s.' + b] = c; l.append(c, document.createTextNode(n)); sp.appendChild(l); c.onchange = fromBoxes; });
  const oct = w.querySelector('input[type=text]'), sym = w.querySelector('.sym'), meta = w.querySelector('.rx-meta');
  function paint(m) { sym.textContent = S.modeStr({ type: 'f', mode: m }); const u = (m >> 6) & 7, gq = (m >> 3) & 7, o = m & 7; const notes = []; if (o & 2) notes.push('world-writable: anyone can modify it'); if (m & 0o4000) notes.push('setuid: runs with the owner\'s privileges'); if (m & 0o2000) notes.push('setgid: on a directory, new files inherit its group'); if (m & 0o1000) notes.push('sticky: in a shared directory, only owners can delete their files'); if (!(u & 4)) notes.push('the owner cannot read it'); meta.textContent = 'chmod ' + m.toString(8).padStart(m > 0o777 ? 4 : 3, '0') + ' FILE' + (notes.length ? '  —  ' + notes.join('; ') : ''); }
  function fromBoxes() { let m = 0; [0, 1, 2].forEach(r => [4, 2, 1].forEach(b => { if (box[r + '.' + b].checked) m |= b << ((2 - r) * 3); })); [4, 2, 1].forEach(b => { if (box['s.' + b].checked) m |= b << 9; }); oct.value = m.toString(8).padStart(4, '0'); paint(m); }
  function fromOct() { if (!/^[0-7]{1,4}$/.test(oct.value)) { sym.textContent = '?'; return; } const m = parseInt(oct.value, 8); [0, 1, 2].forEach(r => [4, 2, 1].forEach(b => { box[r + '.' + b].checked = !!(m & (b << ((2 - r) * 3))); })); [4, 2, 1].forEach(b => { box['s.' + b].checked = !!(m & (b << 9)); }); paint(m); }
  oct.oninput = fromOct; fromOct();
});
$$('[data-widget="regex"]').forEach(w => {
  w.innerHTML = '<h4>Regex lab (extended syntax, as in grep -E)</h4><input type="text" class="rx" aria-label="Regular expression" value="([0-9]{1,3}\\.){3}[0-9]{1,3}"><label class="rx-meta"><input type="checkbox" class="ci"> ignore case (-i)</label><textarea class="tx" aria-label="Sample text"></textarea><div class="rx-out" aria-live="polite"></div><p class="rx-meta"></p>';
  const rx = w.querySelector('.rx'), tx = w.querySelector('.tx'), o = w.querySelector('.rx-out'), meta = w.querySelectorAll('.rx-meta')[1], ci = w.querySelector('.ci');
  tx.value = 'Nov 10 03:12:45 bench sshd[1234]: Failed password for invalid user admin from 203.0.113.7 port 51234 ssh2\nNov 10 03:14:02 bench sshd[1240]: Accepted publickey for op from 192.168.1.20 port 50122 ssh2\nI (1820) sensor-node: MAC 24:6f:28:a1:b2:c4 joined mesh as node-b\nW (1834) sensor-node: vbat 3.21V below 3.30V threshold\nbaud=115200  # was 9600\nTODO: support 921600\n';
  function run() { o.textContent = ''; let re; try { re = new RegExp(S.reConv(rx.value, true), 'g' + (ci.checked ? 'i' : '')); } catch (e) { meta.textContent = 'Invalid pattern: ' + e.message; o.textContent = tx.value; return; } if (!rx.value) { o.textContent = tx.value; meta.textContent = 'Type a pattern.'; return; } let n = 0, lines = 0; tx.value.split('\n').forEach((ln, i, arr) => { let last = 0, m, hit = false; re.lastIndex = 0; while ((m = re.exec(ln))) { if (m[0] === '') { re.lastIndex++; continue; } o.appendChild(document.createTextNode(ln.slice(last, m.index))); o.appendChild(el('mark', '', m[0])); last = m.index + m[0].length; n++; hit = true; } if (hit) lines++; o.appendChild(document.createTextNode(ln.slice(last) + (i < arr.length - 1 ? '\n' : ''))); }); meta.textContent = n + ' match' + (n === 1 ? '' : 'es') + ' on ' + lines + ' line' + (lines === 1 ? '' : 's') + '. grep prints the ' + lines + ' matching line' + (lines === 1 ? '' : 's') + '; grep -o prints the ' + n + ' highlighted piece' + (n === 1 ? '' : 's') + '.'; }
  rx.oninput = tx.oninput = ci.onchange = run; run();
});
$$('[data-widget="vim"]').forEach(w => {
  w.innerHTML = '<h4>Vim grammar decoder</h4><input type="text" class="vi" aria-label="Normal-mode command" value="d2w" maxlength="12"><div class="vimparts"></div><p class="rx-meta">Try: ci"  dap  y$  3dd  gUiw  &gt;ip  dt,  c3w  yy  d/foo  =G</p>';
  const OPS = { d: 'delete', c: 'change (delete, then insert mode)', y: 'yank (copy)', '>': 'indent', '<': 'dedent', '=': 'auto-indent', gU: 'make uppercase', gu: 'make lowercase', 'g~': 'toggle case', '!': 'filter through a shell command' };
  const MOT = { w: 'to the start of the next word', W: 'to the next WORD (space-delimited)', b: 'back to the start of the word', B: 'back one WORD', e: 'to the end of the word', E: 'to the end of the WORD', '0': 'to column 0', '^': 'to the first non-blank character', $: 'to the end of the line', gg: 'to the first line', G: 'to the last line', '}': 'to the next blank line', '{': 'to the previous blank line', ')': 'to the next sentence', '(': 'to the previous sentence', h: 'one character left', l: 'one character right', j: 'this line and the one below', k: 'this line and the one above', '%': 'to the matching bracket', H: 'to the top of the screen', L: 'to the bottom of the screen', n: 'to the next search match', '*': 'to the next occurrence of the word under the cursor' };
  const OBJ = { w: 'word', W: 'WORD', s: 'sentence', p: 'paragraph', '"': 'double-quoted string', "'": 'single-quoted string', '`': 'backtick string', '(': 'parentheses', ')': 'parentheses', b: 'parentheses', '[': 'square brackets', ']': 'square brackets', '{': 'braces', '}': 'braces', B: 'braces', '<': 'angle brackets', '>': 'angle brackets', t: 'HTML/XML tag' };
  const SOLO = { x: 'delete the character under the cursor', p: 'paste after the cursor', P: 'paste before the cursor', u: 'undo', '.': 'repeat the last change', dd: null, i: 'insert before the cursor', a: 'append after the cursor', A: 'append at the end of the line', I: 'insert at the first non-blank', o: 'open a new line below', O: 'open a new line above', J: 'join the next line onto this one', '~': 'toggle case of one character', D: 'delete to the end of the line (same as d$)', C: 'change to the end of the line (same as c$)', Y: 'yank the line', r: 'replace one character (next key)', v: 'start visual selection', V: 'start line-wise visual selection', zz: 'centre the cursor line on screen' };
  const inp2 = w.querySelector('.vi'), outp = w.querySelector('.vimparts');
  function part(k, v, d) { const b = el('div'); b.append(el('small', '', k), el('b', '', v), el('span', '', d)); outp.appendChild(b); }
  function run() {
    outp.textContent = ''; let s = inp2.value; if (!s) return; let m = /^([1-9]\d*)?/.exec(s); const c1 = m[1]; s = s.slice(m[0].length);
    const op = ['gU', 'gu', 'g~', 'd', 'c', 'y', '>', '<', '=', '!'].find(o => s.startsWith(o));
    if (!op) { if (c1) part('count', c1, 'repeat ' + c1 + ' times'); const mv = MOT[s] || SOLO[s]; if (mv) part(MOT[s] ? 'motion' : 'command', s, MOT[s] ? 'move ' + mv : mv); else if (/^[fFtT].$/.test(s)) part('motion', s, 'move ' + ({ f: 'onto', t: 'just before', F: 'back onto', T: 'back to just after' })[s[0]] + ' the next "' + s[1] + '" on this line'); else part('?', s, 'not a command this decoder knows'); return; }
    if (c1) part('count', c1, 'do it ' + c1 + ' times'); part('operator', op, OPS[op]); s = s.slice(op.length); m = /^([1-9]\d*)?/.exec(s); const c2 = m[1]; s = s.slice(m[0].length); if (c2) part('count', c2, 'over ' + c2 + ' of the following');
    if (!s) { part('…', '', 'waiting for a motion or text object'); return; }
    if (s === op || (op.length === 2 && s === op[1])) { part('line', s, 'doubled operator: act on the whole current line'); return; }
    if (/^[ia].$/.test(s) && OBJ[s[1]]) { part('text object', s, (s[0] === 'i' ? 'inside the ' : 'around the ') + OBJ[s[1]] + (s[0] === 'a' ? ' (including its delimiters or trailing space)' : ' (not the delimiters)')); return; }
    if (/^[fFtT].$/.test(s)) { part('motion', s, ({ f: 'up to and including', t: 'up to but not including', F: 'back to and including', T: 'back to just after' })[s[0]] + ' the next "' + s[1] + '" on this line'); return; }
    if (/^[\/?].+/.test(s)) { part('motion', s, 'up to the next match of the search "' + s.slice(1) + '"'); return; }
    if (MOT[s]) { part('motion', s, MOT[s]); return; }
    part('?', s, /^[ia]$/.test(s) ? 'waiting for the object: w p " ( [ { t' : 'unknown motion');
  }
  inp2.oninput = run; run();
});

/* ---------- boot ---------- */
print('Welcome to bench, a simulated Linux machine that runs in this page.\nIt has a real shell grammar, a filesystem, processes, logs, services and an ESP32 on /dev/ttyUSB0.\nNothing here can touch your computer. Type help to see what is installed.\n\n', 'sys');
if (window.matchMedia('(max-width:1180px)').matches) openBench(false); else document.body.dataset.bench = 'true';
progress(); refresh(); show((location.hash || '').slice(1) || store.get('last', mods[0].id));
window.shellcraft = { get sh() { return sh; }, exec };
})();
