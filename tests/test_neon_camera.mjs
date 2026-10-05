import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { NeonRenderer } from '../src/catalog_app/tools/neon_coil/frontend/renderer.js';

// Reuse the frontend's pinned Three.js dependency without a WebGL/DOM context.
const require=createRequire(new URL('../src/catalog_app/tools/neon_coil/frontend/package.json',import.meta.url));
const { OrthographicCamera, Vector3 }=require('three');
const sizes=[[1440,860],[1024,668],[844,320],[720,600],[390,752],[320,480],[1920,980]];
function cameraView(width,height,introMix=0,touchControls=width<721){
  const view={width,height,mobile:width<721,touchControls,introMix,camera:new OrthographicCamera(-20,20,12,-12,.1,150)};
  NeonRenderer.prototype.updateCamera.call(view);
  view.camera.updateMatrixWorld(true);
  return view;
}
for(const [width,height] of sizes){
  for(const introMix of [0,.5,1]){
    test(`grid stays straight and visible at ${width}×${height}, intro=${introMix}`,()=>{
      const view=cameraView(width,height,introMix);
      const project=(x,z)=>new Vector3(x,0,z).project(view.camera);
      const center=project(0,0),right=project(1,0),down=project(0,1);
      assert.ok(Math.abs(right.y-center.y)<1e-10,'horizontal movement must not drift vertically');
      assert.ok(Math.abs(down.x-center.x)<1e-10,'vertical movement must not drift sideways');
      assert.ok(right.x>center.x,'right arrow must move right on screen');
      assert.ok(down.y<center.y,'down arrow must move down on screen');
      const forward=view.camera.getWorldDirection(new Vector3());
      assert.ok(forward.y<-.5&&forward.z<-.3,'preserve a raised, forward-tilted 2.5D view');
      for(const x of [-12.7,12.7])for(const z of [-9.7,9.7]){
        const corner=project(x,z);
        assert.ok(Math.abs(corner.x)<.98&&Math.abs(corner.y)<.98,'board frame must stay inside the viewport');
      }
    });
  }
  test(`playing board fills usable space without covering controls at ${width}×${height}`,()=>{
    const view=cameraView(width,height);
    const pitch=(view.mobile?30:28)/Math.hypot(view.mobile?30:28,view.mobile?18:22);
    const side=Math.min(view.mobile?8:16,width*.025);
    const top=Math.min(view.mobile?116:height<420?66:90,height*.3);
    const bottom=Math.min(view.touchControls?(view.mobile?132:112):26,height*.3);
    const scale=height/(view.camera.top-view.camera.bottom);
    const usedWidth=25.4*scale,usedHeight=(19.4*pitch+1)*scale;
    assert.ok(usedWidth<=width-2*side+1e-8);
    assert.ok(usedHeight<=height-top-bottom+1e-8);
    assert.ok(Math.abs(usedWidth-(width-2*side))<1e-8||Math.abs(usedHeight-(height-top-bottom))<1e-8,'fit must use the full available width or height');
    const back=new Vector3(0,0,-9.7).project(view.camera);
    const front=new Vector3(0,0,9.7).project(view.camera);
    assert.ok((1-back.y)*height/2>=top,'keep the HUD clear');
    assert.ok((1-front.y)*height/2<=height-bottom,'keep the lower controls clear');
  });
}

test('desktop gameplay board is at least 20% larger than the previous framing',()=>{
  const view=cameraView(1440,860);
  const currentScale=860/(view.camera.top-view.camera.bottom);
  const previousScale=815/Math.max(22.5,28/(1440/815));
  assert.ok(currentScale/previousScale>=1.2);
});

test('narrow mouse-only windows do not reserve room for absent touch controls',()=>{
  const mouse=cameraView(700,600,0,false),touch=cameraView(700,600,0,true);
  assert.ok(mouse.camera.top<touch.camera.top,'use the extra space when no D-pad is displayed');
});

test('large touch screens also keep the D-pad outside the board',()=>{
  const view=cameraView(1024,768,0,true);
  const front=new Vector3(0,0,9.7).project(view.camera);
  assert.ok((1-front.y)*768/2<=768-112);
});

test('phone gameplay board uses at least 95% of the available width',()=>{
  const view=cameraView(390,752);
  const boardWidth=25.4*390/(view.camera.right-view.camera.left);
  assert.ok(boardWidth/390>=.95);
});
