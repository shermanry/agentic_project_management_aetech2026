// Drag and drop is native to the whole app: drop files anywhere and they go through the converter
// service (Minh/converter), then wait in this drawer until someone places them in the graph.
import { useCallback, useEffect, useRef, useState } from 'react'
import { CAT } from '../data/sampleProject'
import { CONVERTER_PAGE, converterOnline, convertFiles, nodeKindFor } from '../features/converter'
import { suggestFor } from '../features/organize'
import { isParked, useGraph } from '../model/graph'

const TEXT_FILE = /\.(txt|md|csv|json|log|xml|html?)$/i

interface Props {
  open: boolean
  setOpen: (v: boolean) => void
  /** Show a node on the PM tab. */
  reveal: (id: string) => void
}

export default function Intake({ open, setOpen, reveal }: Props) {
  const { state, dispatch, byId } = useGraph()
  const [online, setOnline] = useState<boolean>()
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(0)
  const [error, setError] = useState<string>()
  const [note, setNote] = useState('')
  const picker = useRef<HTMLInputElement>(null)
  const depth = useRef(0)
  const parked = state.nodes.filter(isParked)

  useEffect(() => {
    void converterOnline().then(setOnline)
  }, [open])

  const addFiles = useCallback(
    async (list: FileList | File[]) => {
      const files = Array.from(list)
      if (!files.length) return
      setOpen(true)
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
              pkg: { id: c.packageId, kind: c.kind, chunks: c.chunkCount, warnings: c.warnings, thumbnail: c.thumbnail },
            })
        } else {
          // Converter not running: keep the demo usable. Plain-text files are read locally; others by name only.
          for (const f of files) {
            const readable = (f.type.startsWith('text/') || TEXT_FILE.test(f.name)) && f.size < 200_000
            const text = readable ? await f.text().catch(() => undefined) : undefined
            dispatch({ type: 'addNode', title: f.name, kind: 'file', text, offline: true })
          }
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'The converter could not read those files.')
      }
      setBusy(0)
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
      if (e.dataTransfer?.files.length) void addFiles(e.dataTransfer.files)
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
  }, [addFiles])

  return (
    <>
      {dragging && (
        <div className="drop-veil" aria-hidden>
          <span className="ed-meta">{online === false ? 'Converter offline · files are added by name' : 'Converter'}</span>
          <span className="big">Drop to add to the project</span>
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
              dispatch({ type: 'addNode', title: t.length > 60 ? t.slice(0, 57) + '…' : t, kind: 'note', text: t })
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
                const sg = suggestFor(n, state.nodes)
                return (
                  <li key={n.id} className="intake-row">
                    {n.pkg?.thumbnail ? <img src={n.pkg.thumbnail} alt="" /> : <span className="ph">{(n.pkg?.kind ?? n.kind).replace(/_.*/, '').slice(0, 5)}</span>}
                    <div className="grow">
                      <button className="t" onClick={() => reveal(n.id)} title="Show in the project tree">
                        {n.title}
                      </button>
                      <span className="ed-meta">
                        {n.origin.name}
                        {n.pkg && n.pkg.warnings > 0 ? ` · ${n.pkg.warnings} warning${n.pkg.warnings === 1 ? '' : 's'}` : ''}
                      </span>
                      <span className="sg" title={sg.reason}>
                        Suggested: <b>{CAT[sg.category].label}</b> {Math.round(sg.confidence * 100)}%
                        {sg.links[0] ? ` · ${sg.links[0].relation} ${byId(sg.links[0].target)?.title}` : ''}
                      </span>
                      <span className="acts">
                        <button
                          className="ed-link plain"
                          onClick={() => {
                            dispatch({ type: 'setSuggestions', suggestions: { [n.id]: sg } })
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
