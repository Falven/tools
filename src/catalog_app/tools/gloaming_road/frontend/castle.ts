import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import modelURL from './assets/castle/last-light.glb?url';
import layout from './assets/castle/layout.json';
import stoneURL from './assets/atmosphere/stone.png?url';
import floorURL from './assets/atmosphere/floor.png?url';
import woodURL from './assets/atmosphere/wood.png?url';
import roofURL from './assets/atmosphere/roof.png?url';
import {Physics,RAPIER} from './physics';
import type {WorldFeature} from './world-contract';
export class Castle {
  root=new THREE.Group();private solid:RAPIER.Collider[]=[];private doorBodies=new Map<string,RAPIER.Collider>();private doors=new Map<string,THREE.Object3D>();private open=new Set<string>();private angles=new Map<string,number>();private active=false;private origin={x:0,z:0};private physics?:Physics;
  private constructor(public feature:WorldFeature){}
  static async load(feature:WorldFeature,doorState:string[]){const c=new Castle(feature),loaderGLB=new GLTFLoader();const gltf=modelURL.startsWith('data:')?await loaderGLB.parseAsync(Uint8Array.from(atob(modelURL.split(',')[1]),v=>v.charCodeAt(0)).buffer,''):await loaderGLB.loadAsync(modelURL);c.root.add(gltf.scene);c.root.position.set(feature.x,feature.y,feature.z);const loader=new THREE.TextureLoader();const maps=Object.fromEntries(await Promise.all(Object.entries({stone:stoneURL,floor:floorURL,wood:woodURL,roof:roofURL}).map(async([key,url])=>{const t=await loader.loadAsync(url);t.colorSpace=THREE.SRGBColorSpace;t.wrapS=t.wrapT=THREE.RepeatWrapping;t.magFilter=THREE.NearestFilter;t.minFilter=THREE.LinearMipmapLinearFilter;return[key,t];})));
    gltf.scene.traverse(object=>{if(object instanceof THREE.Mesh){object.castShadow=true;object.receiveShadow=true;const original=object.material as THREE.MeshStandardMaterial;const name=original.name;const map=maps[name];const m=new THREE.MeshLambertMaterial({color:map?0xffffff:original.color,map:map||null});object.material=m;if(map){const pos=object.geometry.getAttribute('position'),norm=object.geometry.getAttribute('normal');const uv=new Float32Array(pos.count*2);for(let i=0;i<pos.count;i++){const ax=Math.abs(norm.getX(i)),ay=Math.abs(norm.getY(i)),az=Math.abs(norm.getZ(i));uv[i*2]=(ay>ax&&ay>az?pos.getX(i):ax>az?pos.getZ(i):pos.getX(i))/2.2;uv[i*2+1]=(ay>ax&&ay>az?pos.getZ(i):pos.getY(i))/2.2;}object.geometry.setAttribute('uv',new THREE.BufferAttribute(uv,2));}}});
    for(const d of layout.doors){const o=gltf.scene.getObjectByName(d.id)!;c.doors.set(d.id,o);if(doorState.includes(d.id.split('-')[0])){c.open.add(d.id.split('-')[0]);o.rotation.y=-d.sign*Math.PI*.49;c.angles.set(d.id,Math.PI*.49);}else c.angles.set(d.id,0);}return c;}
  setOrigin(x:number,z:number){this.origin={x,z};this.root.position.set(this.feature.x-x,this.feature.y,this.feature.z-z);}
  near(x:number,z:number){return Math.hypot(x-this.feature.x,z-this.feature.z)<140;}
  inside(x:number,y:number,z:number){return Math.abs(x-this.feature.x)<12&&z-this.feature.z<5.5&&z-this.feature.z>-30&&y>=this.feature.y+1.3;}
  chamber(x:number,z:number){return Math.abs(x-this.feature.x)<12&&z-this.feature.z< -4&&z-this.feature.z> -29;}
  activate(physics:Physics){if(this.active)return;this.physics=physics;this.active=true;const ox=this.feature.x-this.origin.x,oz=this.feature.z-this.origin.z;for(const s of layout.collision){this.solid.push(physics.box(ox+s.x,this.feature.y+s.y,oz+s.z,s.sx,s.sy,s.sz,s.kind as 'stone'|'wood'));}for(const d of layout.doors){const collider=physics.box(ox+d.x+d.sign*d.width/2,this.feature.y+d.floor+d.height/2,oz+d.z,d.width,d.height,.2,'wood');this.doorBodies.set(d.id,collider);}this.updateDoors(0);}
  deactivate(){if(!this.active)return;for(const c of [...this.solid,...this.doorBodies.values()])this.physics!.remove(c);this.solid=[];this.doorBodies.clear();this.active=false;}
  updateDoors(dt:number){for(const d of layout.doors){const target=this.open.has(d.id.split('-')[0])?Math.PI*.49:0;let a=this.angles.get(d.id)||0;a=THREE.MathUtils.damp(a,target,4,dt);this.angles.set(d.id,a);const r=-d.sign*a;this.doors.get(d.id)!.rotation.y=r;const c=this.doorBodies.get(d.id);if(c){c.setTranslation({x:this.feature.x-this.origin.x+d.x+Math.cos(r)*d.sign*d.width/2,y:this.feature.y+d.floor+d.height/2,z:this.feature.z-this.origin.z+d.z-Math.sin(r)*d.sign*d.width/2});c.setRotation(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,1,0),r));}}}
  interaction(x:number,z:number,yaw:number){for(const pair of ['gate','hall']){const d=layout.doors.find(d=>d.id.startsWith(pair))!;const dx=this.feature.x-x,dz=this.feature.z+d.z-z;const dist=Math.hypot(dx,dz);const forwardX=-Math.sin(yaw),forwardZ=-Math.cos(yaw);if(dist<3.4&&(dx*forwardX+dz*forwardZ>-.3)&&!this.open.has(pair))return{label:'Open',id:pair};}return null;}
  openDoor(id:string){this.open.add(id);}
  doorState(){return [...this.open];}
  princess(){const p=layout.princess;return{x:this.feature.x+p.x,y:this.feature.y+p.y,z:this.feature.z+p.z};}
  guards(){return layout.guards.map(p=>({x:this.feature.x+p.x,y:this.feature.y+p.y,z:this.feature.z+p.z}));}
  navigation(){return layout.navigation.map(p=>({x:this.feature.x+p.x,z:this.feature.z+p.z}));}
  floor(x:number,z:number){const lx=x-this.feature.x,lz=z-this.feature.z;if(Math.abs(lx)<13&&lz<=6&&lz>-30)return this.feature.y+1.8;if(Math.abs(lx)<3.5&&lz>6&&lz<10.4)return this.feature.y+Math.min(1.8,Math.ceil((10.4-lz)/.68)*.3);return this.feature.y;}
  dispose(){this.deactivate();const materials=new Set<THREE.Material>(),geos=new Set<THREE.BufferGeometry>(),textures=new Set<THREE.Texture>();this.root.traverse(o=>{if(o instanceof THREE.Mesh){geos.add(o.geometry);const m=o.material as THREE.MeshLambertMaterial;materials.add(m);if(m.map)textures.add(m.map);}});geos.forEach(g=>g.dispose());materials.forEach(m=>m.dispose());textures.forEach(t=>t.dispose());this.root.removeFromParent();}
}
