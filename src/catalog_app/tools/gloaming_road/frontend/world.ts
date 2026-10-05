import * as THREE from 'three';
// @ts-ignore -- the parent build's virtual loader bundles this module as a classic-worker string.
import workerSource from './world-worker.ts?worker-source';
import type { Encounter, RestSite, StreamCallbacks, StreamWorld, TerrainAPI } from './world-contract';
import { buildChunk, buildFarTerrain, CHUNK_SIZE, createTerrain } from './terrain';
import type { BuiltChunk, FarData } from './terrain';
import { createWorldMaterials, disposeChunkVisual, disposeWorldMaterials, loadScenery, makeChunkVisual, makeGroundGeometry } from './scenery';
import type { ChunkVisual, SceneryAssets, WorldMaterials } from './scenery';

type ChunkJob={type:'chunk';id:number;key:string;cx:number;cz:number};
type FarJob={type:'far';id:number;key:string;anchorX:number;anchorZ:number};
type Job=ChunkJob|FarJob;
type Ready={type:'chunk';data:BuiltChunk}|{type:'far';data:FarData};
interface Preparation { x:number; z:number; resolve:()=>void; reject:(reason:Error)=>void }
const keyAt=(cx:number,cz:number)=>`${cx},${cz}`;
const chunkAt=(n:number)=>Math.floor(n/CHUNK_SIZE);

/**
 * 5x5 visual working set, 7x7 maximum retention, 3x3 collision-ready preparation.
 * Geometry insertion is RAF-budgeted separately from update(), so a loading screen
 * can await prepare() without running the player's simulation loop.
 */
export class World implements StreamWorld {
  readonly root=new THREE.Group();
  readonly terrain:TerrainAPI;
  readonly origin={x:0,z:0};
  readonly chunks=new Map<string,ChunkVisual>();
  encounters:Encounter[]=[];
  rests:RestSite[]=[];
  private readonly callbacks:StreamCallbacks;
  private plantBudget:number;
  private nearTriangleBudget:number;
  private quality:string;
  private assets?:SceneryAssets;
  private materials?:WorldMaterials;
  private worker?:Worker;
  private workerURL='';
  private workerReady=false;
  private inlineFallback=false;
  private disposed=false;
  private fatal?:Error;
  private frameHandle=0;
  private nextID=1;
  private centerX=0;
  private centerZ=0;
  private targetX=0;
  private targetZ=0;
  private directionX=0;
  private directionZ=0;
  private wanted=new Map<string,{cx:number;cz:number}>();
  private jobs=new Map<number,Job>();
  private ready:Ready[]=[];
  private preparations:Preparation[]=[];
  private far?:{mesh:THREE.Mesh;anchorX:number;anchorZ:number;triangles:number};

  constructor(seed:string,callbacks:StreamCallbacks,quality='balanced') {
    this.terrain=createTerrain(seed);this.callbacks=callbacks;this.quality=quality;
    this.root.name='The Gloaming Road — bounded streamed world';
    const low=/low|mobile|performance|economy/i.test(quality),high=/high|ultra/i.test(quality);
    this.plantBudget=low?2500:high?4200:3600;
    this.nearTriangleBudget=low?200000:high?250000:235000;
    this.recenter(0,0);
    this.startWorker();
    void loadScenery().then(assets=>{
      if(this.disposed)return;
      this.assets=assets;this.materials=createWorldMaterials(assets,this.quality==='low');this.scheduleFrame();
    }).catch(error=>{
      if(this.disposed)return;
      this.fail(error instanceof Error?error:new Error(String(error)));
    });
  }

