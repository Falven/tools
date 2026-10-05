import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { courtLayout } from './layout.js';

const MINT = 0xc2f8b3, CORAL = 0xff936c, GOLD = 0xffe6ac;
const scratch = new THREE.Object3D(), tint = new THREE.Color(), goldTint = new THREE.Color(GOLD);
const PARTICLES = 64, TRAIL = 18;
const lerp = THREE.MathUtils.lerp;
const clamp = THREE.MathUtils.clamp;
function texture(draw, width = 128, height = width) {
  const canvas = document.createElement('canvas'); canvas.width = width; canvas.height = height;
  const context = canvas.getContext('2d'); if (!context) throw new Error('Canvas 2D is unavailable.');
  draw(context, width, height);
  const map = new THREE.CanvasTexture(canvas); map.colorSpace = THREE.SRGBColorSpace;
  return map;
}
function glowTexture() {
  return texture((ctx, w) => {
    const g = ctx.createRadialGradient(w/2,w/2,0,w/2,w/2,w/2);
    g.addColorStop(0,'rgba(255,255,255,1)');g.addColorStop(.18,'rgba(255,255,255,.62)');g.addColorStop(.5,'rgba(255,255,255,.13)');g.addColorStop(1,'rgba(255,255,255,0)');
    ctx.fillStyle=g;ctx.fillRect(0,0,w,w);
  });
}

