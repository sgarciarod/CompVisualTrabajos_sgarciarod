import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x101014);

const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 200);
camera.position.set(6, 5, 10);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.shadowMap.enabled = true;
document.body.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 2, 0);
controls.enableDamping = true;

// Luces
const hemi = new THREE.HemisphereLight(0xaaaaff, 0x222211, 0.6); scene.add(hemi);
const dir = new THREE.DirectionalLight(0xffffff, 1.0); dir.position.set(8, 12, 6); dir.castShadow = true; scene.add(dir);

// Suelo
const ground = new THREE.Mesh(new THREE.PlaneGeometry(200, 200), new THREE.MeshStandardMaterial({ color: 0x2a2a2a }));
ground.rotation.x = -Math.PI/2; ground.receiveShadow = true; scene.add(ground);

// Objetivo visual para IK
const target = new THREE.Mesh(
  new THREE.SphereGeometry(0.15),
  new THREE.MeshStandardMaterial({ color: 0xff5555 })
);
target.position.set(3, 3, 0);
scene.add(target);

// Carga de la grua
const loader = new GLTFLoader();
let crane = null;            // Nodo base de la grúa
let beamObj = null;          // Viga por donde desliza el gancho: Cube055_UV_0

// Grupo del gancho y límites de movimiento a lo largo del brazo
let hookGroup = null;
let hookParent = null;          // Usaremos la viga como parent si es posible
// Eje y puntos en ESPACIO LOCAL DE LA VIGA
let axisLocal = new THREE.Vector3(1,0,0); // Eje de deslizamiento en local del beam
let baseLocal = new THREE.Vector3();      // Punto base en local del beam
let tipLocal = new THREE.Vector3();       // Punto extremo en local del beam
let offsetLocal = new THREE.Vector3();    // Offset perpendicular fijo en local del beam
let hookMinS = 0;                         // s mínimo (0 + margen)
let hookMaxS = 0;                         // s máximo (longitud - margen)
let hookS = 0;                            // posición escalar actual en el eje local

