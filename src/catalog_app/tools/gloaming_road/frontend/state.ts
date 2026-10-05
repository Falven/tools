import type { WorldFeatures } from './world-contract';
export const VERSION = 1;
export const GENERATOR = 1;
export const TUNE = Object.freeze({ step:1/60, walk:3, sprint:4.6, eye:1.65, health:100, stamina:100,
  light:{windup:.24,active:.14,recovery:.32,damage:24,cost:12}, heavy:{windup:.52,active:.18,recovery:.55,damage:40,cost:24},
  parry:.14, block:12, heavyBlock:22, feint:8, dodgeCost:22, dodgeTime:.28, dodgeDistance:.9, regen:24, regenDelay:.65,
  reach:1.85, enemyReaction:.30, cycle:1800, bloodChance:.20, rebase:384, actorRadius:78, maxActors:12, recentLimit:64, respawnAfter:600 });
export type Sector = 'high'|'left'|'right'|'low';
export type EnemyKind = 'swordsman'|'shield'|'archer'|'mage'|'elite';
export interface RecentEncounter { id:string;kind:EnemyKind; x:number;z:number; y?:number;health:number; seen:number; dead:boolean; event?:number; homeX?:number;homeZ?:number; }
export interface SaveRecord { schema:number;generator:number;seed:string;clock:number;features:WorldFeatures;
  player:{x:number;y:number;z:number;yaw:number;pitch:number;health:number;stamina:number};
  recovery:{x:number;z:number;id:string};mission:{guardIds:string[];defeated:string[];rescued:boolean;doors:string[]};recent:RecentEncounter[];savedAt:number;
}
export interface Settings {master:number;music:number;ambience:number;effects:number;sensitivity:number;invert:boolean;fov:number;motion:boolean;flashes:boolean;blood:boolean;captions:boolean;quality:'low'|'balanced'|'high'; bindings:Record<string,string>;}
export const defaults:Settings={master:.75,music:.48,ambience:.64,effects:.85,sensitivity:1,invert:false,fov:65,motion:true,flashes:true,blood:true,captions:true,quality:'balanced',bindings:{forward:'KeyW',back:'KeyS',left:'KeyA',right:'KeyD',sprint:'ShiftLeft',dodge:'Space',interact:'KeyE',high:'Digit1',guardLeft:'Digit2',guardRight:'Digit3',low:'Digit4'}};
const SETTINGS_KEY='gloaming-road.settings.1';
export function settingsRead():Settings { try {const s=JSON.parse(localStorage.getItem(SETTINGS_KEY)||'null');return s?{...defaults,...s,bindings:{...defaults.bindings,...s.bindings}}:{...defaults,bindings:{...defaults.bindings}};}catch{return {...defaults,bindings:{...defaults.bindings}};} }
export function settingsWrite(settings:Settings) { localStorage.setItem(SETTINGS_KEY,JSON.stringify(settings)); }
export function seedHash(s:string) { let h=2166136261;for(let i=0;i<s.length;i++)h=Math.imul(h^s.charCodeAt(i),16777619);return h>>>0; }
export function hashRandom(seed:string, index:number) {let h=seedHash(seed)^Math.imul(index+1,0x45d9f3b);h=Math.imul(h^(h>>>16),0x45d9f3b);h=Math.imul(h^(h>>>16),0x45d9f3b);return ((h^(h>>>16))>>>0)/4294967296;}
export function skyState(clock:number, seed:string) { const day=Math.floor(clock/TUNE.cycle);const t=(clock%TUNE.cycle)/TUNE.cycle;const sun=Math.sin(t*Math.PI*2);const night=t>.51;return {day,t,sun,night,blood:night&&hashRandom(seed,day)<TUNE.bloodChance}; }
export function freshSave(seed:string,features:WorldFeatures):SaveRecord {const c=features.castle;return {schema:VERSION,generator:GENERATOR,seed,features,clock:TUNE.cycle*.21,player:{x:features.spawn.x,y:features.spawn.y+.08,z:features.spawn.z,yaw:features.spawn.yaw,pitch:0,health:100,stamina:100},recovery:{x:features.spawn.x,z:features.spawn.z,id:'first-clearing'},mission:{guardIds:[0,1,2].map(i=>`${c.id}:royal:${i}`),defeated:[],rescued:false,doors:[]},recent:[],savedAt:Date.now()};}
export class Saves {
  hasWorld=false;
  private db?:IDBDatabase; private pending=Promise.resolve();
  async open(){if(!('indexedDB' in window))throw new Error('This browser cannot store worlds. You can play, but progress will not be saved.');this.db=await new Promise<IDBDatabase>((resolve,reject)=>{const r=indexedDB.open('the-gloaming-road',VERSION);r.onupgradeneeded=()=>r.result.createObjectStore('world');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);r.onblocked=()=>reject(new Error('Another tab is preventing save storage from opening. Close the other game tab.'));});}
  async read():Promise<SaveRecord|null>{if(!this.db)return null;const value=await new Promise<SaveRecord|undefined>((resolve,reject)=>{const r=this.db!.transaction('world','readonly').objectStore('world').get('current');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});this.hasWorld=!!value;if(!value)return null;if(value.schema!==VERSION||value.generator!==GENERATOR)throw new Error('This saved world cannot be loaded by this generator version. Starting a New World replaces it.');return value;}
  write(value:SaveRecord):Promise<void>{if(!this.db)return Promise.reject(new Error('Progress is not being saved: browser storage is unavailable.'));const snapshot=structuredClone(value);snapshot.savedAt=Date.now();const work=()=>new Promise<void>((resolve,reject)=>{const tx=this.db!.transaction('world','readwrite');tx.objectStore('world').put(snapshot,'current');tx.oncomplete=()=>resolve();tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error||new Error('Saving was interrupted.'));});this.pending=this.pending.catch(()=>{}).then(work);return this.pending;}
  close(){this.db?.close();}
}
