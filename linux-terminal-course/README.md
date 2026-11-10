# Shellcraft Terminal Course

An interactive course on advanced Linux terminal use. `index.html` is a single self-contained page:
19 modules, 110 graded missions, and a sandbox shell (bash grammar, in-memory filesystem, about 150
commands, simulated services, network and a USB-serial device) that runs entirely in the browser.

- `src/` sources: lesson HTML (`c1`–`c4`), shell interpreter (`shell.js`, `cmds.js`, `awk.js`),
  the simulated machine (`world.js`), missions (`missions.js`) and page behaviour (`ui.js`)
- `./build.sh` concatenates them into `index.html`
- `node test.js` runs every mission's reference solution through the sandbox
