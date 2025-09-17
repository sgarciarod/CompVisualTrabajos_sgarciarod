import React, { useRef } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'

function CuboAnimado() {
  const ref = useRef()

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    // Traslación: movimiento circular
    ref.current.position.x = Math.sin(t) * 2
    ref.current.position.y = Math.cos(t) * 2
    // Rotación sobre eje Y
    ref.current.rotation.y += 0.03
    // Escala oscilante
    const scale = 1 + 0.5 * Math.sin(t)
    ref.current.scale.set(scale, scale, scale)
  })

  return (
    <mesh ref={ref}>
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial color="tomato" />
    </mesh>
  )
}

export default function Escena() {
  return (
    <Canvas camera={{ position: [6, 6, 6] }}>
      <ambientLight intensity={0.5} />
      <pointLight position={[10, 10, 10]} />
      <CuboAnimado />
      <OrbitControls />
    </Canvas>
  )
}