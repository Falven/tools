import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { WIDTH, HEIGHT } from './core.js';

const ACID = 0xc7ff62, ORANGE = 0xff9259;
const DEMO_BODY = [[16,6],[15,6],[14,6],[13,6],[12,6],[11,6],[10,6],[9,6],[9,7],[9,8],[9,9],[10,9],[11,9],[12,9],[13,9],[14,9],[14,10],[14,11],[14,12],[13,12],[12,12],[11,12],[10,12],[9,12],[8,12],[7,12],[6,12]];
const MAX_PARTICLES = 64;
const scratch = new THREE.Object3D();
const color = new THREE.Color();

function glowTexture() {
  const canvas = document.createElement('canvas'); canvas.width = canvas.height = 128;
  const ctx = canvas.getContext('2d');
  const gradient = ctx.createRadialGradient(64,64,1,64,64,64);
  gradient.addColorStop(0,'rgba(255,255,255,.85)'); gradient.addColorStop(.16,'rgba(255,255,255,.5)'); gradient.addColorStop(.48,'rgba(255,255,255,.12)'); gradient.addColorStop(1,'rgba(255,255,255,0)');
  ctx.fillStyle = gradient; ctx.fillRect(0,0,128,128);
  return new THREE.CanvasTexture(canvas);
}
function boardLabel() {
  const canvas = document.createElement('canvas'); canvas.width = 512; canvas.height = 64;
  const ctx = canvas.getContext('2d'); ctx.fillStyle = '#1b2319'; ctx.fillRect(0,0,512,64);
  ctx.font = 'bold 24px monospace'; ctx.textAlign = 'center'; ctx.fillStyle = '#b9d88c'; ctx.fillText('N E O N  / /  C O I L',256,40);
  const tex = new THREE.CanvasTexture(canvas); tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/** A fixed camera, instanced geometry and baked glows — no expensive post-processing. */
export class NeonRenderer {
  constructor(container, onContextLost) {
    this.container = container;
    this.reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.FogExp2(0x111314, .013);
    this.camera = new THREE.OrthographicCamera(-20,20,12,-12,.1,150);
    this.renderer = new THREE.WebGLRenderer({ antialias:false, alpha:true, powerPreference:'high-performance', stencil:false });
    const gl=this.renderer.getContext(), gpuInfo=gl.getExtension('WEBGL_debug_renderer_info');
    this.software=Boolean(gpuInfo&&/SwiftShader|llvmpipe|Software|Subzero|Microsoft Basic/i.test(gl.getParameter(gpuInfo.UNMASKED_RENDERER_WEBGL)));
    this.renderer.setClearColor(0x111314,1);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.25;
    this.renderer.domElement.setAttribute('aria-hidden','true');
    this.renderer.domElement.addEventListener('webglcontextlost', event => { event.preventDefault(); onContextLost?.(); });
    this.renderer.domElement.addEventListener('webglcontextrestored', () => onContextLost?.(true));
    container.append(this.renderer.domElement);
    this.mode = 'auto'; this.dpr = Math.min(devicePixelRatio || 1, 1.65); this.slowFrames = 0; this.goodFrames = 0;
    this.frameTimes = new Float32Array(180); this.frameIndex = 0; this.totalFrames = 0;
    this.intro = true; this.introMix = 1; this.hitFlash = 0; this.biteFlash = 0;
    this.particles = Array.from({length:MAX_PARTICLES}, () => ({life:0,x:0,y:0,z:0,vx:0,vy:0,vz:0,spin:0}));
    this.particleCursor = 0;
    this.glow = glowTexture();
    this.buildWorld(); this.batchStatic(this.scene); this.buildSnake(); this.buildFood(); this.buildParticles();
    this.resizeObserver = new ResizeObserver(() => this.resize()); this.resizeObserver.observe(container); this.resize();
  }
  lit(options) {
    if(!this.software)return new THREE.MeshStandardMaterial(options);
    // Keep volume and highlights on software/mobile renderers without the PBR cost.
    const {color,emissive,emissiveIntensity}=options;
    return new THREE.MeshPhongMaterial({color,emissive:emissive??0,emissiveIntensity:emissiveIntensity??1,shininess:45,specular:0x25311b});
  }
  batchStatic(group) {
    const byMaterial=new Map();group.updateMatrixWorld(true);
    for(const mesh of group.children){
      if(!mesh.isMesh||mesh.isInstancedMesh||Array.isArray(mesh.material))continue;
      const list=byMaterial.get(mesh.material)||[];list.push(mesh);byMaterial.set(mesh.material,list);
    }
    for(const [material,meshes] of byMaterial){
      if(meshes.length<2)continue;
      const parts=meshes.map(mesh=>mesh.geometry.clone().applyMatrix4(mesh.matrix));
      const merged=mergeGeometries(parts);parts.forEach(part=>part.dispose());
      if(!merged)continue;
      meshes.forEach(mesh=>{group.remove(mesh);mesh.geometry.dispose();});
      group.add(new THREE.Mesh(merged,material));
    }
  }
  buildWorld() {
    const {scene} = this;
    scene.add(new THREE.HemisphereLight(0xd2eeb0,0x343345,.85));
    const key = new THREE.DirectionalLight(0xf9ffe5,2.0); key.position.set(-10,25,12); scene.add(key);
    const rim = new THREE.DirectionalLight(0xaca0ff,1.5); rim.position.set(15,12,-14); scene.add(rim);
    const front = new THREE.DirectionalLight(0xafff4f,.5); front.position.set(-2,6,20); scene.add(front);
    const plane = new THREE.Mesh(new THREE.PlaneGeometry(180,180),new THREE.MeshBasicMaterial({color:0x111815,toneMapped:false}));
    plane.rotation.x = -Math.PI/2; plane.position.y = -1.15; scene.add(plane);
    const grid = new THREE.GridHelper(140,70,0x29332c,0x242c26); grid.position.y = -1.14; grid.material.transparent = true; grid.material.opacity = .4; scene.add(grid);
    const underglow = new THREE.Mesh(new THREE.PlaneGeometry(43,34),new THREE.MeshBasicMaterial({map:this.glow,color:0x80b552,transparent:true,opacity:.21,depthWrite:false,blending:THREE.AdditiveBlending}));
    underglow.rotation.x = -Math.PI/2; underglow.position.y = -1.11; scene.add(underglow);
    const sideMaterial = this.lit({color:0x303b29,roughness:.5,metalness:.48});
    const chassis = new THREE.Mesh(new RoundedBoxGeometry(WIDTH+1.35,.85,HEIGHT+1.35,3,.24),sideMaterial); chassis.position.y = -.61; scene.add(chassis);
    const lower = new THREE.Mesh(new RoundedBoxGeometry(WIDTH+1.1,.28,HEIGHT+1.1,2,.1),this.lit({color:0x111910,roughness:.5,metalness:.4})); lower.position.y = -.96; scene.add(lower);
    const deck = new THREE.Mesh(new THREE.BoxGeometry(WIDTH+.26,.18,HEIGHT+.26),this.lit({color:0x111a13,roughness:.5,metalness:.25})); deck.position.y = -.15; scene.add(deck);
    const tiles = new THREE.InstancedMesh(new THREE.BoxGeometry(.942,.06,.942),new THREE.MeshBasicMaterial({toneMapped:false}),WIDTH*HEIGHT);
    for(let y=0;y<HEIGHT;y++) for(let x=0;x<WIDTH;x++) {
      scratch.position.set(x-(WIDTH-1)/2,-.045,y-(HEIGHT-1)/2); scratch.rotation.set(0,0,0); scratch.scale.set(1,1,1); scratch.updateMatrix();
      tiles.setMatrixAt(y*WIDTH+x,scratch.matrix);
      const tone = (x+y)%2 ? 0x263520 : 0x2b3824;
      tiles.setColorAt(y*WIDTH+x,color.setHex(tone));
    }
    tiles.instanceMatrix.needsUpdate = true; tiles.instanceColor.needsUpdate = true; scene.add(tiles);
    const rails = this.lit({color:0x465533,roughness:.38,metalness:.65});
    this.railGlow = new THREE.MeshBasicMaterial({color:0x9ace53,transparent:true,opacity:.85});
    for(const sign of [-1,1]) {
      const horizontal = new THREE.Mesh(new RoundedBoxGeometry(WIDTH+.62,.18,.16,1,.05),rails); horizontal.position.set(0,-.06,sign*(HEIGHT/2+.28)); scene.add(horizontal);
      const vertical = new THREE.Mesh(new RoundedBoxGeometry(.16,.18,HEIGHT+.62,1,.05),rails); vertical.position.set(sign*(WIDTH/2+.28),-.06,0); scene.add(vertical);
      const lightH = new THREE.Mesh(new THREE.BoxGeometry(WIDTH+.49,.022,.034),this.railGlow); lightH.position.set(0,.037,sign*(HEIGHT/2+.28)); scene.add(lightH);
      const lightV = new THREE.Mesh(new THREE.BoxGeometry(.034,.022,HEIGHT+.49),this.railGlow); lightV.position.set(sign*(WIDTH/2+.28),.037,0); scene.add(lightV);
      const skirt = new THREE.Mesh(new THREE.BoxGeometry(WIDTH+.35,.025,.02),new THREE.MeshBasicMaterial({color:0x516a33})); skirt.position.set(0,-.67,sign*(HEIGHT/2+.675)); scene.add(skirt);
    }
    const screwMaterial = this.lit({color:0x8c9980,roughness:.35,metalness:.9});
    for(const x of [-1,1]) for(const z of [-1,1]) {
      const screw = new THREE.Mesh(new THREE.CylinderGeometry(.087,.087,.02,8),screwMaterial); screw.position.set(x*(WIDTH/2+.47),-.19,z*(HEIGHT/2+.47)); scene.add(screw);
    }
    const label = new THREE.Mesh(new THREE.PlaneGeometry(4.4,.55),new THREE.MeshBasicMaterial({map:boardLabel()})); label.position.set(0,-.57,HEIGHT/2+.679); scene.add(label);
    const stripeMaterial = new THREE.MeshBasicMaterial({color:ORANGE});
    for(let i=0;i<4;i++) { const stripe = new THREE.Mesh(new THREE.PlaneGeometry(.16,.27),stripeMaterial); stripe.position.set(WIDTH/2-1.4-i*.27,-.56,HEIGHT/2+.68); stripe.rotation.z = -.35; scene.add(stripe); }
    // A sparse field adds depth, without image downloads or a full-screen effects pass.
    const positions = new Float32Array(72*3);
    let rng = 9741;
    const rand = () => {rng = (Math.imul(1664525,rng)+1013904223)>>>0; return rng/4294967296;};
    for(let i=0;i<72;i++){positions[i*3]=(rand()-.5)*80;positions[i*3+1]=rand()*9-1;positions[i*3+2]=(rand()-.5)*65;}
    const geometry = new THREE.BufferGeometry(); geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));
    this.motes = new THREE.Points(geometry,new THREE.PointsMaterial({color:0xb2d68c,size:.065,transparent:true,opacity:.45,depthWrite:false})); scene.add(this.motes);
  }
  buildSnake() {
    const material = this.lit({color:0x8fda20,emissive:0x68b309,emissiveIntensity:.48,roughness:.26,metalness:.24});
    this.body = new THREE.InstancedMesh(new RoundedBoxGeometry(.91,.61,.91,2,.13),material,WIDTH*HEIGHT); this.body.instanceMatrix.setUsage(THREE.DynamicDrawUsage); this.body.frustumCulled = false; this.scene.add(this.body);
    this.spines = new THREE.InstancedMesh(new RoundedBoxGeometry(.34,.022,.62,1,.01),new THREE.MeshBasicMaterial({color:0xe3ffa5,transparent:true,opacity:.38}),WIDTH*HEIGHT); this.spines.instanceMatrix.setUsage(THREE.DynamicDrawUsage); this.spines.frustumCulled = false; this.scene.add(this.spines);
    this.shadows = new THREE.InstancedMesh(new THREE.PlaneGeometry(1.7,1.7),new THREE.MeshBasicMaterial({map:this.glow,color:0x070e02,transparent:true,opacity:.7,depthWrite:false}),WIDTH*HEIGHT); this.shadows.instanceMatrix.setUsage(THREE.DynamicDrawUsage); this.shadows.frustumCulled = false; this.scene.add(this.shadows);
    this.head = new THREE.Group();
    const headMesh = new THREE.Mesh(new RoundedBoxGeometry(.97,.67,.97,3,.15),this.lit({color:0xaff036,emissive:0x7cc21c,emissiveIntensity:.5,roughness:.2,metalness:.23})); this.head.add(headMesh);
    for(const sign of [-1,1]) {
      const eye = new THREE.Mesh(new THREE.SphereGeometry(.102,12,8),new THREE.MeshBasicMaterial({color:0x14200f})); eye.scale.set(1,.35,1.35); eye.position.set(sign*.24,.332,-.22); this.head.add(eye);
      const glint = new THREE.Mesh(new THREE.SphereGeometry(.026,6,4),new THREE.MeshBasicMaterial({color:0xf5ffd0})); glint.position.set(sign*.24+.022,.367,-.252); this.head.add(glint);
    }
    const mouth = new THREE.Mesh(new THREE.BoxGeometry(.32,.03,.017),new THREE.MeshBasicMaterial({color:0x334621})); mouth.position.set(0,.02,-.489); this.head.add(mouth); this.scene.add(this.head);
    const auraMaterial = new THREE.SpriteMaterial({map:this.glow,color:0xc6ff51,transparent:true,opacity:.14,depthWrite:false,blending:THREE.AdditiveBlending});
    this.headAura = new THREE.Sprite(auraMaterial); this.headAura.scale.set(2.8,2.8,1); this.scene.add(this.headAura);
  }
  buildFood() {
    this.food = new THREE.Group();
    this.foodCore = new THREE.Mesh(new RoundedBoxGeometry(.53,.53,.53,2,.075),this.lit({color:0xff7c2b,emissive:0xff4508,emissiveIntensity:.7,metalness:.32,roughness:.18})); this.foodCore.rotation.set(.18,Math.PI/4,.2); this.food.add(this.foodCore);
    const cage = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.OctahedronGeometry(.53)),new THREE.LineBasicMaterial({color:0xffc892,transparent:true,opacity:.6})); this.food.add(cage); this.foodCage = cage;
    const halo = new THREE.Sprite(new THREE.SpriteMaterial({map:this.glow,color:ORANGE,transparent:true,opacity:.57,blending:THREE.AdditiveBlending,depthWrite:false})); halo.scale.set(2.45,2.45,1); this.food.add(halo); this.foodHalo = halo;
    this.scene.add(this.food);
    this.foodRing = new THREE.Mesh(new THREE.RingGeometry(.49,.515,48),new THREE.MeshBasicMaterial({color:0xffa568,transparent:true,opacity:.7,side:THREE.DoubleSide,depthWrite:false})); this.foodRing.rotation.x=-Math.PI/2; this.foodRing.position.y=.022; this.scene.add(this.foodRing);
    this.foodPool = new THREE.Mesh(new THREE.PlaneGeometry(3.5,3.5),new THREE.MeshBasicMaterial({map:this.glow,color:0xff8a42,transparent:true,opacity:.34,depthWrite:false,blending:THREE.AdditiveBlending})); this.foodPool.rotation.x=-Math.PI/2; this.foodPool.position.y=.025; this.scene.add(this.foodPool);
  }
  buildParticles() {
    this.particleMesh = new THREE.InstancedMesh(new THREE.BoxGeometry(.12,.12,.12),new THREE.MeshBasicMaterial({color:0xffb26c,transparent:true,opacity:.9}),MAX_PARTICLES); this.particleMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage); this.particleMesh.frustumCulled=false; this.scene.add(this.particleMesh); this.particleMesh.count=0;
  }
  setIntro(intro) { this.intro = intro; this.needsRender=true; }
  resize() {
    const box=this.container.getBoundingClientRect(); this.width=Math.max(1,box.width); this.height=Math.max(1,box.height); this.mobile=this.width<721;
    this.renderer.setPixelRatio(this.dpr); this.renderer.setSize(this.width,this.height,false); this.updateCamera(); this.needsRender=true;
  }
  updateCamera() {
    const aspect=this.width/this.height;
    const normalHeight=Math.max(22.5,28/aspect);
    const introHeight=this.mobile?Math.max(37,28/aspect):Math.max(22.5,27/(aspect*.62));
    const viewHeight=THREE.MathUtils.lerp(normalHeight,introHeight,this.introMix);
    const targetX=this.mobile?0:-viewHeight*aspect*.176*this.introMix;
    const targetZ=this.mobile?6.3*this.introMix:0;
    this.camera.left=-viewHeight*aspect/2; this.camera.right=viewHeight*aspect/2; this.camera.top=viewHeight/2; this.camera.bottom=-viewHeight/2;
    // No sideways orbit or roll: screen axes match the grid and arrow keys.
    // A small forward tilt preserves the raised tiles and visible front edge.
    this.camera.position.set(targetX,this.mobile?30:28,(this.mobile?18:22)+targetZ); this.camera.lookAt(targetX,0,targetZ); this.camera.updateProjectionMatrix();
  }
  cycleQuality() {
    this.mode=this.mode==='auto'?'ultra':this.mode==='ultra'?'lite':'auto';
    this.dpr=this.mode==='ultra'?Math.min(devicePixelRatio||1,2):this.mode==='lite'?.85:Math.min(devicePixelRatio||1,1.65);
    this.slowFrames=0;this.goodFrames=0;this.resize();return this.mode;
  }
  burst(cell, death=false) {
    if(!cell||this.reducedMotion)return;
    const count=death?40:22;
    for(let i=0;i<count;i++){
      const p=this.particles[this.particleCursor++%MAX_PARTICLES], a=Math.random()*Math.PI*2, v=1.1+Math.random()*3;
      p.life=.45+Math.random()*.45;p.total=p.life;p.x=cell[0]-(WIDTH-1)/2;p.z=cell[1]-(HEIGHT-1)/2;p.y=.5;p.vx=Math.cos(a)*v;p.vz=Math.sin(a)*v;p.vy=2+Math.random()*3;p.spin=Math.random()*6;
    }
    if(death)this.hitFlash=1;else this.biteFlash=1;
  }
  render(game,previous,alpha,time,dt) {
    const targetMix=this.intro?1:0;
    if(Math.abs(this.introMix-targetMix)>.001){this.introMix=this.reducedMotion?targetMix:THREE.MathUtils.damp(this.introMix,targetMix,7,Math.min(dt,.05));this.updateCamera();}
    const body=game?.body||DEMO_BODY;
    const old=previous||body;
    this.body.count=Math.max(0,body.length-1); this.spines.count=this.body.count; this.shadows.count=body.length;
    for(let i=0;i<body.length;i++){
      const from=old[Math.min(i,old.length-1)]||body[i]; const cell=body[i];
      const x=THREE.MathUtils.lerp(from[0],cell[0],alpha)-(WIDTH-1)/2;
      const z=THREE.MathUtils.lerp(from[1],cell[1],alpha)-(HEIGHT-1)/2;
      const y=.35+(!game&&!this.reducedMotion?Math.sin(time*1.7-i*.32)*.018:0);
      const to=body[Math.max(0,i-1)];const direction=i===0?(game?.direction??1):cell[0]!==to[0]?1:0;
      if(i===0){this.head.position.set(x,y+.015,z);this.head.rotation.y=[0,-Math.PI/2,Math.PI,Math.PI/2][direction];this.headAura.position.set(x,y,z);}
      else {
        scratch.position.set(x,y,z);scratch.rotation.set(0,direction===1?Math.PI/2:0,0);scratch.scale.set(1,1,1);scratch.updateMatrix();this.body.setMatrixAt(i-1,scratch.matrix);
        scratch.position.y=y+.312;scratch.updateMatrix();this.spines.setMatrixAt(i-1,scratch.matrix);
      }
      scratch.position.set(x,.014,z);scratch.rotation.set(-Math.PI/2,0,0);scratch.scale.set(1,1,1);scratch.updateMatrix();this.shadows.setMatrixAt(i,scratch.matrix);
    }
    this.body.instanceMatrix.needsUpdate=true;this.spines.instanceMatrix.needsUpdate=true;this.shadows.instanceMatrix.needsUpdate=true;
    const food=game?.food??(!game?[19,6]:null);this.food.visible=this.foodRing.visible=this.foodPool.visible=!!food;
    if(food){
      const x=food[0]-(WIDTH-1)/2,z=food[1]-(HEIGHT-1)/2;
      this.food.position.set(x,.75+(this.reducedMotion?0:Math.sin(time*3)*.08),z);this.foodRing.position.x=this.foodPool.position.x=x;this.foodRing.position.z=this.foodPool.position.z=z;
      if(!this.reducedMotion){this.foodCore.rotation.y=time*.8;this.foodCage.rotation.y=-time*.45;this.foodCage.rotation.z=Math.sin(time)*.16;}
      this.foodHalo.material.opacity=.48+(this.reducedMotion?0:Math.sin(time*3)*.09);
    }
    this.biteFlash=Math.max(0,this.biteFlash-dt*2.6);this.hitFlash=Math.max(0,this.hitFlash-dt*1.8);
    this.railGlow.color.setHex(this.hitFlash>0?ORANGE:ACID);this.railGlow.opacity=.6+this.biteFlash*.4+this.hitFlash*.4;
    this.headAura.material.opacity=.1+this.biteFlash*.2;
    let count=0;
    for(const p of this.particles){
      if(p.life<=0)continue;p.life-=dt;if(p.life<=0)continue;p.x+=p.vx*dt;p.z+=p.vz*dt;p.y+=p.vy*dt;p.vy-=9*dt;
      scratch.position.set(p.x,Math.max(.05,p.y),p.z);scratch.rotation.set(p.spin+time*3,p.spin+time*4,0);const s=Math.min(1,p.life*4);scratch.scale.set(s,s,s);scratch.updateMatrix();this.particleMesh.setMatrixAt(count++,scratch.matrix);
    }
    this.particleMesh.count=count;if(count)this.particleMesh.instanceMatrix.needsUpdate=true;
    if(!this.reducedMotion)this.motes.rotation.y=Math.sin(time*.022)*.012;
    this.renderer.render(this.scene,this.camera);this.needsRender=false;
  }
  measure(frameMs,active) {
    if(!active||frameMs<3||frameMs>2500)return;
    this.frameTimes[this.frameIndex++%this.frameTimes.length]=frameMs;this.totalFrames++;
    if(this.mode!=='auto')return;
    // Include slow startup/intro frames: adaptation must happen before a run starts.
    if(frameMs>70&&this.totalFrames>3&&this.dpr>.5){this.dpr=Math.max(.5,this.dpr-.25);this.slowFrames=0;this.resize();return;}
    this.slowFrames=frameMs>23?this.slowFrames+1:Math.max(0,this.slowFrames-1);
    this.goodFrames=frameMs<18?this.goodFrames+1:0;
    if(this.slowFrames>45&&this.dpr>.65){this.dpr=Math.max(.65,this.dpr-.2);this.slowFrames=0;this.resize();}
    else if(this.goodFrames>900&&this.dpr<Math.min(devicePixelRatio||1,1.65)){this.dpr=Math.min(devicePixelRatio||1,1.65,this.dpr+.1);this.goodFrames=0;this.resize();}
  }
  diagnostics(){
    const times=Array.from(this.frameTimes.subarray(0,Math.min(this.totalFrames,this.frameTimes.length))).sort((a,b)=>a-b);
    return {threeRevision:THREE.REVISION,softwareRenderer:this.software,quality:this.mode,pixelRatio:this.dpr,drawCalls:this.renderer.info.render.calls,triangles:this.renderer.info.render.triangles,sampledFrames:times.length,medianFrameMs:times[Math.floor(times.length*.5)]||0,p95FrameMs:times[Math.floor(times.length*.95)]||0,canvas:[this.renderer.domElement.width,this.renderer.domElement.height]};
  }
  dispose(){this.resizeObserver.disconnect();this.scene.traverse(obj=>{obj.geometry?.dispose();if(obj.material){const mats=Array.isArray(obj.material)?obj.material:[obj.material];mats.forEach(m=>m.dispose());}});this.glow.dispose();this.renderer.dispose();}
}
