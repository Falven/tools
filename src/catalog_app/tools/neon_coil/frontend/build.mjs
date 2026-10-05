import { build } from 'esbuild';
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
const here=dirname(fileURLToPath(import.meta.url));
const result=await build({
  entryPoints:[resolve(here,'main.js')],
  outfile:resolve(here,'../app.js'),
  bundle:true,
  minify:true,
  format:'esm',
  platform:'browser',
  target:['es2022'],
  loader:{'.woff2':'dataurl'},
  legalComments:'inline',
  charset:'utf8',
  write:false,
  metafile:true,
  banner:{js:'/* NEON COIL — generated from frontend/main.js. Rebuild with npm ci && npm run build. All runtime assets are inlined; no CDN or audio downloads. */'},
  logLevel:'info',
});
// Distribute the exact upstream notices for every package actually in the
// browser bundle, including embedded OFL font files and transitive SDK code.
const packages=new Set();
for(const input of Object.keys(result.metafile.inputs)){
  const path=input.split('node_modules/').at(-1);
  if(path===input)continue;
  const bits=path.split('/');packages.add(bits[0].startsWith('@')?bits.slice(0,2).join('/'):bits[0]);
}
const notices=['THIRD-PARTY NOTICES — NEON COIL\nDependencies below are bundled/minified for the browser; upstream source is otherwise unchanged.'];
for(const name of [...packages].sort()){
  const base=resolve(here,'node_modules',name);
  const manifest=JSON.parse(await readFile(resolve(base,'package.json'),'utf8'));
  let license='';
  for(const file of ['LICENSE','LICENSE.md','LICENSE.txt','license','license.md','license.txt']){
    try{license=await readFile(resolve(base,file),'utf8');break;}catch(error){if(error.code!=='ENOENT')throw error;}
  }
  if(!license)throw new Error(`Missing distributed license for ${name}`);
  notices.push(`\n===== ${name} ${manifest.version} =====\n\n${license}`);
  for(const file of ['NOTICE','NOTICE.txt']){
    try{notices.push(await readFile(resolve(base,file),'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;}
  }
}
const text=notices.join('\n').replace(/[ \t]+$/gm,'').trimEnd();
await writeFile(resolve(here,'../THIRD_PARTY_NOTICES.txt'),text+'\n');
const embedded=text.replaceAll('*/','* /').replace(/<\/script/gi,'<\\/script');
const compiled=result.outputFiles[0].text.replace(/[ \t]+$/gm,'').trimEnd();
await writeFile(resolve(here,'../app.js'),`/*\n${embedded}\n*/\n${compiled}\n`);
console.log(`Built self-contained app with ${packages.size} bundled dependency notices.`);
