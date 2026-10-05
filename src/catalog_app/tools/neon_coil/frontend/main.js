import { App } from '@modelcontextprotocol/ext-apps';
import { createGame, advance, stepMs, DIRS } from './core.js';
import { NeonRenderer } from './renderer.js';
import { ArcadeAudio } from './audio.js';
import grotesk from '@fontsource/space-grotesk/files/space-grotesk-latin-500-normal.woff2';
import groteskBold from '@fontsource/space-grotesk/files/space-grotesk-latin-700-normal.woff2';
import mono from '@fontsource/space-mono/files/space-mono-latin-400-normal.woff2';

const fonts = document.createElement('style');
fonts.textContent = `@font-face{font-family:'Coil Grotesk';src:url('${grotesk}') format('woff2');font-weight:400 600;font-display:swap}@font-face{font-family:'Coil Grotesk';src:url('${groteskBold}') format('woff2');font-weight:700 900;font-display:swap}@font-face{font-family:'Coil Mono';src:url('${mono}') format('woff2');font-weight:400 700;font-display:swap}`;
document.head.append(fonts);
const $ = id => document.getElementById(id);
const ui = Object.fromEntries(['scene','intro','scene-caption','start-button','start-label','identity-label','score','best','level','level-track','pause-button','pause-overlay','pause-reason','resume-button','gameover-overlay','end-score','end-foods','end-level','end-title','end-eyebrow','record-label','save-status','retry-save','restart-button','leaderboard-button','end-leaderboard','scoreboard','close-scoreboard','score-list','empty-scores','empty-title','empty-description','board-player','board-best','refresh-scores','load-more-scores','sfx-button','music-button','quality-button','touch-controls','swipe-hint','footer-state','arena-label','arena-coordinates','toast','live-announcement','renderer-error','renderer-error-message'].map(id => [id,$(id)]));
const audio = new ArcadeAudio();
const app = new App({name:'Neon Coil',version:'1.0.0'},{availableDisplayModes:['inline','fullscreen']},{autoResize:false});
const touchDevice = matchMedia('(pointer: coarse)').matches || navigator.maxTouchPoints > 0;
const MAX_STEPS = 18000;
let renderer, phase='intro', game=null, previous=null, run=null, queued=[], accumulator=0, interval=150;
let connected=false, practice=window.parent===window, canPost=false, player=null, scores=[], epoch=null, best=0, nextOffset=null;
let raf=0,lastFrame=0,disposed=false,toastTimer=0,submission=null,scoreRequest=0,fullscreenRequested=false;
let actualInputAt=0,consumedInputMs=0,inputSamples=0,runStartedAt=0,runEndedAt=0,awayGeneration=0,startVersion=0;

