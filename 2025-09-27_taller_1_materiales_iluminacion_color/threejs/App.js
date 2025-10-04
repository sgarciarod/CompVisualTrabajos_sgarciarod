import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls";

function App() {
  const rendererRef = useRef(null);
  const [rotating, setRotating] = useState(false);
  const [usePerspective, setUsePerspective] = useState(true);
  const [preset, setPreset] = useState("day");

  useEffect(() => {
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setClearColor(0x222222);

    // Evita duplicados de canvas
    if (rendererRef.current.firstChild) {
      rendererRef.current.removeChild(rendererRef.current.firstChild);
    }
    rendererRef.current.appendChild(renderer.domElement);

    const scene = new THREE.Scene();

    // Cámaras
    const aspect = window.innerWidth / window.innerHeight;
    const cameraP = new THREE.PerspectiveCamera(60, aspect, 0.1, 100);
    cameraP.position.set(0, 3, 10);
    cameraP.lookAt(0, 0, 0);
    const cameraO = new THREE.OrthographicCamera(
      -5 * aspect,
      5 * aspect,
      5,
      -5,
      0.1,
      100
    );
    cameraO.position.set(0, 3, 10);
    cameraO.lookAt(0, 0, 0);

    const camera = usePerspective ? cameraP : cameraO;

    // OrbitControls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.enableZoom = true;
    controls.enableRotate = true;
    controls.enablePan = true;

    // Iluminación
    const keyLight = new THREE.DirectionalLight(0xffeecc, 1.2);
    keyLight.position.set(5, 10, 7);
    scene.add(keyLight);

    const fillLight = new THREE.DirectionalLight(0x3366ff, 0.7);
    fillLight.position.set(-5, 5, 3);
    scene.add(fillLight);

    const rimLight = new THREE.DirectionalLight(0xffffff, 0.5);
    rimLight.position.set(0, 5, -8);
    scene.add(rimLight);

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.4);
    scene.add(ambientLight);

    function setDayPreset() {
      keyLight.color.set(0xffeecc);
      keyLight.intensity = 1.2;
      fillLight.color.set(0x3366ff);
      fillLight.intensity = 0.7;
      rimLight.color.set(0xffffff);
      rimLight.intensity = 0.5;
      ambientLight.intensity = 0.4;
    }
    function setSunsetPreset() {
      keyLight.color.set(0xff8844);
      keyLight.intensity = 0.8;
      fillLight.color.set(0x223355);
      fillLight.intensity = 0.5;
      rimLight.color.set(0xffcc88);
      rimLight.intensity = 0.6;
      ambientLight.intensity = 0.2;
    }
    if (preset === "day") setDayPreset();
    else setSunsetPreset();

    // Piso con textura y relieve
    const textureLoader = new THREE.TextureLoader();
    const floorColor = textureLoader.load(
      "/textures/aerial_rocks_02_diff_4k.jpg"
    );
    const floorDisp = textureLoader.load(
      "/textures/aerial_rocks_02_disp_4k.png"
    );
    const floorRough = textureLoader.load(
      "/textures/aerial_rocks_02_rough_4k.jpg"
    );
    const floorNormal = textureLoader.load(
      "/textures/aerial_rocks_02_nor_4k.jpg"
    );

    floorColor.wrapS = floorColor.wrapT = THREE.RepeatWrapping;
    floorDisp.wrapS = floorDisp.wrapT = THREE.RepeatWrapping;
    floorRough.wrapS = floorRough.wrapT = THREE.RepeatWrapping;
    floorNormal.wrapS = floorNormal.wrapT = THREE.RepeatWrapping;

    floorColor.repeat.set(4, 4);
    floorDisp.repeat.set(4, 4);
    floorRough.repeat.set(4, 4);
    floorNormal.repeat.set(4, 4);

    const floorMaterial = new THREE.MeshStandardMaterial({
      map: floorColor,
      displacementMap: floorDisp,
      displacementScale: 0.3,
      roughnessMap: floorRough,
      roughness: 1.0,
      metalness: 0.1,
      normalMap: floorNormal,
      normalScale: new THREE.Vector2(1, 1),
    });

    const floorGeometry = new THREE.PlaneGeometry(20, 20, 100, 100);
    const floorMesh = new THREE.Mesh(floorGeometry, floorMaterial);
    floorMesh.rotation.x = -Math.PI / 2;
    floorMesh.position.y = 0;
    scene.add(floorMesh);

    // Niebla procedural con partículas
    const fogParticles = 30;
    const fogGeometry = new THREE.BufferGeometry();
    const positions = [];
    const colors = [];
    const sizes = [];

    for (let i = 0; i < fogParticles; i++) {
      const x = (Math.random() - 0.5) * 18;
      const y = Math.random() * 2 + 1.2;
      const z = (Math.random() - 0.5) * 18;
      positions.push(x, y, z);
      colors.push(0.7, 0.75, 0.8);
      sizes.push(Math.random() * 14 + 18);
    }

    fogGeometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(positions, 3)
    );
    fogGeometry.setAttribute(
      "color",
      new THREE.Float32BufferAttribute(colors, 3)
    );
    fogGeometry.setAttribute(
      "size",
      new THREE.Float32BufferAttribute(sizes, 1)
    );

    const fogUniforms = {
      iTime: { value: 0 },
    };

    const fogParticleMaterial = new THREE.ShaderMaterial({
      uniforms: fogUniforms,
      vertexShader: `
        attribute float size;
        attribute vec3 color;
        varying vec3 vColor;
        void main() {
          vColor = color;
          vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = size * (300.0 / -mvPosition.z);
          gl_Position = projectionMatrix * mvPosition;
        }
      `,
      fragmentShader: `
        uniform float iTime;
        varying vec3 vColor;
        void main() {
          float dist = length(gl_PointCoord - vec2(0.5));
          float alpha = smoothstep(0.5, 0.0, dist);
          float flicker = 0.95 + 0.05 * sin(iTime * 2.5 + gl_FragCoord.x * 0.02 + gl_FragCoord.y * 0.02);
          alpha *= flicker;
          gl_FragColor = vec4(vColor, alpha * 0.07);
        }
      `,
      transparent: true,
      depthWrite: false,
      blending: THREE.NormalBlending,
    });

    const fogPoints = new THREE.Points(fogGeometry, fogParticleMaterial);
    scene.add(fogPoints);

    // Carretera con shader de rayas
    const roadShaderMaterial = new THREE.ShaderMaterial({
      uniforms: {
        iTime: { value: 0 },
      },
      vertexShader: `
        varying vec2 vUv;
        void main() {
          vUv = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0);
        }
      `,
      fragmentShader: `
        varying vec2 vUv;
        uniform float iTime;
        void main() {
          float roadWidth = 0.6;
          float x = vUv.x;
          float y = vUv.y;

          float noise = fract(sin(dot(vUv*100.0, vec2(12.9898,78.233))) * 43758.5453);
          vec3 asphalt = mix(vec3(0.09,0.09,0.09), vec3(0.16,0.15,0.14), noise * 0.4);

          float centerLine = step(roadWidth/2.0-0.03, abs(x-0.5)) - step(roadWidth/2.0+0.03, abs(x-0.5));
          float dash = step(0.45, fract(y*6.0 + iTime*0.6));
          vec3 lineColor = vec3(1.0, 0.9, 0.3);
          vec3 color = mix(asphalt, lineColor, centerLine * dash);

          float edge = step(roadWidth, abs(x-0.5));
          color = mix(color, vec3(0.18,0.18,0.18), edge);

          gl_FragColor = vec4(color, 1.0);
        }
      `,
    });

    const roadGeometry = new THREE.PlaneGeometry(4, 16, 1, 1);
    const roadMesh = new THREE.Mesh(roadGeometry, roadShaderMaterial);
    roadMesh.rotation.x = -Math.PI / 2;
    roadMesh.position.set(-5, 0.3, 0);
    scene.add(roadMesh);

    // Importar y ubicar modelos GLB
    const loader = new GLTFLoader();
    loader.load("/glb_models/organic.glb", (gltf) => {
      gltf.scene.position.set(5, 0, 5);
      gltf.scene.scale.set(0.01, 0.01, 0.01);
      scene.add(gltf.scene);
    });
    loader.load("/glb_models/architectural.glb", (gltf) => {
      gltf.scene.position.set(3, 0, 0);
      gltf.scene.scale.set(1, 1, 1);
      scene.add(gltf.scene);
    });

    let utilitarianModel = null;
    loader.load("/glb_models/utilitarian.glb", (gltf) => {
      gltf.scene.position.set(-5, 0.5, 0);
      gltf.scene.scale.set(1, 1, 1);
      scene.add(gltf.scene);
      utilitarianModel = gltf.scene;
    });

    // Animaciones
    let time = 0;
    function animate() {
      requestAnimationFrame(animate);
      time += 0.01;

      fogUniforms.iTime.value = performance.now() / 1000;
      roadShaderMaterial.uniforms.iTime.value = performance.now() / 1000;

      if (rotating) {
        if (usePerspective) {
          cameraP.position.x = Math.sin(time) * 10;
          cameraP.position.z = Math.cos(time) * 10;
          cameraP.lookAt(0, 0, 0);
        } else {
          cameraO.position.x = Math.sin(time) * 10;
          cameraO.position.z = Math.cos(time) * 10;
          cameraO.lookAt(0, 0, 0);
        }
      }

      rimLight.position.x = Math.sin(time) * 8;

      if (utilitarianModel) {
        utilitarianModel.position.z = Math.sin(time) * 7;
      }

      controls.update();
      renderer.render(scene, usePerspective ? cameraP : cameraO);
    }
    animate();

    return () => {
      renderer.dispose();
      controls.dispose();
      if (rendererRef.current.firstChild) {
        rendererRef.current.removeChild(rendererRef.current.firstChild);
      }
    };
  }, [rotating, usePerspective, preset]);

  return (
    <>
      {/* Canvas */}
      <div
        ref={rendererRef}
        id="container"
        style={{
          width: "100vw",
          height: "100vh",
          position: "fixed", 
          left: 0,
          top: 0,
          zIndex: 1,
        }}
      />
      {/* Botones */}
      <div
        style={{
          position: "fixed",
          top: 16,
          left: 16,
          zIndex: 10,
          background: "rgba(30,30,30,0.8)",
          padding: "10px",
          borderRadius: "8px",
          display: "flex",
          flexDirection: "column",
          gap: "8px",
          color: "#fff",
        }}
      >
        <button onClick={() => setPreset("day")}>Día</button>
        <button onClick={() => setPreset("sunset")}>Atardecer</button>
        <button onClick={() => setUsePerspective((v) => !v)}>
          {usePerspective ? "Cámara Ortogonal" : "Cámara Perspectiva"}
        </button>
        <button onClick={() => setRotating((r) => !r)}>
          {rotating ? "Detener rotación" : "Iniciar rotación"}
        </button>
      </div>
    </>
  );
}

export default App;
