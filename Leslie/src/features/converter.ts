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

export async function convertFiles(files: File[]): Promise<Converted[]> {
  const form = new FormData()
  files.forEach((f) => form.append('files', f, f.name))
  const res = await fetch(`${BASE}/api/convert`, { method: 'POST', body: form })
  if (!res.ok) throw new Error(`Converter returned ${res.status}`)
  const rows = (await res.json()) as Manifest[]
  return rows.map((m) => ({
    packageId: m.id,
    kind: m.kind,
    title: m.title || m.source?.filename || m.id,
    description: m.description ?? '',
    filename: m.source?.filename ?? m.title ?? m.id,
    thumbnail: m.thumbnail ? `${BASE}/files/${m.id}/${m.thumbnail}` : undefined,
    chunkCount: m.chunk_count ?? 0,
    warnings: m.warnings?.length ?? 0,
    tags: m.tags?.values ?? [],
  }))
}

/** Converter package kind -> the node type shown in YBuild. */
export function nodeKindFor(kind: string): NodeKind {
  if (/rhino|model|bim/.test(kind)) return 'model'
  if (/email|text|note|web|markup/.test(kind)) return 'note'
  if (/document|pdf|presentation|spreadsheet|data/.test(kind)) return 'document'
  return 'file'
}
