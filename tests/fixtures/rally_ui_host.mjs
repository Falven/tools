// Isolated, synthetic bridge fixture. This is NEVER registered or served by MCP.
// node tests/fixtures/rally_ui_host.mjs -> artifacts/rally-qa.html, open via file://.
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
const root=resolve(import.meta.dirname,'../..');
const tool=resolve(root,'src/catalog_app/tools/rally_pong');
let html=await readFile(resolve(tool,'app.html'),'utf8');
const js=await readFile(resolve(tool,'app.js'),'utf8');
const core=(await readFile(resolve(tool,'frontend/core.js'),'utf8')).replace(/^export /gm,'');
const csp="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; font-src data:; img-src data:; connect-src 'none'; media-src 'none'; base-uri 'none'; form-action 'none'";
html=html.replace('<head>',`<head><meta http-equiv="Content-Security-Policy" content="${csp}">`);
html=html.replace('<!-- app.js -->',()=>`<script type="module">${js}</script>`);
const frame=JSON.stringify(html).replace(/</g,'\\u003c');
const host=`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Rally — isolated QA fixture</title><style>html,body{margin:0;height:100%;overflow:hidden;background:#101613;color:#eee;font:10px monospace}#fixture-label{height:24px;display:flex;align-items:center;justify-content:center;background:#34291e;color:#ffe0ac;letter-spacing:.06em}iframe{border:0;width:100%;height:calc(100% - 24px);display:block}</style></head><body><div id="fixture-label">ISOLATED QA · SYNTHETIC IDENTITY · NOT THE LIVE SCOREBOARD</div><iframe title="Rally QA App" id="qa-app" sandbox="allow-scripts allow-same-origin" allow="autoplay; gamepad"></iframe><script>
${core}
const iframe=document.getElementById('qa-app');
const records=new Map(),runs=new Map(),receipts=new Map();let epoch='qa-epoch-A',serial=0,beginWaiters=[],finishWaiters=[];
const fixture=window.fixture={calls:[],displayModes:[],errors:[],delayBegin:false,delayFinish:false,failNextFinish:false,canPost:true,submitted:[]};
const snapshot=(offset=0,limit=50)=>{
 const players=[...records.values()].sort((a,b)=>b.score-a.score);const best=records.get('qa-player')?.score||0;
 return {player:fixture.canPost?{id:'qa-player',name:'QA Current Player',best}:null,canPost:fixture.canPost,epoch,ephemeral:true,totalPlayers:players.length,nextOffset:offset+limit<players.length?offset+limit:null,leaderboard:players.slice(offset,offset+limit).map((p,i)=>({...p,rank:offset+i+1,isYou:p.id==='qa-player'}))};
};
fixture.populate=()=>{for(let i=0;i<65;i++)records.set('qa-'+i,{id:'qa-'+i,name:'QA Player '+String(i+1).padStart(2,'0'),score:(65-i)*100,hits:65-i});};
fixture.addSynthetic=(name,score)=>records.set('qa-unsafe',{id:'qa-unsafe',name,score,hits:0});
fixture.restart=()=>{epoch='qa-epoch-restart-'+(++serial);records.clear();runs.clear();receipts.clear();};
fixture.releaseBegin=()=>{const queued=beginWaiters;beginWaiters=[];for(const callback of queued)callback();};
fixture.releaseFinish=()=>{const queued=finishWaiters;finishWaiters=[];for(const callback of queued)callback();};
fixture.pending=()=>({begin:beginWaiters.length,finish:finishWaiters.length});
fixture.app=()=>iframe.contentWindow.__RALLY_PONG__;
fixture.window=()=>iframe.contentWindow;
fixture.document=()=>iframe.contentDocument;
fixture.key=(code,type='keydown')=>iframe.contentWindow.dispatchEvent(new iframe.contentWindow.KeyboardEvent(type,{code,key:code==='Space'?' ':code,bubbles:true,cancelable:true}));
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
  reply(event.source,id,{protocolVersion:params.protocolVersion,hostInfo:{name:'Rally QA fixture',version:'1.0.0'},hostCapabilities:{serverTools:{},logging:{},sandbox:{csp:{resourceDomains:[],connectDomains:[]}}},hostContext:{theme:'dark',displayMode:'inline',availableDisplayModes:['inline','fullscreen'],locale:'en-US',timeZone:'America/New_York',deviceCapabilities:{touch:innerWidth<721,hover:innerWidth>=721}}});return;
 }
 if(method==='ui/request-display-mode'){fixture.displayModes.push(params.mode);reply(event.source,id,{mode:params.mode});return;}
 if(method==='tools/call'){
  const name=params.name,args=params.arguments||{};fixture.calls.push({name,args});
  if(name==='rally_pong_scores'){toolResult(event.source,id,snapshot(args.offset||0,args.limit||50));return;}
  if(name==='rally_pong_begin'){
   if(!fixture.canPost){toolResult(event.source,id,{error:{code:'ineligible',message:'Sign in to post a ranked score.'},epoch});return;}
   const result={...snapshot(0,10),runId:'qa-run-'+String(++serial).padStart(32,'0'),seed:0,constants:CONSTANTS};runs.set(result.runId,result);
   const respond=()=>toolResult(event.source,id,result);if(fixture.delayBegin)beginWaiters.push(respond);else respond();return;
  }
  if(name==='rally_pong_finish'){
   if(fixture.failNextFinish){fixture.failNextFinish=false;toolResult(event.source,id,{error:{code:'qa_failure',message:'Intentional retry test.'},epoch});return;}
   if(receipts.has(args.run_id)){toolResult(event.source,id,receipts.get(args.run_id));return;}
   const ticket=runs.get(args.run_id);if(!ticket){toolResult(event.source,id,{error:{code:'unavailable_run',message:'Run unavailable. Start a new run.'},epoch});return;}
   let game;try{game=simulateReplay(ticket.seed,args.steps,args.inputs).game;}catch(error){toolResult(event.source,id,{error:{code:'invalid_replay',message:error.message},epoch});return;}
   const previous=records.get('qa-player');const personalBest=!previous||game.score>previous.score;
   if(personalBest)records.set('qa-player',{id:'qa-player',name:'QA Current Player',score:game.score,hits:game.hits});
   const result={...snapshot(0,10),runId:args.run_id,score:game.score,hits:game.hits,playerGoals:game.playerGoals,aiGoals:game.aiGoals,bestRally:game.bestRally,steps:game.steps,won:game.won,personalBest,rank:snapshot(0,100).leaderboard.find(p=>p.id==='qa-player')?.rank};
   receipts.set(args.run_id,result);fixture.submitted.push({steps:args.steps,score:game.score,inputs:args.inputs.length,epoch});
   const respond=()=>toolResult(event.source,id,result);if(fixture.delayFinish)finishWaiters.push(respond);else respond();return;
  }
 }
 reply(event.source,id,{});
});
iframe.addEventListener('load',()=>{iframe.contentWindow.addEventListener('error',event=>fixture.errors.push(event.message));iframe.contentWindow.addEventListener('unhandledrejection',event=>fixture.errors.push(String(event.reason)));});
iframe.srcdoc=${frame};
</script></body></html>`;
await mkdir(resolve(root,'artifacts'),{recursive:true});
await writeFile(resolve(root,'artifacts/rally-qa.html'),host);
await writeFile(resolve(root,'artifacts/rally-standalone.html'),html);
console.log('Generated artifacts/rally-qa.html (synthetic bridge) and rally-standalone.html; no server started.');
