/* Runs every mission's reference solution through the sandbox and checks that it is accepted
   (and that a no-op command is not). Usage: node test.js */
const path = require('path');
for (const f of ['shell', 'cmds', 'awk', 'world', 'missions']) require(path.join(__dirname, 'src', f + '.js'));
const M = globalThis.SandboxMissions;
let fail = 0, total = 0;
const sh = globalThis.SandboxWorld.build();
function attempt(line) {
  const pre = sh.clone();
  const res = sh.run(line);
  if (res.incomplete) throw new Error('incomplete: ' + line);
  return { sh, line, res, ref: c => pre.clone().run(c, { history: false }).stdout, probe: c => sh.clone().run(c, { history: false }) };
}
for (const id of Object.keys(M)) {
  M[id].forEach((m, i) => {
    total++;
    const safe = c => { try { return !!m.check(c); } catch (e) { return false; } };
    if (safe(attempt('true'))) { fail++; console.log('FAIL ' + id + '.' + (i + 1) + ': passes before the solution runs'); }
    let passed = false, last;
    for (const line of [].concat(m.sol)) { last = attempt(line); if (safe(last)) passed = true; }
    if (!passed) { fail++; console.log('FAIL ' + id + '.' + (i + 1) + ': ' + m.t.slice(0, 70) + '\n   status=' + last.res.status + '\n   stdout=' + JSON.stringify(last.res.stdout.slice(0, 300)) + '\n   stderr=' + JSON.stringify(last.res.stderr.slice(0, 300))); }
  });
}
console.log((total - fail) + '/' + total + ' missions accept their reference solution');
process.exit(fail ? 1 : 0);