  configureQuality(quality:string):void {
    if(this.quality===quality)return;
    this.quality=quality;const low=quality==='low',high=quality==='high';
    this.plantBudget=low?2500:high?4200:3600;this.nearTriangleBudget=low?200000:high?250000:235000;
    if(this.assets&&this.materials){
      const old=this.materials,next=createWorldMaterials(this.assets,low);next.time.value=old.time.value;next.cutCenter.value.copy(old.cutCenter.value);next.cutHalf.value=old.cutHalf.value;
      const keys=['terrain','far','solid','crown','plant'] as const;
      this.root.traverse(node=>{if(node instanceof THREE.Mesh){for(const key of keys)if(node.material===old[key]){node.material=next[key];break;}}});
      this.materials=next;disposeWorldMaterials(old);
    }
    this.updateVisibility();
  }
  illuminate(ambient:THREE.Color,strength:number):void {
    if(this.quality==='low'&&this.materials){this.materials.plant.color.copy(ambient).multiplyScalar(strength);this.materials.crown.color.copy(ambient).multiplyScalar(strength);}
  }

  private startWorker():void {
    try {
      if(typeof Worker==='undefined')throw new Error('Dedicated workers unavailable in this host');
      this.workerURL=URL.createObjectURL(new Blob([workerSource],{type:'text/javascript'}));
      this.worker=new Worker(this.workerURL,{name:'gloaming-road-terrain'});
      this.worker.onmessage=event=>{
        if(this.disposed)return;
        const message=event.data;
        if(message.type==='initialized'){
          this.workerReady=true;
          if(this.workerURL){URL.revokeObjectURL(this.workerURL);this.workerURL='';}
          this.scheduleFrame();return;
        }
        const job=this.jobs.get(message.id);
        if(!job)return; // Results from a terminated generation are never adopted.
        this.jobs.delete(message.id);
        if(message.type==='error'){
          this.fail(new Error(`Terrain generation: ${message.message}`));return;
        }
        this.acceptResult({type:message.type,data:message.data} as Ready);
      };
      this.worker.onerror=event=>{
        event.preventDefault();this.useFallback();
      };
      this.worker.postMessage({type:'init',seed:this.terrain.seed});
    } catch {
      this.useFallback();
    }
  }
  private useFallback():void {
    if(this.disposed)return;
    this.worker?.terminate();this.worker=undefined;this.jobs.clear();
    if(this.workerURL){URL.revokeObjectURL(this.workerURL);this.workerURL='';}
    this.workerReady=true;this.inlineFallback=true;console.warn('[The Gloaming Road] Worker unavailable; using bounded main-thread terrain generation.');this.scheduleFrame();
  }
  private fail(error:Error):void {
    this.fatal=error;
    console.error('[The Gloaming Road / world]',error);
    for(const preparation of this.preparations)preparation.reject(error);
    this.preparations=[];
    this.worker?.terminate();this.worker=undefined;this.jobs.clear();
  }

  update(x:number,z:number,dt:number):void {
    if(this.disposed||this.fatal||!Number.isFinite(x)||!Number.isFinite(z))return;
    const dx=x-this.targetX,dz=z-this.targetZ,distance=Math.hypot(dx,dz);
    if(distance>0.005){this.directionX=dx/distance;this.directionZ=dz/distance;}
    this.targetX=x;this.targetZ=z;
    const cx=chunkAt(x),cz=chunkAt(z);
    if(cx!==this.centerX||cz!==this.centerZ)this.recenter(cx,cz);
    if(this.materials)this.materials.time.value+=Math.min(0.10,Math.max(0,Number.isFinite(dt)?dt:0));
    this.updateVisibility();
    this.scheduleFrame();
  }
  private recenter(cx:number,cz:number):void {
    this.centerX=cx;this.centerZ=cz;this.wanted.clear();
    for(let dz=-2;dz<=2;dz++)for(let dx=-2;dx<=2;dx++)this.wanted.set(keyAt(cx+dx,cz+dz),{cx:cx+dx,cz:cz+dz});
    let changed=false;
    for(const [key,chunk]of this.chunks){
      if(Math.max(Math.abs(chunk.data.cx-cx),Math.abs(chunk.data.cz-cz))>3){
        this.chunks.delete(key);disposeChunkVisual(chunk);this.notifyUnload(key);changed=true;
      }
    }
    this.ready=this.ready.filter(result=>this.resultWanted(result));
    if(changed)this.refreshMetadata();
    this.updateVisibility();this.updateFarCut();
  }
  private updateVisibility():void {
    const plants:{mesh:THREE.InstancedMesh;count:number}[]=[];
    let fixedTriangles=0,wantedPlants=0;
    for(const chunk of this.chunks.values()){
      const radius=Math.max(Math.abs(chunk.data.cx-this.centerX),Math.abs(chunk.data.cz-this.centerZ));
      chunk.group.visible=radius<=2;
      if(!chunk.group.visible)continue;
      fixedTriangles+=2048+chunk.sceneryTriangles;
      if(chunk.plants){
        const fraction=radius===0?1:radius===1?0.92:0.14;
        const count=Math.min(chunk.data.plants.length,Math.floor(this.plantBudget*fraction*chunk.plantDensity));
        wantedPlants+=count;plants.push({mesh:chunk.plants,count});
      }
    }
    // Dense meadow foreground must not turn a mature forest into an unbounded triangle workload.
    const allowed=Math.max(0,Math.floor((this.nearTriangleBudget-fixedTriangles)/4));
    const fraction=wantedPlants?Math.min(1,allowed/wantedPlants):1;
    for(const p of plants)p.mesh.count=Math.floor(p.count*fraction);
  }

