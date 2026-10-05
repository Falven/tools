import { createNoise2D } from 'simplex-noise';
import type { Biome, ChunkData, Encounter, Prop, RestSite, TerrainAPI, WorldFeatures } from './world-contract';

/** The lattice is global. Neither floating-origin rebases nor request order enter this module. */
export const CHUNK_SIZE = 64;
export const GRID_STEP = 2;
export type SceneryKind = 'oak' | 'rowan' | 'fir' | 'rock' | 'log' | 'ruin' | 'rest';
export interface PlantPlacement { x:number; y:number; z:number; yaw:number; width:number; height:number; tile:number; tint:number }
export interface SceneryPlacement { kind:SceneryKind; x:number; y:number; z:number; yaw:number; scale:number; tint:number }
export interface BuiltChunk extends ChunkData { surfaces:Float32Array; plants:PlantPlacement[]; scenery:SceneryPlacement[] }
export interface FarData { anchorX:number; anchorZ:number; positions:Float32Array; normals:Float32Array; colors:Float32Array; uvs:Float32Array; surfaces:Float32Array; indices:Uint32Array }

export function seedHash(text:string):number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  h ^= h >>> 16; h = Math.imul(h, 0x7feb352d); h ^= h >>> 15;
  return (Math.imul(h, 0x846ca68b) ^ (h >>> 16)) >>> 0;
}
export function randomStream(seed:number):()=>number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t ^= t + Math.imul(t ^ (t >>> 7), 61 | t);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
export function coordinateRandom(seed:number, x:number, z:number, salt = 0):number {
  let h = seed ^ Math.imul(x | 0, 0x9e3779b1) ^ Math.imul(z | 0, 0x85ebca77) ^ Math.imul(salt, 0xc2b2ae3d);
  h ^= h >>> 16; h = Math.imul(h, 0x7feb352d); h ^= h >>> 15; h = Math.imul(h, 0x846ca68b);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}
const clamp = (n:number, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, n));
const smooth = (a:number, b:number, x:number) => { const t = clamp((x-a)/(b-a)); return t*t*(3-2*t); };
const mix = (a:number,b:number,t:number) => a + (b-a)*t;

