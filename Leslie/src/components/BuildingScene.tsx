// Illustrative massing model of 125 Hudson Street, built from boxes. Not a scan, not to survey accuracy.
import { useEffect, useMemo, useState } from 'react'
import { Canvas, useThree, type ThreeEvent } from '@react-three/fiber'
import { Html, OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import type { ComponentId } from '../data/sampleProject'
import { COMPONENTS } from '../data/sampleProject'

const W = 32 // x, east-west
const D = 24 // z, north = -z
const H1 = 40 // main volume
const UW = 26
const UD = 18
const H2 = 48 // top of setback

export type Preset = { name: 'persp' | 'front' | 'top'; n: number }

interface Props {
  selected?: ComponentId
  onSelect?: (id: ComponentId | undefined) => void
  labels?: boolean
  orbit?: boolean
  preset?: Preset
  interactive?: boolean
  /** Light scene colours for the light UI theme. */
  light?: boolean
  /** Monochrome clay model for the editorial theme (implies light). */
  mono?: boolean
  /** Fixed camera, overrides `preset`. */
  view?: { pos: [number, number, number]; target: [number, number, number] }
}

/** Window mullion grid on all four faces of a box, as one line geometry. */
function windowGrid(w: number, d: number, y0: number, y1: number, colStep: number, rowStep: number) {
  const pts: number[] = []
  const faces: [number, number, number, number, 'x' | 'z'][] = [
    [-w / 2, -d / 2 - 0.02, w / 2, -d / 2 - 0.02, 'x'],
    [-w / 2, d / 2 + 0.02, w / 2, d / 2 + 0.02, 'x'],
    [-w / 2 - 0.02, -d / 2, -w / 2 - 0.02, d / 2, 'z'],
    [w / 2 + 0.02, -d / 2, w / 2 + 0.02, d / 2, 'z'],
  ]
  for (const [ax, az, bx, bz, along] of faces) {
    const len = along === 'x' ? bx - ax : bz - az
    for (let t = 0; t <= len + 0.01; t += colStep) {
      const x = along === 'x' ? ax + t : ax
      const z = along === 'x' ? az : az + t
      pts.push(x, y0, z, x, y1, z)
    }
    for (let y = y0; y <= y1 + 0.01; y += rowStep) pts.push(ax, y, az, bx, y, bz)
  }
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3))
  return g
}

function Rig({ preset, view }: { preset: Preset; view?: Props['view'] }) {
  const camera = useThree((s) => s.camera)
  const controls = useThree((s) => s.controls) as unknown as { target: THREE.Vector3; update: () => void } | null
  useEffect(() => {
    const p: [number, number, number] = preset.name === 'top' ? [0.01, 140, 0.01] : preset.name === 'front' ? [0, 26, -95] : [70, 55, -80]
    camera.position.set(...(view?.pos ?? p))
    controls?.target.set(...(view?.target ?? ([0, preset.name === 'top' ? 0 : 22, 0] as [number, number, number])))
    controls?.update()
  }, [preset.name, preset.n, camera, controls, view])
  return null
}

function Surface({
  id,
  selected,
  hovered,
  setHover,
  onSelect,
  accent,
  solid,
  children,
}: {
  id: ComponentId
  selected?: ComponentId
  hovered?: ComponentId
  setHover: (id?: ComponentId) => void
  onSelect?: (id: ComponentId) => void
  accent: string
  solid?: boolean
  children: (mat: THREE.MeshStandardMaterial) => React.ReactNode
}) {
  const on = selected === id
  const hov = hovered === id
  const mat = useMemo(() => new THREE.MeshStandardMaterial({ transparent: true, side: THREE.DoubleSide, depthWrite: false }), [])
  mat.color.set(accent)
  mat.emissive.set(on && !solid ? accent : '#000000')
  mat.emissiveIntensity = on && !solid ? 0.35 : 0
  mat.opacity = on ? (solid ? 0.9 : 0.5) : hov ? 0.22 : solid ? 0 : 0.05
  return (
    <group
      onPointerOver={(e: ThreeEvent<PointerEvent>) => {
        if (!onSelect) return
        e.stopPropagation()
        setHover(id)
        document.body.style.cursor = 'pointer'
      }}
      onPointerOut={() => {
        setHover(undefined)
        document.body.style.cursor = ''
      }}
      onClick={(e: ThreeEvent<MouseEvent>) => {
        if (!onSelect) return
        e.stopPropagation()
        onSelect(id)
      }}
    >
      {children(mat)}
    </group>
  )
}

