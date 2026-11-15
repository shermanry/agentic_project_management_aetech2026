import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { Badge, CategoryChips, Icon, NodeInspector, SearchBar } from '../components/ui'
import { CAT, CATEGORIES, UNCLASSIFIED_COLOR, type GraphEdge, type GraphNode } from '../data/sampleProject'
import { colorOf, useGraph } from '../model/graph'

const CW = 202
const CH = 114
const COL = 318 // column pitch: card + wire channel
const GAP = 46 // vertical gap between cards (room for a group label)
const LANE = 30 // height reserved for a wire passing through a column
type Mode = 'graph' | 'canvas' | 'decisions'
type P = { x: number; y: number }

const MODES: [Mode, string, string][] = [
  ['graph', 'Tree', 'Reads left to right, like a node graph: outputs on the right of a card wire into inputs on the left of the next.'],
  ['canvas', 'Freeform', 'Arrange cards by hand. Moving a card changes its position only, never its relationships.'],
  ['decisions', 'Decisions', 'Decisions in the middle, what feeds them on the left, what they produce on the right.'],
]

interface Group {
  key: string
  label: string
  color: string
  ids: string[]
  dashed?: boolean
}
interface Flow {
  pos: Record<string, P>
  /** Waypoints for wires that span more than one column, so they run through gaps, never behind cards. */
  routes: Record<string, P[]>
  groups: Group[]
}

/**
 * Layered left-to-right layout (the way Grasshopper canvases are usually organised):
 * rank = longest path from a source, long wires get a lane in every column they cross,
 * rows are ordered to reduce crossings, and same-category neighbours form a group.
 */
