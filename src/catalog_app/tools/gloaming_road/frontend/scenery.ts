import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import sceneryURL from './assets/scenery/gloaming-scenery.glb?url';
import groundURL from './assets/scenery/ground-atlas.png?url';
import type { BuiltChunk, FarData, SceneryKind, SceneryPlacement } from './terrain';

interface Prototype { solid?:THREE.BufferGeometry; crown?:THREE.BufferGeometry }
export interface SceneryAssets { prototypes:Record<SceneryKind,Prototype>; ground:THREE.Texture; bark:THREE.Texture; foliage:THREE.Texture; plant:THREE.BufferGeometry }
export interface WorldMaterials { terrain:THREE.MeshLambertMaterial; far:THREE.MeshLambertMaterial; solid:THREE.MeshLambertMaterial; crown:THREE.MeshLambertMaterial|THREE.MeshBasicMaterial; plant:THREE.MeshLambertMaterial|THREE.MeshBasicMaterial; time:{value:number}; cutCenter:{value:THREE.Vector2}; cutHalf:{value:number} }
export interface ChunkVisual { group:THREE.Group; plants?:THREE.InstancedMesh; geometries:THREE.BufferGeometry[]; data:BuiltChunk; sceneryTriangles:number; trees:number; plantDensity:number }
let assetPromise:Promise<SceneryAssets>|undefined;

function configureTexture(texture:THREE.Texture):THREE.Texture {
  texture.colorSpace=THREE.SRGBColorSpace;
  texture.magFilter=THREE.NearestFilter;
  texture.minFilter=THREE.NearestMipmapLinearFilter;
  texture.generateMipmaps=true;
  texture.anisotropy=1;
  texture.wrapS=texture.wrapT=THREE.ClampToEdgeWrapping;
  texture.flipY=false;
  texture.needsUpdate=true;
  return texture;
}
function crossedPlant():THREE.BufferGeometry {
  const g=new THREE.BufferGeometry();
  g.setAttribute('position',new THREE.Float32BufferAttribute([
    -.5,0,0, .5,0,0, .5,1,0, -.5,1,0,
    0,0,-.5, 0,0,.5, 0,1,.5, 0,1,-.5,
  ],3));
  // An upward diffuse normal gives cutout vegetation a soft, luminous field rather than dark cards.
  g.setAttribute('normal',new THREE.Float32BufferAttribute(Array.from({length:8},()=>[0,1,0]).flat(),3));
  g.setAttribute('uv',new THREE.Float32BufferAttribute([0,0,1,0,1,1,0,1,0,0,1,0,1,1,0,1],2));
  g.setIndex([0,1,2,0,2,3,4,5,6,4,6,7]);
  return g;
}

/** A bounded, immutable cache: shared source geometry/textures outlive individual streamed worlds. */
export function loadScenery():Promise<SceneryAssets> {
  if(assetPromise)return assetPromise;
  assetPromise=(async()=>{
    const manager=new THREE.LoadingManager(),loader=new GLTFLoader(manager);
    // A bundled App can use connect-src 'none'. Image.src is allowed there; ImageBitmapLoader.fetch is not.
    loader.register(parser=>{
      (parser as unknown as {textureLoader:THREE.TextureLoader}).textureLoader=new THREE.TextureLoader(manager);
      return {name:'GLOAMING_local_image_loading'};
    });
    const loadModel=()=>{
      if(!sceneryURL.startsWith('data:'))return loader.loadAsync(sceneryURL);
      const body=sceneryURL.slice(sceneryURL.indexOf(',')+1),binary=atob(body),bytes=new Uint8Array(binary.length);
      for(let i=0;i<binary.length;i++)bytes[i]=binary.charCodeAt(i);
      return loader.parseAsync(bytes.buffer,'');
    };
    const [gltf,ground]=await Promise.all([loadModel(),new THREE.TextureLoader(manager).loadAsync(groundURL)]);
    const prototypes=Object.fromEntries(['oak','rowan','fir','rock','log','ruin','rest'].map(k=>[k,{}])) as Record<SceneryKind,Prototype>;
    let bark:THREE.Texture|undefined,foliage:THREE.Texture|undefined;
    gltf.scene.updateMatrixWorld(true);
    const sourceMaterials=new Set<THREE.Material>();
    gltf.scene.traverse(node=>{
      if(!(node instanceof THREE.Mesh))return;
      const [kind,part]=node.name.split('_') as [SceneryKind,'solid'|'crown'];
      if(!prototypes[kind]||!['solid','crown'].includes(part))return;
      const material=(Array.isArray(node.material)?node.material[0]:node.material) as THREE.MeshStandardMaterial;
      sourceMaterials.add(material);
      if(part==='solid'&&material.map)bark=material.map;
      if(part==='crown'&&material.map)foliage=material.map;
      prototypes[kind][part]=node.geometry.clone().applyMatrix4(node.matrixWorld);
      node.geometry.dispose();
    });
    for(const material of sourceMaterials)material.dispose();
    if(!bark||!foliage)throw new Error('Original scenery GLB is missing its named diffuse atlases.');
    return {prototypes,ground:configureTexture(ground),bark:configureTexture(bark),foliage:configureTexture(foliage),plant:crossedPlant()};
  })().catch(error=>{assetPromise=undefined;throw error;});
  return assetPromise;
}