export function createTerrain(seed:string):TerrainAPI {
  // Each channel owns its PRNG: adding a decoration cannot change mountains or the castle.
  const land = createNoise2D(randomStream(seedHash(seed + ':land:v1')));
  const detail = createNoise2D(randomStream(seedHash(seed + ':detail:v1')));
  const region = createNoise2D(randomStream(seedHash(seed + ':region:v1')));
  const trails = createNoise2D(randomStream(seedHash(seed + ':trails:v1')));
  const featureRandom = randomStream(seedHash(seed + ':features:v1'));
  const bearing = featureRandom()*Math.PI*2;
  const distance = 820 + featureRandom()*410;
  const castleX = Math.sin(bearing)*distance, castleZ = Math.cos(bearing)*distance;
  const ridgeAngle = -0.32 + featureRandom()*0.5;
  const rc = Math.cos(ridgeAngle), rs = Math.sin(ridgeAngle);
  const groveX = -94 + featureRandom()*24, groveZ = -129 + featureRandom()*22;
  const rawHeight = (x:number,z:number):number => {
    const u = x*rc-z*rs, v = x*rs+z*rc;
    const spineA = v + 600 + 80*Math.sin(u/340) + 43*land(u/740, 18.2);
    const spineB = u - 865 + 110*Math.sin(v/570);
    const spineC = v - 1090 + 125*Math.sin(u/510);
    // Broad, continuous traversable flanks; scalloped crests are real height samples at every LOD.
    const cragA = Math.pow(1-Math.abs(detail(u/151,57.2)),2.2);
    const cragB = Math.pow(1-Math.abs(detail(v/173,-31.4)),2.0);
    const cragC = Math.pow(1-Math.abs(detail(u/196,73.1)),2.4);
    // Broken granite teeth belong only to the high crests, beyond the starting valleys.
    // Their broad lower flanks remain continuous; these are not decorative mountain walls.
    const ridgeA = Math.exp(-Math.pow(spineA/252,2))*(132+35*land(u/410,47.1)) + Math.exp(-Math.pow(spineA/117,2))*(12+62*cragA);
    const ridgeB = Math.exp(-Math.pow(spineB/310,2))*(116+31*land(v/500,-11.8)) + Math.exp(-Math.pow(spineB/144,2))*(8+51*cragB);
    const ridgeC = Math.exp(-Math.pow(spineC/335,2))*(100+32*land(u/420,32.4)) + Math.exp(-Math.pow(spineC/158,2))*(8+39*cragC);
    const hills = 21*land(x/410,z/410) + 7.2*land(x/168+15.2,z/168-4.8);
    const folds = 1.7*detail(x/49,z/49) + 0.34*detail(x/16+3.1,z/16);
    return 4 + hills + folds + ridgeA + ridgeB + ridgeC;
  };
  const spawnY = rawHeight(0,0);
  const castleY = rawHeight(castleX,castleZ) + 0.6;
  const features:WorldFeatures = {
    spawn:{ id:`${seed}:spawn`, x:0, z:0, y:spawnY, yaw:0 },
    castle:{ id:`${seed}:castle`, x:castleX, z:castleZ, y:castleY, yaw:0 },
  };
  const height = (x:number,z:number):number => {
    let y = rawHeight(x,z);
    const spawnDistance = Math.hypot(x,z);
    // No steps or tiny terraces beneath the first movement. The blend has zero edge derivatives.
    y = mix(spawnY, y, smooth(24,75,spawnDistance));
    const dx = Math.max(0,Math.abs(x-castleX)-41), dz = Math.max(0,Math.abs(z-castleZ)-50);
    const apronDistance = Math.hypot(dx,dz);
    y = mix(castleY,y,smooth(0,150,apronDistance));
    return y;
  };
  const moisture = (x:number,z:number):number => {
    const natural = clamp(0.48 + 0.32*region(x/360,z/360) + 0.12*region(x/920+12,z/920-8));
    const grove = 1-smooth(38,110,Math.hypot((x-groveX)*0.90,z-groveZ));
    const clearing = smooth(46,89,Math.hypot(x,z));
    return mix(0.28,Math.max(natural,0.78*grove+0.15),clearing);
  };
  const biome = (x:number,z:number):Biome => {
    const d = Math.hypot(x,z);
    if (d < 66) return 'meadow';
    const h = height(x,z), wet = moisture(x,z);
    const cool = region(x/570-37,z/570+21);
    if (h > 76 + 14*cool || (h > 42 && cool < -0.32)) return 'upland';
    if (wet > 0.51 && (h > 36 || cool > 0.43)) return 'conifer';
    if (wet > 0.49) return 'woodland';
    return 'meadow';
  };
  const ux = castleX/distance, uz = castleZ/distance;
  const path = (x:number,z:number):number => {
    const along = x*ux+z*uz, across = -x*uz+z*ux;
    // One meandering trace joins the two regions, but branches continue into an unbounded world.
    const envelope = Math.sin(Math.PI*clamp(along/distance));
    const bend = (12*Math.sin(along/93)+19*Math.sin(along/223))*envelope;
    const verge = 1+0.23*trails(x/43+9.3,z/43-6.1);
    const mainDistance = Math.abs(across-bend)/verge;
    const main = (1-smooth(0.36,1.70,mainDistance))*(0.72+0.28*smooth(-90,0,along));
    const branchA = Math.abs(z - 102 - 30*Math.sin(x/129) - 35*trails(x/380,1.7))/verge;
    const branchB = Math.abs(x + 202 + 39*Math.sin(z/179) + 22*trails(-8.2,z/410))/verge;
    const branchGate = smooth(-0.38,0.20,trails(x/510+81,z/510));
    const branches = Math.max(1-smooth(0.24,1.40,branchA),1-smooth(0.22,1.35,branchB))*branchGate;
    // The authored gate faces +Z. This short approach makes its actual entrance legible.
    const gateZ = z-castleZ;
    const approach = (1-smooth(2.3,5.6,Math.abs(x-castleX))) * smooth(35,50,gateZ) * (1-smooth(118,180,gateZ));
    return clamp(Math.max(main,branches,approach));
  };
  const clear = (x:number,z:number):boolean => (
    (Math.abs(x-castleX) < 48 && Math.abs(z-castleZ) < 58) || Math.hypot(x,z) < 3.1
  );
  return { seed, features, height, biome, moisture, path, clear };
}

