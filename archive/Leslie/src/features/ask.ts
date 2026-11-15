// "Ask" guide: turns a plain-language question into (a) a short answer and (b) the nodes to look at.
//
// This is local logic (word matching + a few intents), standing in for an LLM so the prototype
// runs with no API key. To use a real model, replace `ask()` with a call that receives the
// question plus the graph and returns the same `AskResult` shape. The UI does not change.
import { CAT, type GraphEdge, type GraphNode } from '../data/sampleProject'

export interface AskResult {
  /** Node ids, most relevant first. Empty when nothing matched. */
  ids: string[]
  /** One or two plain sentences for a newcomer. */
  answer: string
  /** What the guide understood the question to be about. */
  intent: string
}

export const EXAMPLES = [
  "What's blocking the flight?",
  'Are we allowed to fly here?',
  'Who looks after safety?',
  'What does the client get?',
  'Is the weather OK this week?',
  'What still needs checking?',
]

const STOP = new Set(
  'a an and are as at be by can could do does for from get has have how i if in is it its me my of on or our should that the their there this to up us was we what when where which who why will with would you your about any some all so than then them they these those not no yes please tell show find give need needs want know still here now ok okay after thing things going much many really just also been being did had were am got into out over under more most very too'.split(
    ' ',
  ),
)

/** Everyday words mapped to the project's own vocabulary. */
const SYNONYMS: Record<string, string[]> = {
  allowed: ['airspace', 'regulatory', 'authorization'], legal: ['airspace', 'regulatory'], permit: ['airspace', 'regulatory', 'authorization'],
  permission: ['airspace', 'regulatory', 'authorization'], permissions: ['airspace', 'regulatory'], law: ['regulatory', 'airspace'], faa: ['airspace', 'regulatory'],
  fly: ['flight', 'airspace'], flying: ['flight', 'airspace'], drone: ['flight', 'equipment'], camera: ['equipment', 'capture'], gear: ['equipment'], kit: ['equipment'],
  windy: ['wind', 'weather'], rain: ['weather'], storm: ['weather'], forecast: ['weather'], sunny: ['weather'], gusts: ['wind', 'weather'],
  safe: ['safety'], danger: ['safety'], dangerous: ['safety'], risk: ['safety'], risks: ['safety'], people: ['pedestrian', 'safety'], public: ['pedestrian', 'safety'],
  street: ['sidewalk', 'safety'], door: ['entrance', 'access'], entry: ['entrance', 'access'], keys: ['access'], dock: ['access'],
  date: ['schedule'], dates: ['schedule'], calendar: ['schedule'], timeline: ['schedule'], deadline: ['schedule'], day: ['schedule'], days: ['schedule'],
  building: ['site', 'geometry', 'bim'], model: ['bim', 'geometry'], drawings: ['bim', 'geometry'], plans: ['bim'], size: ['geometry'], height: ['geometry'], roof: ['parapet', 'roof'],
  facade: ['façade'], wall: ['façade'], walls: ['façade'], damage: ['spalling', 'defect', 'objectives'], cracks: ['cracked', 'objectives'], defects: ['defect', 'objectives'],
  client: ['brief', 'client'], customer: ['client', 'brief'], scope: ['brief', 'objectives'], goal: ['objectives'], goals: ['objectives'], purpose: ['objectives'], aim: ['objectives'],
  report: ['package', 'inspection'], deliverable: ['package', 'deliverable'], deliverables: ['package', 'deliverable'], result: ['package'], results: ['package'], photos: ['imagery', 'capture'], images: ['imagery', 'capture'],
  email: ['email'], mail: ['email'], message: ['email'], ai: ['ai', 'observation'], robot: ['ai'], suggestion: ['suggested', 'ai'], suggestions: ['suggested', 'ai'],
  plan: ['approach', 'plan'], method: ['approach'], approach: ['approach'], route: ['approach', 'capture'],
}

const INTENTS: { name: string; words: string[] }[] = [
  { name: 'blocking', words: ['blocking', 'blocked', 'block', 'stuck', 'waiting', 'holding', 'hold', 'delay', 'delayed', 'issue', 'issues', 'problem', 'problems', 'missing', 'open', 'unresolved', 'next', 'todo', 'checking', 'check', 'unverified', 'unsure', 'pending', 'outstanding', 'left'] },
  { name: 'who', words: ['who', 'owner', 'owns', 'responsible', 'contact', 'charge', 'looks', 'handles', 'handle'] },
  { name: 'deliver', words: ['get', 'gets', 'receive', 'receives', 'deliver', 'delivered', 'deliverable', 'deliverables', 'output', 'outputs', 'final', 'end'] },
  { name: 'when', words: ['when', 'date', 'dates', 'schedule', 'soon', 'start'] },
  { name: 'allowed', words: ['allowed', 'legal', 'permit', 'permission', 'permissions', 'authorized', 'authorization', 'law', 'faa'] },
  { name: 'decide', words: ['decide', 'decided', 'decision', 'decisions', 'chosen', 'choice'] },
]