export function createWorldMaterials(assets:SceneryAssets,low=false):WorldMaterials {
  const time={value:0},cutCenter={value:new THREE.Vector2()},cutHalf={value:0};
  const terrainMaterial=(far:boolean)=>{
    const material=new THREE.MeshLambertMaterial({map:assets.ground,vertexColors:true});
    material.name=far?'sampled-far-earth':'layered-earth-and-path';
    material.polygonOffset=far;
    material.polygonOffsetFactor=far?2:0;
    material.polygonOffsetUnits=far?2:0;
    material.onBeforeCompile=shader=>{
      shader.uniforms.uCutCenter=cutCenter;shader.uniforms.uCutHalf=cutHalf;
      shader.vertexShader=shader.vertexShader.replace('#include <common>',`#include <common>\nattribute vec3 surface; varying vec3 vSurface; varying vec2 vTerrainLocal;`)
        .replace('#include <begin_vertex>',`#include <begin_vertex>\nvSurface=surface; vTerrainLocal=position.xz;`);
      shader.fragmentShader=shader.fragmentShader.replace('#include <common>',`#include <common>
        varying vec3 vSurface; varying vec2 vTerrainLocal; uniform vec2 uCutCenter; uniform float uCutHalf;
        float groundHash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
        float groundNoise(vec2 p){vec2 a=floor(p),f=fract(p);f=f*f*(3.0-2.0*f);return mix(mix(groundHash(a),groundHash(a+vec2(1.,0.)),f.x),mix(groundHash(a+vec2(0.,1.)),groundHash(a+vec2(1.,1.)),f.x),f.y);}
      `).replace('#include <map_pars_fragment>',`#include <map_pars_fragment>\nvec4 groundTile(vec2 uv,vec2 cell){return texture2D(map,(cell+0.009+fract(uv)*0.982)*0.5);}`)
        .replace('#include <map_fragment>',`
        ${far?'if(uCutHalf>0.0&&max(abs(vTerrainLocal.x-uCutCenter.x),abs(vTerrainLocal.y-uCutCenter.y))<uCutHalf) discard;':''}
        vec2 guv=vMapUv;
        vec2 rotated=mat2(0.8,0.6,-0.6,0.8)*guv*0.413+vec2(0.37,0.61);
        float terrainPatch=groundNoise(guv*0.43);
        vec4 grass=mix(groundTile(guv,vec2(0.,0.)),groundTile(rotated,vec2(0.,0.)),terrainPatch*0.58);
        vec4 loam=groundTile(guv*0.81,vec2(1.,0.));
        vec4 stone=mix(groundTile(guv*0.69,vec2(0.,1.)),groundTile(rotated,vec2(0.,1.)),0.31);
        vec4 litter=groundTile(guv*0.9,vec2(1.,1.));
        vec4 earth=mix(grass,litter,clamp(vSurface.z*(0.60+terrainPatch*0.27),0.0,1.0));
        earth=mix(earth,stone,clamp(vSurface.y,0.0,1.0));
        float pathMask=smoothstep(0.13,0.94,vSurface.x+(groundNoise(guv*2.1)-0.5)*0.16);
        earth=mix(earth,loam,pathMask*0.91);
        diffuseColor*=earth;
      `);
      if(low)shader.fragmentShader=shader.fragmentShader.replace('vec2 rotated=mat2(0.8,0.6,-0.6,0.8)*guv*0.413+vec2(0.37,0.61);','').replace('float terrainPatch=groundNoise(guv*0.43);','float terrainPatch=0.45;').replace('mix(groundTile(guv,vec2(0.,0.)),groundTile(rotated,vec2(0.,0.)),terrainPatch*0.58)','groundTile(guv,vec2(0.,0.))').replace('mix(groundTile(guv*0.69,vec2(0.,1.)),groundTile(rotated,vec2(0.,1.)),0.31)','groundTile(guv*0.69,vec2(0.,1.))').replace('vSurface.x+(groundNoise(guv*2.1)-0.5)*0.16','vSurface.x');
    };
    material.customProgramCacheKey=()=>`gloaming-ground-v4-${far}-${low}`;
    return material;
  };
  const solid=new THREE.MeshLambertMaterial({map:assets.bark,vertexColors:true});
  solid.name='weathered-bark-moss-and-stone';
  const crown=low?new THREE.MeshBasicMaterial({map:assets.foliage,vertexColors:true,alphaTest:.34,side:THREE.DoubleSide}):new THREE.MeshLambertMaterial({map:assets.foliage,vertexColors:true,alphaTest:0.34,side:THREE.DoubleSide,emissive:0x10170b,emissiveIntensity:0.18});
  crown.name='textured-layered-leaf-shells';
  const plant=low?new THREE.MeshBasicMaterial({map:assets.foliage,alphaTest:.36,side:THREE.DoubleSide}):new THREE.MeshLambertMaterial({map:assets.foliage,alphaTest:0.36,side:THREE.DoubleSide,emissive:0x172313,emissiveIntensity:0.32});
  plant.name='instanced-meadow-and-understory-atlas';
  plant.onBeforeCompile=shader=>{
    shader.uniforms.uWindTime=time;
    shader.vertexShader=shader.vertexShader.replace('#include <common>',`#include <common>\nattribute float aTile; uniform float uWindTime;`)
      .replace('#include <uv_vertex>',`#include <uv_vertex>
        vMapUv=(vec2(mod(aTile,4.0),floor(aTile/4.0))+vec2(0.009)+vec2(vMapUv.x,1.0-vMapUv.y)*0.982)*0.25;
      `)
      .replace('#include <begin_vertex>',`#include <begin_vertex>
        float sway=sin(uWindTime*1.16+instanceMatrix[3].x*0.19+instanceMatrix[3].z*0.14);
        transformed.x+=sway*0.050*position.y*position.y;
        transformed.z+=cos(uWindTime*0.84+instanceMatrix[3].z*0.21)*0.019*position.y*position.y;
      `);
  };
  plant.customProgramCacheKey=()=> 'gloaming-crossed-atlas-wind-v2';
  return {terrain:terrainMaterial(false),far:terrainMaterial(true),solid,crown,plant,time,cutCenter,cutHalf};
}

