import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { NeonRenderer } from '../src/catalog_app/tools/neon_coil/frontend/renderer.js';

// Reuse the frontend's pinned Three.js dependency without a WebGL/DOM context.
const require=createRequire(new URL('../src/catalog_app/tools/neon_coil/frontend/package.json',import.meta.url));
const { OrthographicCamera, Vector3 }=require('three');
const sizes=[[1440,815],[1024,620],[844,320],[720,600],[390,736],[320,480]];
for(const [width,height] of sizes){
  for(const introMix of [0,.5,1]){
    test(`grid stays straight and visible at ${width}×${height}, intro=${introMix}`,()=>{
      const view={width,height,mobile:width<721,introMix,camera:new OrthographicCamera(-20,20,12,-12,.1,150)};
      NeonRenderer.prototype.updateCamera.call(view);
      view.camera.updateMatrixWorld(true);
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
}