  prepare(x:number,z:number):Promise<void> {
    if(this.disposed)return Promise.reject(new Error('World was disposed.'));
    if(this.fatal)return Promise.reject(this.fatal);
    this.update(x,z,0);
    return new Promise<void>((resolve,reject)=>{
      this.preparations.push({x,z,resolve,reject});
      this.resolvePreparations();this.scheduleFrame();
    });
  }
  private neighborhoodReady(x:number,z:number,radius:number):boolean {
    const cx=chunkAt(x),cz=chunkAt(z);
    for(let dz=-radius;dz<=radius;dz++)for(let dx=-radius;dx<=radius;dx++)if(!this.chunks.has(keyAt(cx+dx,cz+dz)))return false;
    return true;
  }
  private resolvePreparations():void {
    if(!this.assets||!this.far)return;
    this.preparations=this.preparations.filter(p=>{
      if(this.neighborhoodReady(p.x,p.z,1)&&Math.max(Math.abs(p.x-this.far!.anchorX),Math.abs(p.z-this.far!.anchorZ))<384){p.resolve();return false;}
      return true;
    });
  }
  /** Uploaded containing terrain PLUS the immediate 1.25m boundary guard, not an arbitrary 5x5. */
  readyAt(x:number,z:number):boolean {
    if(this.disposed||this.fatal||!Number.isFinite(x)||!Number.isFinite(z))return false;
    const guard=1.25;
    for(const px of [x-guard,x+guard])for(const pz of [z-guard,z+guard])if(!this.chunks.has(keyAt(chunkAt(px),chunkAt(pz))))return false;
    return true;
  }
  /** Only render transforms move. Chunk buffers, placements, IDs and TerrainAPI stay global. */
  setOrigin(x:number,z:number):void {
    if(this.disposed||!Number.isFinite(x)||!Number.isFinite(z))return;
    this.origin.x=x;this.origin.z=z;
    this.root.position.set(0,0,0);this.root.updateMatrix();
    for(const chunk of this.chunks.values()){
      chunk.group.position.set(chunk.data.cx*CHUNK_SIZE-x,0,chunk.data.cz*CHUNK_SIZE-z);
      chunk.group.updateMatrix();
    }
    if(this.far){this.far.mesh.position.set(this.far.anchorX-x,0,this.far.anchorZ-z);this.far.mesh.updateMatrix();}
    this.root.updateMatrixWorld(true);
  }

