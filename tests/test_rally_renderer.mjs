import test from 'node:test';
import assert from 'node:assert/strict';
import { courtLayout } from '../src/catalog_app/tools/rally_pong/frontend/layout.js';

for (const [width,height] of [[1920,930],[1440,768],[1280,600],[1000,500],[760,550],[720,650],[390,650],[360,540],[320,450],[844,280],[667,240]]) {
  for (const intro of [false,true]) test(`court fits ${width}×${height}, ${intro?'intro':'playing'}`,()=>{
    const view=courtLayout(width,height,intro);
    assert.ok(Number.isFinite(view.viewHeight));assert.ok(view.scale>0);
    const b=view.bounds;
    assert.ok(b.left>=0&&b.right<=width);assert.ok(b.top>=0&&b.bottom<=height);
    assert.ok(view.worldWidth*view.scale<=b.right-b.left+.001);
    assert.ok(view.worldHeight*view.scale<=b.bottom-b.top+.001);
    const pitch=26/Math.hypot(26,19);
    const centerX=width/2-view.targetX*view.scale;
    const centerY=height/2-view.targetZ*view.scale*pitch;
    assert.ok(Math.abs(centerX-(b.left+b.right)/2)<1e-6);
    assert.ok(Math.abs(centerY-(b.top+b.bottom)/2)<1e-6);
    if(!intro){assert.equal(view.targetX,0);assert.equal(view.yaw,0);}
    if(intro&&width>720)assert.ok(centerX>width*.6);
  });
}
test('phone preview reserves room for readable heading and start controls',()=>{
  const view=courtLayout(390,700,true);assert.ok(view.bounds.top>=280);assert.equal(view.yaw,0);
});
test('live camera keeps input axes aligned',()=>{
  for(const [w,h] of [[1600,750],[390,700],[844,280]]){
    const view=courtLayout(w,h,false);assert.equal(view.targetX,0);assert.equal(view.yaw,0);
  }
});
test('zero layout during iframe mount stays finite',()=>{
  const view=courtLayout(0,0,false);
  for(const key of ['scale','viewHeight','targetX','targetZ'])assert.ok(Number.isFinite(view[key]));
});
