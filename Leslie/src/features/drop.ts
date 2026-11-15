// Reading what was dropped: plain files, or whole folders with everything inside them.
//
// A dropped folder shows up in `dataTransfer.files` only as an unreadable placeholder, so folders are
// read through the entry API instead. The entries must be taken synchronously, inside the drop event:
// the browser empties the item list as soon as the handler returns or awaits.

export interface Dropped {
  file: File
  /** The file's path inside the dropped folder, e.g. "videos/stills". Empty for a loose file. */
  folder: string
}

const JUNK_NAMES = new Set(['thumbs.db', 'desktop.ini'])
const JUNK_EXT = /\.(3dmbak|bak|tmp|part)$/i

/** Files nobody means to add: hidden files, Office lock files, system and backup files. */
export function isJunk(name: string): boolean {
  return name.startsWith('.') || name.startsWith('~$') || JUNK_NAMES.has(name.toLowerCase()) || JUNK_EXT.test(name)
}

const fileOf = (entry: FileSystemFileEntry) => new Promise<File>((resolve, reject) => entry.file(resolve, reject))

/** Everything in one directory. readEntries returns a batch at a time, so it is called until a batch is empty. */
async function children(dir: FileSystemDirectoryEntry): Promise<FileSystemEntry[]> {
  const reader = dir.createReader()
  const all: FileSystemEntry[] = []
  for (;;) {
    const batch = await new Promise<FileSystemEntry[]>((resolve, reject) => reader.readEntries(resolve, reject))
    if (!batch.length) return all
    all.push(...batch)
  }
}

async function walk(entry: FileSystemEntry, folder: string, out: Dropped[], skipped: { n: number }): Promise<void> {
  if (isJunk(entry.name)) {
    skipped.n++
    return
  }
  if (entry.isFile) {
    try {
      out.push({ file: await fileOf(entry as FileSystemFileEntry), folder })
    } catch {
      skipped.n++ // unreadable (permissions, or removed while reading)
    }
    return
  }
  if (entry.isDirectory) {
    const inside = folder ? `${folder}/${entry.name}` : entry.name
    let kids: FileSystemEntry[] = []
    try {
      kids = await children(entry as FileSystemDirectoryEntry)
    } catch {
      skipped.n++
    }
    kids.sort((a, b) => a.name.localeCompare(b.name))
    for (const kid of kids) await walk(kid, inside, out, skipped)
  }
}

export interface DropContents {
  files: Dropped[]
  /** Junk and unreadable entries left out of a folder drop. */
  skipped: number
  /** True when at least one folder was dropped. */
  hadFolder: boolean
}

/**
 * What a drop contains. Call it first thing in the drop handler: the entries are taken before this
 * function's first await. Without a folder in the drop, this is just `dataTransfer.files`, as before.
 */
export function readDrop(dt: DataTransfer): Promise<DropContents> {
  const loose = Array.from(dt.files)
  const entries: FileSystemEntry[] = []
  for (const item of Array.from(dt.items ?? [])) {
    if (item.kind !== 'file') continue
    const entry = typeof item.webkitGetAsEntry === 'function' ? item.webkitGetAsEntry() : null
    if (entry) entries.push(entry)
  }
  if (!entries.some((e) => e.isDirectory)) {
    return Promise.resolve({ files: loose.map((file) => ({ file, folder: '' })), skipped: 0, hadFolder: false })
  }
  return (async () => {
    const files: Dropped[] = []
    const skipped = { n: 0 }
    for (const entry of entries) await walk(entry, '', files, skipped)
    return { files, skipped: skipped.n, hadFolder: true }
  })()
}