function groundSample(terrain:TerrainAPI,x:number,z:number,y:number,nx:number,nz:number):{ color:number[]; surface:number[] } {
  const biome = terrain.biome(x,z), trail = terrain.path(x,z);
  const variation = Math.sin(x*0.046+Math.sin(z*0.028))*Math.cos(z*0.039-x*0.013);
  const slope = Math.hypot(nx,nz);
  const highRidge=smooth(42,109,y)*smooth(175,355,Math.hypot(x,z));
  const rock = clamp(smooth(0.31,0.68,slope)*0.78 + highRidge*1.08);
  const forest = (biome === 'upland'?0:smooth(0.39,0.61,terrain.moisture(x,z)))*(1-rock*0.83);
  // Linear vertex colours multiply the sRGB atlas, rather than encoding biome IDs as block colours.
  const base = biome === 'woodland' ? [0.68,0.82,0.52] : biome === 'conifer' ? [0.55,0.72,0.59] : biome === 'upland' ? [0.86,0.86,0.77] : [0.83,0.99,0.59];
  const color = base.map((v,i) => mix(v*(0.91+variation*0.08),[1.06,1.05,1.01][i],rock*0.82));
  return { color, surface:[trail,rock,forest] };
}
function sampleNormal(terrain:TerrainAPI,x:number,z:number):number[] {
  // Crucially samples ABSOLUTE neighbouring coordinates, even at chunk boundaries.
  const dx = terrain.height(x-0.8,z)-terrain.height(x+0.8,z), dz = terrain.height(x,z-0.8)-terrain.height(x,z+0.8);
  const l = Math.hypot(dx,1.6,dz);
  return [dx/l,1.6/l,dz/l];
}

