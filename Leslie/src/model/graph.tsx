// One in-memory graph shared by every view. Views only render it differently.
import { createContext, useContext, useMemo, useReducer, type ReactNode } from 'react'
import { ask, type AskResult } from '../features/ask'
import { CANDIDATES, CAT, EDGES, INITIAL_LOG, NODES, UNCLASSIFIED_COLOR, type Candidate, type CategoryId, type GraphEdge, type GraphNode } from '../data/sampleProject'

export type Filter = CategoryId | 'all' | 'unclassified'

/** A proposed home for a parked item. Produced by the organizer, applied only when a person accepts it. */
export interface Suggestion {
  category: CategoryId
  confidence: number // 0-1
  links: { target: string; relation: string }[]
  reason: string
}

/** Answers from the first-run questionnaire on the Overview. */
export interface Onboarding {
  role: 'client' | 'pm' | 'pilot' | 'explore'
  goal: 'building' | 'blocking' | 'find' | 'add'
  level: 'new' | 'some' | 'expert'
}

const OB_KEY = 'ybuild.onboarding'
function loadOnboarding(): Onboarding | undefined {
  try {
    const raw = localStorage.getItem(OB_KEY)
    return raw ? (JSON.parse(raw) as Onboarding) : undefined
  } catch {
    return undefined
  }
}
function saveOnboarding(o?: Onboarding) {
  try {
    if (o) localStorage.setItem(OB_KEY, JSON.stringify(o))
    else localStorage.removeItem(OB_KEY)
  } catch {
    /* storage unavailable: the questionnaire simply shows again next time */
  }
}

export interface LogEntry {
  at: string
  who: string
  text: string
}

export interface GraphState {
  nodes: GraphNode[]
  edges: GraphEdge[]
  candidates: Candidate[]
  log: LogEntry[]
  selectedId?: string
  /** Search text and category filter, shared by the PM canvas and the Pilot network. */
  query: string
  filter: Filter
  /** Organizer output per parked node id. */
  suggestions: Record<string, Suggestion>
  onboarding?: Onboarding
}

type Action =
  | { type: 'select'; id?: string }
  | { type: 'setQuery'; query: string }
  | { type: 'setOnboarding'; onboarding?: Onboarding }
  | { type: 'setFilter'; filter: Filter }
  | { type: 'move'; id: string; x: number; y: number }
  | { type: 'resetLayout' }
  | { type: 'accept'; id: string }
  | { type: 'dismiss'; id: string }
  | { type: 'addNode'; title: string; kind: 'note' | 'file'; text?: string }
  | { type: 'setSuggestions'; suggestions: Record<string, Suggestion> }
  | { type: 'applySuggestion'; id: string }
  | { type: 'dropSuggestion'; id: string }
  | { type: 'removeNode'; id: string }

const stamp = () => new Date().toISOString().slice(0, 16).replace('T', ' ')

function reducer(s: GraphState, a: Action): GraphState {
  switch (a.type) {
    case 'select':
      return { ...s, selectedId: a.id }
    case 'setQuery':
      return { ...s, query: a.query }
    case 'setOnboarding':
      saveOnboarding(a.onboarding)
      return { ...s, onboarding: a.onboarding }
    case 'setFilter':
      return { ...s, filter: a.filter }
    case 'move':
      // Display position only. Never creates or changes a relationship.
      return { ...s, nodes: s.nodes.map((n) => (n.id === a.id ? { ...n, canvas: { x: a.x, y: a.y } } : n)) }
    case 'resetLayout': {
      const home = Object.fromEntries(NODES.map((n) => [n.id, n.canvas]))
      let inbox = 0
      return {
        ...s,
        nodes: s.nodes.map((n) => ({ ...n, canvas: home[n.id] ?? { x: 1170, y: 340 + 135 * inbox++ } })),
      }
    }
    case 'accept': {
      const c = s.candidates.find((x) => x.id === a.id)
      if (!c || c.state !== 'pending') return s
      const edge: GraphEdge = { id: `${c.source}-${c.relation}-${c.target}`, source: c.source, target: c.target, relation: c.relation, status: 'accepted', provenance: 'ai-suggestion' }
      return {
        ...s,
        candidates: s.candidates.map((x) => (x.id === a.id ? { ...x, state: 'accepted' } : x)),
        edges: [...s.edges, edge],
        log: [{ at: stamp(), who: 'You (local)', text: `Accepted: ${title(s, c.source)} ${c.relation} ${title(s, c.target)}` }, ...s.log],
      }
    }
    case 'dismiss': {
      const c = s.candidates.find((x) => x.id === a.id)
      if (!c || c.state !== 'pending') return s
      return {
        ...s,
        candidates: s.candidates.map((x) => (x.id === a.id ? { ...x, state: 'dismissed' } : x)),
        log: [{ at: stamp(), who: 'You (local)', text: `Dismissed suggestion: ${title(s, c.source)} ${c.relation} ${title(s, c.target)}` }, ...s.log],
      }
    }
    case 'addNode': {
      const inInbox = s.nodes.filter((n) => n.category === null).length
      const id = `local-${Date.now().toString(36)}`
      const node: GraphNode = {
        id,
        title: a.title,
        kind: a.kind,
        category: null,
        status: 'Unclassified',
        summary: a.text?.trim() ? a.text.trim().slice(0, 220) : a.kind === 'file' ? 'File added locally. Its contents were not read.' : 'Note added locally.',
        why: 'Parked: organize it into the graph, or remove it.',
        origin: { kind: 'local', name: a.kind === 'file' ? 'Dropped file (name only)' : 'Typed note' },
        owner: 'You (local)',
        updatedAt: new Date().toISOString().slice(0, 10),
        verification: 'Unreviewed',
        importance: 'low',
        openQuestion: 'Parked. Organize it into the graph, or remove it.',
        canvas: { x: 1170, y: 340 + 135 * inInbox },
        pos3d: [-200 + Math.random() * 60, -150 + Math.random() * 40, 150],
      }
      return {
        ...s,
        nodes: [...s.nodes, node],
        selectedId: id,
        log: [{ at: stamp(), who: 'You (local)', text: `Added ${a.kind}: ${a.title}` }, ...s.log],
      }
    }
    case 'setSuggestions':
      return { ...s, suggestions: { ...s.suggestions, ...a.suggestions } }
    case 'dropSuggestion': {
      const rest = { ...s.suggestions }
      delete rest[a.id]
      return { ...s, suggestions: rest }
    }
    case 'applySuggestion': {
      const sg = s.suggestions[a.id]
      const node = s.nodes.find((n) => n.id === a.id)
      if (!sg || !node) return s
      const fresh = sg.links.filter((l) => !s.edges.some((e) => e.source === a.id && e.target === l.target))
      const added: GraphEdge[] = fresh.map((l) => ({ id: `${a.id}-${l.relation}-${l.target}`, source: a.id, target: l.target, relation: l.relation, status: 'accepted', provenance: 'ai-suggestion' }))
      const rest = { ...s.suggestions }
      delete rest[a.id]
      return {
        ...s,
        nodes: s.nodes.map((n) => (n.id === a.id ? { ...n, category: sg.category, status: 'Review', verification: 'Organized by assistant, accepted by you', openQuestion: undefined } : n)),
        edges: [...s.edges, ...added],
        candidates: s.candidates.map((c) => (c.state === 'pending' && c.source === a.id && sg.links.some((l) => l.target === c.target) ? { ...c, state: 'accepted' } : c)),
        suggestions: rest,
        log: [{ at: stamp(), who: 'You (local)', text: `Organized ${node.title} into ${CAT[sg.category].label}` }, ...s.log],
      }
    }
    case 'removeNode': {
      const node = s.nodes.find((n) => n.id === a.id)
      if (!node) return s
      return {
        ...s,
        nodes: s.nodes.filter((n) => n.id !== a.id),
        edges: s.edges.filter((e) => e.source !== a.id && e.target !== a.id),
        candidates: s.candidates.filter((c) => c.source !== a.id && c.target !== a.id),
        selectedId: s.selectedId === a.id ? undefined : s.selectedId,
        log: [{ at: stamp(), who: 'You (local)', text: `Removed ${node.title}` }, ...s.log],
      }
    }
  }
}

