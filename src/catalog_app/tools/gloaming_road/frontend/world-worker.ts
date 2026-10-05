import { buildChunk, buildFarTerrain, createTerrain } from './terrain';
import type { TerrainAPI } from './world-contract';

/** Bundled to an inline classic-worker string by the parent's ?worker-source plugin. */
type Request = { type:'init'; seed:string } | { type:'chunk'; id:number; cx:number; cz:number } | { type:'far'; id:number; anchorX:number; anchorZ:number };
const scope = globalThis as unknown as DedicatedWorkerGlobalScope;
let terrain:TerrainAPI | undefined;
scope.onmessage = (event:MessageEvent<Request>) => {
  const request=event.data;
  if(request.type==='init') {
    terrain=createTerrain(request.seed);
    scope.postMessage({type:'initialized'});
    return;
  }
  try {
    if(!terrain) throw new Error('Terrain worker must receive init before a build request.');
    const data=request.type==='chunk'?buildChunk(terrain,request.cx,request.cz):buildFarTerrain(terrain,request.anchorX,request.anchorZ);
    scope.postMessage({type:request.type,id:request.id,data},[
      data.positions.buffer,data.normals.buffer,data.colors.buffer,data.uvs.buffer,data.surfaces.buffer,data.indices.buffer,
    ]);
  } catch(error) {
    scope.postMessage({type:'error',id:request.id,message:error instanceof Error?error.message:String(error)});
  }
};
