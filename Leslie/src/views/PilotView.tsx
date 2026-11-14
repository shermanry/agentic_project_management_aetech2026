import { useState } from 'react'
import NetworkScene from '../components/NetworkScene'
import { CategoryChips, NodeInspector, SearchBar } from '../components/ui'
import { useGraph } from '../model/graph'

export default function PilotView() {
  const { state, dispatch, matches, neighbors } = useGraph()
  const [labels, setLabels] = useState(true)
  const [focus, setFocus] = useState(false)
  const [proposed, setProposed] = useState(true)
  const [orbit, setOrbit] = useState(false)
  const [resetN, setResetN] = useState(0)
  const pending = state.candidates.filter((c) => c.state === 'pending').length

  // Label states as CSS keyed on data-id, so they never lag behind the 3D scene.
  const sel = state.selectedId
  const searching = state.query.trim() !== '' || state.filter !== 'all'
  const near = sel ? neighbors(sel) : new Set<string>()
  const dim = state.nodes.filter((n) => n.id !== sel && ((searching && !matches(n)) || (focus && sel !== undefined && !near.has(n.id)))).map((n) => n.id)
  const labelCss =
    (sel ? `.node-chip[data-id="${sel}"]{background:#0a0a0a;color:#fff}` : '') + dim.map((id) => `.node-chip[data-id="${id}"]{opacity:.2}`).join('')

  const toggles: [string, boolean, (v: boolean) => void][] = [
    ['Labels', labels, setLabels],
    ['Focus neighborhood', focus, setFocus],
    ['Proposed links', proposed, setProposed],
    ['Auto-orbit', orbit, setOrbit],
  ]

  return (
    <div className="twin net">
      <style>{labelCss}</style>
      <div className="twin-canvas">
        <NetworkScene light labels={labels} focus={focus} showProposed={proposed} orbit={orbit} resetN={resetN} />
      </div>
      <div className="hud">
        <div className="hud-col left">
          <section className="glass">
            <div className="eyebrow">Pilot</div>
            <h1 className="site-name">Knowledge network</h1>
            <p className="body dim">
              Grouped by category. Drag to orbit, scroll to zoom, click a node.
            </p>
            <div className="netstats">
              <div>
                <b className="mono">{state.nodes.length}</b>
                <span>nodes</span>
              </div>
              <div>
                <b className="mono">{state.edges.length}</b>
                <span>relationships</span>
              </div>
              <div>
                <b className="mono">{pending}</b>
                <span>proposed</span>
              </div>
            </div>
          </section>
          <section className="glass">
            <div className="glass-h">
              <h2>Categories</h2>
            </div>
            <CategoryChips />
          </section>
          <section className="glass">
            <div className="glass-h">
              <h2>Links</h2>
            </div>
            <div className="edge-key">
              <span className="k-app">approved</span>
              <span className="k-prop">proposed</span>
            </div>
          </section>
        </div>

        <div className="hud-top stack">
          <div className="glass net-search">
            <SearchBar id="pilot-search" />
          </div>
          <div className="toolbar glass" role="toolbar" aria-label="Network view">
            <button className="btn sm" onClick={() => setResetN((n) => n + 1)}>
              Reset view
            </button>
            <span className="sep" />
            {toggles.map(([l, v, set]) => (
              <label key={l} className={`toggle ${v ? 'on' : ''}`}>
                <input type="checkbox" checked={v} onChange={() => set(!v)} />
                {l}
              </label>
            ))}
          </div>
        </div>

        <div className="hud-col right">
          {state.selectedId ? (
            <section className="glass">
              <NodeInspector compact onClose={() => dispatch({ type: 'select', id: undefined })} jump={{ label: 'Open in canvas', hash: 'pm' }} />
            </section>
          ) : (
            <section className="glass">
              <p className="body dim">Click a node to see its category, status, summary and connections.</p>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}
