// Drag and drop is native to the whole app: drop files or whole folders anywhere and they go through
// the converter service (Minh/converter), then wait in this drawer until someone places them in the graph.
//
// Files are sent one per request, two at a time, so a large drop keeps moving: each item joins
// "Waiting to be placed" as it finishes, a failed file does not hold up the rest, and Stop ends the queue.
// When the converter's AI reading is on, each file comes back with a title and a summary.
import { useCallback, useEffect, useRef, useState } from 'react'
import { CAT, COMPONENTS } from '../data/sampleProject'
import { CONVERTER_PAGE, agentAvailable, converterOnline, convertOne, nodeKindFor } from '../features/converter'
import { readDrop, type Dropped } from '../features/drop'
import { suggestFor } from '../features/organize'
import { isParked, useGraph, type DropHint, type Suggestion } from '../model/graph'
import type { GraphNode } from '../data/sampleProject'

const TEXT_FILE = /\.(txt|md|csv|json|log|xml|html?)$/i
/** Requests in flight at once. */
const PARALLEL = 2

interface Job extends Dropped {
  attach?: GraphNode['attach']
  /** The note in the Add page when the files were dropped: the AI's prompt. */
  prompt: string
}
interface Progress {
  total: number
  done: number
  failed: number
  /** Left in the queue when Stop was pressed. */
  unsent: number
  /** Junk and unreadable entries left out of a folder drop. */
  skipped: number
  running: boolean
  stopped: boolean
}
interface Failure {
  key: number
  name: string
  folder: string
  message: string
}
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

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
  const [ai, setAi] = useState(false)
  const [progress, setProgress] = useState<Progress>()
  const [failures, setFailures] = useState<Failure[]>([])
  const [scanning, setScanning] = useState(false)
  const [error, setError] = useState<string>()
  const [note, setNote] = useState('')
  const queue = useRef<Job[]>([])
  const running = useRef(false)
  const failKey = useRef(0)
  const noteRef = useRef(note)
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
    noteRef.current = note
  })

  /** What a drop target means in graph terms: the node to attach to. */
  const attachFor = useCallback((h?: DropHint): GraphNode['attach'] => {
    if (!h) return undefined
    if (h.kind === 'node') return { id: h.id, label: h.label }
    const first = COMPONENTS.find((c) => c.id === h.id)?.nodes[0]
    return first ? { id: first, label: h.label } : undefined
  }, [])

  useEffect(() => {
    void converterOnline().then(async (up) => {
      setOnline(up)
      setAi(up && (await agentAvailable()))
    })
  }, [open])

  /** One file through the converter (or by name when it is offline). Never throws: a failure becomes a row. */
  const convertJob = useCallback(
    async (job: Job, up: boolean, useAi: boolean) => {
      const { file, folder, attach } = job
      try {
        if (up) {
          const c = await convertOne(file, { ai: useAi, folder, prompt: job.prompt })
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
              warning: c.warning,
              folder: folder || undefined,
              ai: c.ai,
            },
            attach,
          })
        } else {
          // Converter not running: keep the demo usable. Plain-text files are read locally; others by name only.
          const readable = (file.type.startsWith('text/') || TEXT_FILE.test(file.name)) && file.size < 200_000
          const text = readable ? await file.text().catch(() => undefined) : undefined
          dispatch({ type: 'addNode', title: file.name, kind: 'file', text, offline: true, attach })
        }
        setProgress((p) => p && { ...p, done: p.done + 1 })
      } catch (e) {
        const message =
          e instanceof TypeError ? 'The converter did not answer.' : e instanceof Error ? e.message : 'The converter could not read this file.'
        setFailures((f) => [...f, { key: failKey.current++, name: file.name, folder, message }])
        setProgress((p) => p && { ...p, failed: p.failed + 1 })
      }
    },
    [dispatch],
  )

  /** Work through the queue, PARALLEL requests in flight, until it is empty or stopped. */
  const run = useCallback(
    async (quiet: boolean, attach?: GraphNode['attach']) => {
      running.current = true
      const up = await converterOnline()
      const useAi = up && (await agentAvailable())
      setOnline(up)
      setAi(useAi)
      const worker = async () => {
        for (let job = queue.current.shift(); job; job = queue.current.shift()) await convertJob(job, up, useAi)
      }
      // files dropped while a run is going join the same queue; loop in case they arrive as the workers finish
      while (queue.current.length) await Promise.all(Array.from({ length: PARALLEL }, worker))
      running.current = false
      setProgress((p) => p && { ...p, running: false })
      if (quiet) {
        setNotice(attach ? `Added next to ${attach.label}. Open + Add to place it.` : 'Added. Open + Add to place it.')
        setTimeout(() => setNotice(undefined), 4200)
      }
    },
    [convertJob],
  )

  const addFiles = useCallback(
    (list: Dropped[], attach?: GraphNode['attach'], quiet = false, skipped = 0) => {
      if (!list.length) return
      // In a 3D view the scene stays visible: the new item appears where it was dropped.
      if (!quiet) setOpen(true)
      setError(undefined)
      const prompt = noteRef.current.trim()
      queue.current.push(...list.map((d) => ({ ...d, attach, prompt })))
      if (running.current) {
        setProgress((p) => p && { ...p, total: p.total + list.length, skipped: p.skipped + skipped, stopped: false })
        return
      }
      setFailures([])
      setProgress({ total: list.length, done: 0, failed: 0, unsent: 0, skipped, running: true, stopped: false })
      void run(quiet, attach)
    },
    [run, setOpen],
  )

  /** Stop: nothing more is sent. The requests already in flight finish and their items are kept. */
  const stop = useCallback(() => {
    const unsent = queue.current.length
    queue.current = []
    setProgress((p) => p && { ...p, unsent: p.unsent + unsent, stopped: true })
  }, [])

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
      const quiet = !!sceneRef.current
      dispatch({ type: 'setDropHint', hint: undefined })
      if (!e.dataTransfer) return
      // readDrop takes the dropped entries synchronously (the browser clears them once this handler returns),
      // then reads any folders. A plain file drop resolves at once.
      const contents = readDrop(e.dataTransfer)
      setScanning(true)
      void contents
        .then((c) => {
          if (c.files.length) addFiles(c.files, attach, quiet, c.skipped)
          else if (c.hadFolder) {
            setError('That folder has no files to add.')
            if (!quiet) setOpen(true)
          }
        })
        .catch(() => setError('That drop could not be read.'))
        .finally(() => setScanning(false))
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
  }, [addFiles, attachFor, dispatch, setOpen])

  const handled = progress ? progress.done + progress.failed : 0
  const progressLabel = !progress
    ? ''
    : progress.running
      ? progress.stopped
        ? 'Stopping'
        : online === false
          ? 'Adding by name'
          : ai
            ? 'Reading with AI'
            : 'Converting'
      : progress.stopped
        ? 'Stopped'
        : 'Done'

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
      {progress?.running && !open && !dragging && (
        <div className="drop-bar on" role="status">
          {progressLabel} · {handled} / {progress.total}
        </div>
      )}
      {notice && !dragging && !progress?.running && (
        <div className="drop-bar on" role="status">
          {notice}
        </div>
      )}

      {open && <div className="intake-scrim" onClick={() => setOpen(false)} />}
      <aside className={`intake ${open ? 'open' : ''}`} aria-label="Add to project" aria-hidden={!open}>
        <header>
          <div>
            <span className="ed-meta">Add to project</span>
            <h2>Drop files or folders anywhere</h2>
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
              {ai ? 'Converter connected · AI reading on' : 'Converter connected · AI reading off, files are converted without a summary'}
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
              if (e.target.files) addFiles(Array.from(e.target.files, (file) => ({ file, folder: '' })))
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

        {scanning && !progress?.running && (
          <p className="intake-busy" aria-live="polite">
            Reading what was dropped…
          </p>
        )}
        {progress && (
          <div className="intake-progress" aria-live="polite">
            <span className="line">
              <b>{progressLabel}</b> · {handled} / {progress.total}
              {progress.failed > 0 && ` · ${progress.failed} failed`}
              {progress.unsent > 0 && ` · ${progress.unsent} not sent`}
              {progress.skipped > 0 && ` · ${plural(progress.skipped, 'junk file')} skipped`}
            </span>
            {progress.running && !progress.stopped && progress.total > 1 && (
              <button className="ed-link plain" onClick={stop}>
                Stop
              </button>
            )}
            <span className="bar" aria-hidden>
              <i style={{ width: `${progress.total ? Math.round((handled / progress.total) * 100) : 0}%` }} />
            </span>
          </div>
        )}
        {error && <p className="intake-error">{error}</p>}

        <div className="intake-list">
          <span className="ed-meta">Waiting to be placed · {parked.length}</span>
          {failures.length > 0 && (
            <ul className="ed-rows intake-fails">
              {failures.map((f) => (
                <li key={f.key} className="intake-row fail">
                  <span className="ph">!</span>
                  <div className="grow">
                    <span className="t">{f.name}</span>
                    {f.folder && <span className="ed-meta">{f.folder}</span>}
                    <span className="sg warn">Not added: {f.message}</span>
                  </div>
                </li>
              ))}
              <li className="intake-fails-foot">
                <button className="ed-link dim" onClick={() => setFailures([])}>
                  Clear {plural(failures.length, 'error')}
                </button>
              </li>
            </ul>
          )}
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
                        {n.pkg?.folder ? ` · ${n.pkg.folder}` : ''}
                        {n.pkg && n.pkg.warnings > 0 && !n.pkg.warning ? ` · ${plural(n.pkg.warnings, 'warning')}` : ''}
                      </span>
                      {n.pkg?.ai && n.summary && <span className="sum">{n.summary}</span>}
                      {n.pkg?.warning && <span className="sg warn">Converted without an AI summary: {n.pkg.warning}</span>}
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

        <footer className="ed-meta">Titles and summaries come from the converter. Where things go is suggested by local sample logic, not a live AI. You decide what is placed.</footer>
      </aside>
    </>
  )
}
