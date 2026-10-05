import type * as THREE from 'three';
export type Biome = 'meadow'|'woodland'|'conifer'|'upland';
export interface WorldFeature { id:string; x:number; z:number; y:number; yaw:number }
export interface WorldFeatures { castle:WorldFeature; spawn:WorldFeature }
export interface Prop { id:string; kind:string; x:number; y:number; z:number; radius:number; height:number; yaw:number; scale:number }
export interface Encounter { id:string; kind:'swordsman'|'shield'|'archer'|'mage'; x:number; z:number; event?:number }
export interface RestSite { id:string; x:number; z:number }
export interface ChunkData { key:string; cx:number; cz:number; positions:Float32Array; normals:Float32Array; colors:Float32Array; uvs:Float32Array; indices:Uint32Array; props:Prop[]; encounters:Encounter[]; rests:RestSite[]; }
export interface TerrainAPI { seed:string; features:WorldFeatures; height(x:number,z:number):number; biome(x:number,z:number):Biome; moisture(x:number,z:number):number; path(x:number,z:number):number; clear(x:number,z:number):boolean; }
export interface StreamCallbacks { onLoad(data:ChunkData):void; onUnload(key:string):void; }
export interface StreamWorld { root:THREE.Group; terrain:TerrainAPI; origin:{x:number,z:number}; chunks:Map<string,unknown>; encounters:Encounter[]; rests:RestSite[]; update(x:number,z:number,dt:number):void; prepare(x:number,z:number):Promise<void>; setOrigin(x:number,z:number):void; readyAt(x:number,z:number):boolean; dispose():void; stats():Record<string,number>; }