loader.load('/grua.glb', (gltf) => {
  crane = gltf.scene;
  crane.traverse(o => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  scene.add(crane);

  beamObj = crane.getObjectByName('Cube055_UV_0'); // viga

  buildHookGroup(crane);
  // Calcular eje y límites de movimiento a partir de la viga (en local del beam)
  computeAxisAndExtentsFromBeam();
  // Inicial: ubicar hookS en el mínimo y mantener offset lateral
  if (hookGroup && hookParent) {
    hookS = hookMinS;
    updateHookGroupPosition();
  }
}, undefined, (err) => console.error('Error cargando /grua.glb', err));

function buildHookGroup(root){
  const names = [
    'Cube063_UV_0',           // caja
    'Cube065_UV_0',           // rueda 1
    'Cube064_UV_0',           // rueda 2
    'Plane005_Curve003_ROPE_0', // cuerda 1
    'Plane005_Curve002_ROPE_0', // cuerda 2
    'Cube068_BUCKET_0',       // base del gancho
    'Plane025_IRON_0',        // gancho
  ];
  const parts = names.map(n => root.getObjectByName(n)).filter(Boolean);
  if (parts.length === 0) {
    console.warn('[Hook] No se encontraron partes del gancho');
    return;
  }
  // Preferir SIEMPRE la viga como parent si existe, para que rote con ella
  hookParent = beamObj || findCommonAncestor(parts) || root;

  hookGroup = new THREE.Group();
  hookGroup.name = 'HookGroup';
  hookParent.add(hookGroup);
  // Posicionar el grupo en el promedio local de las piezas (en espacio de hookParent)
  const avg = new THREE.Vector3();
  parts.forEach(p => {
    const w = new THREE.Vector3(); p.getWorldPosition(w);
    const l = hookParent.worldToLocal(w.clone());
    avg.add(l);
  });
  avg.multiplyScalar(1 / parts.length);
  hookGroup.position.copy(avg);
  hookGroup.updateMatrixWorld(true);
  // Reagrupar piezas bajo el hookGroup preservando transformaciones
  parts.forEach(p => hookGroup.attach(p));
  console.log('[Hook] Partes agrupadas:', parts.map(p=>p.name));
}

function findCommonAncestor(nodes){
  if (nodes.length === 0) return null;
  const paths = nodes.map(n => {
    const arr = [];
    let cur = n;
    while (cur) { arr.unshift(cur); cur = cur.parent; }
    return arr;
  });
  let common = null;
  for (let i = 0; i < paths[0].length; i++) {
    const candidate = paths[0][i];
    if (paths.every(p => p[i] === candidate)) {
      common = candidate;
    } else break;
  }
  return common;
}

function computeAxisAndExtentsFromBeam(){
  if (!hookParent || !hookGroup || !beamObj) return;
  // Usar bounding box de la GEOMETRÍA en local del beam
  if (beamObj.isMesh && beamObj.geometry) {
    if (!beamObj.geometry.boundingBox) {
      beamObj.geometry.computeBoundingBox();
    }
    const bb = beamObj.geometry.boundingBox; // local del beam
    const size = new THREE.Vector3().subVectors(bb.max, bb.min);
    axisLocal.set(1, 0, 0);
    if (size.z > size.x) axisLocal.set(0, 0, 1);
    const centerLocal = new THREE.Vector3().addVectors(bb.min, bb.max).multiplyScalar(0.5);
    const halfLen = (axisLocal.x ? size.x : size.z) * 0.5;
    baseLocal.copy(centerLocal).add(axisLocal.clone().multiplyScalar(-halfLen));
    tipLocal.copy(centerLocal).add(axisLocal.clone().multiplyScalar( halfLen));

    // s actual y offset en local del beam
    const posLocal = hookGroup.position.clone(); // ya en espacio del hookParent (beam)
    const toLocal = posLocal.clone().sub(baseLocal);
    hookS = toLocal.dot(axisLocal);
    const proj = axisLocal.clone().multiplyScalar(hookS);
    offsetLocal.copy(toLocal.sub(proj));

    const beamLength = tipLocal.clone().sub(baseLocal).length();
    const margin = 0.15;
    hookMinS = 0 + margin;
    hookMaxS = Math.max(margin, beamLength - margin);
    hookS = THREE.MathUtils.clamp(hookS, hookMinS, hookMaxS);

    console.log('[Hook] Eje (local) y límites s:', { axisLocal: axisLocal.toArray(), hookMinS, hookMaxS });
  } else {
    console.warn('[Hook] La viga no es una malla con geometría. No se puede derivar el eje.');
  }
}

function updateHookGroupPosition(){
  if (!hookGroup || !hookParent) return;
  // Posición en local del beam: baseLocal + axisLocal * s + offsetLocal
  const localPos = baseLocal.clone().add(axisLocal.clone().multiplyScalar(hookS)).add(offsetLocal);
  hookGroup.position.copy(localPos);
  hookGroup.updateMatrixWorld(true);
}

function isAncestor(ancestor, node) {
  let cur = node;
  while (cur) { if (cur === ancestor) return true; cur = cur.parent; }
  return false;
}

// ---------------- CINEMÁTICA INVERSA --------------------

// Permite mover el target con el teclado
window.addEventListener('keydown', (e) => {
  const step = (e.shiftKey ? 0.5 : 0.2);
  if (e.key === 'ArrowUp')    target.position.z -= step;
  if (e.key === 'ArrowDown')  target.position.z += step;
  if (e.key === 'ArrowLeft')  target.position.x -= step;
  if (e.key === 'ArrowRight') target.position.x += step;
  if (e.key === 'PageUp')     target.position.y += step;
  if (e.key === 'PageDown')   target.position.y -= step;
  if (e.key.toLowerCase() === 'r') target.position.set(3, 3, 0);
});

let _lastTime = performance.now();
function animate(){
  requestAnimationFrame(animate);

  // ---- CINEMÁTICA INVERSA ----
  if (crane && beamObj && hookGroup) {
    // 1. Calcular la posición del objetivo en el espacio de la grúa
    // La base rota en Y, así que transformamos el target al espacio de la grúa
    const cranePos = crane.position.clone();
    const targetXZ = target.position.clone().sub(cranePos);

    // 2. Calcular el ángulo de giro de la base (YAW)
    const baseYawAngle = Math.atan2(targetXZ.x, targetXZ.z);
    crane.rotation.y = baseYawAngle;
    crane.updateMatrixWorld(true);

    // 3. Calcular el punto del objetivo en el espacio local de la viga
    const worldToBeam = new THREE.Matrix4().copy(beamObj.matrixWorld).invert();
    const targetLocal = target.position.clone().applyMatrix4(worldToBeam);

    // 4. Proyectar la posición del objetivo sobre el eje de la viga (axisLocal)
    const toTarget = targetLocal.clone().sub(baseLocal);
    let s = toTarget.dot(axisLocal);

    // Clampear para que no se salga de los límites
    s = THREE.MathUtils.clamp(s, hookMinS, hookMaxS);

    // 5. Actualizar la posición del gancho para alcanzar el objetivo
    hookS = s;
    updateHookGroupPosition();
  }

  controls.update();
  renderer.render(scene, camera);
}
animate();

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});