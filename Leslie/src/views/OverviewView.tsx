// Overview: the project at a glance, in the editorial kit (src/design/ui.css).
// Monochrome on purpose: no colour coding, status is a word. Everything derives from the shared graph.
import { useState } from 'react'
import BuildingScene from '../components/BuildingScene'
import { CATEGORIES, COMPONENTS, PROJECT, SAMPLE_WINDOW, type ComponentId } from '../data/sampleProject'
import { needsAttention, useGraph } from '../model/graph'
import Onboarding, { startFor, type Start } from './Onboarding'
import north from '../assets/comp-north.jpg'
import east from '../assets/comp-east.jpg'
import roof from '../assets/comp-roof.jpg'
import entrance from '../assets/comp-entrance.jpg'
import upper from '../assets/comp-upper.jpg'

const IMG: Record<ComponentId, string> = { north, east, roof, entrance, upper }

interface Props {
  openPM: (id: string) => void
  openClient: (c?: ComponentId) => void
  openPilot: (id?: string) => void
  /** Go to a tab, optionally asking the guide a question on arrival. */
  goTo: (s: Start) => void
}

const two = (n: number) => String(n).padStart(2, '0')

export default function OverviewView({ openPM, openClient, openPilot, goTo }: Props) {
  const { state, dispatch, byId } = useGraph()
  const [comp, setComp] = useState<ComponentId>('roof')
  const { nodes, edges, candidates } = state
  const pending = candidates.filter((c) => c.state === 'pending')
  const open = nodes.filter((n) => needsAttention(n) && n.openQuestion)
  const current = COMPONENTS.find((c) => c.id === comp)!
  const [skipped, setSkipped] = useState(false)
  const start = state.onboarding ? startFor(state.onboarding) : undefined

  // First visit: a short questionnaire before the board.
  if (!state.onboarding && !skipped)
    return (
      <Onboarding
        onSkip={() => setSkipped(true)}
        onDone={(a, go) => {
          dispatch({ type: 'setOnboarding', onboarding: a })
          if (go) goTo(go)
        }}
      />
    )

  return (
    <div className="ed-page">
      <header className="ov-hero">
        <div className="ed-meta">
          {PROJECT.code} — {PROJECT.status}
        </div>
        <h1 className="ed-display">{PROJECT.name}</h1>
        <div className="ov-hero-foot">
          <p className="ed-lede">Façade condition survey. Everything the project knows, in one graph.</p>
          <button className="ed-link" onClick={() => openClient(comp)}>
            Enter building
          </button>
        </div>
      </header>

      <div className="ov-start">
        {start ? (
          <>
            <span className="ed-meta">Suggested for you</span>
            <button className="ed-link" onClick={() => goTo(start)}>
              {start.label}
            </button>
            <span className="why">{start.why}</span>
            <button className="ed-link dim" onClick={() => dispatch({ type: 'setOnboarding', onboarding: undefined })}>
              Retake questions
            </button>
          </>
        ) : (
          <>
            <span className="ed-meta">New here?</span>
            <button className="ed-link" onClick={() => setSkipped(false)}>
              Answer 3 questions to find your start
            </button>
          </>
        )}
      </div>

      <figure className="ed-figure ov-figure">
        <div className="frame">
          <BuildingScene mono orbit selected={comp} onSelect={(id) => id && setComp(id)} labels={false} />
        </div>
        <figcaption className="ed-meta">
          <span>Illustrative model</span>
          <span>{current.label}</span>
        </figcaption>
      </figure>

      <section className="ed-nums" aria-label="Project totals">
        {[
          [nodes.length, 'Nodes'],
          [edges.length, 'Links'],
          [pending.length, 'To review'],
          [open.length, 'Open questions'],
        ].map(([n, l]) => (
          <div key={l}>
            <span className="ed-num">{n}</span>
            <span className="ed-meta">{l}</span>
          </div>
        ))}
      </section>

      <section className="ed-section">
        <div className="ed-label">
          <span className="ed-meta">01</span>
          <h2>Review</h2>
        </div>
        <div className="ed-body">
          {pending.length ? (
            <ul className="ed-rows">
              {pending.map((c) => (
                <li key={c.id} className="ed-row" title={c.reason}>
                  <span className="t">
                    {byId(c.source)?.title} → {byId(c.target)?.title}
                  </span>
                  <span className="side">
                    <span className="ed-meta">{c.relation}</span>
                    <button className="ed-link plain" onClick={() => dispatch({ type: 'accept', id: c.id })}>
                      Accept
                    </button>
                    <button className="ed-link dim" onClick={() => dispatch({ type: 'dismiss', id: c.id })}>
                      Dismiss
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="ed-empty">Nothing to review.</p>
          )}
        </div>
      </section>

      <section className="ed-section">
        <div className="ed-label">
          <span className="ed-meta">02</span>
          <h2>Open questions</h2>
        </div>
        <div className="ed-body">
          <ul className="ed-rows">
            {open.map((n) => (
              <li key={n.id}>
                <button className="ed-row" title={n.openQuestion} onClick={() => openPM(n.id)}>
                  <span className="t">{n.title}</span>
                  <span className="side">
                    <span className="ed-meta">{n.status}</span>
                    <span className="go" aria-hidden>
                      →
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="ed-section">
        <div className="ed-label">
          <span className="ed-meta">03</span>
          <h2>Building</h2>
          <button className="ed-link" onClick={() => openClient(comp)}>
            Enter
          </button>
        </div>
        <div className="ed-body ed-tiles">
          {COMPONENTS.map((c, i) => (
            <button key={c.id} className={`ed-tile ${c.id === comp ? 'on' : ''}`} onClick={() => setComp(c.id)} aria-pressed={c.id === comp}>
              <span className="frame">
                <img src={IMG[c.id]} alt={`Model view of the ${c.label.toLowerCase()}`} loading="lazy" />
              </span>
              <span className="ed-meta">{two(i + 1)}</span>
              <span className="t">{c.label}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="ed-section">
        <div className="ed-label">
          <span className="ed-meta">04</span>
          <h2>Project map</h2>
          <button className="ed-link" onClick={() => openPilot(state.selectedId)}>
            View in 3D
          </button>
        </div>
        <div className="ed-body ed-cols">
          {CATEGORIES.map((c) => (
            <div key={c.id} className="ed-col">
              <span className="ed-meta">{c.label}</span>
              {nodes
                .filter((n) => n.category === c.id)
                .map((n) => (
                  <button key={n.id} className="ed-item" title={n.summary} onClick={() => openPM(n.id)}>
                    <span className="t">{n.title}</span>
                    <span className="ed-meta">{n.status}</span>
                  </button>
                ))}
            </div>
          ))}
        </div>
      </section>

      <section className="ed-section">
        <div className="ed-label">
          <span className="ed-meta">05</span>
          <h2>This week</h2>
        </div>
        <div className="ed-body">
          <div className="ed-week">
            {SAMPLE_WINDOW.map((d) => (
              <div key={d.day} className="ed-day" title={d.note}>
                <span className="ed-meta">{d.day.split(' ')[0]}</span>
                <b>{d.day.split(' ')[1]}</b>
                <span className={`ed-glyph ${d.tone}`} role="img" aria-label={d.tone === 'ok' ? 'Clear' : d.tone === 'warn' ? 'Marginal' : 'Not workable'} />
              </div>
            ))}
          </div>
          <div className="ed-key ed-meta">
            <span>
              <i className="ed-glyph ok" /> Clear
            </span>
            <span>
              <i className="ed-glyph warn" /> Marginal
            </span>
            <span>
              <i className="ed-glyph" /> Not workable
            </span>
          </div>
        </div>
      </section>

      <footer className="ed-foot ed-meta">
        <span>Sample data. No live services connected.</span>
        <span>{PROJECT.workspace}</span>
      </footer>
    </div>
  )
}
