// Browser integration tests against the isolated synthetic MCP bridge, never production.
// Requires agent-browser; build the App and run tests/fixtures/rally_ui_host.mjs first.
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { resolve } from 'node:path';
import { mkdir, writeFile } from 'node:fs/promises';
const exec=promisify(execFile),root=resolve(import.meta.dirname,'..');
const fixtureUrl='file://'+resolve(root,'artifacts/rally-qa.html');
const session=(await exec('agent-browser',['session','id','--scope','worktree','--prefix','rally-qa'])).stdout.trim();
const env={...process.env,AGENT_BROWSER_SESSION:session};
const checks=[],measurements={},screenshots=[];
async function browser(...args){
  const {stdout}=await exec('agent-browser',[...args,'--json'],{env,timeout:90000,maxBuffer:4*1024*1024});
  const result=JSON.parse(stdout);if(!result.success)throw new Error(`${args.join(' ')}: ${JSON.stringify(result.error)}`);
  return result.data;
}
// Some CLI wait implementations evaluate in the top frame even when eval/click
// use the selected frame. Resolve the owned fixture's document explicitly.
async function evaluate(code){const result=await browser('eval',`(()=>{const f=window.fixture||parent.fixture;const document=f.document(),win=f.window(),innerWidth=win.innerWidth,innerHeight=win.innerHeight,performance=win.performance;return (${code});})()`);return result.result;}
async function wait(condition){return browser('wait','--fn',`(()=>{const f=window.fixture||parent.fixture;const document=f.document();return (${condition});})()`);}
async function click(id){return browser('click',`#${id}`);}
async function check(name,fn){await fn();checks.push(name);console.log(`PASS ${name}`);}
async function snapshot(){return evaluate('f.app().snapshot()');}
async function open(width=1280,height=800){await browser('set','viewport',String(width),String(height));await browser('open',fixtureUrl);await browser('frame','#qa-app');await wait('f.app()?.snapshot().connected === true');}
async function capture(name){const path=resolve(root,`artifacts/${name}.png`);await browser('screenshot',path);screenshots.push(path);}
await mkdir(resolve(root,'artifacts'),{recursive:true});
try{
  await open();
  await check('real bundled SDK connects, opening starts no run and is silent',async()=>{
    const data=await evaluate('f.result()');assert.equal(data.state.phase,'intro');assert.equal(data.graphics.audio.contextState,'none');assert.equal(data.graphics.audio.timers,0);assert.deepEqual(data.calls,['rally_pong_scores']);assert.equal(data.graphics.threeVersion,'180');assert.equal(data.graphics.networkInRenderLoop,false);
  });
  await check('music and effects mute independently in a real AudioContext',async()=>{
    await click('sfx-button');await wait('f.app().diagnostics().audio.musicRunning');
    let a=await evaluate('f.app().diagnostics().audio');assert.equal(a.sfxEnabled,false);assert.equal(a.musicEnabled,true);assert.equal(a.voices.sfx,0);
    await click('music-button');a=await evaluate('f.app().diagnostics().audio');assert.equal(a.musicEnabled,false);assert.equal(a.sfxEnabled,false);assert.equal(a.timers,0);assert.equal(a.voices.music,0);
    await click('sfx-button');a=await evaluate('f.app().diagnostics().audio');assert.equal(a.musicEnabled,false);assert.equal(a.sfxEnabled,true);assert.equal(a.timers,0);
    await click('music-button');await wait('f.app().diagnostics().audio.musicRunning');assert.equal((await evaluate('f.app().diagnostics().audio')).timers,1);
  });
  await check('ranked start requests native fullscreen and responsive keys stop on release',async()=>{
    await click('start-button');await wait('f.app().snapshot().phase === "playing"');await evaluate('f.key("KeyW")');await wait('f.app().snapshot().playerY < -2000');await evaluate('f.key("KeyW","keyup")');
    const y=await evaluate('f.app().snapshot().playerY');await evaluate('new Promise(resolve=>setTimeout(()=>resolve(true),160))');const after=await snapshot();assert.ok(Math.abs(after.playerY-y)<=260);
    await evaluate('f.key("KeyP")');assert.equal((await snapshot()).phase,'paused');
    const data=await evaluate('f.result()');assert.deepEqual(data.displayModes,['fullscreen']);assert.equal(data.calls.filter(x=>x==='rally_pong_begin').length,1);assert.ok(data.graphics.inputSamples>0);measurements.inputToTickMs=data.graphics.meanInputToTickMs;assert.ok(measurements.inputToTickMs<150);
  });
  await check('pause freezes physics and silences audio without changing preferences',async()=>{
    const before=await snapshot();await evaluate('new Promise(resolve=>setTimeout(()=>resolve(true),220))');const after=await snapshot(),a=await evaluate('f.app().diagnostics().audio');assert.equal(after.steps,before.steps);assert.equal(a.timers,0);assert.equal(a.voices.music+a.voices.sfx,0);assert.equal(a.musicEnabled,true);assert.equal(a.sfxEnabled,true);
  });
  await check('leaderboard empty state, pagination, and names rendered as text',async()=>{
    await click('scores-button');await wait('f.app().snapshot().dialog === "scores"');assert.equal(await evaluate('document.querySelectorAll("#score-list li").length'),0);
    await evaluate('f.populate()');await evaluate('f.addSynthetic("<img src=x onerror=alert(1)>",9999)');await click('refresh-scores');await wait('document.querySelectorAll("#score-list li").length === 50');
    assert.equal(await evaluate('document.querySelectorAll("#score-list img").length'),0);assert.ok(await evaluate('document.querySelector("#score-list").textContent.includes("<img src=x onerror=alert(1)>")'));
    await click('more-scores');await wait('document.querySelectorAll("#score-list li").length === 66');await capture('rally-scoreboard-qa');await click('close-scores');assert.equal((await snapshot()).phase,'paused');
  });
  await check('how-to modal supports Escape and never silently resumes a match',async()=>{
    await click('help-button');await wait('f.app().snapshot().dialog === "help"');await browser('press','Escape');assert.equal((await snapshot()).dialog,null);assert.equal((await snapshot()).phase,'paused');
  });
  await check('touch/pointer controls map to the tilted court and blur pauses',async()=>{
    await click('resume-button');await wait('f.app().snapshot().phase === "playing"');
    await evaluate('(()=>{const el=document.querySelector("#scene"),r=el.getBoundingClientRect();el.dispatchEvent(new PointerEvent("pointerdown",{pointerId:71,pointerType:"touch",clientX:r.left+r.width*.4,clientY:r.top+r.height*.8,bubbles:true}));el.dispatchEvent(new PointerEvent("pointermove",{pointerId:71,pointerType:"touch",clientX:r.left+r.width*.4,clientY:r.top+r.height*.9,bubbles:true}));return true;})()');
    await wait('f.app().snapshot().playerY > 2000');const data=await snapshot();assert.equal(data.source,'pointer');assert.ok(data.target>=600);await evaluate('f.away()');assert.equal((await snapshot()).phase,'paused');assert.equal((await evaluate('f.app().diagnostics().audio')).timers,0);
  });
  await check('complete browser replay is accepted and best is recorded once',async()=>{
    await click('resume-button');await wait('f.app().snapshot().phase === "over" && !f.app().snapshot().pendingSave');
    const data=await evaluate('f.result()');assert.match(data.state.savedMessage,/^Verified/);assert.equal(data.calls.filter(x=>x==='rally_pong_finish').length,1);assert.equal(data.errors.length,0);measurements.completedRun=data.state;measurements.graphics=data.graphics;
  });
  await check('failed score save can retry the same complete replay safely',async()=>{
    await evaluate('f.failNextFinish=true');await click('again-button');await wait('f.app().snapshot().phase === "over" && !f.app().snapshot().pendingSave');assert.match((await snapshot()).savedMessage,/Score not saved/);await click('retry-save');await wait('f.app().snapshot().savedMessage.startsWith("Verified")');assert.equal((await evaluate('f.calls.filter(x=>x.name==="rally_pong_finish").length')),3);
  });
  await check('a begin response arriving after blur starts paused with no audio',async()=>{
    await click('home-button');await evaluate('f.delayBegin=true');await click('start-button');await wait('f.pending().begin === 1');await evaluate('f.away()');await evaluate('f.releaseBegin()');await wait('f.app().snapshot().phase === "paused"');assert.equal((await evaluate('f.app().diagnostics().audio')).timers,0);await evaluate('f.delayBegin=false');await click('leave-button');
  });
  await check('a stale begin cannot roll back a freshly observed server epoch',async()=>{
    await evaluate('f.delayBegin=true');await click('start-button');await wait('f.pending().begin === 1');await evaluate('f.restart()');await click('scores-button');await wait('f.app().snapshot().epoch.includes("restart")');const newEpoch=(await snapshot()).epoch;await evaluate('f.releaseBegin()');await wait('f.app().snapshot().phase === "intro"');assert.equal((await snapshot()).epoch,newEpoch);assert.equal((await snapshot()).best,0);await evaluate('f.delayBegin=false');await click('close-scores');
  });
  await check('restart plus a late finish receipt cannot restore an obsolete score',async()=>{
    await evaluate('f.delayFinish=true');await click('start-button');await wait('f.pending().finish === 1');await evaluate('f.restart()');await click('end-scores-button');await wait('f.app().snapshot().epoch.includes("restart")');await evaluate('f.releaseFinish()');await wait('!f.app().snapshot().pendingSave');
    const data=await snapshot();assert.equal(data.best,0);assert.equal(await evaluate('document.querySelectorAll("#score-list li").length'),0);assert.ok(!data.savedMessage.startsWith('Verified'));await evaluate('f.delayFinish=false');await click('close-scores');await click('home-button');
  });
  await check('application-only identity can practice without calling ranked mutations',async()=>{
    await evaluate('f.canPost=false');await click('scores-button');await wait('!f.app().snapshot().canPost');await click('close-scores');const before=await evaluate('f.calls.filter(x=>x.name!=="rally_pong_scores").length');await click('start-button');await wait('f.app().snapshot().phase === "playing"');assert.equal((await snapshot()).practice,true);assert.equal(await evaluate('f.calls.filter(x=>x.name!=="rally_pong_scores").length'),before);await evaluate('f.key("KeyP")');await click('leave-button');
  });
  for(const [width,height,label] of [[1440,900,'desktop'],[390,844,'phone'],[320,640,'compact-phone'],[844,390,'landscape']]){
    await open(width,height);
    await check(`${label}: viewport-filling layout, no clipped controls or network assets`,async()=>{
      const data=await evaluate('(()=>{const buttons=[...document.querySelectorAll("header button,#start-button,#practice-button")].filter(x=>x.getClientRects().length).map(x=>({id:x.id,box:x.getBoundingClientRect().toJSON()}));return {width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight,buttons,network:performance.getEntriesByType("resource").filter(x=>/^https?:/.test(x.name)).map(x=>x.name)};})()');
      assert.ok(data.scrollWidth<=data.width);assert.ok(data.scrollHeight<=data.height);assert.deepEqual(data.network,[]);for(const {id,box} of data.buttons){assert.ok(box.left>=-1&&box.right<=data.width+1,`${id} horizontally clipped`);assert.ok(box.top>=-1&&box.bottom<=data.height+1,`${id} vertically clipped`);}
      await capture(`rally-${label}-qa`);
      await click('practice-button');await wait('f.app().snapshot().phase === "playing"');await evaluate('f.key("KeyP")');assert.equal((await snapshot()).phase,'paused');
    });
  }
  await check('axe WCAG A/AA audit has no violations',async()=>{
    const report=await browser('a11y','--tags','wcag2a,wcag2aa');assert.equal(report.violations?.length,0);measurements.accessibility={counts:report.counts,incomplete:report.incomplete?.map(x=>x.id)};
  });
  measurements.runtimeErrors=await evaluate('f.errors');assert.deepEqual(measurements.runtimeErrors,[]);
  await writeFile(resolve(root,'artifacts/rally-browser-results.json'),JSON.stringify({checks,measurements,screenshots},null,2));
  console.log(`\n${checks.length} browser integration checks passed. Artifacts in artifacts/.`);
}catch(error){
  try{const diagnostics=await evaluate('f.result()');await writeFile(resolve(root,'artifacts/rally-browser-failure.json'),JSON.stringify(diagnostics,null,2));await capture('rally-browser-failure');}catch{}
  throw error;
}finally{await browser('close');}
