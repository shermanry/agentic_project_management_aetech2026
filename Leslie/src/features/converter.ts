// Client for the converter service (Minh/converter in this repo): any dropped file becomes an
// embedding-ready package. YBuild only reads the result; the converter converts, it does not judge.
//
// In development Vite proxies /api and /files to the converter on 127.0.0.1:8765 (vite.config.ts).
// Set VITE_CONVERTER_URL to point somewhere else. If the service is not running, files are still
// added to the project by name so the demo keeps working, and the UI says so.
import type { NodeKind } from '../data/sampleProject'

const BASE = ((import.meta.env.VITE_CONVERTER_URL as string | undefined) ?? '').replace(/\/$/, '')
/** Where the converter's own page lives, for the "Open converter" link. */
export const CONVERTER_PAGE = BASE || 'http://127.0.0.1:8765'

export interface Converted {
  packageId: string
  kind: string
  title: string
  description: string
  filename: string
  thumbnail?: string
  chunkCount: number
  warnings: number
  tags: string[]
  /** Set when the file was converted but the AI reading did not finish: shown as a warning on the row. */
  warning?: string
  /** True when the title and summary come from the converter's AI reading (/api/ask). */
  ai?: boolean
}

export async function converterOnline(): Promise<boolean> {
  try {
    const ctl = new AbortController()
    const t = setTimeout(() => ctl.abort(), 1500)
    const res = await fetch(`${BASE}/api/formats`, { signal: ctl.signal })
    clearTimeout(t)
    return res.ok && (res.headers.get('content-type') ?? '').includes('json')
  } catch {
    return false
  }
}

/** Whether the converter's AI reading is switched on (it needs a key on the converter's side). */
export async function agentAvailable(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE}/api/agent`)
    if (!res.ok) return false
    return ((await res.json()) as { available?: boolean }).available === true
  } catch {
    return false
  }
}

interface Manifest {
  id: string
  kind: string
  title?: string
  description?: string
  source?: { filename?: string }
  thumbnail?: string | null
  chunk_count?: number
  warnings?: unknown[]
  tags?: { values?: string[] }
}

/** One file's result from POST /api/ask. `agent` is null when the AI reading failed; the file is still converted. */
interface AskItem {
  id: string
  filename: string
  kind: string
  thumbnail?: string | null
  agent?: { title?: string; summary?: string } | null
  error?: string | null
}
interface AskResponse {
  items?: AskItem[]
  errors?: string[]
  cost_usd?: number
}

const thumb = (id: string, name?: string | null) => (name ? `${BASE}/files/${id}/${name}` : undefined)

function fromManifest(m: Manifest): Converted {
  return {
    packageId: m.id,
    kind: m.kind,
    title: m.title || m.source?.filename || m.id,
    description: m.description ?? '',
    filename: m.source?.filename ?? m.title ?? m.id,
    thumbnail: thumb(m.id, m.thumbnail),
    chunkCount: m.chunk_count ?? 0,
    warnings: m.warnings?.length ?? 0,
    tags: m.tags?.values ?? [],
  }
}

/** The server's own explanation when a request fails (FastAPI puts it in `detail`). */
async function failure(res: Response): Promise<Error> {
  let detail = ''
  try {
    const body = (await res.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') detail = body.detail
  } catch {
    /* not JSON */
  }
  return new Error(detail || `Converter returned ${res.status}`)
}

export interface ConvertOptions {
  /** Use the AI reading (/api/ask). When false, local extraction only (/api/convert). */
  ai: boolean
  /** The file's path inside a dropped folder, e.g. "videos/stills". */
  folder?: string
  /** The user's note from the Add page, passed to the AI as its prompt. */
  prompt?: string
}

/** Convert one file. One file per request keeps large drops moving and lets each row arrive as it finishes. */
export async function convertOne(file: File, opts: ConvertOptions): Promise<Converted> {
  const form = new FormData()
  form.append('files', file, file.name)
  if (opts.folder) form.append('folder', opts.folder)

  if (!opts.ai) {
    const res = await fetch(`${BASE}/api/convert`, { method: 'POST', body: form })
    if (!res.ok) throw await failure(res)
    const rows = (await res.json()) as Manifest[]
    if (!rows[0]) throw new Error('The converter returned nothing for this file.')
    return fromManifest(rows[0])
  }

  if (opts.prompt) form.append('prompt', opts.prompt)
  const res = await fetch(`${BASE}/api/ask`, { method: 'POST', body: form })
  if (!res.ok) throw await failure(res)
  const out = (await res.json()) as AskResponse
  const item = out.items?.[0]
  if (!item) throw new Error(out.errors?.[0] || 'The converter returned nothing for this file.')
  const warning = item.agent ? undefined : item.error || 'The AI reading did not finish. The file was converted without it.'
  return {
    packageId: item.id,
    kind: item.kind,
    title: item.agent?.title ?? item.filename,
    description: item.agent?.summary ?? '',
    filename: item.filename,
    thumbnail: thumb(item.id, item.thumbnail),
    chunkCount: 0,
    warnings: warning ? 1 : 0,
    tags: [],
    warning,
    ai: !!item.agent,
  }
}

/** Converter package kind -> the node type shown in YBuild. */
export function nodeKindFor(kind: string): NodeKind {
  if (/rhino|model|bim/.test(kind)) return 'model'
  if (/email|text|note|web|markup/.test(kind)) return 'note'
  if (/document|pdf|presentation|spreadsheet|data/.test(kind)) return 'document'
  return 'file'
}
