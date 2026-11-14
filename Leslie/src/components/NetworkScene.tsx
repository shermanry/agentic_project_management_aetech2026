// 3D knowledge network: every graph node as a sphere, clustered by category (illustrative placement,
// not an embedding projection). Same category colours as the PM canvas.
import { useEffect, useMemo } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import { Html, Line, OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import { CATEGORIES } from '../data/sampleProject'
import { colorOf, useGraph } from '../model/graph'

interface Props {
  labels: boolean
  focus: boolean
  showProposed: boolean
  orbit: boolean
  resetN: number
  compact?: boolean
  /** Monochrome: black nodes on white, no category colour. */
  mono?: boolean
  /** White background with category colours (matches the PM canvas). */
  light?: boolean
}

function Rig({ n }: { n: number }) {
  const camera = useThree((s) => s.camera)
  const controls = useThree((s) => s.controls) as unknown as { target: THREE.Vector3; update: () => void } | null
  useEffect(() => {
    camera.position.set(310, 190, 460)
    controls?.target.set(45, -15, 0)
    controls?.update()
  }, [n, camera, controls])
  return null
}

export default function NetworkScene({ labels, focus, showProposed, orbit, resetN, compact, mono = false, light = false }: Props) {
  const paper = mono || light
  const bg = paper ? '#ffffff' : '#060d1a'
  const { state, dispatch, neighbors, matches } = useGraph()
  const sel = state.selectedId
  const near = useMemo(() => (sel ? neighbors(sel) : new Set<string>()), [sel, state.edges]) // eslint-disable-line react-hooks/exhaustive-deps
  const pos = useMemo(() => Object.fromEntries(state.nodes.map((n) => [n.id, n.pos3d])), [state.nodes])
  const centers = useMemo(
    () =>
      CATEGORIES.map((c) => {
        const ps = state.nodes.filter((n) => n.category === c.id).map((n) => n.pos3d)
        const avg = ps.reduce((a, p) => [a[0] + p[0], a[1] + p[1], a[2] + p[2]], [0, 0, 0]).map((v) => v / (ps.length || 1)) as [number, number, number]
        return { c, avg, count: ps.length }
      }),
    [state.nodes],
  )
  const searching = state.query.trim() !== '' || state.filter !== 'all'
  const hit = useMemo(() => new Set(state.nodes.filter(matches).map((n) => n.id)), [state.nodes, state.query, state.filter]) // eslint-disable-line react-hooks/exhaustive-deps
  const dimmed = (id: string) => id !== sel && ((searching && !hit.has(id)) || (focus && sel !== undefined && !near.has(id)))

  return (
    <Canvas camera={{ position: [310, 190, 460], fov: 45, near: 1, far: 4000 }} onPointerMissed={() => dispatch({ type: 'select', id: undefined })}>
      <color attach="background" args={[bg]} />
      <fog attach="fog" args={[bg, 500, 1100]} />
      <ambientLight intensity={0.5} />
      <pointLight position={[0, 300, 300]} intensity={1.2} decay={0} />

      {/* faint category halos */}
      {centers.map(({ c, avg, count }) =>
        count ? (
          <group key={c.id} position={avg}>
            <mesh>
              <sphereGeometry args={[34 + count * 8, 24, 24]} />
              <meshBasicMaterial color={mono ? '#000000' : c.color} transparent opacity={mono ? 0.025 : light ? 0.07 : 0.05} depthWrite={false} />
            </mesh>
            {labels && !compact && (
              <Html position={[0, -(40 + count * 8), 0]} center style={{ pointerEvents: 'none' }}>
                <div className="cluster-tag" style={{ color: mono ? '#6b6b6b' : c.color }}>
                  {c.label}
                </div>
              </Html>
            )}
          </group>
        ) : null,
      )}

      {state.edges.map((e) => {
        const hot = sel !== undefined && (e.source === sel || e.target === sel)
        const off = (focus && sel !== undefined && !hot) || (searching && !(hit.has(e.source) && hit.has(e.target)))
        return (
          <Line
            key={e.id}
            points={[pos[e.source], pos[e.target]]}
            color={paper ? (hot ? '#0a0a0a' : '#8c8c88') : hot ? '#38d6ff' : e.status === 'accepted' ? '#b58cf0' : '#8fa3b8'}
            lineWidth={hot ? 2.2 : 1}
            transparent
            opacity={off ? 0.08 : hot ? 0.95 : paper ? 0.6 : 0.32}
          />
        )
      })}
      {showProposed &&
        state.candidates
          .filter((c) => c.state === 'pending')
          .map((c) => (
            <Line key={c.id} points={[pos[c.source], pos[c.target]]} color={paper ? '#8c8c88' : '#b58cf0'} lineWidth={1} dashed dashSize={6} gapSize={5} transparent opacity={0.6} />
          ))}

      {state.nodes.map((n) => {
        const on = n.id === sel
        const col = mono ? '#141414' : colorOf(n)
        const off = dimmed(n.id)
        const r = n.importance === 'high' ? 7 : n.importance === 'medium' ? 5.5 : 4.5
        return (
          <group key={n.id} position={n.pos3d}>
            <mesh
              onClick={(e) => {
                e.stopPropagation()
                dispatch({ type: 'select', id: n.id })
              }}
              onPointerOver={(e) => {
                e.stopPropagation()
                document.body.style.cursor = 'pointer'
              }}
              onPointerOut={() => (document.body.style.cursor = '')}
            >
              <sphereGeometry args={[on ? r * 1.35 : r, 24, 24]} />
              <meshStandardMaterial color={col} emissive={col} emissiveIntensity={mono ? 0 : light ? 0.35 : on ? 1.1 : 0.55} transparent opacity={off ? 0.18 : 1} />
            </mesh>
            <mesh>
              <sphereGeometry args={[r * 2.1, 16, 16]} />
              <meshBasicMaterial color={col} transparent opacity={mono ? 0 : off ? 0.02 : on ? 0.22 : light ? 0.14 : 0.08} depthWrite={false} />
            </mesh>
            {on && (
              <mesh rotation-x={Math.PI / 2}>
                <ringGeometry args={[r * 2, r * 2.3, 48]} />
                <meshBasicMaterial color={paper ? '#0a0a0a' : '#ffffff'} side={THREE.DoubleSide} transparent opacity={0.8} />
              </mesh>
            )}
            {labels && (
              <Html position={[0, r + 8, 0]} center>
                {/* selected / dimmed styling comes from a stylesheet in PilotView, keyed on data-id */}
                <button
                  type="button"
                  className={`node-chip ${n.category === null ? 'uncl' : ''}`}
                  data-id={n.id}
                  onClick={(e) => {
                    e.stopPropagation()
                    dispatch({ type: 'select', id: n.id })
                  }}
                >
                  {n.title}
                </button>
              </Html>
            )}
          </group>
        )
      })}

      <OrbitControls makeDefault autoRotate={orbit} autoRotateSpeed={0.5} minDistance={120} maxDistance={1200} />
      <Rig n={resetN} />
    </Canvas>
  )
}
