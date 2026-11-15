// Drag and drop is native to the whole app: drop files anywhere and they go through the converter
// service (Minh/converter), then wait in this drawer until someone places them in the graph.
import { useCallback, useEffect, useRef, useState } from 'react'
import { CAT, COMPONENTS } from '../data/sampleProject'
import { CONVERTER_PAGE, converterOnline, convertFiles, nodeKindFor } from '../features/converter'
import { suggestFor } from '../features/organize'
import { isParked, useGraph, type DropHint, type Suggestion } from '../model/graph'
import type { GraphNode } from '../data/sampleProject'

const TEXT_FILE = /\.(txt|md|csv|json|log|xml|html?)$/i

interface Props {
  open: boolean
  setOpen: (v: boolean) => void
  /** Show a node on the PM tab. */
  reveal: (id: string) => void
  /** The current tab is a 3D view: dropping attaches to what is under the cursor and does not cover the scene. */
  scene3d?: 'network' | 'building'
}

export default function Intake({ open, setOpen, reveal, scene3d }: Props) {
  const { state, dispatch, byId } = useGraph()
  const [online, setOnline] = useState<boolean>()
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(0)
  const [error, setError] = useState<string>()
  const [note, setNote] = useState('')
  const picker = useRef<HTMLInputElement>(null)
  const depth = useRef(0)
  const parked = state.nodes.filter(isParked)
  const [notice, setNotice] = useState<string>()
  const hint = state.dropHint
  const hintRef = useRef<DropHint | undefined>(hint)
  const sceneRef = useRef(scene3d)
  useEffect(() => {
    hintRef.current = hint
    sceneRef.current = scene3d
  })

  /** What a drop target means in graph terms: the node to attach to. */
  const attachFor = useCallback((h?: DropHint): GraphNode['attach'] => {
    if (!h) return undefined
    if (h.kind === 'node') return { id: h.id, label: h.label }
    const first = COMPONENTS.find((c) => c.id === h.id)?.nodes[0]
    return first ? { id: first, label: h.label } : undefined
  }, [])

  useEffect(() => {
    void converterOnline().then(setOnline)
  }, [open])

  const addFiles = useCallback(
    async (list: FileList | File[], attach?: GraphNode['attach'], quiet = false) => {
      const files = Array.from(list)
      if (!files.length) return
      // In a 3D view the scene stays visible: the new item appears where it was dropped.
      if (!quiet) setOpen(true)
      else setNotice(`Adding ${files.length} file${files.length === 1 ? '' : 's'}…`)
      setError(undefined)
      setBusy(files.length)
      const up = await converterOnline()
      setOnline(up)
      try {
        if (up) {
          const out = await convertFiles(files)
          for (const c of out)
            dispatch({
              type: 'addNode',
              title: c.title,
              kind: nodeKindFor(c.kind),
              text: c.description || c.tags.join(', '),
              pkg: {
                id: c.packageId,
                kind: c.kind,
                chunks: c.chunkCount,
                warnings: c.warnings,
                thumbnail: c.thumbnail,
              },
              attach,
            })
        } else {
          // Converter not running: keep the demo usable. Plain-text files are read locally; others by name only.
          for (const f of files) {
            const readable = (f.type.startsWith('text/') || TEXT_FILE.test(f.name)) && f.size < 200_000
            const text = readable ? await f.text().catch(() => undefined) : undefined
            dispatch({
              type: 'addNode',
              title: f.name,
              kind: 'file',
              text,
              offline: true,
              attach,
            })
          }
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'The converter could not read those files.')
      }
      setBusy(0)
      if (quiet) {
        setNotice(attach ? `Added next to ${attach.label}. Open + Add to place it.` : 'Added. Open + Add to place it.')
        setTimeout(() => setNotice(undefined), 4200)
      }
    },
    [dispatch, setOpen],
  )

  // Whole-window drop target
  useEffect(() => {
    const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes('Files')
    const enter = (e: DragEvent) => {
      if (!hasFiles(e)) return
      depth.current++
      setDragging(true)
    }
    const over = (e: DragEvent) => {
      if (hasFiles(e)) e.preventDefault()
    }
    const leave = (e: DragEvent) => {
      if (!hasFiles(e)) return
      depth.current = Math.max(0, depth.current - 1)
      if (!depth.current) setDragging(false)
    }
    const drop = (e: DragEvent) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      depth.current = 0
      setDragging(false)
      const attach = attachFor(hintRef.current)
      dispatch({ type: 'setDropHint', hint: undefined })
      if (e.dataTransfer?.files.length) void addFiles(e.dataTransfer.files, attach, !!sceneRef.current)
    }
    window.addEventListener('dragenter', enter)
    window.addEventListener('dragover', over)
    window.addEventListener('dragleave', leave)
    window.addEventListener('drop', drop)
    return () => {
      window.removeEventListener('dragenter', enter)
      window.removeEventListener('dragover', over)
      window.removeEventListener('dragleave', leave)
      window.removeEventListener('drop', drop)
    }
  }, [addFiles, attachFor, dispatch])

  return (
    <>
      {dragging && !scene3d && (
        <div className="drop-veil" aria-hidden>
          <span className="ed-meta">{online === false ? 'Converter offline · files are added by name' : 'Converter'}</span>
          <span className="big">Drop to add to the project</span>
        </div>
      )}
      {dragging && scene3d && (
        <div className={`drop-bar ${hint ? 'on' : ''}`} aria-hidden>
          {hint ? (
            <>
              Drop to attach to <b>{hint.label}</b>
            </>
          ) : scene3d === 'network' ? (
            'Drop on a node to attach it there, or anywhere to add it'
          ) : (
            'Drop on a part of the building to attach it there'
          )}
        </div>
      )}
      {notice && !dragging && (
        <div className="drop-bar on" role="status">
          {notice}
        </div>
      )}

      {open && <div className="intake-scrim" onClick={() => setOpen(false)} />}
      <aside className={`intake ${open ? 'open' : ''}`} aria-label="Add to project" aria-hidden={!open}>
        <header>
          <div>
            <span className="ed-meta">Add to project</span>
            <h2>Drop files anywhere</h2>
          </div>
          <button className="icon-btn" onClick={() => setOpen(false)} aria-label="Close">
            ×
          </button>
        </header>

        <div className={`intake-status ${online ? 'on' : ''}`}>
          <i />
          {online === undefined ? (
            'Checking the converter…'
          ) : online ? (
            <>
              Converter connected
              <a className="ed-link" href={CONVERTER_PAGE} target="_blank" rel="noreferrer">
                Open converter
              </a>
            </>
          ) : (
            'Converter offline. Files are added by name only until it is running.'
          )}
        </div>

        <div className="intake-drop">
          <button className="ed-cta" onClick={() => picker.current?.click()}>
            Choose files
          </button>
          <input
            ref={picker}
            id="intake-files"
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
              dispatch({
                type: 'addNode',
                title: t.length > 60 ? t.slice(0, 57) + '…' : t,
                kind: 'note',
                text: t,
              })
              setNote('')
            }}
          >
            <input id="intake-note" aria-label="Paste a note" placeholder="or paste a note" value={note} onChange={(e) => setNote(e.target.value)} />
            <button className="ed-link plain" disabled={!note.trim()}>
              Add
            </button>
          </form>
        </div>

        {busy > 0 && (
          <p className="intake-busy" aria-live="polite">
            Converting {busy} file{busy === 1 ? '' : 's'}…
          </p>
        )}
        {error && <p className="intake-error">{error}</p>}

        <div className="intake-list">
          <span className="ed-meta">Waiting to be placed · {parked.length}</span>
          {parked.length ? (
            <ul className="ed-rows">
              {parked.map((n) => {
                const base = suggestFor(n, state.nodes)
                const target = n.attach ? byId(n.attach.id) : undefined
                // Dropped onto something in 3D: that is the strongest signal of where it belongs.
                const sg: Suggestion = target
                  ? {
                      category: target.category ?? base.category,
                      confidence: 0.9,
                      links: [{ target: target.id, relation: 'relates to' }],
                      reason: `Dropped on ${n.attach!.label}`,
                    }
                  : base
                return (
                  <li key={n.id} className="intake-row">
                    {n.pkg?.thumbnail ? (
                      <img src={n.pkg.thumbnail} alt="" />
                    ) : (
                      <span className="ph">{(n.pkg?.kind ?? n.kind).replace(/_.*/, '').slice(0, 5)}</span>
                    )}
                    <div className="grow">
                      <button className="t" onClick={() => reveal(n.id)} title="Show in the project tree">
                        {n.title}
                      </button>
                      <span className="ed-meta">
                        {n.origin.name}
                        {n.pkg && n.pkg.warnings > 0 ? ` · ${n.pkg.warnings} warning${n.pkg.warnings === 1 ? '' : 's'}` : ''}
                      </span>
                      <span className="sg" title={sg.reason}>
                        {target ? `Dropped on ${n.attach!.label}: ` : 'Suggested: '}
                        <b>{CAT[sg.category].label}</b> {Math.round(sg.confidence * 100)}%
                        {sg.links[0] ? ` · ${sg.links[0].relation} ${byId(sg.links[0].target)?.title}` : ''}
                      </span>
                      <span className="acts">
                        <button
                          className="ed-link plain"
                          onClick={() => {
                            dispatch({
                              type: 'setSuggestions',
                              suggestions: { [n.id]: sg },
                            })
                            dispatch({ type: 'applySuggestion', id: n.id })
                          }}
                        >
                          Accept
                        </button>
                        <button className="ed-link dim" onClick={() => dispatch({ type: 'removeNode', id: n.id })}>
                          Remove
                        </button>
                      </span>
                    </div>
                  </li>
                )
              })}
            </ul>
          ) : (
            <p className="ed-empty">Nothing waiting. Everything is placed in the project.</p>
          )}
        </div>

        <footer className="ed-meta">Suggestions are local sample logic, not a live AI. You decide what is placed.</footer>
      </aside>
    </>
  )
}