const title = (s: GraphState, id: string) => s.nodes.find((n) => n.id === id)?.title ?? id

const Ctx = createContext<{ state: GraphState; dispatch: React.Dispatch<Action>; guide?: AskResult } | null>(null)

export function GraphProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, { nodes: NODES, edges: EDGES, candidates: CANDIDATES, log: INITIAL_LOG, selectedId: 'flight', query: '', filter: 'all', suggestions: {} } as GraphState, (s: GraphState) => ({ ...s, onboarding: loadOnboarding() }))
  // The question in the ask bar, interpreted once and shared by every view.
  const guide = useMemo(() => (state.query.trim() ? ask(state.query, state.nodes, state.edges) : undefined), [state.query, state.nodes, state.edges])
  return <Ctx.Provider value={{ state, dispatch, guide }}>{children}</Ctx.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useGraph() {
  const c = useContext(Ctx)
  if (!c) throw new Error('useGraph outside GraphProvider')
  const { state, dispatch, guide } = c
  const byId = (id?: string) => state.nodes.find((n) => n.id === id)
  const edgesOf = (id: string) => state.edges.filter((e) => e.source === id || e.target === id)
  const degree = (id: string) => edgesOf(id).length
  const pendingFor = (id: string) => state.candidates.filter((x) => x.state === 'pending' && (x.source === id || x.target === id))
  const neighbors = (id: string) => new Set(edgesOf(id).flatMap((e) => [e.source, e.target]))
  /** Passes the category filter and, when a question is asked, is one of the guide's answers. */
  const matches = (n: GraphNode) => inCategory(n, state.filter) && (!guide || guide.ids.includes(n.id))
  return { state, dispatch, byId, edgesOf, degree, pendingFor, neighbors, matches, guide }
}

// eslint-disable-next-line react-refresh/only-export-components
export function inCategory(n: GraphNode, filter: Filter) {
  return filter === 'all' || (filter === 'unclassified' ? n.category === null || n.status === 'Unclassified' : n.category === filter)
}

/** Parked = imported but not yet placed in the graph. */
// eslint-disable-next-line react-refresh/only-export-components
export const isParked = (n: GraphNode) => n.category === null

// eslint-disable-next-line react-refresh/only-export-components
export const colorOf = (n: GraphNode) => (n.category ? CAT[n.category].color : UNCLASSIFIED_COLOR)

/** Status badge tone, deliberately separate from category colour. */
// eslint-disable-next-line react-refresh/only-export-components
export function toneOf(status: string): 'ok' | 'warn' | 'info' | 'muted' | 'ai' {
  const s = status.toLowerCase()
  if (['verified', 'reviewed', 'source', 'linked'].includes(s)) return 'ok'
  if (['review', 'monitor', 'pending'].includes(s)) return 'warn'
  if (s === 'suggested' || s === 'ai-generated') return 'ai'
  if (s === 'unclassified') return 'muted'
  return 'info'
}

// eslint-disable-next-line react-refresh/only-export-components
export const needsAttention = (n: GraphNode) => ['warn', 'muted', 'ai'].includes(toneOf(n.status)) || n.status === 'Proposed'