function flowLayout(nodes: GraphNode[], edges: GraphEdge[]): Flow {
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]))
  const live = edges.filter((e) => byId[e.source] && byId[e.target])
  const linked = new Set(live.flatMap((e) => [e.source, e.target]))
  // Rank from the outputs backwards, so every input sits in the column just before what it feeds.
  const toSink: Record<string, number> = Object.fromEntries(nodes.map((n) => [n.id, 0]))
  for (let i = 0; i < nodes.length; i++) for (const e of live) toSink[e.source] = Math.max(toSink[e.source], toSink[e.target] + 1)
  const depth = Math.max(0, ...nodes.filter((n) => linked.has(n.id)).map((n) => toSink[n.id]))
  const rank: Record<string, number> = Object.fromEntries(nodes.map((n) => [n.id, depth - toSink[n.id]]))

  type Item = { id: string; dummy?: boolean }
  const layers: Item[][] = []
  const catIdx = (id: string) => CATEGORIES.findIndex((c) => c.id === byId[id]?.category)
  for (const n of nodes) if (linked.has(n.id)) (layers[rank[n.id]] ??= []).push({ id: n.id })
  // chain of items each wire passes through, including a lane ("dummy") in every column it crosses
  const chains: Record<string, string[]> = {}
  for (const e of live) {
    const chain = [e.source]
    for (let r = rank[e.source] + 1; r < rank[e.target]; r++) {
      const id = `${e.id}@${r}`
      ;(layers[r] ??= []).push({ id, dummy: true })
      chain.push(id)
    }
    chain.push(e.target)
    chains[e.id] = chain
  }
  const up: Record<string, string[]> = {}
  const down: Record<string, string[]> = {}
  for (const c of Object.values(chains))
    for (let i = 1; i < c.length; i++) {
      ;(down[c[i - 1]] ??= []).push(c[i])
      ;(up[c[i]] ??= []).push(c[i - 1])
    }
  for (const l of layers) l?.sort((a, b) => Number(a.dummy ?? 0) - Number(b.dummy ?? 0) || catIdx(a.id) - catIdx(b.id) || a.id.localeCompare(b.id))
  // barycentre sweeps to reduce wire crossings
  const index = () => Object.fromEntries(layers.flatMap((l) => (l ?? []).map((it, i) => [it.id, i])))
  for (let sweep = 0; sweep < 6; sweep++) {
    const idx = index()
    const order = sweep % 2 === 0 ? layers.map((_, i) => i).slice(1) : layers.map((_, i) => i).slice(0, -1).reverse()
    for (const li of order) {
      const nb = sweep % 2 === 0 ? up : down
      const score = (it: Item, i: number) => {
        const ns = nb[it.id]
        return ns?.length ? ns.reduce((a, x) => a + idx[x], 0) / ns.length : i
      }
      const l = layers[li]
      if (!l) continue
      const scored = l.map((it, i) => ({ it, s: score(it, i) }))
      scored.sort((a, b) => a.s - b.s)
      layers[li] = scored.map((x) => x.it)
    }
  }

  const pos: Record<string, P> = {}
  const laneY: Record<string, number> = {}
  const heights = layers.map((l) => (l ?? []).reduce((h, it) => h + (it.dummy ? LANE : CH + GAP), 0))
  const tallest = Math.max(0, ...heights)
  layers.forEach((l, r) => {
    let y = 70 + (tallest - heights[r]) / 2
    for (const it of l ?? []) {
      if (it.dummy) {
        laneY[it.id] = y + LANE / 2
        y += LANE
      } else {
        pos[it.id] = { x: 60 + r * COL, y }
        y += CH + GAP
      }
    }
  })
  const routes: Record<string, P[]> = {}
  for (const [eid, chain] of Object.entries(chains)) {
    const pts: P[] = []
    chain.slice(1, -1).forEach((id) => {
      const r = Number(id.split('@')[1])
      pts.push({ x: 60 + r * COL - 10, y: laneY[id] }, { x: 60 + r * COL + CW + 10, y: laneY[id] })
    })
    routes[eid] = pts
  }

  // Not wired to anything yet: parked at the bottom of columns that have room, else in a row underneath.
  const loose = nodes.filter((n) => !linked.has(n.id))
  const free = layers.map((_, r) => r).filter((r) => heights[r] <= tallest - 2 * (CH + GAP)).reverse()
  loose.forEach((n, i) => {
    pos[n.id] = i < free.length ? { x: 60 + free[i] * COL, y: 70 + tallest - CH - GAP } : { x: 60 + (i - free.length) * (CW + 36), y: 70 + tallest + 40 }
  })

  const groups: Group[] = []
  layers.forEach((l, r) => {
    let run: string[] = []
    let cat: string | null | undefined
    const flush = () => {
      if (run.length) {
        const c = cat ? CAT[cat as keyof typeof CAT] : undefined
        groups.push({ key: `${r}-${run[0]}`, label: c?.label ?? 'Unclassified', color: c?.color ?? UNCLASSIFIED_COLOR, ids: run })
      }
      run = []
    }
    for (const it of l ?? []) {
      const c = it.dummy ? undefined : byId[it.id].category
      if (it.dummy || c !== cat) flush()
      if (!it.dummy) {
        cat = c
        run.push(it.id)
      } else cat = undefined
    }
    flush()
  })
  loose.forEach((n) => groups.push({ key: `loose-${n.id}`, label: n.category ? `${CAT[n.category].label} · not wired` : 'Parked', color: n.category ? CAT[n.category].color : UNCLASSIFIED_COLOR, ids: [n.id], dashed: true }))
  return { pos, routes, groups }
}

function decisionLayout(nodes: GraphNode[], edges: GraphEdge[]) {
  const decisions = nodes.filter((n) => n.kind === 'decision')
  const dIds = new Set(decisions.map((d) => d.id))
  const up = [...new Set(edges.filter((e) => dIds.has(e.target) && !dIds.has(e.source)).map((e) => e.source))]
  const down = [...new Set(edges.filter((e) => dIds.has(e.source) && !dIds.has(e.target)).map((e) => e.target))]
  const used = new Set([...dIds, ...up, ...down])
  const rest = nodes.filter((n) => !used.has(n.id)).map((n) => n.id)
  const pos: Record<string, P> = {}
  const col = (ids: string[], x: number, gap = 140) => {
    const top = Math.max(60, 330 - ((ids.length - 1) * gap) / 2)
    ids.forEach((id, i) => (pos[id] = { x, y: top + i * gap }))
  }
  col(up, 40)
  col([...dIds], 420, 220)
  col(down, 800)
  col(rest, 1180)
  return { pos, focus: used }
}