export function buildChunk(terrain:TerrainAPI,cx:number,cz:number):BuiltChunk {
  const size = CHUNK_SIZE/GRID_STEP+1, count = size*size;
  const positions = new Float32Array(count*3), normals = new Float32Array(count*3), colors = new Float32Array(count*3);
  const surfaces = new Float32Array(count*3), uvs = new Float32Array(count*2), indices = new Uint32Array((size-1)*(size-1)*6);
  const ox = cx*CHUNK_SIZE, oz = cz*CHUNK_SIZE;
  for (let iz=0;iz<size;iz++) for (let ix=0;ix<size;ix++) {
    const i=iz*size+ix, x=ox+ix*GRID_STEP,z=oz+iz*GRID_STEP,y=terrain.height(x,z);
    const n=sampleNormal(terrain,x,z), ground=groundSample(terrain,x,z,y,n[0],n[2]);
    positions.set([ix*GRID_STEP,y,iz*GRID_STEP],i*3); normals.set(n,i*3); colors.set(ground.color,i*3); surfaces.set(ground.surface,i*3);
    uvs.set([x/7,z/7],i*2);
  }
  let ii=0;
  for (let z=0;z<size-1;z++) for (let x=0;x<size-1;x++) {
    const a=z*size+x,b=a+1,c=a+size,d=c+1;
    indices.set([a,c,b,b,c,d],ii); ii+=6;
  }
  const hash=seedHash(terrain.seed+':population:v1');
  const random=(salt:number)=>coordinateRandom(hash,cx,cz,salt);
  const scenery:SceneryPlacement[]=[], props:Prop[]=[], encounters:Encounter[]=[], rests:RestSite[]=[];
  const plantExclusions:{x:number;z:number;radius:number}[]=[];
  const sceneryAt=(kind:SceneryKind,x:number,z:number,scale:number,yaw:number,salt:number,solid=true) => {
    const y=terrain.height(x,z), tint=0.88+coordinateRandom(hash,Math.floor(x*4),Math.floor(z*4),salt)*0.19;
    scenery.push({kind,x,y,z,yaw,scale,tint});
    if (!solid) return;
    const dimensions:Record<SceneryKind,[number,number]>={oak:[0.43,7.6],rowan:[0.34,6.6],fir:[0.40,10.8],rock:[1.18,1.28],log:[1.50,0.77],ruin:[0.72,1.8],rest:[0,0]};
    const [r,h]=dimensions[kind];
    if(r>0) props.push({id:`${terrain.seed}:${cx}:${cz}:${kind}:${salt}`,kind,x,y,z,radius:r*scale,height:h*scale,yaw,scale});
    plantExclusions.push({x,z,radius:kind==='rock'?scale*1.05:kind==='ruin'?scale*0.72:kind==='log'?scale*1.7:0.50*scale});
  };
  // The planting grid, like terrain, is global. It never grows a second edge tree in a neighbour.
  const treeStep=11.5;
  for(let gz=Math.floor(oz/treeStep);gz<=Math.ceil((oz+64)/treeStep);gz++) for(let gx=Math.floor(ox/treeStep);gx<=Math.ceil((ox+64)/treeStep);gx++) {
    const x=(gx+0.17+coordinateRandom(hash,gx,gz,41)*0.66)*treeStep,z=(gz+0.17+coordinateRandom(hash,gx,gz,42)*0.66)*treeStep;
    if(x<ox||x>=ox+64||z<oz||z>=oz+64||Math.hypot(x,z)<48||terrain.clear(x,z)||terrain.path(x,z)>0.27) continue;
    // Crown overhangs also stay out of the castle's clean apron.
    if(Math.abs(x-terrain.features.castle.x)<54&&Math.abs(z-terrain.features.castle.z)<64) continue;
    const b=terrain.biome(x,z), wet=terrain.moisture(x,z), roll=coordinateRandom(hash,gx,gz,43);
    const density=b==='woodland'?0.80:b==='conifer'?0.74:b==='upland'?0.035:0.045;
    if(roll>density || Math.abs(terrain.height(x+2,z)-terrain.height(x-2,z))>3.8) continue;
    const kind:SceneryKind=b==='conifer'?'fir':coordinateRandom(hash,gx,gz,44)<0.15+(wet<0.50?0.18:0)?'rowan':'oak';
    sceneryAt(kind,x,z,0.75+coordinateRandom(hash,gx,gz,45)*0.51,coordinateRandom(hash,gx,gz,46)*Math.PI*2,Math.imul(gx,7919)^gz);
  }
  const rocks = 2+Math.floor(random(52)*6);
  for(let i=0;i<rocks;i++) {
    const x=ox+3+random(70+i*7)*58,z=oz+3+random(71+i*7)*58;
    if(Math.hypot(x,z)<26||terrain.clear(x,z)||terrain.path(x,z)>0.20) continue;
    const b=terrain.biome(x,z);
    if(b==='meadow'&&random(72+i*7)<0.55) continue;
    sceneryAt('rock',x,z,(b==='upland'?1.15:0.52)+random(73+i*7)*1.08,random(74+i*7)*Math.PI*2,200+i);
  }
  if(random(131)<0.43) {
    const x=ox+8+random(132)*48,z=oz+8+random(133)*48;
    if(Math.hypot(x,z)>34&&!terrain.clear(x,z)&&terrain.path(x,z)<0.2) sceneryAt('log',x,z,0.75+random(134)*0.7,random(135)*Math.PI*2,311);
  }
  // Low, broken wayside masonry, never a second keep or castle landmark.
  if(random(151)<0.12) {
    const x=ox+11+random(152)*42,z=oz+11+random(153)*42;
    if(Math.hypot(x,z)>54&&!terrain.clear(x,z)) for(let i=0;i<3;i++) {
      const px=x+(i-1)*1.95,pz=z+Math.sin(i*2.2)*0.6;
      if(!terrain.clear(px,pz)) sceneryAt('ruin',px,pz,0.50+random(154+i)*0.62,random(159)*0.5,400+i);
    }
  }
  if(cx===0&&cz===0) {
    rests.push({id:`${terrain.seed}:rest:spawn`,x:0,z:0});
    sceneryAt('rest',0,0,1,0,900,false); plantExclusions.push({x:0,z:0,radius:3.15});
  }
  if(random(301)<0.055) {
    const x=ox+12+random(302)*40,z=oz+12+random(303)*40;
    if(Math.hypot(x,z)>95&&!terrain.clear(x,z)&&Math.abs(terrain.height(x-3,z)-terrain.height(x+3,z))<1.6) {
      rests.push({id:`${terrain.seed}:rest:${cx}:${cz}`,x,z});
      sceneryAt('rest',x,z,1,random(304)*6.283,901,false); plantExclusions.push({x,z,radius:4});
    }
  }
  if(random(501)<0.32) {
    const x=ox+10+random(502)*44,z=oz+10+random(503)*44;
    if(Math.hypot(x,z)>34&&!terrain.clear(x,z)&&!rests.some(r=>Math.hypot(x-r.x,z-r.z)<16)) {
      const kinds:Encounter['kind'][]=['swordsman','shield','archer','mage'];
      const n=random(504)<0.24?2:1;
      for(let i=0;i<n;i++) {
        const px=x+i*3.4,pz=z+i*2.1;
        if(Math.hypot(px,pz)>32&&!terrain.clear(px,pz)) encounters.push({id:`${terrain.seed}:encounter:${cx}:${cz}:${i}`,kind:kinds[Math.floor(random(505+i)*kinds.length)],x:px,z:pz});
      }
    }
  }
  const plants:PlantPlacement[]=[];
  // Dense multi-stem cutouts, in a shuffled sequence so reducing the instance count thins evenly.
  // 4,320 is a HARD candidate cap. World thins the distant/wooded set and caps total near triangles.
  for(let i=0;i<4320;i++) {
    const x=ox+random(1000+i*6)*64,z=oz+random(1001+i*6)*64;
    if(terrain.clear(x,z)) continue;
    const road=terrain.path(x,z), roll=random(1002+i*6);
    if((road>0.80&&roll<0.93)||(road>0.35&&roll<road*0.44)) continue;
    if(plantExclusions.some(p=>Math.abs(x-p.x)<p.radius&&Math.abs(z-p.z)<p.radius&&Math.hypot(x-p.x,z-p.z)<p.radius)) continue;
    const b=terrain.biome(x,z), d=Math.hypot(x,z), patch=0.5+0.5*Math.sin(x*0.055+Math.sin(z*0.068))*Math.cos(z*0.043);
    let tile:number, width:number, h:number;
    if(b==='meadow') {
      if(roll < (d<94?0.62:0.48)+patch*0.16) { tile=roll<0.27?0:roll<0.53?1:2; width=1.28; h=1.52; }
      else if(roll<0.81) {tile=roll<0.72?3:4;width=1.35;h=0.36;}
      else {tile=roll<0.89?5:6;width=1.05;h=0.58;}
    } else if(b==='woodland') {
      if(roll<0.43){tile=7;width=1.20;h=0.64;}
      else if(roll<0.68){tile=6;width=0.95;h=0.68;}
      else if(roll<0.80){tile=8;width=1.05;h=0.85;}
      else if(roll<0.92){tile=3;width=1.04;h=0.32;}
      else {tile=1;width=0.83;h=1.04;}
    } else if(b==='conifer') {
      if(roll<0.50){tile=7;width=1.05;h=0.54;}
      else if(roll<0.72){tile=6;width=0.94;h=0.52;}
      else if(roll<0.91){tile=8;width=0.83;h=0.69;}
      else {tile=4;width=1.1;h=0.32;}
    } else {
      if(roll>0.60) continue;
      tile=roll<0.28?6:roll<0.46?4:5; width=0.86;h=tile===6?0.43:0.30;
    }
    if(road>0.65){tile=roll<0.95?6:3;width=0.79;h=0.27;}
    const scale=tile<3?0.87+random(1003+i*6)*0.27:0.69+random(1003+i*6)*0.64;
    plants.push({x,y:terrain.height(x,z)-0.035,z,yaw:random(1004+i*6)*6.283185,width:width*scale,height:h*scale,tile,tint:0.81+random(1005+i*6)*0.25});
  }
  return {key:`${cx},${cz}`,cx,cz,positions,normals,colors,uvs,indices,props,encounters,rests,surfaces,plants,scenery};
}