  private priority(cx:number,cz:number):number {
    const dx=cx-this.centerX,dz=cz-this.centerZ,radius=Math.max(Math.abs(dx),Math.abs(dz));
    return (radius<=1?0:30)+dx*dx+dz*dz-(dx*this.directionX+dz*this.directionZ)*0.19;
  }
  private missingChunks():{cx:number;cz:number;key:string;priority:number}[] {
    const queued=new Set<string>();
    for(const job of this.jobs.values())if(job.type==='chunk')queued.add(job.key);
    for(const result of this.ready)if(result.type==='chunk')queued.add(result.data.key);
    return [...this.wanted].filter(([key])=>!this.chunks.has(key)&&!queued.has(key)).map(([key,p])=>({...p,key,priority:this.priority(p.cx,p.cz)})).sort((a,b)=>a.priority-b.priority||a.key.localeCompare(b.key));
  }
  private nextJob():Job|undefined {
    const missing=this.missingChunks(),near=missing[0];
    const anchorX=this.centerX*CHUNK_SIZE+32,anchorZ=this.centerZ*CHUNK_SIZE+32;
    const farNeeded=!this.far||this.far.anchorX!==anchorX||this.far.anchorZ!==anchorZ;
    const farQueued=[...this.jobs.values()].some(job=>job.type==='far')||this.ready.some(result=>result.type==='far');
    if(farNeeded&&!farQueued&&(!near||near.priority>12))return {type:'far',id:this.nextID++,key:`far:${anchorX},${anchorZ}`,anchorX,anchorZ};
    if(near)return {type:'chunk',id:this.nextID++,key:near.key,cx:near.cx,cz:near.cz};
    return undefined;
  }
  private resultWanted(result:Ready):boolean {
    if(result.type==='chunk')return this.wanted.has(result.data.key)&&!this.chunks.has(result.data.key);
    // A still-covering far result is useful during sprinting; the next request refreshes its anchor.
    return Math.max(Math.abs(result.data.anchorX-(this.centerX*64+32)),Math.abs(result.data.anchorZ-(this.centerZ*64+32)))<=192;
  }
  private acceptResult(result:Ready):void {
    if(this.disposed)return;
    if(this.resultWanted(result))this.ready.push(result);
    this.scheduleFrame();
  }
  private scheduleFrame():void {
    if(this.disposed||this.fatal||this.frameHandle)return;
    this.frameHandle=requestAnimationFrame(()=>this.frame());
  }
  private frame():void {
    this.frameHandle=0;
    if(this.disposed||this.fatal||!this.assets||!this.materials||!this.workerReady)return;
    this.ready=this.ready.filter(result=>this.resultWanted(result));
    this.ready.sort((a,b)=>{
      const p=(r:Ready)=>r.type==='far'?12:this.priority(r.data.cx,r.data.cz);
      return p(a)-p(b);
    });
    // At most ONE geometry result is adopted on this animation frame, irrespective of update calls.
    const result=this.ready.shift();
    if(result){
      try {
        if(result.type==='chunk')this.uploadChunk(result.data);
        else this.uploadFar(result.data);
      } catch(error){this.fail(error instanceof Error?error:new Error(String(error)));return;}
    }
    this.updateFarCut();this.resolvePreparations();
    // The pending message queue is never longer than two, and total pending/ready never exceeds three.
    while(this.jobs.size<2&&this.jobs.size+this.ready.length<3){
      const job=this.nextJob();if(!job)break;
      this.jobs.set(job.id,job);
      if(this.inlineFallback){
        try {
          const data=job.type==='chunk'?buildChunk(this.terrain,job.cx,job.cz):buildFarTerrain(this.terrain,job.anchorX,job.anchorZ);
          this.jobs.delete(job.id);this.acceptResult({type:job.type,data} as Ready);
        } catch(error){this.fail(error instanceof Error?error:new Error(String(error)));}
        break; // CSP fallback still does at most one expensive CPU build per frame.
      } else this.worker!.postMessage(job);
    }
    if(this.ready.length)this.scheduleFrame();
  }
  private uploadChunk(data:BuiltChunk):void {
    if(!this.wanted.has(data.key)||this.chunks.has(data.key))return;
    const chunk=makeChunkVisual(data,this.assets!,this.materials!);
    chunk.group.position.set(data.cx*64-this.origin.x,0,data.cz*64-this.origin.z);
    this.root.add(chunk.group);this.chunks.set(data.key,chunk);this.updateVisibility();
    // Main-thread buffers and meshes now exist. The parent may safely create its trimesh collider.
    this.callbacks.onLoad(data);
    this.refreshMetadata();
  }
  private uploadFar(data:FarData):void {
    const geometry=makeGroundGeometry(data),mesh=new THREE.Mesh(geometry,this.materials!.far);
    mesh.name='sampled moving far terrain — 1792m';mesh.receiveShadow=false;
    mesh.position.set(data.anchorX-this.origin.x,0,data.anchorZ-this.origin.z);
    this.root.add(mesh);
    if(this.far){this.far.mesh.removeFromParent();this.far.mesh.geometry.dispose();}
    this.far={mesh,anchorX:data.anchorX,anchorZ:data.anchorZ,triangles:data.indices.length/3};
  }
  private updateFarCut():void {
    if(!this.materials||!this.far)return;
    this.materials.cutCenter.value.set(this.centerX*64+32-this.far.anchorX,this.centerZ*64+32-this.far.anchorZ);
    this.materials.cutHalf.value=this.neighborhoodReady(this.targetX,this.targetZ,2)?159.75:this.neighborhoodReady(this.targetX,this.targetZ,1)?95.75:0;
  }
  private refreshMetadata():void {
    // Retained global records stay stable under rebases. These collections are bounded by 49 chunks.
    this.encounters=[...this.chunks.values()].flatMap(chunk=>chunk.data.encounters).sort((a,b)=>a.id.localeCompare(b.id));
    this.rests=[...this.chunks.values()].flatMap(chunk=>chunk.data.rests).sort((a,b)=>a.id.localeCompare(b.id));
  }
  private notifyUnload(key:string):void {
    try{this.callbacks.onUnload(key);}catch(error){console.error('[The Gloaming Road / unload]',error);}
  }