const pad = n => String(Math.max(0,Number(n)||0)).padStart(6,'0');
function announce(message){ui['live-announcement'].textContent=message;}
function toast(message){ui.toast.textContent=message;ui.toast.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>ui.toast.hidden=true,4200);}
function readResult(result){
  if(result?.isError)throw new Error(result.content?.filter(x=>x.type==='text').map(x=>x.text).join(' ')||'The arcade server could not complete this request.');
  let data=result?.structuredContent;
  if(!data&&result?.content)for(const item of result.content){if(item.type==='text'){try{data=JSON.parse(item.text);break;}catch{ /* A non-JSON fallback is not game state. */ }}}
  if(!data&&result&&('leaderboard' in result||'runId' in result||'error' in result))data=result;
  if(!data)throw new Error('The arcade returned an unreadable response.');
  if(data.error){const error=new Error(data.error.message||'The arcade request was rejected.');error.code=data.error.code;error.retryAfterMs=data.error.retryAfterMs;throw error;}
  return data;
}
async function call(name,args={}){return readResult(await app.callServerTool({name,arguments:args},{timeout:15000}));}
function updateIdentity(data){
  const samePlayer=(!data.epoch||data.epoch===epoch)&&Boolean(player?.id)&&data.player?.id===player.id;
  if('player' in data&&player?.id&&data.player?.id!==player.id&&run)run.unranked=true;
  if(data.epoch&&epoch&&data.epoch!==epoch){best=0;scores=[];if(run&&!practice)toast('The server restarted. This run is now unranked; start a new run to post a score.');if(run)run.unranked=true;}
  if(data.epoch)epoch=data.epoch;
  if('player' in data)player=data.player;
  if('canPost' in data)canPost=Boolean(data.canPost);
  else if(player)canPost=true;
  if(player)best=Math.max(samePlayer?best:0,Number(player.best)||0);
  else best=0;
  if(Array.isArray(data.leaderboard)){scores=data.leaderboard;nextOffset=data.nextOffset??null;}
  ui.best.textContent=pad(best);ui['board-best'].textContent=pad(best);
  if(practice){ui['identity-label'].textContent='Standalone preview · unranked practice';ui['start-label'].textContent='PLAY PRACTICE';ui['footer-state'].textContent='PRACTICE · NO SCORES SAVED';}
  else if(player&&canPost){ui['identity-label'].textContent=`Playing as ${player.name} · scores in RAM`;ui['start-label'].textContent='LET’S PLAY';}
  else{ui['identity-label'].textContent='Sign in as a user for ranked scores · practice available';ui['start-label'].textContent='PLAY PRACTICE';}
  renderScores();
}
function hud(){
  const value=pad(game?.score||0);const leading=value.match(/^0*/)?.[0].length||0;
  const dim=document.createElement('span');dim.className='leading';dim.textContent=value.slice(0,Math.min(5,leading));ui.score.replaceChildren(dim,document.createTextNode(value.slice(Math.min(5,leading))));ui.score.setAttribute('aria-label',`Score ${game?.score||0}`);
  const level=1+Math.floor((game?.foods||0)/5);ui.level.textContent=`LEVEL ${String(level).padStart(2,'0')}`;
  Array.from(ui['level-track'].children).forEach((el,i)=>el.classList.toggle('filled',i<(game?.foods||0)%5));
}
function setPhase(next){
  phase=next;document.body.dataset.phase=phase;
  ui.intro.hidden=!['intro','starting'].includes(phase);ui['scene-caption'].hidden=ui.intro.hidden;
  ui['pause-overlay'].hidden=phase!=='paused';ui['gameover-overlay'].hidden=phase!=='over';
  ui['pause-button'].hidden=!['playing','paused'].includes(phase);ui['touch-controls'].hidden=!touchDevice||phase!=='playing';
  ui['pause-button'].setAttribute('aria-label',phase==='paused'?'Resume game':'Pause game');
  renderer?.setIntro(phase==='intro'||phase==='starting');
  if(phase==='playing'){
    ui['footer-state'].textContent=(run?.unranked?'UNRANKED PRACTICE':'AUTHENTICATED RUN')+' · KEEP GROWING';
    ui['arena-label'].textContent='01 / THE NEON GRID';ui['arena-coordinates'].textContent='100 POINTS / BITE';
  }
}
async function unlock(){await audio.unlock();if(!audio.available){ui['sfx-button'].disabled=true;ui['music-button'].disabled=true;ui['sfx-button'].title=ui['music-button'].title='Web Audio is unavailable in this browser';}}
function focusScene(){ui.scene.focus({preventScroll:true});}
async function requestFullscreen(){
  if(fullscreenRequested||!connected)return;fullscreenRequested=true;
  const context=app.getHostContext();
  if(context?.availableDisplayModes?.includes('fullscreen')&&context.displayMode!=='fullscreen'){
    try{await app.requestDisplayMode({mode:'fullscreen'});}catch{ /* The native host Fullscreen control remains available. */ }
  }
}
async function start(){
  if(phase==='starting'||phase==='playing'||!renderer||ui['start-button'].disabled&&phase==='intro')return;
  const audioReady=unlock(), generation=awayGeneration, version=++startVersion;void requestFullscreen();
  scoreRequest++;
  const oldPhase=phase;setPhase('starting');ui['start-button'].disabled=true;ui['restart-button'].disabled=true;ui['start-label'].textContent='SPAWNING…';queued=[];
  try{
    let issued;
    if(connected&&canPost&&!practice){issued=await call('neon_coil_begin');issued.unranked=false;}
    else{const seed=new Uint32Array(1);crypto.getRandomValues(seed);issued={seed:seed[0],runId:null,unranked:true};}
    if(disposed||version!==startVersion)return;
    scoreRequest++;
    if(!issued.unranked)updateIdentity(issued);
    run=issued;game=createGame(issued.seed);previous=game.body.map(cell=>cell.slice());interval=stepMs(0);accumulator=0;lastFrame=performance.now();runStartedAt=lastFrame;
    actualInputAt=0;consumedInputMs=0;inputSamples=0;submission=null;hud();ui['record-label'].hidden=true;ui['retry-save'].hidden=true;
    setPhase('playing');audio.setPlaying(true);void audioReady.then(()=>{if(!disposed&&phase==='playing'&&!document.hidden)audio.play('start');});
    if(document.hidden||generation!==awayGeneration||ui.scoreboard.open){pause('Your run is ready. Resume when you’re back at the controls.');audio.suspend();if(ui.scoreboard.open)void refreshScores();}
    else{focusScene();announce('Run started. Eat the orange energy cubes. Avoid walls and your tail.');}
  }catch(error){
    if(disposed||version!==startVersion)return;
    setPhase(oldPhase==='over'?'over':'intro');toast(error.message);ui['start-label'].textContent='TRY AGAIN';
  }finally{ui['start-button'].disabled=false;ui['restart-button'].disabled=false;}
}
function queueDirection(direction){
  if(phase!=='playing'&&phase!=='starting')return false;
  const last=queued.length?queued[queued.length-1].direction:(phase==='starting'?1:(game?.direction??1));
  if(direction===last||direction===(last+2)%4||queued.length>=2)return false;
  actualInputAt=performance.now();queued.push({direction,at:actualInputAt});return true;
}
function pause(reason='Your next high score can wait a second.'){
  if(phase!=='playing')return;
  setPhase('paused');queued=[];ui['pause-reason'].textContent=reason;audio.setPlaying(false);audio.play('pause');ui['resume-button'].focus({preventScroll:true});announce('Game paused.');
}
function resume(){
  if(disposed||document.hidden||phase!=='paused'||ui.scoreboard.open)return;
  const ready=unlock();accumulator=Math.min(accumulator,interval*.9);lastFrame=performance.now();setPhase('playing');audio.setPlaying(true);focusScene();announce('Game resumed.');
  void ready.then(()=>{if(!disposed&&phase==='playing'&&!document.hidden&&!ui.scoreboard.open)audio.play('resume');});
}
function togglePause(){if(phase==='playing')pause();else if(phase==='paused')void resume();}
function finish(limited=false){
  if(phase!=='playing')return;
  setPhase('over');runEndedAt=performance.now();audio.setPlaying(false);audio.play(game.won?'level':'death');renderer.burst(game.body[0],true);queued=[];
  ui['end-title'].textContent=game.won?'GRID CONQUERED.':limited?'GRID COMPLETE.':'SIGNAL LOST.';
  ui['end-eyebrow'].textContent=game.won?'ALL 432 CELLS. LEGENDARY.':limited?'MAXIMUM RUN LENGTH REACHED.':'GOOD RUN. GO AGAIN.';
  ui['end-score'].textContent=pad(game.score);ui['end-foods'].textContent=`${game.foods} ${game.foods===1?'BITE':'BITES'}`;ui['end-level'].textContent=`LEVEL ${String(1+Math.floor(game.foods/5)).padStart(2,'0')}`;
  ui['restart-button'].focus({preventScroll:true});announce(`Run complete. ${game.score} points, ${game.foods} bites.`);
  if(run?.unranked||!run?.runId){ui['save-status'].textContent='Unranked practice. Nothing is saved.';return;}
  submission={id:run.runId,epoch:run.epoch,playerId:run.player?.id,steps:game.steps,turns:game.turns.map(turn=>turn.slice()),score:game.score,foods:game.foods,busy:false};
  void save(submission);
}
async function save(pending){
  if(!pending||pending.busy)return;pending.busy=true;
  if(pending===submission){ui['retry-save'].hidden=true;ui['save-status'].textContent='Verifying your run…';}
  try{
    const result=await call('neon_coil_finish',{run_id:pending.id,steps:pending.steps,turns:pending.turns});
    if(disposed||pending!==submission)return;
    // Receipts are immutable snapshots, not current standings. Never let a late
    // receipt roll back a new run/epoch, regress a best, or truncate loaded pages.
    if(result.epoch!==pending.epoch||epoch!==pending.epoch||player?.id!==pending.playerId){
      ui['save-status'].textContent='The server session or player changed. This old run is not on the current leaderboard.';ui['retry-save'].hidden=true;return;
    }
    best=Math.max(best,Number(result.player?.best)||0);player={...player,best};ui.best.textContent=ui['board-best'].textContent=pad(best);
    ui['record-label'].hidden=!result.personalBest;
    ui['save-status'].textContent=result.personalBest?`New personal best · #${result.rank} on this server.`:`Verified · ${result.score.toLocaleString()} points. ${result.rank?`Your best is #${result.rank}.`:''}`;
    ui['retry-save'].hidden=true;
    if(ui.scoreboard.open)void refreshScores();
    // Deliberately do not copy scores/replays into conversation history via updateModelContext.
    // The score's only durable owner is the current MCP process's volatile memory.
  }catch(error){
    if(!disposed&&pending===submission){ui['save-status'].textContent=`Score not saved. ${error.message}`;ui['retry-save'].hidden=false;}
  }finally{pending.busy=false;}
}
function renderScores(){
  const ranked=scores.slice().sort((a,b)=>Number(b.score)-Number(a.score));ui['score-list'].replaceChildren();
  ranked.forEach((entry,index)=>{
    const row=document.createElement('li');row.className='score-row';row.classList.toggle('is-you',Boolean(entry.isYou||entry.id===player?.id));
    const place=document.createElement('span');place.className='place';place.textContent=String(entry.rank||index+1).padStart(2,'0');
    const name=document.createElement('span');name.className='player-name';name.textContent=entry.name||'Player';
    if(entry.isYou||entry.id===player?.id){const badge=document.createElement('span');badge.className='you-tag';badge.textContent='YOU';name.append(badge);}
    const points=document.createElement('span');points.className='player-score';points.textContent=Number(entry.score||0).toLocaleString();row.append(place,name,points);ui['score-list'].append(row);
  });
  ui['empty-scores'].hidden=ranked.length>0;ui['score-list'].hidden=ranked.length===0;
  ui['load-more-scores'].hidden=nextOffset===null||!connected;
  ui['board-player'].textContent=player?`${player.name} · YOUR BEST`:'YOUR PERSONAL BEST';ui['board-best'].textContent=pad(best);
  if(practice||!connected){ui['empty-title'].textContent='A live arcade, not a save file.';ui['empty-description'].textContent='Open this app through MCP to see authenticated players’ scores. Practice runs never enter the leaderboard.';ui['refresh-scores'].disabled=true;}
  else{ui['empty-title'].textContent='The top spot is yours.';ui['empty-description'].textContent='No scores on this grid yet. Play a run and make your mark.';ui['refresh-scores'].disabled=false;}
}
async function refreshScores(){
  if(!connected)return;const request=++scoreRequest;ui['refresh-scores'].disabled=true;
  try{const data=await call('neon_coil_scores');if(request===scoreRequest)updateIdentity(data);}
  catch(error){toast(error.message);}
  finally{if(request===scoreRequest)ui['refresh-scores'].disabled=false;}
}
async function loadMoreScores(){
  if(!connected||nextOffset===null)return;ui['load-more-scores'].disabled=true;
  const request=++scoreRequest, oldScores=scores, oldEpoch=epoch;
  try{
    const data=await call('neon_coil_scores',{offset:nextOffset,limit:50});
    if(request!==scoreRequest)return;
    if(data.epoch!==oldEpoch){await refreshScores();return;}
    const unique=new Map(oldScores.map(entry=>[entry.id,entry]));
    for(const entry of data.leaderboard||[])unique.set(entry.id,entry);
    updateIdentity({...data,leaderboard:Array.from(unique.values())});
  }catch(error){toast(error.message);}
  finally{ui['load-more-scores'].disabled=false;}
}
function openScores(){
  if(phase==='playing')pause('The grid is paused while you check the leaderboard.');
  void unlock().then(()=>{if(!disposed&&ui.scoreboard.open)audio.play('ui');});renderScores();ui.scoreboard.showModal();ui['close-scoreboard'].focus({preventScroll:true});void refreshScores();
}
function closeScores(){ui.scoreboard.close();audio.play('ui');if(phase==='paused')ui['resume-button'].focus({preventScroll:true});else if(phase==='over')ui['restart-button'].focus({preventScroll:true});else ui['leaderboard-button'].focus({preventScroll:true});}
function updateAudioButtons(){
  ui['sfx-button'].setAttribute('aria-pressed',String(audio.sfxEnabled));ui['sfx-button'].setAttribute('aria-label',audio.sfxEnabled?'Mute sound effects':'Unmute sound effects');
  ui['music-button'].setAttribute('aria-pressed',String(audio.musicEnabled));ui['music-button'].setAttribute('aria-label',audio.musicEnabled?'Mute music':'Unmute music');
}
async function toggleSfx(){await unlock();audio.setSfx(!audio.sfxEnabled);updateAudioButtons();if(audio.sfxEnabled)audio.play('ui');if(phase==='playing')focusScene();}
async function toggleMusic(){await unlock();audio.setMusic(!audio.musicEnabled);updateAudioButtons();audio.play('ui');if(phase==='playing')focusScene();}

