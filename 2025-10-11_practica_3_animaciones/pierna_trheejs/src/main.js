import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

let scene = new THREE.Scene();
scene.background = new THREE.Color(0x111111);

let camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 100);
camera.position.set(40, 10, 20);

let renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
document.body.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 2, 0);
controls.enableDamping = true;

let dirLight = new THREE.DirectionalLight(0xffffff, 1);
dirLight.position.set(5, 10, 7);
scene.add(dirLight);

let ambient = new THREE.AmbientLight(0xffffff, 0.35);
scene.add(ambient);

let legModel = null;
let hipPivot = null;
let kneePivot = null;
let anklePivot = null;

// Carga el modelo de la pierna
const loader = new GLTFLoader();
loader.load(
  // Vite sirve los archivos en /public en la raíz: "/archivo"
  "/pierna.glb",
  (gltf) => {
    legModel = gltf.scene;
    legModel.traverse((o) => {
      // Asegura que todo reciba luz direccional correctamente
      if (o.isMesh) {
        o.castShadow = true;
        o.receiveShadow = true;
      }
    });
    scene.add(legModel);

    // Construir cadena FK con objetos conocidos: Object_13 (muslo), Object_19 y Object_20 (pantorrilla), resto (pie)
    buildLegChain(legModel);
  },
  undefined,
  (err) => {
    console.error('Error cargando /pierna.glb:', err);
  }
);

// Construye pivotes de FK con objetos: 13 (muslo), 19+20 (pantorrilla) y resto (pie)
function buildLegChain(root) {
  const thigh = root.getObjectByName('Object_13');
  const calf19 = root.getObjectByName('Object_19');
  const calf20 = root.getObjectByName('Object_20');
  if (!thigh || (!calf19 && !calf20)) {
    console.warn('[FK] No se encontraron Object_13 o (Object_19/Object_20).');
    return;
  }

  const calfParts = [calf19, calf20].filter(Boolean);

  // Piezas del pie = todos los Mesh que no sean 13, 19, 20
  const footParts = [];
  root.traverse((o) => {
    if (o.isMesh && o.name !== 'Object_13' && o.name !== 'Object_19' && o.name !== 'Object_20') {
      footParts.push(o);
    }
  });

  // Crear pivotes
  hipPivot = new THREE.Group(); hipPivot.name = 'HipPivot';
  kneePivot = new THREE.Group(); kneePivot.name = 'KneePivot';
  anklePivot = new THREE.Group(); anklePivot.name = 'AnklePivot';
  scene.add(hipPivot);

  // Calcular cajas globales
  const boxThigh = new THREE.Box3().setFromObject(thigh);
  const boxCalf = calfParts.reduce((acc, p) => acc.union(new THREE.Box3().setFromObject(p)), new THREE.Box3());
  const boxFoot = footParts.length > 0 ? footParts.reduce((acc, p) => acc.union(new THREE.Box3().setFromObject(p)), new THREE.Box3()) : null;

  // Posiciones de pivote (centro XZ y extremos Y)
  const centerXZ = (b) => new THREE.Vector3((b.min.x + b.max.x) * 0.5, 0, (b.min.z + b.max.z) * 0.5);
  const hipPos = centerXZ(boxThigh).setY(boxThigh.max.y);
  const kneePos = centerXZ(boxCalf).setY(boxCalf.max.y); // parte superior de la pantorrilla
  const anklePos = centerXZ(boxCalf).setY(boxCalf.min.y); // parte inferior de la pantorrilla

  // Colocar pivotes en mundo
  hipPivot.position.copy(hipPos);
  // Importante: asegurar matrices actualizadas
  hipPivot.updateMatrixWorld(true);

  // Reparentar preservando transformaciones
  hipPivot.attach(thigh);
  hipPivot.attach(kneePivot);
  // Posicionar la rodilla en el espacio del hipPivot
  kneePivot.position.copy(kneePos.clone().applyMatrix4(new THREE.Matrix4().copy(hipPivot.matrixWorld).invert()));
  kneePivot.updateMatrixWorld(true);

  // Mover las piezas de pantorrilla bajo kneePivot
  calfParts.forEach((p) => kneePivot.attach(p));

  // Colocar el tobillo como hijo de la rodilla
  kneePivot.attach(anklePivot);
  anklePivot.position.copy(anklePos.clone().applyMatrix4(new THREE.Matrix4().copy(kneePivot.matrixWorld).invert()));
  anklePivot.updateMatrixWorld(true);

  // Mover piezas del pie bajo el tobillo
  footParts.forEach((p) => anklePivot.attach(p));

  console.log('[FK] Cadena creada con pivotes:', { hipPos, kneePos, anklePos, thigh: thigh.name, calf: calfParts.map(p=>p.name), footCount: footParts.length });
}

function animate() {
  requestAnimationFrame(animate);
  const t = performance.now() * 0.001; // segundos

  // Animación con cinemática directa: definimos los ángulos y los aplicamos en cadena
  // Eje X para flexión/extensión
  const hipAngle = Math.sin(t * 1.2) * THREE.MathUtils.degToRad(30);  // +/- 30°
  const kneeAngle = Math.max(0, Math.sin(t * 1.2 + Math.PI * 0.5)) * THREE.MathUtils.degToRad(60); // 0 a ~60°
  const ankleAngle = -0.35 * kneeAngle + Math.sin(t * 2.0) * THREE.MathUtils.degToRad(5);

  if (hipPivot) hipPivot.rotation.x = hipAngle;
  if (kneePivot) kneePivot.rotation.x = kneeAngle;
  if (anklePivot) anklePivot.rotation.x = ankleAngle;

  controls.update();
  renderer.render(scene, camera);
}
animate();

// Resize
window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});