export default function BuildingScene({ selected, onSelect, labels = true, orbit = false, preset = { name: 'persp', n: 0 }, interactive = true, light: lightProp = false, mono = false, view }: Props) {
  const light = lightProp || mono
  const [hovered, setHover] = useState<ComponentId>()
  const grids = useMemo(() => [windowGrid(W, D, 6, H1, 3.2, 3.4), windowGrid(UW, UD, H1, H2, 2.6, 4)], [])
  const sel = interactive ? (id: ComponentId) => onSelect?.(id) : undefined
  const anchors: Record<ComponentId, [number, number, number]> = {
    north: [-8, 26, -D / 2 - 1],
    east: [W / 2 + 1, 22, 4],
    roof: [0, H2 + 4, 0],
    entrance: [0, 4, -D / 2 - 6],
    upper: [-UW / 2 - 1, 44, -4],
  }
  const P = mono
    ? { bg: '#ffffff', ground: '#f6f6f4', street: '#ededea', main: '#f2f2ef', line1: '#cdcdc9', line2: '#cdcdc9', upper: '#e7e7e3', trim: '#dcdcd8', mech: '#d3d3cf', glass: '#bcbcb7', accent: '#141414' }
    : light
      ? { bg: '#fafafc', ground: '#f3f4f7', street: '#e9ebef', main: '#eef1f5', line1: '#c3cbd6', line2: '#c9b3a4', upper: '#e8cdbd', trim: '#d4c6b8', mech: '#cfd5dd', glass: '#aeb9c7', accent: '#0071e3' }
      : { bg: '#050b14', ground: '#09141f', street: '#0f1d2b', main: '#a9b8c9', line1: '#5d6f84', line2: '#6f5f55', upper: '#c99a80', trim: '#d4c6b8', mech: '#7b8796', glass: '#2b3c50', accent: '#38d6ff' }
  const s = { selected, hovered, setHover, onSelect: sel, accent: P.accent, solid: mono }
  const bg = P.bg

  return (
    <Canvas camera={{ position: [70, 55, -80], fov: 42, near: 0.5, far: 2000 }} onPointerMissed={() => interactive && onSelect?.(undefined)}>
      <color attach="background" args={[bg]} />
      <fog attach="fog" args={[bg, 160, 380]} />
      <hemisphereLight args={light ? ['#ffffff', '#dfe3ea', 1.5] : ['#cfe2ff', '#0b1a26', 0.9]} />
      <directionalLight position={[60, 120, -40]} intensity={1.4} />
      <directionalLight position={[-80, 40, 60]} intensity={0.35} />

      {/* ground, streets */}
      <mesh rotation-x={-Math.PI / 2} position={[0, -0.01, 0]}>
        <planeGeometry args={[260, 260]} />
        {light ? <meshBasicMaterial color={P.ground} /> : <meshStandardMaterial color={P.ground} />}
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position={[0, 0.01, -D / 2 - 14]}>
        <planeGeometry args={[260, 16]} />
        {light ? <meshBasicMaterial color={P.street} /> : <meshStandardMaterial color={P.street} />}
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position={[W / 2 + 10, 0.01, 0]}>
        <planeGeometry args={[10, 260]} />
        {light ? <meshBasicMaterial color={P.street} /> : <meshStandardMaterial color={P.street} />}
      </mesh>
      {!light && <gridHelper args={[260, 52, '#12324a', '#0d2234']} position={[0, 0.02, 0]} />}
      {labels && (
        <>
          <Html position={[-40, 0.5, -D / 2 - 14]} center style={{ pointerEvents: 'none' }}>
            <div className="tag dim-tag">Hudson St</div>
          </Html>
          <Html position={[W / 2 + 10, 0.5, 30]} center style={{ pointerEvents: 'none' }}>
            <div className="tag dim-tag">side street</div>
          </Html>
        </>
      )}

      {/* massing */}
      <mesh position={[0, H1 / 2, 0]}>
        <boxGeometry args={[W, H1, D]} />
        <meshStandardMaterial color={P.main} roughness={0.85} />
      </mesh>
      <lineSegments geometry={grids[0]}>
        <lineBasicMaterial color={P.line1} />
      </lineSegments>
      <lineSegments geometry={grids[1]}>
        <lineBasicMaterial color={P.line2} />
      </lineSegments>

      {/* Upper façade: setback volume (terracotta) */}
      <Surface id="upper" {...s}>
        {(mat) => (
          <>
            <mesh position={[0, (H1 + H2) / 2, 0]}>
              <boxGeometry args={[UW, H2 - H1, UD]} />
              <meshStandardMaterial color={P.upper} roughness={0.8} />
            </mesh>
            <mesh position={[0, (H1 + H2) / 2, 0]} material={mat}>
              <boxGeometry args={[UW + 0.3, H2 - H1 + 0.1, UD + 0.3]} />
            </mesh>
          </>
        )}
      </Surface>

      {/* Roof & parapet */}
      <Surface id="roof" {...s}>
        {(mat) => (
          <>
            {[
              [0, -UD / 2, UW, 0.6],
              [0, UD / 2, UW, 0.6],
              [-UW / 2, 0, 0.6, UD],
              [UW / 2, 0, 0.6, UD],
            ].map(([x, z, w, d], i) => (
              <mesh key={i} position={[x, H2 + 0.6, z]}>
                <boxGeometry args={[w, 1.2, d]} />
                <meshStandardMaterial color={P.trim} />
              </mesh>
            ))}
            <mesh position={[4, H2 + 2, 2]}>
              <boxGeometry args={[8, 4, 6]} />
              <meshStandardMaterial color={P.mech} />
            </mesh>
            <mesh position={[0, H2 + 0.05, 0]} rotation-x={-Math.PI / 2} material={mat}>
              <planeGeometry args={[UW, UD]} />
            </mesh>
            <mesh position={[0, H2 + 0.7, 0]} material={mat}>
              <boxGeometry args={[UW + 0.4, 1.4, UD + 0.4]} />
            </mesh>
          </>
        )}
      </Surface>

      {/* North façade */}
      <Surface id="north" {...s}>
        {(mat) => (
          <mesh position={[0, (6 + H1) / 2, -D / 2 - 0.15]} material={mat}>
            <planeGeometry args={[W, H1 - 6]} />
          </mesh>
        )}
      </Surface>

      {/* East elevation */}
      <Surface id="east" {...s}>
        {(mat) => (
          <mesh position={[W / 2 + 0.15, (6 + H1) / 2, 0]} rotation-y={Math.PI / 2} material={mat}>
            <planeGeometry args={[D, H1 - 6]} />
          </mesh>
        )}
      </Surface>

      {/* Ground-level entrance + plaza */}
      <Surface id="entrance" {...s}>
        {(mat) => (
          <>
            <mesh position={[0, 3, -D / 2 - 0.1]}>
              <boxGeometry args={[W, 6, 0.3]} />
              <meshStandardMaterial color={P.glass} metalness={0.4} roughness={0.3} />
            </mesh>
            <mesh position={[0, 6.4, -D / 2 - 2.5]}>
              <boxGeometry args={[12, 0.5, 5]} />
              <meshStandardMaterial color={P.trim} />
            </mesh>
            <mesh position={[0, 3, -D / 2 - 0.35]} material={mat}>
              <boxGeometry args={[W + 0.2, 6.2, 0.4]} />
            </mesh>
            <mesh position={[0, 0.05, -D / 2 - 4]} rotation-x={-Math.PI / 2} material={mat}>
              <planeGeometry args={[W, 8]} />
            </mesh>
          </>
        )}
      </Surface>

      {labels &&
        COMPONENTS.map((c) => (
          <Html key={c.id} position={anchors[c.id]} center style={{ pointerEvents: 'none' }}>
            <div className={`tag comp-tag ${selected === c.id ? 'on' : ''}`}>{c.label}</div>
          </Html>
        ))}

      <OrbitControls makeDefault maxPolarAngle={Math.PI / 2.05} target={[0, 22, 0]} autoRotate={orbit} autoRotateSpeed={0.6} minDistance={30} maxDistance={260} />
      <Rig preset={preset} view={view} />
    </Canvas>
  )
}