ui['start-button'].addEventListener('click',start);ui['restart-button'].addEventListener('click',start);
ui['pause-button'].addEventListener('click',togglePause);ui['resume-button'].addEventListener('click',resume);
ui['leaderboard-button'].addEventListener('click',openScores);ui['end-leaderboard'].addEventListener('click',openScores);
ui['close-scoreboard'].addEventListener('click',closeScores);ui['refresh-scores'].addEventListener('click',refreshScores);ui['load-more-scores'].addEventListener('click',loadMoreScores);
ui.scoreboard.addEventListener('cancel',event=>{event.preventDefault();closeScores();});
ui.scoreboard.addEventListener('click',event=>{if(event.target===ui.scoreboard){const r=ui.scoreboard.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right)closeScores();}});
ui['sfx-button'].addEventListener('click',toggleSfx);ui['music-button'].addEventListener('click',toggleMusic);
ui['retry-save'].addEventListener('click',()=>save(submission));
ui['quality-button'].addEventListener('click',()=>{if(!renderer)return;const mode=renderer.cycleQuality();ui['quality-button'].textContent=`${mode.toUpperCase()} GRAPHICS`;ui['quality-button'].setAttribute('aria-label',`Graphics quality: ${mode}`);toast(mode==='auto'?'Adaptive resolution. Full-speed controls.':mode==='ultra'?'Ultra graphics · up to 2× pixel density.':'Lite graphics · same gameplay, less GPU work.');if(phase==='playing')focusScene();});
ui['swipe-hint'].hidden=!touchDevice;
ui.scene.addEventListener('pointerdown',()=>{if(phase==='playing')focusScene();});
let gesture=null;
ui.scene.addEventListener('pointerdown',event=>{if(event.pointerType==='mouse'||phase!=='playing')return;event.preventDefault();gesture={id:event.pointerId,x:event.clientX,y:event.clientY};ui.scene.setPointerCapture(event.pointerId);},{passive:false});
ui.scene.addEventListener('pointermove',event=>{
  if(!gesture||gesture.id!==event.pointerId||phase!=='playing')return;event.preventDefault();const dx=event.clientX-gesture.x,dy=event.clientY-gesture.y;
  if(Math.max(Math.abs(dx),Math.abs(dy))<12)return;
  const direction=Math.abs(dx)>Math.abs(dy)?dx>0?1:3:dy>0?2:0;
  queueDirection(direction);gesture.x=event.clientX;gesture.y=event.clientY;
},{passive:false});
for(const name of ['pointerup','pointercancel','lostpointercapture'])ui.scene.addEventListener(name,()=>gesture=null);
ui['touch-controls'].querySelectorAll('button').forEach(button=>button.addEventListener('pointerdown',event=>{event.preventDefault();queueDirection(Number(button.dataset.dir));focusScene();},{passive:false}));
const keyDirections={ArrowUp:0,KeyW:0,ArrowRight:1,KeyD:1,ArrowDown:2,KeyS:2,ArrowLeft:3,KeyA:3};
window.addEventListener('keydown',event=>{
  if(event.altKey||event.ctrlKey||event.metaKey||ui.scoreboard.open||event.target?.matches?.('input,textarea,select,[contenteditable="true"]'))return;
  if(Object.hasOwn(keyDirections,event.code)){
    if(phase==='playing'||phase==='starting'){event.preventDefault();if(!event.repeat)queueDirection(keyDirections[event.code]);}return;
  }
  if(event.repeat)return;
  if(event.code==='KeyM'){event.preventDefault();void toggleSfx();return;}
  if(event.code==='KeyN'){event.preventDefault();void toggleMusic();return;}
  const onButton=event.target?.closest?.('button');
  if((event.code==='Space'||event.code==='KeyP'||event.code==='Escape')&&(phase==='playing'||phase==='paused')){
    if(onButton&&event.code==='Space')return;event.preventDefault();togglePause();return;
  }
  if(event.code==='Enter'&&!onButton&&(phase==='intro'||phase==='over')){event.preventDefault();void start();}
},{capture:true});
function away(){awayGeneration++;gesture=null;if(phase==='playing')pause('Paused while you were away. Take a breath, then jump back in.');audio.suspend();}
window.addEventListener('blur',away);
document.addEventListener('visibilitychange',()=>{
  if(document.hidden){away();cancelAnimationFrame(raf);raf=0;}
  else{lastFrame=performance.now();if(!raf&&!disposed)raf=requestAnimationFrame(frame);}
});
function frame(now){
  if(disposed||document.hidden){raf=0;return;}
  const elapsed=lastFrame?now-lastFrame:16.67;lastFrame=now;
  renderer?.measure(elapsed,phase==='playing'||phase==='intro');
  if(phase==='playing'){
    // Never fast-forward after a suspended or severely stalled renderer.
    if(elapsed>350){pause('A frame took too long, so the game paused instead of jumping ahead.');}
    else{
      accumulator+=elapsed;let ticks=0;
      while(accumulator>=interval&&phase==='playing'&&ticks<4){
        accumulator-=interval;previous=game.body.map(cell=>cell.slice());
        const input=queued.shift();const direction=input?.direction??game.direction;
        const oldFood=game.food;const before=game.direction;const result=advance(game,direction);
        if(input){consumedInputMs+=Math.max(0,now-input.at);inputSamples++;}
        if(game.direction!==before)audio.play('turn');
        interval=stepMs(game.foods);
        if(result.ate){audio.play(game.foods%5===0?'level':'eat');renderer.burst(oldFood);hud();if(game.foods%5===0)announce(`Level ${1+Math.floor(game.foods/5)}. ${game.score} points.`);}
        if(result.dead||result.won||game.steps>=MAX_STEPS){previous=game.body.map(cell=>cell.slice());accumulator=interval;finish(game.steps>=MAX_STEPS&&!result.dead&&!result.won);}
        ticks++;
      }
      if(ticks===4&&accumulator>=interval)pause('Rendering slowed down. Paused to keep your next move fair.');
    }
  }
  const cameraSettling=renderer&&Math.abs(renderer.introMix-(renderer.intro?1:0))>.002;
  const animate=['intro','starting','playing'].includes(phase)||(phase==='over'&&now-runEndedAt<1100);
  if(animate||cameraSettling||renderer?.needsRender)renderer?.render(game,previous,game?Math.min(1,accumulator/interval):1,now/1000,Math.min(elapsed/1000,.05));
  raf=requestAnimationFrame(frame);
}
function dispose(){if(disposed)return;disposed=true;cancelAnimationFrame(raf);clearTimeout(toastTimer);audio.dispose();renderer?.dispose();queued=[];game=null;previous=null;scores=[];submission=null;run=null;}
app.onteardown=async()=>{dispose();return {};};
app.ontoolresult=result=>{if(connected||epoch||disposed)return;try{updateIdentity(readResult(result));}catch(error){toast(error.message);}};
app.onhostcontextchanged=context=>{if(context.displayMode)document.body.dataset.displayMode=context.displayMode;renderer?.resize();};
app.ontoolcancelled=()=>{if(phase==='starting'){startVersion++;setPhase('intro');ui['start-button'].disabled=false;toast('The request was cancelled. You can try again.');}};
window.addEventListener('pagehide',dispose,{once:true});
try{
  renderer=new NeonRenderer(ui.scene,restored=>{
    if(restored){ui['renderer-error'].hidden=true;renderer.resize();toast('Graphics restored. Resume when you’re ready.');}
    else{pause('The graphics context was interrupted.');audio.suspend();ui['renderer-error'].hidden=false;ui['renderer-error-message'].textContent='The graphics driver paused. Your run is on hold. If graphics do not recover, reopen the app.';}
  });
  raf=requestAnimationFrame(frame);
}catch{
  ui['renderer-error'].hidden=false;ui['start-button'].disabled=true;
}
// Read-only diagnostics help measure real rendering and input behavior, not a claimed FPS.
Object.defineProperty(window,'__NEON_COIL__',{value:Object.freeze({
  snapshot:()=>({phase,connected,practice:practice||Boolean(run?.unranked),score:game?.score??0,foods:game?.foods??0,steps:game?.steps??0,direction:game?.direction??1,head:game?.body[0]?.slice(),body:game?.body.map(c=>c.slice()),food:game?.food?.slice(),queue:queued.map(q=>q.direction),best,epoch,music:audio.musicEnabled,sfx:audio.sfxEnabled,dialogOpen:ui.scoreboard.open}),
  diagnostics:()=>({...renderer?.diagnostics(),inputSamples,meanInputToTickMs:inputSamples?consumedInputMs/inputSamples:0,elapsedRunMs:game?performance.now()-runStartedAt:0,networkInRenderLoop:false}),
}),writable:false,configurable:false});
async function connect(){
  if(practice){updateIdentity({});ui['start-button'].disabled=!renderer;return;}
  try{
    await app.connect(undefined,{timeout:12000});connected=true;
    updateIdentity(await call('neon_coil_scores'));ui['start-button'].disabled=!renderer;
    void requestFullscreen();
  }catch(error){
    // A broken bridge must never pretend to have saved a ranked score.
    practice=true;connected=false;updateIdentity({});ui['start-button'].disabled=!renderer;
    toast('Server connection unavailable. Practice is unranked; reopen the app to reconnect.');
  }
}
updateAudioButtons();setPhase('intro');void connect();
