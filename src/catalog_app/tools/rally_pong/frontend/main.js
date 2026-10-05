import { App } from '@modelcontextprotocol/ext-apps';
import { CONSTANTS as C, createGame, advance } from './core.js';
import { RallyRenderer } from './renderer.js';
import { RallyAudio } from './audio.js';
import grotesk from '@fontsource/space-grotesk/files/space-grotesk-latin-500-normal.woff2';
import groteskBold from '@fontsource/space-grotesk/files/space-grotesk-latin-700-normal.woff2';
import mono from '@fontsource/space-mono/files/space-mono-latin-400-normal.woff2';

const fontStyle=document.createElement('style');
fontStyle.textContent=`@font-face{font-family:'Rally Grotesk';src:url('${grotesk}') format('woff2');font-weight:400 600;font-display:swap}@font-face{font-family:'Rally Grotesk';src:url('${groteskBold}') format('woff2');font-weight:700 900;font-display:swap}@font-face{font-family:'Rally Mono';src:url('${mono}') format('woff2');font-weight:400 700;font-display:swap}`;
document.head.append(fontStyle);
const $=id=>document.getElementById(id);
const ui=Object.fromEntries(['scene','start-button','start-label','practice-button','identity-label','arena-label','player-goals','ai-goals','clock','score','best','hits','rally-text','rally-badge','pause-button','pause-overlay','pause-reason','resume-button','leave-button','end-overlay','end-title','end-kicker','record-label','end-score','end-match','end-rally','end-hits','save-status','retry-save','again-button','home-button','scores-button','end-scores-button','scoreboard','close-scores','score-list','empty-scores','empty-title','empty-description','board-player','board-best','refresh-scores','more-scores','epoch-note','help-button','help','close-help','music-button','sfx-button','music-state','sfx-state','footer-state','connection-dot','quality-button','announcement','toast','graphics-error','graphics-message','countdown','point-callout','touch-hint'].map(id=>[id,$(id)]));
const app=new App({name:'Rally — After Hours',version:'1.0.0'},{availableDisplayModes:['inline','fullscreen']},{autoResize:false});
const audio=new RallyAudio();
const STEP_MS=1000/C.tickRate;
let renderer,phase='intro',connected=false,bridgeSettled=false,canPost=false,player=null,best=0,epoch=null,scores=[],nextOffset=null,totalPlayers=0;
let disposed=false,run=null,game=null,previous=null,submission=null,scoreRequest=0,startVersion=0,awayVersion=0,modalReturn=null;
let raf=0,lastFrame=0,accumulator=0,toastTimer=0,calloutTimer=0,bridgeTimer=0,fullscreenRequested=false;
let demo=createGame(17072),demoPrevious={...demo},demoSeed=17072,demoAccumulator=0;
let source='hold',target=0,pointerId=null,keys=new Set(),padAxis=0,padPause=false;
let inputAt=0,inputSerial=0,consumedSerial=0,inputLatency=0,inputSamples=0,runStartedAt=0,lastHud='',lastCountdown=-1;
let touchDevice=matchMedia('(pointer: coarse)').matches||navigator.maxTouchPoints>0;
const pad=(n,length=4)=>String(Math.max(0,Math.trunc(Number(n)||0))).padStart(length,'0');
const clamp=(n,a,b)=>Math.min(b,Math.max(a,n));
const modalOpen=()=>ui.scoreboard.open||ui.help.open;
function announce(text){ui.announcement.textContent=text;}
function toast(text){ui.toast.textContent=text;ui.toast.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>{ui.toast.hidden=true;},5000);}
function readResult(result){
  if(result?.isError)throw new Error(result.content?.filter(x=>x.type==='text').map(x=>x.text).join(' ')||'The arcade server could not complete this request.');
  let data=result?.structuredContent;
  if(!data&&result?.content)for(const item of result.content){if(item.type==='text'){try{data=JSON.parse(item.text);break;}catch{/* Text fallback need not be JSON. */}}}
  if(!data&&result&&('leaderboard' in result||'runId' in result||'error' in result))data=result;
  if(!data||typeof data!=='object')throw new Error('The arcade returned an unreadable response.');
  if(data.error){const error=new Error(data.error.message||'This arcade request was rejected.');error.code=data.error.code;error.data=data;throw error;}
  return data;
}
async function call(name,args={}){return readResult(await app.callServerTool({name,arguments:args},{timeout:20000}));}
function markUnranked(message){
  if(run&&!run.unranked){run.unranked=true;toast(message);}
  if(submission){submission.invalidated=true;ui['retry-save'].hidden=true;if(phase==='over')ui['save-status'].textContent=message;}
}
function applyOverview(data,{replaceScores=true}={}){
  if(disposed)return;
  const changedEpoch=Boolean(epoch&&data.epoch&&data.epoch!==epoch);
  const changedPlayer=Boolean(player?.id&&'player' in data&&data.player?.id!==player.id);
  if(changedEpoch||changedPlayer){best=0;scores=[];nextOffset=null;markUnranked(changedEpoch?'The server restarted. This match is now practice; start a new ranked run to post.':'The signed-in player changed. This match is now practice.');}
  if(data.epoch)epoch=data.epoch;
  if('player' in data)player=data.player;
  if('canPost' in data)canPost=Boolean(data.canPost);
  best=player?Math.max(best,Number(player.best)||0):0;
  if(replaceScores&&Array.isArray(data.leaderboard)){scores=data.leaderboard;nextOffset=data.nextOffset??null;totalPlayers=data.totalPlayers??scores.length;}
  syncIdentity();renderScores();
}
function syncIdentity(){
  ui['best'].textContent=ui['board-best'].textContent=player?pad(best):'—';
  ui['connection-dot'].classList.toggle('live',connected);
  if(connected&&canPost&&player){
    ui['identity-label'].textContent=`Playing as ${player.name} · ranked scores live in RAM`;
    if(phase!=='starting')ui['start-label'].textContent='TAKE THE COURT';
  }else if(connected){
    ui['identity-label'].textContent='Practice is open. A signed-in user is required for ranked scores.';
    if(phase!=='starting')ui['start-label'].textContent='PLAY PRACTICE';
  }else{
    ui['identity-label'].textContent=bridgeSettled?'Offline practice · open through MCP for ranked scores.':'Connecting… or warm up with an unranked practice match.';
    if(phase!=='starting')ui['start-label'].textContent=bridgeSettled?'PLAY PRACTICE':'CONNECTING…';
  }
  ui['start-button'].disabled=!renderer||renderer.lost||(!connected&&!bridgeSettled)||phase==='starting';
  ui['practice-button'].disabled=!renderer||renderer.lost||phase==='starting';
  ui['again-button'].disabled=!renderer||renderer.lost||phase==='starting';
  ui['arena-label'].textContent=['playing','paused','over'].includes(phase)?run?.unranked?'PRACTICE / NO SCORE POSTED':'RANKED / REPLAY VERIFIED':'THE MIDNIGHT CIRCUIT';
  ui['footer-state'].textContent=['playing','paused','over'].includes(phase)?(run?.unranked?'PRACTICE · NO SCORES SAVED':'RANKED RUN · SCORES IN MEMORY'):connected?'LIVE SERVER · SCORES IN MEMORY':bridgeSettled?'PRACTICE · NO SCORES SAVED':'CONNECTING TO THE CLUB';
}
function syncAudio(){
  ui['music-button'].setAttribute('aria-pressed',String(audio.musicEnabled));
  ui['music-button'].setAttribute('aria-label',audio.musicEnabled?'Mute music':'Unmute music');
  ui['sfx-button'].setAttribute('aria-pressed',String(audio.sfxEnabled));
  ui['sfx-button'].setAttribute('aria-label',audio.sfxEnabled?'Mute sound effects':'Unmute sound effects');
  ui['music-state'].textContent=audio.musicEnabled?'On':'Off';ui['sfx-state'].textContent=audio.sfxEnabled?'On':'Off';
  const diag=audio.diagnostics();document.body.dataset.audible=String(Boolean(diag.musicRunning&&audio.musicEnabled));
  if(!audio.available){ui['music-button'].disabled=ui['sfx-button'].disabled=true;ui['music-button'].title=ui['sfx-button'].title='Web Audio is unavailable; gameplay is still available.';}
}
function unlock(){const ready=audio.unlock();void ready.then(syncAudio);return ready;}
function toggleMusic(){audio.setMusic(!audio.musicEnabled);syncAudio();void unlock();if(phase==='playing')focusCourt();}
function toggleSfx(){audio.setSfx(!audio.sfxEnabled);syncAudio();void unlock().then(()=>{if(audio.sfxEnabled)audio.play('ui');});if(phase==='playing')focusCourt();}
function focusCourt(){ui.scene.focus({preventScroll:true});}
function resetInput(){keys.clear();source='hold';target=game?Math.round(game.playerY/C.paddleLimit*1000):0;pointerId=null;padAxis=0;inputAt=0;}
function setPhase(value){
  phase=value;document.body.dataset.phase=value;ui['pause-overlay'].hidden=value!=='paused';ui['end-overlay'].hidden=value!=='over';
  ui['pause-button'].hidden=!['playing','paused'].includes(value);ui['pause-button'].setAttribute('aria-label',value==='paused'?'Resume game':'Pause game');
  ui['touch-hint'].hidden=!touchDevice||value!=='playing';renderer?.setIntro(value==='intro'||value==='starting');
  if(value!=='playing')ui.countdown.hidden=true;
  syncIdentity();
}
async function requestFullscreen(){
  if(fullscreenRequested||!connected)return;
  const context=app.getHostContext();
  if(context?.availableDisplayModes?.includes('fullscreen')&&context.displayMode!=='fullscreen'){
    fullscreenRequested=true;
    try{await app.requestDisplayMode({mode:'fullscreen'});}catch{fullscreenRequested=false;/* Native host Fullscreen remains available. */}
  }
}
async function start(forcePractice=false){
  if(disposed||phase==='starting'||phase==='playing'||!renderer||renderer.lost)return;
  audio.setActive(true);const audioReady=unlock();void requestFullscreen();
  const version=++startVersion,away=awayVersion,oldPhase=phase,startEpoch=epoch,startPlayer=player?.id;
  scoreRequest++;resetInput();setPhase('starting');ui['start-label'].textContent='OPENING…';
  try{
    let issued;
    if(!forcePractice&&connected&&canPost){issued=await call('rally_pong_begin');issued.unranked=false;}
    else{const seed=new Uint32Array(1);crypto.getRandomValues(seed);issued={seed:seed[0],runId:null,unranked:true};}
    if(disposed||version!==startVersion)return;
    scoreRequest++;
    if(!issued.unranked){
      if((epoch!==startEpoch&&issued.epoch!==epoch)||(player?.id!==startPlayer&&issued.player?.id!==player?.id)){
        throw new Error('The server session or signed-in player changed while the court opened. Start a fresh ranked match.');
      }
      applyOverview(issued);
      if(issued.constants?.version!==undefined&&issued.constants.version!==C.version)throw new Error('This court was updated. Reopen the App before starting a ranked run.');
    }
    run=issued;game=createGame(issued.seed);previous={...game};submission=null;accumulator=0;lastFrame=performance.now();runStartedAt=lastFrame;
    inputLatency=inputSamples=inputSerial=consumedSerial=0;lastHud='';lastCountdown=-1;resetInput();
    ui['record-label'].hidden=true;ui['retry-save'].hidden=true;ui['point-callout'].hidden=true;clearTimeout(calloutTimer);
    setPhase('playing');hud();
    if(document.hidden||away!==awayVersion||modalOpen())pause('Your court is ready. Resume when you’re back at the controls.');
    else{focusCourt();announce(`${run.unranked?'Practice':'Ranked'} match started. You are the mint paddle on the left. First to seven.`);}
    void audioReady.then(()=>{if(!disposed&&phase==='playing'&&!document.hidden)audio.play('ui');syncAudio();});
  }catch(error){
    if(disposed||version!==startVersion)return;
    setPhase(oldPhase==='over'?'over':'intro');toast(error.message);if(error.data?.epoch&&error.data.epoch!==epoch)applyOverview(error.data);
  }finally{if(!disposed&&version===startVersion)syncIdentity();}
}
function pause(reason='The court can wait. Your rally stays right here.'){
  if(phase!=='playing')return;
  resetInput();setPhase('paused');ui['pause-reason'].textContent=reason;audio.setActive(false);syncAudio();ui['resume-button'].focus({preventScroll:true});announce('Game paused.');
}
function resume(){
  if(disposed||document.hidden||phase!=='paused'||modalOpen()||renderer?.lost)return;
  resetInput();accumulator=0;lastCountdown=-1;lastFrame=performance.now();audio.setActive(true);void unlock();setPhase('playing');focusCourt();announce('Game resumed.');
}
function togglePause(){if(phase==='playing')pause();else if(phase==='paused')resume();}
function home(){
  if(disposed)return;
  startVersion++;scoreRequest++;resetInput();run=game=previous=submission=null;accumulator=0;lastHud='';
  ui['point-callout'].hidden=true;clearTimeout(calloutTimer);setPhase('intro');audio.setActive(true);void unlock();syncAudio();ui['start-button'].focus({preventScroll:true});
}
function hud(){
  if(!game)return;
  const remaining=Math.max(0,Math.ceil((C.maxSteps-game.steps)/C.tickRate));
  const signature=[game.score,game.playerGoals,game.aiGoals,remaining,game.hits,game.rally].join('/');
  if(signature!==lastHud){
    lastHud=signature;ui['player-goals'].textContent=String(game.playerGoals);ui['ai-goals'].textContent=String(game.aiGoals);
    ui.score.textContent=pad(game.score);ui.hits.textContent=pad(game.hits,2);ui.clock.textContent=`${Math.floor(remaining/60)}:${pad(remaining%60,2)}`;
    ui['rally-text'].textContent=game.rally>1?`${pad(game.rally,2)} HIT RALLY`:'FIND YOUR RHYTHM';
    Array.from(ui['rally-badge'].querySelectorAll('i')).forEach((item,i)=>item.classList.toggle('lit',game.rally>i));
  }
  const count=game.serveTicks>0?Math.ceil(game.serveTicks/30):0;
  if(count!==lastCountdown){
    lastCountdown=count;ui.countdown.hidden=!count||phase!=='playing';
    if(count){const small=document.createElement('small');small.textContent=game.playerGoals+game.aiGoals?'NEXT SERVE':'FIND YOUR RHYTHM';ui.countdown.replaceChildren(document.createTextNode(String(count)),small);}
  }
}
function point(event){
  const yours=event.goal==='player';ui['point-callout'].textContent=yours?'YOUR POINT. +100':'THE HOUSE SCORES.';ui['point-callout'].style.color=yours?'var(--mint)':'var(--coral)';ui['point-callout'].hidden=false;
  clearTimeout(calloutTimer);calloutTimer=setTimeout(()=>{ui['point-callout'].hidden=true;},1000);
  announce(`${yours?'Your point':'The house scores'}. ${game.playerGoals} to ${game.aiGoals}.`);
}
function finish(){
  if(phase!=='playing')return;
  resetInput();setPhase('over');audio.play(game.won?'win':'lose');
  ui['end-title'].textContent=game.won?'The night is yours.':game.endedByLimit?'Right on time.':'One more, surely.';
  ui['end-kicker'].textContent=game.won?'YOU BEAT THE HOUSE':game.endedByLimit?'TWO MINUTES. ALL HEART.':'THE HOUSE TAKES THIS ONE';
  ui['end-score'].textContent=pad(game.score);ui['end-match'].textContent=`YOU ${game.playerGoals} — ${game.aiGoals} HOUSE`;ui['end-rally'].textContent=String(game.bestRally);ui['end-hits'].textContent=String(game.hits);
  ui['again-button'].focus({preventScroll:true});announce(`Match complete. ${game.score} points, ${game.playerGoals} to ${game.aiGoals}.`);
  if(run?.unranked||!run?.runId){ui['save-status'].textContent='Practice complete. No score was posted.';return;}
  submission={id:run.runId,epoch:run.epoch,playerId:run.player?.id,steps:game.steps,inputs:game.inputs.map(input=>input.slice()),busy:false,invalidated:false};
  void save(submission);
}
async function save(pending){
  if(!pending||pending.busy||pending.invalidated)return;
  pending.busy=true;if(pending===submission){ui['retry-save'].hidden=true;ui['save-status'].textContent='Replaying and verifying your match…';}
  try{
    const result=await call('rally_pong_finish',{run_id:pending.id,steps:pending.steps,inputs:pending.inputs});
    if(disposed||pending!==submission)return;
    if(result.epoch!==pending.epoch||epoch!==pending.epoch||player?.id!==pending.playerId||pending.invalidated){
      ui['save-status'].textContent='The server session or player changed. This old match is not on the current board.';ui['retry-save'].hidden=true;return;
    }
    // A receipt is an immutable historical response, never a fresh leaderboard.
    best=Math.max(best,Number(result.player?.best)||0);player={...player,best};syncIdentity();
    ui['record-label'].hidden=!result.personalBest;
    ui['save-status'].textContent=`Verified · ${Number(result.score).toLocaleString()} points.${result.rank?` Your best is #${result.rank} on this server.`:''}`;
    ui['retry-save'].hidden=true;if(ui.scoreboard.open)void refreshScores();
    // Scores/replays are deliberately not copied into localStorage or model context.
  }catch(error){
    if(disposed||pending!==submission)return;
    if(error.data?.epoch&&error.data.epoch!==pending.epoch){applyOverview(error.data);pending.invalidated=true;}
    ui['save-status'].textContent=`Score not saved. ${error.message}`;ui['retry-save'].hidden=Boolean(pending.invalidated||error.code==='unavailable_run'||error.code==='ineligible');
  }finally{pending.busy=false;}
}
function renderScores(){
  ui['score-list'].replaceChildren();
  scores.forEach((entry,index)=>{
    const row=document.createElement('li');row.className='score-row';row.classList.toggle('is-you',Boolean(entry.isYou||entry.id===player?.id));
    const place=document.createElement('span');place.className='place';place.textContent=pad(entry.rank||index+1,2);
    const name=document.createElement('span');name.className='player-name';name.textContent=entry.name||'Player';
    if(entry.isYou||entry.id===player?.id){const tag=document.createElement('span');tag.className='you-tag';tag.textContent='YOU';name.append(tag);}
    const score=document.createElement('span');score.className='player-score';score.textContent=Number(entry.score||0).toLocaleString();row.append(place,name,score);ui['score-list'].append(row);
  });
  ui['empty-scores'].hidden=scores.length>0;ui['score-list'].hidden=scores.length===0;
  ui['more-scores'].hidden=nextOffset===null||!connected;ui['refresh-scores'].disabled=!connected;
  ui['board-player'].textContent=player?`${player.name} / YOUR PERSONAL BEST`:'YOUR PERSONAL BEST';ui['board-best'].textContent=player?pad(best):'—';
  ui['empty-title'].textContent=connected?'Make the first impression.':'The live board is at the club.';
  ui['empty-description'].textContent=connected?'No high scores yet. Take the court and set the tone for tonight.':'Open through MCP to see signed-in players’ high scores. Offline practice never posts a score.';
  ui['epoch-note'].textContent=connected?`${totalPlayers} ranked player${totalPlayers===1?'':'s'} · ties keep the first-achieved order · this server process only.`:'Scores exist only in the live server’s memory. No local score files.';
}
async function refreshScores(){
  if(!connected)return;const request=++scoreRequest;ui['refresh-scores'].disabled=true;
  try{const data=await call('rally_pong_scores');if(!disposed&&request===scoreRequest)applyOverview(data);}
  catch(error){if(!disposed&&request===scoreRequest)toast(error.message);}
  finally{if(!disposed&&request===scoreRequest)ui['refresh-scores'].disabled=false;}
}
async function moreScores(){
  if(!connected||nextOffset===null||ui['more-scores'].disabled)return;
  const request=++scoreRequest,oldScores=scores,oldEpoch=epoch;ui['more-scores'].disabled=true;
  try{
    const data=await call('rally_pong_scores',{offset:nextOffset,limit:50});if(disposed||request!==scoreRequest)return;
    if(data.epoch!==oldEpoch){await refreshScores();return;}
    const byId=new Map(oldScores.map(entry=>[entry.id,entry]));for(const entry of data.leaderboard||[])byId.set(entry.id,entry);
    applyOverview({...data,leaderboard:[...byId.values()]});
  }catch(error){if(!disposed)toast(error.message);}
  finally{ui['more-scores'].disabled=false;}
}
function openModal(which,trigger){
  if(modalOpen())return;modalReturn=trigger;
  if(phase==='playing')pause('The match is paused while you’re off the court.');
  resetInput();which.showModal();
  if(which===ui.scoreboard){renderScores();ui['close-scores'].focus({preventScroll:true});void refreshScores();}
  else ui['close-help'].focus({preventScroll:true});
  if(phase!=='paused')void unlock().then(()=>audio.play('ui'));
}
function closeModal(which){
  which.close();if(phase==='paused')ui['resume-button'].focus({preventScroll:true});else modalReturn?.focus({preventScroll:true});modalReturn=null;
}
function markInput(){inputAt=performance.now();inputSerial++;}
function effectiveTarget(){
  if(source==='keyboard'){
    const up=keys.has('ArrowUp')||keys.has('KeyW'),down=keys.has('ArrowDown')||keys.has('KeyS');
    return up&&!down?-1000:down&&!up?1000:Math.round(game.playerY/C.paddleLimit*1000);
  }
  if(source==='gamepad')return clamp(Math.round((game.playerY+padAxis*C.playerSpeed)/C.paddleLimit*1000),-1000,1000);
  return target;
}
function pollGamepad(){
  if(!navigator.getGamepads)return;
  let pads;try{pads=navigator.getGamepads();}catch{return;}
  const pad=Array.from(pads).find(p=>p?.connected);if(!pad){if(source==='gamepad'){source='hold';target=game?Math.round(game.playerY/C.paddleLimit*1000):0;}padPause=false;return;}
  const pausePressed=Boolean(pad.buttons[9]?.pressed);if(pausePressed&&!padPause&&!modalOpen())togglePause();padPause=pausePressed;
  if(phase!=='playing')return;
  const raw=pad.buttons[12]?.pressed?-1:pad.buttons[13]?.pressed?1:pad.axes[1]||0;
  const value=Math.abs(raw)>.13?clamp(raw,-1,1):0;
  if(value||source==='gamepad'){if(value!==padAxis)markInput();source='gamepad';padAxis=value;}
}
ui['start-button'].addEventListener('click',()=>start(false));ui['practice-button'].addEventListener('click',()=>start(true));
ui['again-button'].addEventListener('click',()=>start(Boolean(run?.unranked)));ui['home-button'].addEventListener('click',home);ui['leave-button'].addEventListener('click',home);
ui['pause-button'].addEventListener('click',togglePause);ui['resume-button'].addEventListener('click',resume);
ui['scores-button'].addEventListener('click',()=>openModal(ui.scoreboard,ui['scores-button']));ui['end-scores-button'].addEventListener('click',()=>openModal(ui.scoreboard,ui['end-scores-button']));
ui['help-button'].addEventListener('click',()=>openModal(ui.help,ui['help-button']));ui['close-scores'].addEventListener('click',()=>closeModal(ui.scoreboard));ui['close-help'].addEventListener('click',()=>closeModal(ui.help));
for(const modal of [ui.scoreboard,ui.help]){
  modal.addEventListener('cancel',event=>{event.preventDefault();closeModal(modal);});
  modal.addEventListener('click',event=>{if(event.target!==modal)return;const b=modal.getBoundingClientRect();if(event.clientX<b.left||event.clientX>b.right||event.clientY<b.top||event.clientY>b.bottom)closeModal(modal);});
}
ui['refresh-scores'].addEventListener('click',refreshScores);ui['more-scores'].addEventListener('click',moreScores);ui['retry-save'].addEventListener('click',()=>save(submission));
ui['music-button'].addEventListener('click',toggleMusic);ui['sfx-button'].addEventListener('click',toggleSfx);
ui['quality-button'].addEventListener('click',()=>{if(!renderer)return;const mode=renderer.cycleQuality();ui['quality-button'].textContent=`${mode.toUpperCase()} / FX`;ui['quality-button'].setAttribute('aria-label',`Graphics quality: ${mode}`);toast(mode==='lite'?'Lighter graphics. Same quick controls.':mode==='high'?'High-resolution graphics.':'Automatic resolution, tuned to your device.');if(phase==='playing')focusCourt();});
ui.scene.addEventListener('pointerdown',event=>{
  if(phase!=='playing'||modalOpen())return;event.preventDefault();focusCourt();void unlock();
  pointerId=event.pointerId;source='pointer';target=renderer.screenToTarget(event.clientX,event.clientY);markInput();
  try{ui.scene.setPointerCapture(event.pointerId);}catch{/* Pointer motion still works within the court. */}
},{passive:false});
ui.scene.addEventListener('pointermove',event=>{
  if(phase!=='playing'||modalOpen()||(event.pointerType!=='mouse'&&event.pointerId!==pointerId))return;
  if(event.pointerType!=='mouse')event.preventDefault();
  const next=renderer.screenToTarget(event.clientX,event.clientY);if(source!=='pointer'||next!==target){source='pointer';target=next;markInput();}
},{passive:false});
for(const type of ['pointerup','pointercancel','lostpointercapture'])ui.scene.addEventListener(type,event=>{if(pointerId===event.pointerId)pointerId=null;});
window.addEventListener('keydown',event=>{
  if(event.altKey||event.ctrlKey||event.metaKey||modalOpen()||event.target?.matches?.('input,textarea,select,[contenteditable="true"]'))return;
  if(['ArrowUp','ArrowDown','KeyW','KeyS'].includes(event.code)){
    if(phase==='playing'){event.preventDefault();keys.add(event.code);source='keyboard';if(!event.repeat)markInput();}return;
  }
  if(event.repeat)return;
  if(event.code==='KeyM'){event.preventDefault();toggleMusic();return;}
  if(event.code==='KeyN'){event.preventDefault();toggleSfx();return;}
  const button=event.target?.closest?.('button');
  if(['Space','KeyP','Escape'].includes(event.code)&&['playing','paused'].includes(phase)){
    if(event.code==='Space'&&button)return;event.preventDefault();togglePause();return;
  }
  if(event.code==='Enter'&&!button&&['intro','over'].includes(phase)){event.preventDefault();void start(phase==='over'&&Boolean(run?.unranked));}
},{capture:true});
window.addEventListener('keyup',event=>{if(keys.delete(event.code)){if(phase==='playing'&&source==='keyboard')markInput();}});
function away(){awayVersion++;resetInput();if(phase==='playing')pause('Paused while you were away. The next return is still yours.');audio.suspend();syncAudio();}
window.addEventListener('blur',away);
window.addEventListener('focus',()=>{if(!disposed&&phase==='intro'){audio.setActive(true);syncAudio();}});
document.addEventListener('visibilitychange',()=>{
  if(document.hidden){away();cancelAnimationFrame(raf);raf=0;}
  else{lastFrame=performance.now();if(!raf&&!disposed)raf=requestAnimationFrame(frame);}
});
function frame(now){
  if(disposed||document.hidden){raf=0;return;}
  const elapsed=lastFrame?now-lastFrame:16.67;lastFrame=now;
  const active=['playing','intro','starting'].includes(phase);renderer?.measure(elapsed,active);pollGamepad();
  if(phase==='playing'){
    if(elapsed>300)pause('A frame took too long, so the match paused instead of jumping ahead.');
    else{
      accumulator+=elapsed;let ticks=0;
      while(accumulator>=STEP_MS&&phase==='playing'&&ticks<24){
        accumulator-=STEP_MS;previous={...game};const event=advance(game,effectiveTarget());
        if(inputSerial!==consumedSerial&&inputAt){inputLatency+=Math.max(0,performance.now()-inputAt);inputSamples++;consumedSerial=inputSerial;}
        if(previous.serveTicks>0&&game.serveTicks===0)audio.play('serve');
        if(event.playerHit)audio.play('paddle',{rally:game.rally});else if(event.aiHit)audio.play('rival',{rally:game.rally});
        if(event.wall)audio.play('wall');
        if(event.playerHit||event.aiHit||event.wall||event.goal)renderer?.burst(event,event.goal?previous:game);
        if(event.goal){audio.play(event.goal==='player'?'goal':'miss');point(event);}
        if(event.ended)finish();ticks++;
      }
      if(phase==='playing'&&accumulator>=STEP_MS&&ticks===24)pause('Rendering slowed down. Paused to keep the next return fair.');
      hud();
    }
  }else if(phase==='intro'||phase==='starting'){
    demoAccumulator+=Math.min(elapsed,80);let ticks=0;
    while(demoAccumulator>=STEP_MS&&ticks++<16){demoAccumulator-=STEP_MS;demoPrevious={...demo};advance(demo,clamp(Math.round((demo.ballY+(demo.vx<0?demo.vy*6:0))/C.paddleLimit*1000),-1000,1000));if(!demo.alive){demo=createGame(++demoSeed);demoPrevious={...demo};}}
  }
  const intro=phase==='intro'||phase==='starting';
  const settling=renderer&&Math.abs(renderer.introMix-(renderer.intro?1:0))>.001;
  if(active||settling||renderer?.needsRender)renderer?.render(intro?demo:game,intro?demoPrevious:previous,intro?Math.min(1,demoAccumulator/STEP_MS):phase==='playing'?Math.min(1,accumulator/STEP_MS):1,now/1000,Math.min(elapsed/1000,.05));
  raf=requestAnimationFrame(frame);
}
function dispose(){
  if(disposed)return;disposed=true;startVersion++;scoreRequest++;cancelAnimationFrame(raf);clearTimeout(toastTimer);clearTimeout(calloutTimer);clearTimeout(bridgeTimer);
  audio.dispose();renderer?.dispose();keys.clear();game=previous=run=submission=demo=demoPrevious=null;scores=[];
}
app.onteardown=async()=>{dispose();return {};};
app.ontoolresult=result=>{if(disposed||connected&&epoch)return;try{applyOverview(readResult(result));}catch(error){toast(error.message);}};
app.onhostcontextchanged=context=>{
  if(context.displayMode)document.body.dataset.displayMode=context.displayMode;
  touchDevice=touchDevice||Boolean(context.deviceCapabilities?.touch);ui['touch-hint'].hidden=!touchDevice||phase!=='playing';renderer?.resize();
};
app.ontoolcancelled=()=>{if(phase==='starting'){startVersion++;setPhase('intro');toast('The request was cancelled. Your next match is ready when you are.');}};
window.addEventListener('pagehide',dispose,{once:true});
try{
  renderer=new RallyRenderer(ui.scene,restored=>{
    if(restored){ui['graphics-error'].hidden=true;renderer.resize();syncIdentity();toast('Court restored. Resume when you’re ready.');}
    else{pause('Your graphics driver interrupted the court.');audio.suspend();ui['graphics-error'].hidden=false;ui['graphics-message'].textContent='The graphics driver paused. Your match is on hold. If the lights don’t come back, reopen the App. You can still read the leaderboard.';syncIdentity();}
  });
  raf=requestAnimationFrame(frame);
}catch(error){ui['graphics-error'].hidden=false;ui['graphics-message'].textContent='This court needs WebGL 2. Enable hardware acceleration or try another browser, then reopen the App. The leaderboard still works.';}
Object.defineProperty(window,'__RALLY_PONG__',{value:Object.freeze({
  snapshot:()=>({phase,connected,canPost,practice:Boolean(run?.unranked),steps:game?.steps??0,score:game?.score??0,playerGoals:game?.playerGoals??0,aiGoals:game?.aiGoals??0,hits:game?.hits??0,rally:game?.rally??0,bestRally:game?.bestRally??0,playerY:game?.playerY??0,aiY:game?.aiY??0,ballX:game?.ballX??0,ballY:game?.ballY??0,vx:game?.vx??0,vy:game?.vy??0,serveTicks:game?.serveTicks??0,target,source,best,epoch,music:audio.musicEnabled,sfx:audio.sfxEnabled,dialog:ui.scoreboard.open?'scores':ui.help.open?'help':null,pendingSave:Boolean(submission?.busy),savedMessage:ui['save-status'].textContent}),
  diagnostics:()=>({...renderer?.diagnostics(),inputSamples,meanInputToTickMs:inputSamples?inputLatency/inputSamples:0,tickRate:C.tickRate,elapsedRunMs:game?performance.now()-runStartedAt:0,networkInRenderLoop:false,audio:audio.diagnostics()}),
})});
syncAudio();syncIdentity();renderScores();
if(window.parent===window){bridgeSettled=true;syncIdentity();}
else{
  bridgeTimer=setTimeout(()=>{if(!connected&&!disposed){bridgeSettled=true;syncIdentity();toast('The server is taking a moment. Practice is available while it connects.');}},7000);
  void app.connect().then(async()=>{
    if(disposed)return;clearTimeout(bridgeTimer);connected=true;bridgeSettled=true;
    const context=app.getHostContext();if(context?.displayMode)document.body.dataset.displayMode=context.displayMode;
    touchDevice=touchDevice||Boolean(context?.deviceCapabilities?.touch);syncIdentity();
    await refreshScores();
  }).catch(()=>{if(!disposed){clearTimeout(bridgeTimer);bridgeSettled=true;connected=false;syncIdentity();renderScores();toast('The bridge is unavailable. Practice works; ranked scores need a live MCP connection.');}});
}