const norm = (s: string) => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')

export function ask(question: string, nodes: GraphNode[], edges: GraphEdge[]): AskResult {
  const words = norm(question).split(/[^a-z0-9]+/).filter(Boolean)
  const intents = INTENTS.filter((i) => i.words.some((w) => words.includes(w))).map((i) => i.name)
  const intentWords = new Set(INTENTS.flatMap((i) => i.words))
  const terms = new Set<string>()
  for (const w of words) {
    if (STOP.has(w) || (w.length < 3 && !SYNONYMS[w])) continue
    if (!intentWords.has(w) || SYNONYMS[w]) terms.add(w)
    for (const s of SYNONYMS[w] ?? []) terms.add(norm(s))
  }

  const score = new Map<string, number>()
  for (const n of nodes) {
    const title = norm(n.title)
    const cat = n.category ? norm(CAT[n.category].label) : 'unclassified'
    const body = norm(`${n.summary} ${n.why} ${n.kind} ${n.status} ${n.owner} ${n.origin.name} ${n.openQuestion ?? ''}`)
    let s = 0
    for (const t of terms) {
      if (title.includes(t)) s += 3
      if (cat.includes(t)) s += 2
      if (body.includes(t)) s += 1
    }
    if (intents.includes('blocking') && n.openQuestion && s > 0) s += 2
    if (intents.includes('deliver') && n.kind === 'output') s += n.category === 'requirements' ? 6 : 3
    if (intents.includes('when') && (n.category === 'schedule' || n.category === 'weather')) s += n.category === 'schedule' ? 3 : 1
    if (intents.includes('allowed') && n.category === 'regulatory') s += 3
    if (intents.includes('decide') && n.kind === 'decision') s += 3
    if (s > 0) score.set(n.id, s)
  }

  // "What needs checking?" with no particular subject: every open item.
  if (intents.includes('blocking') && score.size === 0) for (const n of nodes) if (n.openQuestion) score.set(n.id, n.importance === 'high' ? 3 : 2)

  // For "what's blocking X": also pull in the open items that feed the best match.
  const ranked0 = [...score.entries()].sort((a, b) => b[1] - a[1])
  if (intents.includes('blocking') && ranked0[0]) {
    const top = ranked0[0][0]
    for (const e of edges) {
      if (e.target !== top) continue
      const up = nodes.find((n) => n.id === e.source)
      if (up?.openQuestion) score.set(up.id, (score.get(up.id) ?? 0) + 2.5)
    }
  }

  const ranked = [...score.entries()].sort((a, b) => b[1] - a[1])
  const cut = ranked.length ? Math.max(1, ranked[0][1] * 0.34) : 0
  const ids = ranked.filter(([, s]) => s >= cut).slice(0, 8).map(([id]) => id)
  const hit = ids.map((id) => nodes.find((n) => n.id === id)!)
  const intent = intents[0] ?? 'about'

  if (!hit.length) {
    return { ids: [], intent, answer: "I couldn't find that in this project. Try asking about weather, permits, safety, the schedule, or what the client gets." }
  }

  const top = hit[0]
  let answer: string
  if (intent === 'blocking') {
    const open = hit.filter((n) => n.openQuestion)
    answer = open.length
      ? `${open.length} thing${open.length === 1 ? ' is' : 's are'} still open. ${open.slice(0, 3).map((n) => `${n.title}: ${n.openQuestion}`).join(' ')}${open.length > 3 ? ` Plus ${open.length - 3} more below.` : ''}`
      : `Nothing is flagged as open on ${top.title}.`
  } else if (intent === 'who') {
    answer = hit.slice(0, 2).map((n) => `${n.title} is looked after by ${n.owner}.`).join(' ')
  } else if (intent === 'deliver') {
    const outs = hit.filter((n) => n.kind === 'output')
    const main = outs.find((n) => n.category === 'requirements') ?? outs[0]
    answer = main ? `The client receives the ${main.title}: ${main.summary}` : `${top.title}: ${top.summary}`
  } else if (intent === 'when') {
    answer = `${top.title}: ${top.summary}${top.openQuestion ? ` Note: ${top.openQuestion}` : ''}`
  } else if (intent === 'allowed') {
    answer = top.openQuestion ? `Not confirmed yet. ${top.title}: ${top.openQuestion}` : `${top.title}: ${top.summary}`
  } else {
    answer = `${top.title}: ${top.summary}${top.openQuestion ? ` Still open: ${top.openQuestion}` : ''}`
  }
  return { ids, answer, intent }
}
