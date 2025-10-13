import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0f0f13);

const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 100);
camera.position.set(4, 3, 6);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
document.body.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.target.set(0, 1, 0);

// Luces
const hemi = new THREE.HemisphereLight(0xffffff, 0x222233, 0.7); scene.add(hemi);
const dir = new THREE.DirectionalLight(0xffffff, 0.8); dir.position.set(3, 6, 2); scene.add(dir);

// Suelo
const groundMat = new THREE.MeshStandardMaterial({ color: 0x2b2b2b, metalness: 0.1, roughness: 0.9 });
const ground = new THREE.Mesh(new THREE.PlaneGeometry(10, 10), groundMat);
ground.rotation.x = -Math.PI / 2;
ground.receiveShadow = true;
scene.add(ground);

// Pelota
const ballGeo = new THREE.SphereGeometry(0.5, 48, 48);
const ballMat = new THREE.MeshStandardMaterial({ color: 0x6cc0ff, metalness: 0.2, roughness: 0.4 });
const ball = new THREE.Mesh(ballGeo, ballMat);
ball.castShadow = true;
scene.add(ball);

// Línea de referencia (altura base)
const grid = new THREE.GridHelper(10, 20, 0x333333, 0x242424); scene.add(grid);

// Parámetros de animación
const state = {
  phase: 'anticipation', // anticipation -> launch -> flightUp -> apex -> fall -> impact
  t: 0,
  y: 0.5, // posición vertical base (radio)
  vy: 0,
  g: -9.8,
  baseY: 0.5,
  squash: new THREE.Vector3(1, 1, 1),
};

function setBallScale(x, y, z) {
  ball.scale.set(x, y, z);
}

function animate(time) {
  requestAnimationFrame(animate);
  const dt = Math.min(0.033, (time - (animate.prevTime || time)) / 1000);
  animate.prevTime = time;

  state.t += dt;

  switch (state.phase) {
    case 'anticipation': {
      // Se prepara el salto: aplasta y baja un poquito
      const dur = 0.25; // 250ms de anticipación clara
      const k = Math.min(1, state.t / dur);
      const ease = k * k * (3 - 2 * k); // smoothstep

      const squashY = THREE.MathUtils.lerp(1.0, 0.6, ease); // se aplasta
      const squashX = THREE.MathUtils.lerp(1.0, 1.25, ease); // se ensancha
      setBallScale(squashX, squashY, squashX);
      ball.position.y = state.baseY + THREE.MathUtils.lerp(0, -0.12, ease);

      if (k >= 1) {
        state.phase = 'launch';
        state.t = 0;
      }
      break;
    }
    case 'launch': {
      // Estiramiento inicial y comienzo del salto (impulso)
      const dur = 0.12;
      const k = Math.min(1, state.t / dur);
      const ease = k; // lineal breve para expresar el impulso

      const stretchY = THREE.MathUtils.lerp(1.1, 1.35, ease);
      const stretchX = THREE.MathUtils.lerp(0.95, 0.8, ease);
      setBallScale(stretchX, stretchY, stretchX);

      // Impulso vertical
      if (k >= 1) {
        state.phase = 'flightUp';
        state.t = 0;
        state.vy = 5.8; // velocidad inicial (ajustada para buen arco visual)
        ball.position.y = state.baseY + 0.02;
      }
      break;
    }
    case 'flightUp': {
      // Subida con stretch
      state.vy += state.g * dt;
      ball.position.y += state.vy * dt;

      const speedNorm = Math.max(0, state.vy) / 6.0; // normaliza a [0..~1]
      const sy = THREE.MathUtils.lerp(1.1, 1.35, speedNorm);
      const sx = THREE.MathUtils.lerp(0.95, 0.8, speedNorm);
      setBallScale(sx, sy, sx);

      if (state.vy <= 0) { // llegó al ápice
        state.phase = 'apex';
        state.t = 0;
      }
      break;
    }
    case 'apex': {
      // Micro pausa en el punto más alto (claridad)
      const dur = 0.08;
      if (state.t >= dur) {
        state.phase = 'fall';
        state.t = 0;
      } else {
        setBallScale(1.0, 1.0, 1.0);
      }
      break;
    }
    case 'fall': {
      // Caída con stretch (se estira más cuanto más rápido)
      state.vy += state.g * dt;
      ball.position.y += state.vy * dt;

      const speed = Math.abs(state.vy);
      const sy = THREE.MathUtils.clamp(1.0 + speed * 0.05, 1.0, 1.5);
      const sx = THREE.MathUtils.clamp(1.0 - speed * 0.03, 0.7, 1.1);
      setBallScale(sx, sy, sx);

      if (ball.position.y <= state.baseY) {
        // impacto
        ball.position.y = state.baseY;
        state.phase = 'impact';
        state.t = 0;
        state.vy = 0;
      }
      break;
    }
    case 'impact': {
      // Aplasta claro y rebota menos (pérdida de energía)
      const dur = 0.14;
      const k = Math.min(1, state.t / dur);
      const easeOut = 1 - Math.pow(1 - k, 3);

      const squashY = THREE.MathUtils.lerp(0.6, 0.9, easeOut);
      const squashX = THREE.MathUtils.lerp(1.3, 1.05, easeOut);
      setBallScale(squashX, squashY, squashX);

      if (k >= 1) {
        // Nuevo salto más bajo
        state.phase = 'flightUp';
        state.t = 0;
        state.vy = 4.3; // rebote con menos energía
      }
      break;
    }
  }

  // Limitar rotación de cámara y renderizar
  controls.update();
  renderer.render(scene, camera);
}

animate(0);

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});