export function makeGroundGeometry(data:Pick<FarData,'positions'|'normals'|'colors'|'uvs'|'surfaces'|'indices'>):THREE.BufferGeometry {
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.BufferAttribute(data.positions,3));
  geometry.setAttribute('normal',new THREE.BufferAttribute(data.normals,3));
  geometry.setAttribute('color',new THREE.BufferAttribute(data.colors,3));
  geometry.setAttribute('uv',new THREE.BufferAttribute(data.uvs,2));
  geometry.setAttribute('surface',new THREE.BufferAttribute(data.surfaces,3));
  geometry.setIndex(new THREE.BufferAttribute(data.indices,1));
  geometry.computeBoundingBox();geometry.computeBoundingSphere();
  return geometry;
}

function bakeScenery(placements:SceneryPlacement[],assets:SceneryAssets,part:'solid'|'crown',ox:number,oz:number):THREE.BufferGeometry|undefined {
  const instances=placements.map(p=>({p,g:assets.prototypes[p.kind][part]})).filter((i):i is {p:SceneryPlacement;g:THREE.BufferGeometry}=>!!i.g);
  if(!instances.length)return undefined;
  let vertices=0,indicesCount=0;
  for(const {g}of instances){vertices+=g.getAttribute('position').count;indicesCount+=g.index?.count??g.getAttribute('position').count;}
  const positions=new Float32Array(vertices*3),normals=new Float32Array(vertices*3),colors=new Float32Array(vertices*3),uvs=new Float32Array(vertices*2),indices=new Uint32Array(indicesCount);
  let vertexOffset=0,indexOffset=0;
  for(const {p,g}of instances){
    const pos=g.getAttribute('position'),normal=g.getAttribute('normal'),uv=g.getAttribute('uv'),color=g.getAttribute('color');
    const sin=Math.sin(p.yaw),cos=Math.cos(p.yaw),scale=p.scale;
    for(let i=0;i<pos.count;i++){
      const v=(vertexOffset+i)*3,u=(vertexOffset+i)*2,px=pos.getX(i),py=pos.getY(i),pz=pos.getZ(i),nx=normal.getX(i),ny=normal.getY(i),nz=normal.getZ(i);
      positions[v]=(px*cos+pz*sin)*scale+p.x-ox;positions[v+1]=py*scale+p.y;positions[v+2]=(-px*sin+pz*cos)*scale+p.z-oz;
      normals[v]=nx*cos+nz*sin;normals[v+1]=ny;normals[v+2]=-nx*sin+nz*cos;
      const warmth=p.kind==='rowan'?1.04:1;
      colors[v]=(color?color.getX(i):1)*p.tint*warmth;colors[v+1]=(color?color.getY(i):1)*p.tint;colors[v+2]=(color?color.getZ(i):1)*p.tint;
      uvs[u]=uv.getX(i);uvs[u+1]=uv.getY(i);
    }
    const count=g.index?.count??pos.count;
    for(let i=0;i<count;i++)indices[indexOffset+i]=vertexOffset+(g.index?g.index.getX(i):i);
    vertexOffset+=pos.count;indexOffset+=count;
  }
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));geometry.setAttribute('normal',new THREE.BufferAttribute(normals,3));geometry.setAttribute('color',new THREE.BufferAttribute(colors,3));geometry.setAttribute('uv',new THREE.BufferAttribute(uvs,2));geometry.setIndex(new THREE.BufferAttribute(indices,1));
  geometry.computeBoundingBox();geometry.computeBoundingSphere();
  return geometry;
}