/** Real, moving global terrain. The central tile also backs up not-yet-loaded visual edges. */
export function buildFarTerrain(terrain:TerrainAPI,anchorX:number,anchorZ:number):FarData {
  const positions:number[]=[],normals:number[]=[],colors:number[]=[],uvs:number[]=[],surfaces:number[]=[],indices:number[]=[];
  const rings:[number,number,number][]=[[0,320,8],[320,640,16],[640,1280,32],[1280,1792,64]];
  for(const [inner,outer,step] of rings) {
    const cells=outer*2/step, width=cells+1, start=positions.length/3;
    for(let iz=0;iz<=cells;iz++) for(let ix=0;ix<=cells;ix++) {
      const lx=-outer+ix*step,lz=-outer+iz*step,x=anchorX+lx,z=anchorZ+lz,y=terrain.height(x,z);
      const n=sampleNormal(terrain,x,z),g=groundSample(terrain,x,z,y,n[0],n[2]);
      positions.push(lx,y-0.25,lz); normals.push(...n);colors.push(...g.color);surfaces.push(...g.surface);uvs.push(x/7,z/7);
    }
    for(let iz=0;iz<cells;iz++) for(let ix=0;ix<cells;ix++) {
      const x=-outer+ix*step,z=-outer+iz*step;
      if(inner>0&&x>=-inner&&x+step<=inner&&z>=-inner&&z+step<=inner)continue;
      const a=start+iz*width+ix,b=a+1,c=a+width,d=c+1;indices.push(a,c,b,b,c,d);
    }
    // Draped skirts at LOD joins hide T-junction pinholes; their top is the sampled terrain.
    if(inner>0) {
      const points:[number,number][]=[];
      for(let t=-inner;t<inner;t+=step)points.push([t,-inner]);
      for(let t=-inner;t<inner;t+=step)points.push([inner,t]);
      for(let t=inner;t>-inner;t-=step)points.push([t,inner]);
      for(let t=inner;t>-inner;t-=step)points.push([-inner,t]);
      for(let i=0;i<points.length;i++) {
        const pair=[points[i],points[(i+1)%points.length]],base=positions.length/3;
        for(const [lx,lz]of pair) {
          const x=anchorX+lx,z=anchorZ+lz,y=terrain.height(x,z),n=sampleNormal(terrain,x,z),g=groundSample(terrain,x,z,y,n[0],n[2]);
          for(const drop of[0,6]) {positions.push(lx,y-0.25-drop,lz);normals.push(...n);colors.push(...g.color);surfaces.push(...g.surface);uvs.push(x/7,z/7);}
        }
        indices.push(base,base+1,base+2,base+2,base+1,base+3);
      }
    }
  }
  return {anchorX,anchorZ,positions:new Float32Array(positions),normals:new Float32Array(normals),colors:new Float32Array(colors),uvs:new Float32Array(uvs),surfaces:new Float32Array(surfaces),indices:new Uint32Array(indices)};
}
