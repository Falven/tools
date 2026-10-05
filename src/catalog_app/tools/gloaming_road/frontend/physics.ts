import RAPIER from '@dimforge/rapier3d-compat';
import * as THREE from 'three';
import type {ChunkData} from './world-contract';
export {RAPIER};
export type BodyTag={kind:'ground'|'stone'|'wood'|'trunk'|'rock'|'player'|'enemy';id?:string};
export interface Capsule {body:RAPIER.RigidBody;collider:RAPIER.Collider;grounded:boolean;vy:number;}
const q={x:0,y:0,z:0,w:1};
export class Physics {
  world:RAPIER.World;controller:RAPIER.KinematicCharacterController;tags=new Map<number,BodyTag>(); private chunkData=new Map<string,ChunkData>();private chunkSolids=new Map<string,RAPIER.Collider[]>();private origin={x:0,z:0};private sweepBall=new RAPIER.Ball(.055);private projectileBall=new RAPIER.Ball(.09);
  constructor(){this.world=new RAPIER.World({x:0,y:-16,z:0});this.world.timestep=1/60;this.controller=this.world.createCharacterController(.015);this.controller.setMaxSlopeClimbAngle(50*Math.PI/180);this.controller.setMinSlopeSlideAngle(53*Math.PI/180);this.controller.enableAutostep(.34,.18,false);this.controller.enableSnapToGround(.45);}
  static async initialize(){await RAPIER.init();}
  addChunk(data:ChunkData){this.chunkData.set(data.key,data);}
  removeChunk(key:string){const all=this.chunkSolids.get(key);if(all)for(const c of all)this.remove(c);this.chunkSolids.delete(key);this.chunkData.delete(key);}
  syncChunks(x:number,z:number){const cx=Math.floor(x/64),cz=Math.floor(z/64);for(const [key,data] of this.chunkData){const near=Math.abs(data.cx-cx)<=1&&Math.abs(data.cz-cz)<=1;if(near&&!this.chunkSolids.has(key)){const all:RAPIER.Collider[]=[];const desc=RAPIER.ColliderDesc.trimesh(data.positions,data.indices).setTranslation(data.cx*64-this.origin.x,0,data.cz*64-this.origin.z).setFriction(.85);all.push(this.add(desc,{kind:'ground'}));for(const p of data.props){if(p.radius<=0||p.height<=0)continue;let d:RAPIER.ColliderDesc;if(p.kind.includes('rock')||p.kind.includes('boulder'))d=RAPIER.ColliderDesc.ball(p.radius).setTranslation(p.x-this.origin.x,p.y+p.height*.35,p.z-this.origin.z);else d=RAPIER.ColliderDesc.cylinder(p.height*.5,p.radius).setTranslation(p.x-this.origin.x,p.y+p.height*.5,p.z-this.origin.z);all.push(this.add(d,{kind:p.kind.includes('rock')?'rock':'trunk',id:p.id}));}this.chunkSolids.set(key,all);}else if(!near&&this.chunkSolids.has(key)){for(const c of this.chunkSolids.get(key)!)this.remove(c);this.chunkSolids.delete(key);}}}
  ready(x:number,z:number){return this.chunkSolids.has(`${Math.floor(x/64)},${Math.floor(z/64)}`)||this.chunkSolids.has(`${Math.floor(x/64)}:${Math.floor(z/64)}`);}
  add(desc:RAPIER.ColliderDesc,tag:BodyTag,body?:RAPIER.RigidBody){const c=this.world.createCollider(desc,body);this.tags.set(c.handle,tag);return c;}
  box(x:number,y:number,z:number,sx:number,sy:number,sz:number,kind:BodyTag['kind']='stone',yaw=0){const rotation=new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,1,0),yaw);return this.add(RAPIER.ColliderDesc.cuboid(sx/2,sy/2,sz/2).setTranslation(x,y,z).setRotation(rotation),{kind});}
  capsule(x:number,y:number,z:number,id:string,player=false):Capsule{const body=this.world.createRigidBody(RAPIER.RigidBodyDesc.kinematicPositionBased().setTranslation(x,y+.86,z));const c=this.add(RAPIER.ColliderDesc.capsule(.54,.31).setFriction(0),{kind:player?'player':'enemy',id},body);return{body,collider:c,grounded:false,vy:0};}
  feet(c:Capsule){const p=c.body.translation();return new THREE.Vector3(p.x,p.y-.86,p.z);}
  move(c:Capsule,dx:number,dz:number,dt:number){c.vy=c.grounded?-1:Math.max(-22,c.vy-16*dt);this.controller.computeColliderMovement(c.collider,{x:dx,y:c.vy*dt,z:dz},undefined,undefined,col=>col.handle!==c.collider.handle);const m=this.controller.computedMovement();const p=c.body.translation();c.grounded=this.controller.computedGrounded();if(c.grounded)c.vy=-1;c.body.setNextKinematicTranslation({x:p.x+m.x,y:p.y+m.y,z:p.z+m.z});return m;}
  teleport(c:Capsule,x:number,y:number,z:number){c.body.setTranslation({x,y:y+.86,z},true);c.body.setNextKinematicTranslation({x,y:y+.86,z});c.vy=0;c.grounded=false;this.world.propagateModifiedBodyPositionsToColliders();}
  step(){this.world.step();}
  remove(c:RAPIER.Collider){this.tags.delete(c.handle);if(c.isValid())this.world.removeCollider(c,true);}
  removeCapsule(c:Capsule){this.tags.delete(c.collider.handle);if(c.body.isValid())this.world.removeRigidBody(c.body);}
  wallBetween(a:THREE.Vector3,b:THREE.Vector3):boolean{const delta=b.clone().sub(a),length=delta.length();if(length<.01)return false;const hit=this.world.castRay(new RAPIER.Ray(a,delta.multiplyScalar(1/length)),length,true,undefined,undefined,undefined,undefined,c=>{const k=this.tags.get(c.handle)?.kind;return k!=='player'&&k!=='enemy';});return !!hit&&hit.timeOfImpact<length-.07;}
  raySurface(a:THREE.Vector3,b:THREE.Vector3,ignore?:string){const delta=b.clone().sub(a),length=delta.length();if(length<.001)return null;const h=this.world.castShape(a,q,delta,this.projectileBall,0,1,true,undefined,undefined,undefined,undefined,c=>this.tags.get(c.handle)?.id!==ignore);return h?{tag:this.tags.get(h.collider.handle)!,point:a.clone().addScaledVector(delta,h.time_of_impact),collider:h.collider}:null;}
  bladeSweep(previous:{base:THREE.Vector3,tip:THREE.Vector3},next:{base:THREE.Vector3,tip:THREE.Vector3},owner:string,contact:(tag:BodyTag,point:THREE.Vector3)=>void){const touched=new Set<number>();const cast=(a:THREE.Vector3,b:THREE.Vector3)=>{const v=b.clone().sub(a);if(v.lengthSq()<.000001)return;const hit=this.world.castShape(a,q,v,this.sweepBall,0,1,true,undefined,undefined,undefined,undefined,c=>this.tags.get(c.handle)?.id!==owner);if(hit&&!touched.has(hit.collider.handle)){touched.add(hit.collider.handle);const tag=this.tags.get(hit.collider.handle);if(tag)contact(tag,a.clone().addScaledVector(v,hit.time_of_impact));}};
    // Sweep five points along the blade plus its length through three interpolated
    // poses. Only the active phase calls this, and each swing deduplicates IDs.
    for(let i=0;i<=4;i++){const t=i/4;cast(previous.base.clone().lerp(previous.tip,t),next.base.clone().lerp(next.tip,t));}for(let i=1;i<=3;i++){const f=i/3;cast(previous.base.clone().lerp(next.base,f),previous.tip.clone().lerp(next.tip,f));}
  }
  rebase(x:number,z:number){const dx=x-this.origin.x,dz=z-this.origin.z;this.world.bodies.forEach(b=>{const p=b.translation();const n={x:p.x-dx,y:p.y,z:p.z-dz};b.setTranslation(n,true);if(b.isKinematic())b.setNextKinematicTranslation(n);});this.world.colliders.forEach(c=>{if(!c.parent()){const p=c.translation();c.setTranslation({x:p.x-dx,y:p.y,z:p.z-dz});}});this.origin={x,z};this.world.propagateModifiedBodyPositionsToColliders();}
  stats(){return{colliders:this.tags.size,collisionChunks:this.chunkSolids.size};}
  dispose(){this.world.free();this.tags.clear();this.chunkSolids.clear();this.chunkData.clear();}
}