export function makeChunkVisual(data:BuiltChunk,assets:SceneryAssets,materials:WorldMaterials):ChunkVisual {
  const group=new THREE.Group();group.name=`terrain ${data.key}`;
  const ground=makeGroundGeometry(data),geometries=[ground];
  const terrainMesh=new THREE.Mesh(ground,materials.terrain);
  terrainMesh.name=`ground ${data.key}`;terrainMesh.receiveShadow=true;group.add(terrainMesh);
  let sceneryTriangles=0;
  for(const part of ['solid','crown']as const){
    const geometry=bakeScenery(data.scenery,assets,part,data.cx*64,data.cz*64);
    if(!geometry)continue;
    geometries.push(geometry);sceneryTriangles+=(geometry.index?.count??0)/3;
    const mesh=new THREE.Mesh(geometry,materials[part]);mesh.name=`${part} ${data.key}`;
    mesh.castShadow=part==='solid';mesh.receiveShadow=true;group.add(mesh);
  }
  let plants:THREE.InstancedMesh|undefined;
  if(data.plants.length){
    const geometry=assets.plant.clone();geometries.push(geometry);
    const tiles=new Float32Array(data.plants.length);
    plants=new THREE.InstancedMesh(geometry,materials.plant,data.plants.length);
    plants.name=`spires and understory ${data.key}`;plants.castShadow=false;plants.receiveShadow=true;
    const dummy=new THREE.Object3D(),color=new THREE.Color();
    for(let i=0;i<data.plants.length;i++){
      const p=data.plants[i];tiles[i]=p.tile;
      dummy.position.set(p.x-data.cx*64,p.y,p.z-data.cz*64);dummy.rotation.set(0,p.yaw,0);dummy.scale.set(p.width,p.height,p.width);dummy.updateMatrix();plants.setMatrixAt(i,dummy.matrix);
      color.setRGB(p.tint,p.tint,p.tint*(p.tile<3?1.015:0.98));plants.setColorAt(i,color);
    }
    geometry.setAttribute('aTile',new THREE.InstancedBufferAttribute(tiles,1));
    plants.instanceMatrix.needsUpdate=true;if(plants.instanceColor)plants.instanceColor.needsUpdate=true;
    plants.computeBoundingBox();plants.computeBoundingSphere();
    group.add(plants);
  }
  const pinkShare=data.plants.filter(p=>p.tile<3).length/Math.max(1,data.plants.length);
  const plantDensity=Math.min(1,0.48+pinkShare*0.98);
  return {group,plants,geometries,data,sceneryTriangles,trees:data.scenery.filter(p=>['oak','rowan','fir'].includes(p.kind)).length,plantDensity};
}

export function disposeChunkVisual(chunk:ChunkVisual):void {
  chunk.group.removeFromParent();
  chunk.plants?.dispose();
  for(const geometry of chunk.geometries)geometry.dispose();
  chunk.group.clear();
}
export function disposeWorldMaterials(materials:WorldMaterials):void {
  for(const material of [materials.terrain,materials.far,materials.solid,materials.crown,materials.plant])material.dispose();
  // Textures and authored prototype geometries are owned by the single shared cache, NOT a chunk.
}
