// Parking lot: everything imported lands here first. "Organize" proposes a category and links for
// each parked item; nothing joins the graph until a person accepts.
import { useRef, useState } from 'react'
import { CAT } from '../data/sampleProject'
import { organize } from '../features/organize'
import { isParked, useGraph } from '../model/graph'

const TEXT_FILE = /\.(txt|md|csv|json|log|xml|html?)$/i

export default function ParkingView({ openPM }: { openPM: (id: string) => void }) {
  const { state, dispatch, byId } = useGraph()
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const [over, setOver] = useState(false)
  const picker = useRef<HTMLInputElement>(null)
  const parked = state.nodes.filter(isParked)
  const placed = state.nodes.filter((n) => !isParked(n))
  const waiting = parked.filter((n) => !state.suggestions[n.id])

  const addFiles = async (files: FileList | File[]) => {
    for (const f of Array.from(files)) {
      // Plain-text files are read locally so the organizer has something to go on. Others: name only.
      const readable = (f.type.startsWith('text/') || TEXT_FILE.test(f.name)) && f.size < 200_000
      const text = readable ? await f.text().catch(() => undefined) : undefined
      dispatch({ type: 'addNode', title: f.name, kind: 'file', text })
    }
  }

  const run = async () => {
    setBusy(true)
    const out = await organize(parked, state.nodes)
    dispatch({ type: 'setSuggestions', suggestions: out })
    setBusy(false)
  }

  return (
    <div className="ed-page">
      <header className="ov-hero">
        <div className="ed-meta">Data — {parked.length} parked · {placed.length} in the graph</div>
        <h1 className="ed-display md">Parking lot</h1>
        <div className="ov-hero-foot">
          <p className="ed-lede">Everything imported lands here first. Organize sorts it. You approve.</p>
          <button className="ed-cta" onClick={run} disabled={busy || !parked.length}>
            {busy ? 'Organizing…' : waiting.length || !parked.length ? 'Organize' : 'Organize again'}
          </button>
        </div>
      </header>

      <div
        className={`pk-drop ${over ? 'over' : ''}`}
        onDragOver={(e) => (e.preventDefault(), setOver(true))}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setOver(false)
          void addFiles(e.dataTransfer.files)
        }}
      >
        <span className="big">Drop files here</span>
        <button className="ed-link" onClick={() => picker.current?.click()}>
          Browse
        </button>
        <input
          ref={picker}
          id="pk-files"
          type="file"
          multiple
          hidden
          onChange={(e) => {
            if (e.target.files) void addFiles(e.target.files)
            e.target.value = ''
          }}
        />
        <form
          className="pk-note"
          onSubmit={(e) => {
            e.preventDefault()
            const t = note.trim()
            if (!t) return
            dispatch({ type: 'addNode', title: t.length > 60 ? t.slice(0, 57) + '…' : t, kind: 'note', text: t })
            setNote('')
          }}
        >
          <input id="pk-note" aria-label="Paste a note" placeholder="or paste a note" value={note} onChange={(e) => setNote(e.target.value)} />
          <button className="ed-link plain" disabled={!note.trim()}>
            Add
          </button>
        </form>
      </div>

      <section className="ed-section">
        <div className="ed-label">
          <span className="ed-meta">01</span>
          <h2>Parked</h2>
        </div>
        <div className="ed-body">
          {parked.length ? (
            <ul className="ed-rows">
              {parked.map((n) => {
                const sg = state.suggestions[n.id]
                return (
                  <li key={n.id} className="ed-row pk-row">
                    <span className="t">
                      {n.title}
                      <span className="ed-meta sub">
                        {n.kind} · {n.origin.name}
                      </span>
                    </span>
                    <span className="side">
                      {sg ? (
                        <>
                          <span className="pk-sg" title={sg.reason}>
                            <span className="arrow" aria-hidden>
                              →
                            </span>
                            <b>{CAT[sg.category].label}</b>
                            <span className="ed-meta">{Math.round(sg.confidence * 100)}%</span>
                            {sg.links.length > 0 && (
                              <span className="ed-meta links">
                                {sg.links.map((l) => `${l.relation} ${byId(l.target)?.title}`).join(' · ')}
                              </span>
                            )}
                          </span>
                          <button className="ed-link plain" onClick={() => dispatch({ type: 'applySuggestion', id: n.id })}>
                            Accept
                          </button>
                          <button className="ed-link dim" onClick={() => dispatch({ type: 'dropSuggestion', id: n.id })}>
                            Dismiss
                          </button>
                        </>
                      ) : (
                        <>
                          <span className="ed-meta">{busy ? 'Organizing…' : 'Not organized'}</span>
                          <button className="ed-link dim" onClick={() => dispatch({ type: 'removeNode', id: n.id })}>
                            Remove
                          </button>
                        </>
                      )}
                    </span>
                  </li>
                )
              })}
            </ul>
          ) : (
            <p className="ed-empty">Nothing parked. Drop a file or paste a note above.</p>
          )}
        </div>
      </section>

      <section className="ed-section">
        <div className="ed-label">
          <span className="ed-meta">02</span>
          <h2>In the graph</h2>
        </div>
        <div className="ed-body">
          <ul className="ed-rows">
            {placed.map((n) => (
              <li key={n.id}>
                <button className="ed-row" onClick={() => openPM(n.id)}>
                  <span className="t">
                    {n.title}
                    <span className="ed-meta sub">{n.origin.name}</span>
                  </span>
                  <span className="side">
                    <span className="ed-meta">{n.category ? CAT[n.category].label : ''}</span>
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

      <footer className="ed-foot ed-meta">
        <span>Sample data. The organizer is a local stand-in for an LLM; no model is called.</span>
        <span>Files stay in this browser tab</span>
      </footer>
    </div>
  )
}
