/** Private, local art-turntable entry. Bundled by characters-preview.mjs; not game code. */
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { loadCharacters, VIEWMODEL_MOUNT, type CharacterKind } from '../frontend/characters';

const kinds: CharacterKind[] = ['swordsman', 'elite', 'shield', 'archer', 'mage', 'princess', 'viewmodel'];
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(1);
renderer.setSize(1280, 900);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.06;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.querySelector('#stage')!.appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.background = new THREE.Color('#333d3d');
const environment = new RoomEnvironment();
const pmrem = new THREE.PMREMGenerator(renderer);
const envMap = pmrem.fromScene(environment, .04);
scene.environment = envMap.texture;
scene.environmentIntensity = .45;
environment.dispose();
pmrem.dispose();
scene.add(new THREE.HemisphereLight(0xb6ccd3, 0x5d5040, 2.0));
const key = new THREE.DirectionalLight(0xffe9c6, 3.0);
key.position.set(-3.5, 5, 4);
key.castShadow = true;
key.shadow.mapSize.set(2048, 2048);
key.shadow.camera.left = -5;
key.shadow.camera.right = 5;
key.shadow.camera.top = 5;
key.shadow.camera.bottom = -5;
key.shadow.normalBias = .015;
scene.add(key);
const fill = new THREE.DirectionalLight(0xb7d0e6, 1.05);
fill.position.set(3, 2, -2);
scene.add(fill);
const floor = new THREE.Mesh(new THREE.PlaneGeometry(30, 30), new THREE.MeshStandardMaterial({ color: '#394039', roughness: 1 }));
floor.rotation.x = -Math.PI/2;
floor.position.y = -.012;
floor.receiveShadow = true;
scene.add(floor);
const camera = new THREE.OrthographicCamera(-1.85, 1.85, 2.20, -.40, .01, 50);
camera.position.set(2.4, 1.65, 5.5);
camera.lookAt(0, .88, .04);
const fpCamera = new THREE.PerspectiveCamera(70, 1280/900, .035, 50);
scene.add(fpCamera);
const label = document.querySelector('#caption')!;
const info = document.querySelector('#status')!;
const library = await loadCharacters(text => { info.textContent = text; });
const views = new Map(kinds.map(kind => [kind, library.create(kind)]));
for (const [kind, view] of views) {
  view.root.visible = false;
  if (kind === 'viewmodel') {
    fpCamera.add(view.root);
    view.root.position.fromArray(VIEWMODEL_MOUNT.position);
    view.root.rotation.fromArray([...VIEWMODEL_MOUNT.rotation, 'XYZ']);
  } else scene.add(view.root);
}
let active: CharacterKind = 'swordsman';
let chosenClip = 'idle';
let chosenTime = 0;
let playing = false;
let angle = .23;
let sheet = false;

function render(): void {
  const view = views.get(active)!;
  for (const [kind, actor] of views) actor.root.visible = kind === active;
  floor.visible = active !== 'viewmodel';
  if (active !== 'viewmodel') {
    view.root.rotation.y = angle;
    camera.left = -1.56;
    camera.right = 1.56;
    camera.top = 1.20;
    camera.bottom = -.995;
    camera.position.set(0, 1.38, 5.5);
    camera.lookAt(0, .93, 0);
    camera.updateProjectionMatrix();
  }
  view.pose(chosenClip, chosenTime);
  const height = active === 'viewmodel' ? 720 : 900;
  if (renderer.domElement.height !== height || renderer.domElement.width !== 1280) renderer.setSize(1280, height);
  fpCamera.aspect = 1280/height;
  fpCamera.updateProjectionMatrix();
  renderer.setViewport(0, 0, 1280, height);
  renderer.setScissorTest(false);
  renderer.render(scene, active === 'viewmodel' ? fpCamera : camera);
  label.textContent = `${active.toUpperCase()}  /  ${chosenClip}  /  ${chosenTime.toFixed(2)}s`;
  info.textContent = `${renderer.info.render.triangles.toLocaleString()} rendered triangles · original 512px atlas · named GLB articulation`;
}

function show(kind: CharacterKind, clip = 'idle', time = 0, rotation = .23): void {
  sheet = false;
  active = kind;
  chosenClip = clip;
  chosenTime = time;
  angle = rotation;
  const select = document.querySelector('#clip') as HTMLSelectElement;
  select.innerHTML = library.clips[kind].map(name => `<option value="${name}">${name}</option>`).join('');
  select.value = clip;
  render();
}

function contactSheet(clip = 'idle', time = 0, rotation = .23): void {
  sheet = true;
  renderer.setSize(1680, 1120);
  renderer.setScissorTest(true);
  floor.visible = true;
  camera.left = -1.25;
  camera.right = 1.25;
  camera.top = 1.22;
  camera.bottom = -1.28;
  camera.position.set(0, 1.43, 5.5);
  camera.lookAt(0, 1.08, 0);
  camera.updateProjectionMatrix();
  for (let i = 0; i < 6; i++) {
    const actor = views.get(kinds[i])!;
    for (const [kind, view] of views) view.root.visible = kind === kinds[i];
    actor.root.rotation.y = rotation;
    actor.pose(clip, time);
    const x = (i%3)*560;
    const y = (1-Math.floor(i/3))*560;
    renderer.setViewport(x, y, 560, 560);
    renderer.setScissor(x, y, 560, 560);
    renderer.render(scene, camera);
  }
  renderer.setScissorTest(false);
  label.textContent = `THE GLOAMING ROAD / ORIGINAL CHARACTER LINEUP / ${clip} ${time.toFixed(2)}s`;
  info.textContent = 'Swordsman · Elite · Shield / Archer · Mage · Princess';
}

for (const kind of kinds) {
  const button = document.createElement('button');
  button.textContent = kind;
  button.addEventListener('click', () => { renderer.setSize(1280, 900); show(kind); });
  document.querySelector('#kinds')!.append(button);
}
(document.querySelector('#clip') as HTMLSelectElement).addEventListener('change', event => {
  chosenClip = (event.target as HTMLSelectElement).value;
  chosenTime = 0;
  render();
});
(document.querySelector('#time') as HTMLInputElement).addEventListener('input', event => {
  chosenTime = Number((event.target as HTMLInputElement).value);
  render();
});
(document.querySelector('#rotate') as HTMLInputElement).addEventListener('input', event => {
  angle = Number((event.target as HTMLInputElement).value);
  render();
});
document.querySelector('#play')!.addEventListener('click', () => { playing = !playing; });
document.querySelector('#sheet')!.addEventListener('click', () => contactSheet());
let previous = performance.now();
function frame(now: number): void {
  if (playing && !sheet) {
    chosenTime += Math.min(.05, (now-previous)/1000);
    const duration = views.get(active)!.mixer.existingAction(chosenClip)?.getClip().duration ?? 3.2;
    if (chosenTime > duration) chosenTime = 0;
    render();
  }
  previous = now;
  requestAnimationFrame(frame);
}
show('swordsman');
requestAnimationFrame(frame);
Object.assign(window, { characterPreview: { library, views, scene, renderer, camera, fpCamera, show, contactSheet, render }, characterPreviewReady: true });
