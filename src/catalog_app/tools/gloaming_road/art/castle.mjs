// Original reusable architectural model. Run from frontend: node ../art/castle.mjs
import * as THREE from '../frontend/node_modules/three/build/three.module.js';
import {GLTFExporter} from '../frontend/node_modules/three/examples/jsm/exporters/GLTFExporter.js';
import {mergeGeometries} from '../frontend/node_modules/three/examples/jsm/utils/BufferGeometryUtils.js';
import {writeFile,mkdir} from 'node:fs/promises';
class FileReader {readAsArrayBuffer(blob){blob.arrayBuffer().then(x=>{this.result=x;this.onloadend?.();});}readAsDataURL(blob){blob.arrayBuffer().then(x=>{this.result=`data:${blob.type};base64,${Buffer.from(x).toString('base64')}`;this.onloadend?.();});}}
globalThis.FileReader=FileReader;
const scene=new THREE.Group();scene.name='Castle_of_the_Last_Light';const batches=new Map();
const colors={stone:0xb6b9a5,trim:0xd1ccb3,roof:0x97602f,wood:0x493827,iron:0x454a47,red:0x672e39,gold:0xb69b59,floor:0x999a87,ceiling:0x888d86,glass:0x657d7c};
const mats=Object.fromEntries(Object.entries(colors).map(([name,color])=>[name,new THREE.MeshStandardMaterial({name,color,roughness:.95,metalness:name==='iron'?.35:name==='gold'?.18:0})]));
const solid=[];const furniture=[];
function add(geo,mat,x,y,z,rotation=[0,0,0],scale=[1,1,1],area='exterior'){if(geo.index)geo=geo.toNonIndexed();const matrix=new THREE.Matrix4().compose(new THREE.Vector3(x,y,z),new THREE.Quaternion().setFromEuler(new THREE.Euler(...rotation)),new THREE.Vector3(...scale));geo.applyMatrix4(matrix);const key=area+'_'+mat;(batches.get(key)||batches.set(key,[]).get(key)).push(geo);}
function box(mat,x,y,z,sx,sy,sz,collision=true,area='exterior'){add(new THREE.BoxGeometry(sx,sy,sz),mat,x,y,z,[0,0,0],[1,1,1],area);if(collision)solid.push({x,y,z,sx,sy,sz,kind:mat==='wood'?'wood':'stone'});}
function cyl(mat,x,y,z,r1,r2,h,segments=12,area='exterior'){add(new THREE.CylinderGeometry(r1,r2,h,segments),mat,x,y,z,[0,0,0],[1,1,1],area);}
function arch(x,y,z,w,h,depth,mat='trim',area='exterior'){// pointed original masonry arch, split piers never cover the opening
  const r=w/2;for(const side of [-1,1]){const shape=new THREE.Shape();shape.moveTo(side*r,0);shape.lineTo(side*(r+.45),0);shape.lineTo(side*(r+.45),h*.6);shape.quadraticCurveTo(side*(r+.35),h*.92,0,h+.46);shape.lineTo(0,h);shape.quadraticCurveTo(side*r*.95,h*.72,side*r,h*.58);shape.closePath();const g=new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:5});add(g,mat,x,y,z,[0,0,0],[1,1,1],area);}
  for(let i=0;i<9;i++){const t=i/8*Math.PI;const xx=Math.cos(t)*r,yy=Math.sin(t)*r*.78;box('trim',x+xx,y+h*.6+yy,z+.03,.22,.35,depth+.12,false,area);}}
