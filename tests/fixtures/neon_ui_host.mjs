// A local, memory-only browser QA fixture. Never served by the MCP resource.
// Generate with: node tests/fixtures/neon_ui_host.mjs
// Open artifacts/neon-coil-qa.html in an isolated browser. All names/scores are
// explicitly synthetic. Real identity/replay verification is covered in Python.
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
const root=resolve(import.meta.dirname,'../..');
const tool=resolve(root,'src/catalog_app/tools/neon_coil');
let html=await readFile(resolve(tool,'app.html'),'utf8');
const js=await readFile(resolve(tool,'app.js'),'utf8');
const core=(await readFile(resolve(tool,'frontend/core.js'),'utf8')).replace(/^export /gm,'');
const csp="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; font-src data:; img-src data:; connect-src 'none'; media-src 'none'; base-uri 'none'; form-action 'none'";
html=html.replace('<head>',`<head><meta http-equiv="Content-Security-Policy" content="${csp}">`);
html=html.replace('<!-- app.js -->',()=>`<script type="module">${js}</script>`);
const frameData=JSON.stringify(html).replace(/</g,'\\u003c');
const host=`<!doctype html><html><head><meta charset="utf-8"><title>Neon Coil — isolated QA fixture</title><style>html,body{margin:0;height:100%;overflow:hidden;background:#111;color:#eee;font:12px monospace}#fixture-label{height:28px;display:flex;align-items:center;justify-content:center;color:#ffc17d;background:#291f18}iframe{border:0;width:100%;height:calc(100% - 28px);display:block}</style></head><body><div id="fixture-label">ISOLATED QA FIXTURE · SYNTHETIC USERS / SCORES · NOT THE LIVE MCP SERVER</div><iframe title="Neon Coil QA app" id="qa-app" sandbox="allow-scripts allow-same-origin" allow="autoplay"></iframe><script>
${core}
const iframe=document.getElementById('qa-app');
const records=Array.from({length:96},(_,i)=>({id:'fixture-'+i,name:'QA Player '+String(i+1).padStart(2,'0'),score:(96-i)*100,foods:96-i}));
const runs=new Map();let best=0,epoch='qa-epoch-A',serial=0,beginWaiters=[],finishWaiters=[];
const fixture=window.fixture={calls:[],displayModes:[],errors:[],delayBegin:false,delayFinish:false,failNextFinish:false,submitted:[]};
const snapshot=(offset=0,limit=50)=>{
 const players=records.slice();if(best>=0&&fixture.hasScore)players.push({id:'qa-caller',name:'QA Current User',score:best,foods:best/100});
 players.sort((a,b)=>b.score-a.score);
 return {player:{id:'qa-caller',name:'QA Current User',best},canPost:true,epoch,ephemeral:true,totalPlayers:players.length,nextOffset:offset+limit<players.length?offset+limit:null,leaderboard:players.slice(offset,offset+limit).map((p,i)=>({...p,rank:offset+i+1,isYou:p.id==='qa-caller'}))};
};
fixture.restart=()=>{epoch='qa-epoch-'+(++serial)+'-restart';best=0;records.length=0;runs.clear();fixture.hasScore=false;};
fixture.releaseBegin=()=>{const waiters=beginWaiters;beginWaiters=[];for(const fn of waiters)fn();};
fixture.releaseFinish=()=>{const waiters=finishWaiters;finishWaiters=[];for(const fn of waiters)fn();};
fixture.pending=()=>({begin:beginWaiters.length,finish:finishWaiters.length});
fixture.app=()=>iframe.contentWindow.__NEON_COIL__;
fixture.key=code=>iframe.contentWindow.dispatchEvent(new KeyboardEvent('keydown',{code,key:code==='Space'?' ':code,bubbles:true,cancelable:true}));
fixture.click=id=>iframe.contentDocument.getElementById(id).click();
fixture.away=()=>iframe.contentWindow.dispatchEvent(new Event('blur'));
fixture.focus=()=>{iframe.focus();iframe.contentWindow.dispatchEvent(new Event('focus'));};
fixture.result=()=>({state:fixture.app()?.snapshot(),graphics:fixture.app()?.diagnostics(),calls:fixture.calls.map(x=>x.name),displayModes:fixture.displayModes,errors:fixture.errors});
function reply(target,id,result){target.postMessage({jsonrpc:'2.0',id,result},'*');}
function toolResult(target,id,result){reply(target,id,{content:[{type:'text',text:JSON.stringify(result)}],structuredContent:result});}
window.addEventListener('message',event=>{
 if(event.source!==iframe.contentWindow||!event.data||event.data.jsonrpc!=='2.0')return;
 const {id,method,params={}}=event.data;if(id===undefined)return;
 if(method==='ui/initialize'){
  reply(event.source,id,{protocolVersion:params.protocolVersion,hostInfo:{name:'Neon Coil QA fixture',version:'1.0.0'},hostCapabilities:{serverTools:{},logging:{},sandbox:{csp:{resourceDomains:[],connectDomains:[]}}},hostContext:{theme:'dark',displayMode:'inline',availableDisplayModes:['inline','fullscreen'],locale:'en-US',timeZone:'America/New_York',deviceCapabilities:{touch:innerWidth<721,hover:innerWidth>=721}}});return;
 }
 if(method==='ui/request-display-mode'){fixture.displayModes.push(params.mode);reply(event.source,id,{mode:params.mode});return;}
 if(method==='tools/call'){
  const name=params.name,args=params.arguments||{};fixture.calls.push({name,args});
  if(name==='neon_coil_scores'){toolResult(event.source,id,snapshot(args.offset||0,args.limit||50));return;}
  if(name==='neon_coil_begin'){
   const result={...snapshot(0,10),runId:'qa-run-'+String(++serial).padStart(30,'0'),seed:305419896};runs.set(result.runId,result);
   const respond=()=>toolResult(event.source,id,result);if(fixture.delayBegin)beginWaiters.push(respond);else respond();return;
  }
  if(name==='neon_coil_finish'){
   if(fixture.failNextFinish){fixture.failNextFinish=false;toolResult(event.source,id,{error:{code:'qa_failure',message:'Intentional QA retry test'},epoch,ephemeral:true});return;}
   const ticket=runs.get(args.run_id);if(!ticket){toolResult(event.source,id,{error:{code:'unavailable_run',message:'Run unavailable. Start a new run.'},epoch,ephemeral:true});return;}
   const game=createGame(ticket.seed);let ti=0;for(let tick=1;tick<=args.steps;tick++){const turn=args.turns[ti];advance(game,turn?.[0]===tick?args.turns[ti++][1]:game.direction);}
   const personalBest=!fixture.hasScore||game.score>best;best=Math.max(best,game.score);fixture.hasScore=true;
   const result={...snapshot(0,10),runId:args.run_id,score:game.score,foods:game.foods,steps:game.steps,won:game.won,personalBest,rank:snapshot(0,100).leaderboard.find(x=>x.id==='qa-caller')?.rank||97};
   fixture.submitted.push({steps:args.steps,turns:args.turns,score:game.score,epoch});
   const respond=()=>toolResult(event.source,id,result);if(fixture.delayFinish)finishWaiters.push(respond);else respond();return;
  }
 }
 reply(event.source,id,{});
});
iframe.srcdoc=${frameData};
</script></body></html>`;
await mkdir(resolve(root,'artifacts'),{recursive:true});
await writeFile(resolve(root,'artifacts/neon-coil-qa.html'),host);
console.log('Generated artifacts/neon-coil-qa.html (synthetic test bridge; no server started)');
