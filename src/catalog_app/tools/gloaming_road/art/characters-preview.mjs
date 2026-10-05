// Build a completely local, self-contained artist's turntable into /tmp.
// Run: node src/catalog_app/tools/gloaming_road/art/characters-preview.mjs
import { build } from '../frontend/node_modules/esbuild/lib/main.js';
import { writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const here = dirname(fileURLToPath(import.meta.url));
const result = await build({
  entryPoints: [resolve(here, 'characters-preview.ts')],
  bundle: true, write: false, format: 'esm', target: 'es2022',
  loader: { '.glb': 'dataurl' }, minify: false,
  nodePaths: [resolve(here, '../frontend/node_modules')],
});
const script = result.outputFiles[0].text.replaceAll('</script', '<\\/script');
const html = `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; connect-src 'none'"><title>The Gloaming Road — character workshop</title><style>
*{box-sizing:border-box}html,body{margin:0;background:#202a29;color:#d4cbb9;font:13px Georgia,serif}header{display:flex;justify-content:space-between;align-items:center;padding:12px 20px;border-bottom:1px solid #5c6255}header b{letter-spacing:.20em;font-weight:400}#kinds{display:flex;gap:7px}button,select{background:#333e3a;color:#d8ceb5;border:1px solid #697061;padding:6px 11px;font:12px Georgia,serif;text-transform:capitalize;cursor:pointer}#stage{display:flex;justify-content:center;width:100%;overflow:hidden}canvas{max-width:100%;height:auto!important;display:block}footer{padding:12px 20px;display:flex;justify-content:space-between;border-top:1px solid #525d54}#caption{font-size:13px;letter-spacing:.15em}#status{color:#9da898;font-size:12px}nav{padding:9px 20px;display:flex;gap:16px;align-items:center}label{display:flex;gap:7px;align-items:center}input{accent-color:#ab9b74;width:145px}</style></head><body>
<header><b>THE GLOAMING ROAD / CHARACTER WORKSHOP</b><div id="kinds"></div></header><nav><select id="clip" aria-label="Animation clip"></select><label>Time <input id="time" aria-label="Animation time" type="range" min="0" max="3.2" step=".01" value="0"></label><label>Turntable <input id="rotate" aria-label="Turntable angle" type="range" min="-3.14" max="3.14" step=".01" value=".23"></label><button id="play">Play / pause</button><button id="sheet">Six-character contact sheet</button></nav><div id="stage"></div><footer><span id="caption"></span><span id="status"></span></footer><script type="module">${script}</script></body></html>`;
await writeFile('/tmp/gloaming-characters-preview.html', html);
console.log(`Built /tmp/gloaming-characters-preview.html (${html.length.toLocaleString()} bytes; no network dependencies)`);