function roof(x,z,r,h,y){cyl('roof',x,y+h/2,z,.08,r,h,12);cyl('trim',x,y,z,r+.25,r+.25,.3,12);cyl('gold',x,y+h+.32,z,.055,.09,.6,8);for(let i=1;i<5;i++){const rh=r*(1-i/5);cyl('roof',x,y+h*i/5,z,rh+.05,rh+.13,.13,12);}}
function tower(x,z,h,r){cyl('stone',x,h*.5,z,r,r+.5,h,12);cyl('trim',x,1,z,r+.64,r+.75,.55,12);cyl('trim',x,h-.4,z,r+.42,r+.25,.8,12);cyl('stone',x,h+1.05,z,r+.45,r+.45,2.1,12);for(let i=0;i<12;i++){const a=i*Math.PI/6;box('trim',x+Math.cos(a)*(r+.28),h+2.4,z+Math.sin(a)*(r+.28),.78,.9,.78,false);}roof(x,z,r+.1,5.5,h+2.6);for(const ang of [0,Math.PI*.5,Math.PI,Math.PI*1.5]){const px=x+Math.sin(ang)*(r+.025),pz=z+Math.cos(ang)*(r+.025);add(new THREE.PlaneGeometry(.32,1.75),'iron',px,h*.62,pz,[0,ang,0]);}solid.push({x,y:h/2,z,sx:r*1.42,sy:h,sz:r*1.42,kind:'stone'});}
// Terraced grounded perimeter and flagstone forecourt.
box('floor',0,-.18,0,50,.36,68);box('stone',0,-.7,0,51,1.0,69);
box('stone',-24,4.8,0,2,9.6,68);box('stone',24,4.8,0,2,9.6,68);box('stone',0,4.8,-33,48,9.6,2);
box('stone',-14.25,4.8,33,19.5,9.6,2);box('stone',14.25,4.8,33,19.5,9.6,2);box('stone',0,8.5,33,9,2.2,2);
arch(0,0,32.0,8.5,7.4,2);box('trim',0,9.75,33,47,.5,2.3,false);
for(let z=-30;z<=30;z+=3){for(const x of [-24,24]){box('trim',x,10.15,z,2.45,1.25,1.3,false);box('trim',x,1.2,z,2.4,.24,1.8,false);}}
for(let x=-21;x<=21;x+=3){box('trim',x,10.15,-33,1.3,1.25,2.45,false);if(Math.abs(x)>6)box('trim',x,10.15,33,1.3,1.25,2.45,false);}
for(const [x,z,h,r] of [[-23,31,16,3.1],[23,31,16,3.1],[-23,-31,20,3.5],[23,-31,20,3.5],[-7,32.5,12.5,2.4],[7,32.5,12.5,2.4]])tower(x,z,h,r);
// Royal hall. Ground floor raised 1.8m; broad stair connects courtyard.
box('stone',0,.8,-12,27,2,36);box('floor',0,1.72,-12,27,.16,36,false,'interior');
for(let i=0;i<6;i++)box('floor',0,(i+1)*.15,10-i*.68,7,(i+1)*.3,.72);
for(const x of [-12.7,12.7]){box('stone',x,6.4,-12,1.4,9.2,36);for(let z=-27;z<=1;z+=7){box('trim',x*1.02,6.5,z,1.7,10,1.1,false);box('trim',x*1.08,1.8,z,2.3,.5,1.7,false);}}
box('stone',0,6.3,-29.5,27,9.2,1.2);box('stone',-8.65,6.3,5.5,8.1,9.2,1.3);box('stone',8.65,6.3,5.5,8.1,9.2,1.3);box('stone',0,9.6,5.5,9.2,2.6,1.3);arch(0,1.8,4.8,8.2,6.1,1.3);
// True gabled roof, not flat boxes, ends ornamental apex.
const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute([-14,0,-19,14,0,-19,0,7,-19,14,0,19,-14,0,19,0,7,19,-14,0,19,-14,0,-19,0,7,-19,-14,0,19,0,7,-19,0,7,19,14,0,-19,14,0,19,0,7,19,14,0,-19,0,7,19,0,7,-19],3));g.computeVertexNormals();g.setAttribute('uv',new THREE.Float32BufferAttribute(Array.from({length:18},(_,i)=>i%3===2?[.5,1]:[i%3,0]).flat(),2));add(g,'roof',0,10.8,-12);
box('ceiling',0,10.75,-12,26,.25,35,false,'interior');
for(let z=-26;z<=4;z+=5){box('wood',0,10.32,z,25,.3,.36,false,'interior');for(const x of [-11.7,11.7]){cyl('trim',x,6.3,z,.27,.34,9,8,'interior');box('trim',x,2,z,.85,.42,.85,false,'interior');box('trim',x,10.1,z,.85,.45,.85,false,'interior');}}
// Vestibule arch creates a short, seamless interior route to the chamber.
box('stone',-8.9,5.5,-3,6.3,7.4,.7,true,'interior');box('stone',8.9,5.5,-3,6.3,7.4,.7,true,'interior');box('stone',0,8.95,-3,12,1.1,.7,true,'interior');arch(0,1.8,-3.3,11.1,6.1,.6,'trim','interior');
// Tapestries, casement recesses, carpet and old furnishings.
box('red',0,1.82,-13,4.3,.025,27,false,'interior');for(const x of [-2.08,2.08])box('gold',x,1.845,-13,.04,.01,27,false,'interior');
for(const x of [-11.94,11.94])for(const z of [-22,-12]){box('iron',x,6.6,z,.06,4.4,2.8,false,'interior');box('glass',x*.999,6.6,z,.035,4,2.4,false,'interior');for(const yy of [4.6,6.6,8.6])box('trim',x*.998,yy,z,.12,.12,2.55,false,'interior');for(const zz of [z-.85,z,z+.85])box('trim',x*.998,6.6,zz,.12,4.15,.1,false,'interior');}
for(const x of [-6.5,6.5]){box('red',x,6.5,-28.82,2.0,5.2,.04,false,'interior');box('gold',x,8.94,-28.77,2.15,.15,.12,false,'interior');box('gold',x,6.55,-28.76,.16,2.5,.03,false,'interior');box('gold',x,7.3,-28.73,.95,.12,.02,false,'interior');}
box('floor',0,1.95,-25,8,.3,6,true,'interior');box('floor',0,2.12,-26,6,.15,3.8,true,'interior');
box('wood',0,2.62,-26.8,2,.85,1.25,true,'interior');box('red',0,3.05,-26.7,1.6,.15,1.0,false,'interior');box('wood',0,4.1,-27.3,2,3.4,.26,true,'interior');box('red',0,4.1,-27.12,1.52,2.8,.04,false,'interior');for(const x of [-1.08,1.08]){box('gold',x,4.2,-27.3,.12,3.65,.32,false,'interior');box('wood',x,3.28,-26.7,.18,.2,1.5,false,'interior');cyl('gold',x,6.1,-27.3,.015,.13,.35,8,'interior');}
arch(0,2.45,-27.5,2.3,3.35,.2,'gold','interior');
for(const x of [-8,8]){box('wood',x,2.5,-15,1.7,.14,6,true,'interior');for(const z of [-17.5,-12.5])box('wood',x,2.12,z,1.0,.55,.35,true,'interior');for(let i=0;i<3;i++){box('wood',x,2.22,-6+i*.4,1.6,.15,.32,true,'interior');}}
// Planter seats around courtyard; dry central well is scenery, never a quest.
for(const x of [-17,17]){box('stone',x,.6,21,3.8,1.2,1.4);box('trim',x,1.3,21,4.1,.3,1.6);}
for(let i=0;i<12;i++){const a=i*Math.PI/6;box('stone',-13+Math.cos(a)*1.5,.65,12+Math.sin(a)*1.5,.9,1.3,.8);}
// Doors are separate named assemblies with hinges; runtime handles collision.
const doors=[{id:'gate-left',x:-4.15,z:33.05,width:4.15,height:6.7,floor:0,sign:1},{id:'gate-right',x:4.15,z:33.05,width:4.15,height:6.7,floor:0,sign:-1},{id:'hall-left',x:-4.0,z:5.5,width:4.0,height:5.7,floor:1.8,sign:1},{id:'hall-right',x:4.0,z:5.5,width:4.0,height:5.7,floor:1.8,sign:-1}];
for(const d of doors){const hinge=new THREE.Group();hinge.name=d.id;hinge.position.set(d.x,d.floor,d.z);const leaf=new THREE.Mesh(new THREE.BoxGeometry(d.width-.12,d.height,.18),mats.wood);leaf.position.set(d.sign*d.width/2,d.height/2,0);hinge.add(leaf);for(const y of [.65,d.height*.5,d.height-.55]){const strap=new THREE.Mesh(new THREE.BoxGeometry(d.width-.12,.13,.24),mats.iron);strap.position.set(d.sign*d.width/2,y,0);hinge.add(strap);}for(let i=1;i<8;i++){const seam=new THREE.Mesh(new THREE.BoxGeometry(.018,d.height-.12,.21),mats.iron);seam.position.set(d.sign*(d.width*i/8),d.height/2,0);hinge.add(seam);}scene.add(hinge);}
for(const [key,geos] of batches){const matName=key.slice(key.indexOf('_')+1);const merged=mergeGeometries(geos,false);const mesh=new THREE.Mesh(merged,mats[matName]);mesh.name=key;scene.add(mesh);geos.forEach(g=>g.dispose());}
scene.userData={author:'The Gloaming Road original architecture',units:'metres',front:'+Z',collision:solid,doors,princess:{x:2.65,y:2.13,z:-25.9},guards:[{x:0,y:1.8,z:1},{x:-4,y:1.8,z:-12},{x:4,y:1.8,z:-17}],navigation:[{x:0,z:39},{x:0,z:24},{x:0,z:11},{x:0,z:5},{x:0,z:0},{x:0,z:-8},{x:-6,z:-13},{x:6,z:-13},{x:0,z:-22}]};
await mkdir(new URL('../frontend/assets/castle/',import.meta.url),{recursive:true});
const bytes=await new GLTFExporter().parseAsync(scene,{binary:true});await writeFile(new URL('../frontend/assets/castle/last-light.glb',import.meta.url),Buffer.from(bytes));await writeFile(new URL('../frontend/assets/castle/layout.json',import.meta.url),JSON.stringify(scene.userData,null,2)+'\n');console.log(`Original castle exported: ${(bytes.byteLength/1024).toFixed(0)}KiB, ${solid.length} colliders, ${batches.size} material/zone batches.`);