export default function PMView() {
  const { state, dispatch, degree, matches: passes } = useGraph()
  const [mode, setMode] = useState<Mode>('graph')
  const [zoom, setZoom] = useState(0.8)
  const [pan, setPan] = useState<P>({ x: 20, y: 10 })
  const [over, setOver] = useState<Record<Mode, Record<string, P>>>({ canvas: {}, graph: {}, decisions: {} })
  const [note, setNote] = useState<string>()
  const wrap = useRef<HTMLDivElement>(null)

  const nodeKey = state.nodes.map((n) => `${n.id}:${n.category}`).join()
  const flow = useMemo(() => flowLayout(state.nodes, state.edges), [nodeKey, state.edges]) // eslint-disable-line react-hooks/exhaustive-deps
  const dec = useMemo(() => decisionLayout(state.nodes, state.edges), [nodeKey, state.edges]) // eslint-disable-line react-hooks/exhaustive-deps

  const posOf = useCallback(
    (n: GraphNode): P => (mode === 'canvas' ? n.canvas : over[mode][n.id] ?? (mode === 'graph' ? flow.pos[n.id] : dec.pos[n.id]) ?? n.canvas),
    [mode, over, flow, dec],
  )
  const matches = (n: GraphNode) => passes(n) && (mode !== 'decisions' || dec.focus.has(n.id))

  const fit = useCallback(() => {
    const el = wrap.current
    if (!el || !state.nodes.length) return
    const ps = state.nodes.map(posOf)
    const minX = Math.min(...ps.map((p) => p.x)) - 20
    const minY = Math.min(...ps.map((p) => p.y)) - 44
    const maxX = Math.max(...ps.map((p) => p.x)) + CW + 20
    const maxY = Math.max(...ps.map((p) => p.y)) + CH + 20
    const z = Math.max(0.35, Math.min(1.15, (el.clientWidth - 40) / (maxX - minX), (el.clientHeight - 110) / (maxY - minY)))
    setZoom(z)
    setPan({ x: (el.clientWidth - (maxX - minX) * z) / 2 - minX * z, y: (el.clientHeight - (maxY - minY) * z) / 2 - minY * z - 14 })
  }, [state.nodes, posOf])

  useEffect(() => {
    const id = requestAnimationFrame(fit)
    return () => cancelAnimationFrame(id)
  }, [mode]) // eslint-disable-line react-hooks/exhaustive-deps

  // Re-fit when the canvas area changes size (e.g. the guide's answer appears above it).
  const fitRef = useRef(fit)
  useEffect(() => {
    fitRef.current = fit
  })
  useEffect(() => {
    const el = wrap.current
    if (!el || typeof ResizeObserver === 'undefined') return
    let h = el.clientHeight
    const ro = new ResizeObserver(() => {
      if (Math.abs(el.clientHeight - h) > 24) {
        h = el.clientHeight
        fitRef.current()
      }
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Wheel zoom around the cursor
  useEffect(() => {
    const el = wrap.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const r = el.getBoundingClientRect()
      const mx = e.clientX - r.left
      const my = e.clientY - r.top
      setZoom((z) => {
        const nz = Math.max(0.3, Math.min(2, z * (e.deltaY < 0 ? 1.1 : 0.9)))
        setPan((p) => ({ x: mx - ((mx - p.x) * nz) / z, y: my - ((my - p.y) * nz) / z }))
        return nz
      })
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [])

  // Dragging cards / panning background
  const drag = useRef<{ id?: string; sx: number; sy: number; ox: number; oy: number; moved: boolean } | null>(null)
  const zoomRef = useRef(zoom)
  const modeRef = useRef(mode)
  useEffect(() => {
    zoomRef.current = zoom
    modeRef.current = mode
  })
  useEffect(() => {
    const move = (e: PointerEvent) => {
      const d = drag.current
      if (!d) return
      const dx = e.clientX - d.sx
      const dy = e.clientY - d.sy
      if (Math.abs(dx) + Math.abs(dy) > 4) d.moved = true
      if (!d.moved) return
      if (!d.id) return setPan({ x: d.ox + dx, y: d.oy + dy })
      const x = Math.round(d.ox + dx / zoomRef.current)
      const y = Math.round(d.oy + dy / zoomRef.current)
      if (modeRef.current === 'canvas') dispatch({ type: 'move', id: d.id, x, y })
      else setOver((o) => ({ ...o, [modeRef.current]: { ...o[modeRef.current], [d.id!]: { x, y } } }))
    }
    const up = () => {
      const d = drag.current
      if (d?.id && !d.moved) dispatch({ type: 'select', id: d.id })
      if (d && !d.id && !d.moved) dispatch({ type: 'select', id: undefined })
      drag.current = null
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
    }
  }, [dispatch])

  const sel = state.selectedId
  const pos = Object.fromEntries(state.nodes.map((n) => [n.id, posOf(n)]))

  /** Wire from a card's output port (right) to another card's input port (left), through any lanes. */
  const wire = (source: string, target: string, edgeId?: string) => {
    const a = pos[source]
    const b = pos[target]
    if (!a || !b) return { d: '', mid: { x: 0, y: 0 } }
    const routed = mode === 'graph' && edgeId && !over.graph[source] && !over.graph[target] ? flow.routes[edgeId] ?? [] : []
    const pts: P[] = [{ x: a.x + CW, y: a.y + CH / 2 }, ...routed, { x: b.x, y: b.y + CH / 2 }]
    let d = `M${pts[0].x},${pts[0].y}`
    for (let i = 1; i < pts.length; i++) {
      const p = pts[i - 1]
      const q = pts[i]
      const k = q.x >= p.x ? Math.max(36, (q.x - p.x) / 2) : Math.max(90, (p.x - q.x) / 2) // loop out and back if the target is to the left
      d += ` C${p.x + k},${p.y} ${q.x - k},${q.y} ${q.x},${q.y}`
    }
    return { d, mid: { x: (pts[0].x + pts[1].x) / 2, y: (pts[0].y + pts[1].y) / 2 } }
  }

  const groups =
    mode === 'graph'
      ? flow.groups
          .map((g) => {
            const ps = g.ids.map((id) => pos[id]).filter(Boolean)
            if (!ps.length) return null
            const x0 = Math.min(...ps.map((p) => p.x)) - 14
            const y0 = Math.min(...ps.map((p) => p.y)) - 28
            return { ...g, x: x0, y: y0, w: Math.max(...ps.map((p) => p.x)) + CW + 14 - x0, h: Math.max(...ps.map((p) => p.y)) + CH + 14 - y0 }
          })
          .filter((g) => g !== null)
      : []

  const addNote = (e: React.FormEvent) => {
    e.preventDefault()
    if (note?.trim()) dispatch({ type: 'addNode', title: note.trim(), kind: 'note' })
    setNote(undefined)
    requestAnimationFrame(fit)
  }

  return (
    <div className="pm">
      <div className="pm-main">
        <div className="pm-search">
          <SearchBar id="pm-search" />
          <button className="ed-cta" onClick={() => setNote(note === undefined ? '' : undefined)} aria-expanded={note !== undefined}>
            + Add node
          </button>
        </div>
        {note !== undefined && (
          <form className="pm-add" onSubmit={addNote}>
            <input id="new-node" autoFocus aria-label="New node title" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Name the new node" />
            <button className="ed-link plain" disabled={!note.trim()}>
              Add
            </button>
            <button type="button" className="ed-link dim" onClick={() => setNote(undefined)}>
              Cancel
            </button>
            <span className="ed-meta">Lands in Parked until it is organized</span>
          </form>
        )}

        <div className="pm-toolbar">
          <div className="seg sm" role="group" aria-label="Layout">
            {MODES.map(([m, label]) => (
              <button key={m} className={mode === m ? 'on' : ''} onClick={() => setMode(m)}>
                {label}
              </button>
            ))}
          </div>
          <span className="dim small mode-info">{MODES.find(([m]) => m === mode)?.[2]}</span>
        </div>

        <CategoryChips />

        <div
          ref={wrap}
          className="canvas-wrap"
          onPointerDown={(e) => {
            if (e.button !== 0) return
            drag.current = { sx: e.clientX, sy: e.clientY, ox: pan.x, oy: pan.y, moved: false }
          }}
        >
          <div className="layer" style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}>
            {mode === 'canvas' &&
              [
                [40, 'Project inputs'],
                [320, 'Planning & constraints'],
                [610, 'Decisions & outputs'],
                [1170, 'Parked'],
              ].map(([x, l]) => (
                <div key={l} className="group-label" style={{ left: x as number, top: 22 }}>
                  {l}
                </div>
              ))}

            {groups.map((g) => (
              <div key={g.key} className={`gh-group ${g.dashed ? 'dashed' : ''}`} style={{ left: g.x, top: g.y, width: g.w, height: g.h, '--c': g.color } as CSSProperties}>
                <span>{g.label}</span>
              </div>
            ))}

            {/* Wires are always drawn: never toggled off, never faded by search or filters. */}
            <svg className="edges" width="1600" height="1000" style={{ overflow: 'visible' }}>
              {state.candidates
                .filter((c) => c.state === 'pending')
                .map((c) => (
                  <g key={c.id} className="edge cand">
                    <path d={wire(c.source, c.target).d} />
                  </g>
                ))}
              {state.edges.map((e) => {
                const hot = sel !== undefined && (e.source === sel || e.target === sel)
                const w = wire(e.source, e.target, e.id)
                return (
                  <g key={e.id} className={`edge ${hot ? 'hot' : ''} ${e.status === 'accepted' ? 'acc' : ''}`}>
                    <path d={w.d} />
                    {hot && (
                      <text x={w.mid.x} y={w.mid.y - 7} textAnchor="middle">
                        {e.relation}
                      </text>
                    )}
                  </g>
                )
              })}
            </svg>

            {state.nodes.map((n) => {
              const p = pos[n.id]
              const on = n.id === sel
              return (
                <div
                  key={n.id}
                  className={`card ${on ? 'sel' : ''} ${matches(n) ? '' : 'fade'} ${n.category === null ? 'uncl' : ''}`}
                  style={{ left: p.x, top: p.y, '--cat': colorOf(n) } as CSSProperties}
                  onPointerDown={(e) => {
                    if (e.button !== 0) return
                    e.stopPropagation()
                    drag.current = { id: n.id, sx: e.clientX, sy: e.clientY, ox: p.x, oy: p.y, moved: false }
                  }}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => e.key === 'Enter' && dispatch({ type: 'select', id: n.id })}
                  aria-label={n.title}
                >
                  <i className="port in" aria-hidden />
                  <i className="port out" aria-hidden />
                  <div className="card-top">
                    <span className="ico">
                      <Icon kind={n.kind} size={14} />
                    </span>
                    <span className="kind">{n.kind}</span>
                    {n.origin.kind === 'ai-generated' && <span className="badge t-ai">AI</span>}
                  </div>
                  <div className="card-title">{n.title}</div>
                  <div className="card-sub">{n.summary}</div>
                  <div className="card-foot">
                    <Badge status={n.status} />
                    <span className="links" title="Approved relationships">
                      ⇄ {degree(n.id)}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>

          <div className="zoombar" onPointerDown={(e) => e.stopPropagation()}>
            <button onClick={() => setZoom((z) => Math.max(0.3, z / 1.15))} aria-label="Zoom out">
              −
            </button>
            <span className="mono">{Math.round(zoom * 100)}%</span>
            <button onClick={() => setZoom((z) => Math.min(2, z * 1.15))} aria-label="Zoom in">
              +
            </button>
            <button onClick={fit}>Fit</button>
            <button
              onClick={() => {
                if (mode === 'canvas') dispatch({ type: 'resetLayout' })
                else setOver((o) => ({ ...o, [mode]: {} }))
                requestAnimationFrame(() => requestAnimationFrame(fit))
              }}
            >
              Auto-arrange
            </button>
          </div>
          <div className="legend-box" onPointerDown={(e) => e.stopPropagation()}>
            <div className="wire-key">
              <span className="k-app">approved</span>
              <span className="k-acc">AI · accepted</span>
              <span className="k-prop">proposed</span>
            </div>
          </div>
        </div>
      </div>

      <aside className="pm-side">
        <NodeInspector jump={{ label: 'View in 3D', hash: 'pilot' }} />
      </aside>
    </div>
  )
}