  stats():Record<string,number> {
    let visible=0,plants=0,trees=0,props=0,solidTriangles=0;
    for(const chunk of this.chunks.values()){
      props+=chunk.data.props.length;
      if(!chunk.group.visible)continue;
      visible++;plants+=chunk.plants?.count??0;trees+=chunk.trees;solidTriangles+=chunk.sceneryTriangles;
    }
    let collisionReady=0;
    for(let dz=-1;dz<=1;dz++)for(let dx=-1;dx<=1;dx++)if(this.chunks.has(keyAt(this.centerX+dx,this.centerZ+dz)))collisionReady++;
    return {chunks:this.chunks.size,visibleChunks:visible,retainedChunks:this.chunks.size-visible,wanted:this.wanted.size,queue:this.missingChunks().length,inFlight:this.jobs.size,ready:this.ready.length,collisionReady,
      plants,trees,props,encounters:this.encounters.length,rests:this.rests.length,terrainTriangles:visible*2048,sceneryTriangles:solidTriangles,plantTriangles:plants*4,nearTriangles:visible*2048+solidTriangles+plants*4,nearTriangleBudget:this.nearTriangleBudget,farTriangles:this.far?.triangles??0,
      worker:this.worker&&!this.inlineFallback?1:0,fallback:this.inlineFallback?1:0,assets:this.assets?1:0,disposed:this.disposed?1:0};
  }
  dispose():void {
    if(this.disposed)return;
    this.disposed=true;
    if(this.frameHandle)cancelAnimationFrame(this.frameHandle);this.frameHandle=0;
    this.worker?.terminate();this.worker=undefined;
    if(this.workerURL){URL.revokeObjectURL(this.workerURL);this.workerURL='';}
    this.jobs.clear();this.ready=[];this.wanted.clear();
    for(const [key,chunk]of this.chunks){disposeChunkVisual(chunk);this.notifyUnload(key);}
    this.chunks.clear();this.encounters=[];this.rests=[];
    if(this.far){this.far.mesh.removeFromParent();this.far.mesh.geometry.dispose();this.far=undefined;}
    if(this.materials){disposeWorldMaterials(this.materials);this.materials=undefined;}
    this.root.clear();this.root.removeFromParent();
    for(const preparation of this.preparations)preparation.reject(new Error('World was disposed during preparation.'));
    this.preparations=[];
  }
}