/** Raised geometry + orthographic projection. All animation is cosmetic; physics lives in core.js. */
export class RallyRenderer {
  constructor(container, onContextChange) {
    this.container = container; this.onContextChange = onContextChange;
    this.reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.scene = new THREE.Scene(); this.scene.fog = new THREE.FogExp2(0x101613, .013);
    this.camera = new THREE.OrthographicCamera(-20,20,12,-12,.1,140);
    this.renderer = new THREE.WebGLRenderer({alpha:true,antialias:false,powerPreference:'high-performance',stencil:false});
    this.renderer.setClearColor(0x101613,0);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping; this.renderer.toneMappingExposure = 1.22;
    const gl=this.renderer.getContext(), info=gl.getExtension('WEBGL_debug_renderer_info');
    this.software=Boolean(info&&/SwiftShader|llvmpipe|Software|Subzero|Microsoft Basic/i.test(gl.getParameter(info.UNMASKED_RENDERER_WEBGL)));
    if(this.software)this.scene.fog=null;
    this.container.classList.toggle('software-renderer',this.software);
    this.canvas=this.renderer.domElement; this.canvas.setAttribute('aria-hidden','true');
    this.lost=false; this.disposed=false;
    this.lostHandler=e=>{e.preventDefault();this.lost=true;this.onContextChange?.(false);};
    this.restoreHandler=()=>{this.lost=false;this.resize();this.onContextChange?.(true);};
    this.canvas.addEventListener('webglcontextlost',this.lostHandler);
    this.canvas.addEventListener('webglcontextrestored',this.restoreHandler);
    container.append(this.canvas);
    this.mode='auto';this.dpr=Math.min(devicePixelRatio||1,this.software?.75:1.6);
    this.intro=true;this.introMix=1;this.needsRender=true;this.frames=0;this.frameTimes=new Float32Array(120);this.slow=0;this.good=0;
    this.glow=glowTexture();this.world=new THREE.Group();this.scene.add(this.world);
    this.raycaster=new THREE.Raycaster();this.pointer=new THREE.Vector2();this.hit=new THREE.Vector3();this.plane=new THREE.Plane(new THREE.Vector3(0,1,0),-.18);
    this.particles=Array.from({length:PARTICLES},()=>({life:0,x:0,y:0,z:0,vx:0,vy:0,vz:0,color:MINT}));this.particleCursor=0;
    this.trail=Array.from({length:TRAIL},()=>({x:0,z:0}));this.trailClock=0;this.lastServe=true;this.flash=0;
    this.buildWorld();this.batchStatic(this.world);this.buildPlayers();this.buildBall();this.buildParticles();
    this.resizeObserver=new ResizeObserver(()=>this.resize());this.resizeObserver.observe(container);this.resize();
  }
  lit(color,options={}) {
    if(this.software){
      // Software rasterizers get vertex-lit volume with a tiny fragment shader;
      // expensive per-pixel lighting is not allowed to slow down paddle input.
      return new THREE.ShaderMaterial({
        uniforms:{tint:{value:new THREE.Color(color).convertLinearToSRGB()}},
        vertexShader:'varying float shade; void main(){shade=0.60+0.36*max(normal.y,0.0)+0.10*max(-normal.x,0.0)+0.04*max(normal.z,0.0);gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}',
        fragmentShader:'uniform vec3 tint; varying float shade; void main(){gl_FragColor=vec4(tint*shade,1.0);}',
      });
    }
    return new THREE.MeshStandardMaterial({color,roughness:.33,metalness:.28,...options});
  }
  box(w,h,d,color,x=0,y=0,z=0,r=.06,parent=this.world) {
    const mesh=new THREE.Mesh(r?new RoundedBoxGeometry(w,h,d,2,r):new THREE.BoxGeometry(w,h,d),typeof color==='number'?this.lit(color):color);
    mesh.position.set(x,y,z);parent.add(mesh);return mesh;
  }
  planeMesh(w,h,material,x,y,z,parent=this.world) {
    const mesh=new THREE.Mesh(new THREE.PlaneGeometry(w,h),material);mesh.rotation.x=-Math.PI/2;mesh.position.set(x,y,z);parent.add(mesh);return mesh;
  }
  buildWorld() {
    this.scene.add(new THREE.HemisphereLight(0xd9f4d9,0x20291f,1.45));
    const key=new THREE.DirectionalLight(0xf1ffdc,2.1);key.position.set(-9,20,9);this.scene.add(key);
    const rim=new THREE.DirectionalLight(0xffa37c,2.2);rim.position.set(12,9,-9);this.scene.add(rim);
    const fill=new THREE.DirectionalLight(0x95dec3,.65);fill.position.set(-14,6,-11);this.scene.add(fill);
    if(!this.software){
      this.planeMesh(160,160,new THREE.MeshBasicMaterial({color:0x101613}),0,-2.12,0,this.scene);
      const grid=new THREE.GridHelper(120,60,0x36443a,0x293b2e);grid.position.y=-2.1;grid.material.transparent=true;grid.material.opacity=.32;this.scene.add(grid);
      this.planeMesh(36,27,new THREE.MeshBasicMaterial({map:this.glow,color:0x080c09,transparent:true,opacity:.9,depthWrite:false}),0,-2.075,.8);
      this.planeMesh(32,24,new THREE.MeshBasicMaterial({map:this.glow,color:0x679650,transparent:true,opacity:.2,depthWrite:false,blending:THREE.AdditiveBlending}),0,-2.06,0);
    }
    this.box(22.0,.28,14.0,0x1b241c,0,-1.01,0,.2);
    this.box(22.4,.72,14.4,0x35473c,0,-.64,0,.28);
    this.box(22.0,.1,14.0,0x7f9280,0,-.25,0,.07);
    this.box(21.8,.15,13.8,0x152b20,0,-.13,0,.06);
    // Court surface is a physical mat, not an image or an external texture.
    this.box(20.1,.06,12.08,this.lit(0x204635,{roughness:.86,metalness:0}),0,-.025,0,0);
    const lineMaterial=new THREE.LineBasicMaterial({color:0xacc7a4,transparent:true,opacity:.65});
    const lines=[-10,.018,-6,10,.018,-6,10,.018,-6,10,.018,6,10,.018,6,-10,.018,6,-10,.018,6,-10,.018,-6];
    for(let z=-5.7;z<6;z+=.67)lines.push(0,.022,z,0,.022,z+.3);
    const lineGeo=new THREE.BufferGeometry();lineGeo.setAttribute('position',new THREE.Float32BufferAttribute(lines,3));this.world.add(new THREE.LineSegments(lineGeo,lineMaterial));
    const ring=new THREE.Mesh(new THREE.RingGeometry(1.45,1.485,80),new THREE.MeshBasicMaterial({color:0x97b992,transparent:true,opacity:.56,side:THREE.DoubleSide}));ring.rotation.x=-Math.PI/2;ring.position.y=.024;this.world.add(ring);
    const center=new THREE.Mesh(new THREE.CircleGeometry(.055,16),new THREE.MeshBasicMaterial({color:0xdbebc8}));center.rotation.x=-Math.PI/2;center.position.y=.025;this.world.add(center);
    const edgeMetal=this.lit(0x75836d);this.edgeGlow=new THREE.MeshBasicMaterial({color:0xc8d9b8,transparent:true,opacity:.78});
    for(const sign of [-1,1]) {
      this.box(20.55,.21,.19,edgeMetal,0,.07,sign*6.28,.05);
      this.box(20.4,.03,.05,this.edgeGlow,0,.183,sign*6.28,.008);
      const c=sign<0?MINT:CORAL;
      this.box(.09,.05,11.86,new THREE.MeshBasicMaterial({color:c}),sign*10.19,.014,0,.015);
      this.planeMesh(3,14,new THREE.MeshBasicMaterial({map:this.glow,color:c,transparent:true,opacity:.1,depthWrite:false,blending:THREE.AdditiveBlending}),sign*9.8,.03,0);
      this.box(21.7,.024,.028,new THREE.MeshBasicMaterial({color:0x899c76}),0,-.78,sign*7.194,0);
    }
    // Engraved ticks on the raised rim evoke a studio instrument.
    const ticks=new THREE.InstancedMesh(new THREE.BoxGeometry(.024,.015,.15),new THREE.MeshBasicMaterial({color:0x90a087}),62);
    for(let i=0;i<62;i++){scratch.position.set(-10.5+(i%31)*.7,-.042,i<31?-6.67:6.67);scratch.rotation.set(0,0,0);scratch.scale.set(1,1,i%5===0?1.7:1);scratch.updateMatrix();ticks.setMatrixAt(i,scratch.matrix);}this.world.add(ticks);
    const screws=this.lit(0xaab7a1);
    for(const x of [-1,1])for(const z of [-1,1]){const screw=new THREE.Mesh(new THREE.CylinderGeometry(.07,.07,.025,10),screws);screw.position.set(x*10.73,-.04,z*6.73);this.world.add(screw);}
    const title=texture((ctx,w,h)=>{ctx.fillStyle='#bac6a4';ctx.font='500 26px monospace';ctx.textAlign='center';ctx.fillText('R A L L Y   /   A F T E R   H O U R S',w/2,h*.67);},1024,64);
    const label=new THREE.Mesh(new THREE.PlaneGeometry(7.1,.44),new THREE.MeshBasicMaterial({map:title,transparent:true,opacity:.75}));label.position.set(0,-.58,7.205);this.world.add(label);
    const courtPrint=texture((ctx,w,h)=>{ctx.fillStyle='#759f77';ctx.font='600 44px monospace';ctx.textAlign='center';ctx.fillText('N I G H T   S H I F T',w/2,h*.62);},1024,90);
    this.planeMesh(4.7,.4,new THREE.MeshBasicMaterial({map:courtPrint,transparent:true,opacity:.55,depthWrite:false}),-5.2,.025,-5.35);
    const detailMaterial=new THREE.MeshBasicMaterial({color:CORAL});
    for(let i=0;i<3;i++)this.box(.11,.26,.02,detailMaterial,9.8-i*.25,-.56,7.212,0).rotation.z=-.3;
  }
  batchStatic(group) {
    const groups=new Map();
    for(const mesh of [...group.children]) {
      if(!mesh.isMesh||mesh.isInstancedMesh||Array.isArray(mesh.material)||mesh.material.transparent)continue;
      const meshes=groups.get(mesh.material)||[];meshes.push(mesh);groups.set(mesh.material,meshes);
    }
    for(const [material,meshes] of groups) {
      if(meshes.length<2)continue;
      const parts=meshes.map(m=>{m.updateMatrix();return m.geometry.clone().applyMatrix4(m.matrix);});
      const merged=mergeGeometries(parts);parts.forEach(g=>g.dispose());if(!merged)continue;
      meshes.forEach(m=>{group.remove(m);m.geometry.dispose();});group.add(new THREE.Mesh(merged,material));
    }
  }
  buildPlayers() {
    this.paddles=[];
    for(const sign of [-1,1]) {
      const group=new THREE.Group();group.position.x=sign*9;this.world.add(group);
      const color=sign<0?MINT:CORAL;
      this.planeMesh(1.8,3.9,new THREE.MeshBasicMaterial({map:this.glow,color,transparent:true,opacity:.19,depthWrite:false,blending:THREE.AdditiveBlending}),0,.035,0,group);
      this.planeMesh(.9,2.9,new THREE.MeshBasicMaterial({map:this.glow,color:0x06100b,transparent:true,opacity:.8,depthWrite:false}),.16,.04,.16,group);
      this.box(.44,.17,2.24,0x183627,0,.13,0,.09,group);
      this.box(.36,.5,2.2,this.lit(color,{emissive:color,emissiveIntensity:.15}),0,.42,0,.12,group);
      this.box(.14,.025,1.9,new THREE.MeshBasicMaterial({color:sign<0?0xe5ffda:0xffc5a2}),0,.68,0,.03,group);
      this.paddles.push(group);
    }
  }
  buildBall() {
    this.ball=new THREE.Mesh(new THREE.SphereGeometry(.185,20,14),this.lit(GOLD,{emissive:0xffc561,emissiveIntensity:.6}));this.ball.position.y=.32;this.world.add(this.ball);
    this.ballGlow=new THREE.Sprite(new THREE.SpriteMaterial({map:this.glow,color:0xffdca5,transparent:true,opacity:.52,depthWrite:false,blending:THREE.AdditiveBlending}));this.ballGlow.scale.set(1.6,1.6,1);this.world.add(this.ballGlow);
    this.ballShadow=this.planeMesh(.85,.85,new THREE.MeshBasicMaterial({map:this.glow,color:0x08170a,transparent:true,opacity:.88,depthWrite:false}),0,.04,0);
    this.trailMesh=new THREE.InstancedMesh(new THREE.SphereGeometry(.13,8,5),new THREE.MeshBasicMaterial({transparent:true,opacity:.6,depthWrite:false}),TRAIL);this.trailMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);this.trailMesh.frustumCulled=false;this.world.add(this.trailMesh);
  }
  buildParticles() {
    this.particleMesh=new THREE.InstancedMesh(new THREE.BoxGeometry(.07,.07,.07),new THREE.MeshBasicMaterial({transparent:true,opacity:.86,depthWrite:false}),PARTICLES);this.particleMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);this.particleMesh.frustumCulled=false;this.particleMesh.count=0;this.world.add(this.particleMesh);
  }
  setIntro(value){this.intro=Boolean(value);this.needsRender=true;}
  resize() {
    if(this.disposed)return;
    const box=this.container.getBoundingClientRect();this.width=Math.max(1,box.width);this.height=Math.max(1,box.height);
    this.renderer.setPixelRatio(this.dpr);this.renderer.setSize(this.width,this.height,false);this.updateCamera();this.needsRender=true;
  }
  updateCamera() {
    const start=courtLayout(this.width,this.height,true),play=courtLayout(this.width,this.height,false),mix=this.introMix;
    const h=lerp(play.viewHeight,start.viewHeight,mix),x=lerp(play.targetX,start.targetX,mix),z=lerp(play.targetZ,start.targetZ,mix),aspect=this.width/this.height;
    this.camera.left=-h*aspect/2;this.camera.right=h*aspect/2;this.camera.top=h/2;this.camera.bottom=-h/2;
    this.camera.position.set(x,26,z+19);this.camera.lookAt(x,0,z);this.camera.updateProjectionMatrix();this.camera.updateMatrixWorld();
    this.world.rotation.y=lerp(play.yaw,start.yaw,mix);
  }
  screenToTarget(clientX,clientY) {
    const box=this.container.getBoundingClientRect();this.pointer.set((clientX-box.left)/box.width*2-1,-(clientY-box.top)/box.height*2+1);
    this.raycaster.setFromCamera(this.pointer,this.camera);
    if(!this.raycaster.ray.intersectPlane(this.plane,this.hit))return 0;
    this.world.updateMatrixWorld();this.world.worldToLocal(this.hit);
    return clamp(Math.round(this.hit.z/4.9*1000),-1000,1000);
  }
  burst(event,game) {
    if(this.reducedMotion)return;
    const goal=Boolean(event.goal);const color=event.goal==='ai'||event.aiHit?CORAL:MINT;
    const count=goal?28:event.wall?5:12;
    for(let i=0;i<count;i++) {
      const p=this.particles[this.particleCursor++%PARTICLES],a=Math.random()*Math.PI*2,s=1+Math.random()*(goal?7:4);
      Object.assign(p,{life:.25+Math.random()*.35,x:game.ballX/1000,y:.35,z:game.ballY/1000,vx:Math.cos(a)*s,vy:1+Math.random()*3,vz:Math.sin(a)*s,color});
    }
    if(goal)this.flash=.7;this.needsRender=true;
  }
  measure(ms,active=true) {
    if(!active||ms<1||ms>2000)return;
    this.frameTimes[this.frames++%this.frameTimes.length]=ms;
    if(this.mode!=='auto')return;
    this.slow=ms>27?this.slow+1:Math.max(0,this.slow-2);this.good=ms<18?this.good+1:0;
    const minimum=this.software?.55:.7;
    if(this.slow>30&&this.dpr>minimum){this.dpr=Math.max(minimum,this.dpr-.1);this.slow=0;this.resize();}
    if(this.good>900&&this.dpr<Math.min(devicePixelRatio||1,this.software?.85:1.6)){this.dpr=Math.min(this.dpr+.1,devicePixelRatio||1,this.software?.85:1.6);this.good=0;this.resize();}
  }
  cycleQuality() {
    this.mode=this.mode==='auto'?'lite':this.mode==='lite'?'high':'auto';
    this.dpr=this.mode==='lite'?.75:this.mode==='high'?Math.min(devicePixelRatio||1,2):Math.min(devicePixelRatio||1,this.software?.85:1.6);
    this.slow=this.good=0;this.resize();return this.mode;
  }
  render(game,previous,alpha,time,dt) {
    if(this.disposed||this.lost||!game)return;
    const next=this.intro?1:0;
    if(Math.abs(this.introMix-next)>.001){this.introMix=this.reducedMotion?next:lerp(this.introMix,next,1-Math.exp(-dt*9));this.updateCamera();}
    else if(this.introMix!==next){this.introMix=next;this.updateCamera();}
    this.paddles[0].position.z=game.playerY/1000;this.paddles[1].position.z=game.aiY/1000;
    const discontinuity=!previous||game.serveTicks>0||previous.serveTicks>0||Math.abs(game.ballX-previous.ballX)>700;
    const x=(discontinuity?game.ballX:lerp(previous.ballX,game.ballX,alpha))/1000,z=(discontinuity?game.ballY:lerp(previous.ballY,game.ballY,alpha))/1000;
    const serving=game.serveTicks>0;
    this.ball.position.set(x,.34,z);this.ballGlow.position.copy(this.ball.position);this.ballShadow.position.set(x+.08,.04,z+.11);
    const pulse=serving&&!this.reducedMotion?1+Math.sin(time*8)*.12:1;this.ball.scale.setScalar(pulse);this.ballGlow.material.opacity=serving?.38:.55;
    if(discontinuity||this.lastServe!==serving)for(const p of this.trail){p.x=x;p.z=z;}
    this.lastServe=serving;this.trailClock+=dt;
    if(this.trailClock>=1/90){this.trailClock=0;this.trail.pop();this.trail.unshift({x,z});}
    const length=this.reducedMotion||serving?0:TRAIL;
    for(let i=0;i<length;i++){const p=this.trail[i],fade=1-i/TRAIL;scratch.position.set(p.x,.3,p.z);scratch.rotation.set(0,0,0);scratch.scale.setScalar(.3+fade*.7);scratch.updateMatrix();this.trailMesh.setMatrixAt(i,scratch.matrix);this.trailMesh.setColorAt(i,tint.setHex(0x31533d).lerp(goldTint,fade*.85));}
    this.trailMesh.count=length;this.trailMesh.instanceMatrix.needsUpdate=true;if(this.trailMesh.instanceColor)this.trailMesh.instanceColor.needsUpdate=true;
    let n=0;
    for(const p of this.particles){if(p.life<=0)continue;p.life-=dt;p.x+=p.vx*dt;p.z+=p.vz*dt;p.y+=p.vy*dt;p.vy-=9*dt;scratch.position.set(p.x,Math.max(.06,p.y),p.z);scratch.rotation.set(time*3,time*4,0);scratch.scale.setScalar(clamp(p.life*4,0,1));scratch.updateMatrix();this.particleMesh.setMatrixAt(n,scratch.matrix);this.particleMesh.setColorAt(n,tint.setHex(p.color));n++;}
    this.particleMesh.count=n;this.particleMesh.instanceMatrix.needsUpdate=true;if(this.particleMesh.instanceColor)this.particleMesh.instanceColor.needsUpdate=true;
    this.flash=Math.max(0,this.flash-dt*2);this.edgeGlow.opacity=.78+this.flash*.2;
    this.renderer.render(this.scene,this.camera);this.needsRender=false;
  }
  diagnostics() {
    const count=Math.min(this.frames,this.frameTimes.length);let sum=0;for(let i=0;i<count;i++)sum+=this.frameTimes[i];
    const playable=courtLayout(this.width,this.height,false);
    return {threeVersion:THREE.REVISION,webgl2:true,width:this.width,height:this.height,quality:this.mode,pixelRatio:this.dpr,softwareRenderer:this.software,renderedFrames:this.frames,measuredFps:sum?Math.round(1000*count/sum):0,drawCalls:this.renderer.info.render.calls,triangles:this.renderer.info.render.triangles,contextLost:this.lost,reducedMotion:this.reducedMotion,playableBounds:playable.bounds,inlineAssets:true};
  }
  dispose() {
    if(this.disposed)return;this.disposed=true;this.resizeObserver.disconnect();
    this.canvas.removeEventListener('webglcontextlost',this.lostHandler);this.canvas.removeEventListener('webglcontextrestored',this.restoreHandler);
    const geometries=new Set(),materials=new Set(),textures=new Set([this.glow]);
    this.scene.traverse(object=>{if(object.geometry)geometries.add(object.geometry);for(const m of object.material?(Array.isArray(object.material)?object.material:[object.material]):[]){materials.add(m);for(const value of Object.values(m))if(value?.isTexture)textures.add(value);}});
    for(const item of [...geometries,...materials,...textures])item.dispose();this.renderer.dispose();this.canvas.remove();
  }
}
