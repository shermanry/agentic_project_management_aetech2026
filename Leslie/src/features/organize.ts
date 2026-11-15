// Organizer: proposes where a parked item belongs (category + links).
//
// This is a local keyword stand-in for an LLM so the prototype runs with no API key. To use a real
// model, replace the body of `organize` with a call that sends each item's title/text plus the list
// of categories and existing nodes, and returns the same `Suggestion` shape. Nothing is applied
// until a person accepts a suggestion.
import { CATEGORIES, type CategoryId, type GraphNode } from '../data/sampleProject'
import type { Suggestion } from '../model/graph'

const KEYWORDS: Record<CategoryId, string[]> = {
  requirements: ['brief', 'rfp', 'scope', 'deliverable', 'objective', 'requirement', 'client', 'report', 'contract', 'proposal'],
  site: ['site', 'geometry', 'bim', 'revit', 'model', 'survey plan', 'drawing', 'elevation', 'floor', 'parcel', 'gis', 'scan', 'point cloud', 'dwg', 'ifc', 'rvt'],
  regulatory: ['faa', 'airspace', 'authorization', 'permit', 'waiver', 'laanc', 'regulation', 'notam', 'license', 'compliance'],
  weather: ['weather', 'wind', 'gust', 'rain', 'forecast', 'visibility', 'temperature', 'storm', 'cloud'],
  safety: ['safety', 'access', 'dock', 'key', 'pedestrian', 'sidewalk', 'closure', 'hazard', 'launch', 'security', 'plaza', 'risk', 'insurance'],
  technical: ['drone', 'camera', 'equipment', 'flight', 'capture', 'gimbal', 'battery', 'sensor', 'overlap', 'resolution', 'payload', 'lens'],
  schedule: ['schedule', 'date', 'calendar', 'deadline', 'week', 'session', 'timeline', 'milestone', 'monday', 'saturday'],
}

/** Words too common in this project to justify a link on their own. */
const GENERIC = new Set(['building', 'access', 'ground', 'survey', 'project', 'client', 'inspection', 'safety', 'potential', 'observation'])

/** The node new items in a category most naturally connect to. */
const ANCHOR: Record<CategoryId, [string, string]> = {
  requirements: ['objective', 'informs'],
  site: ['site', 'details'],
  regulatory: ['airspace', 'informs'],
  weather: ['weather', 'refines'],
  safety: ['safety', 'informs'],
  technical: ['flight', 'informs'],
  schedule: ['schedule', 'constrains'],
}

export function suggestFor(node: GraphNode, all: GraphNode[]): Suggestion {
  const text = `${node.title} ${node.summary}`.toLowerCase()
  const scored = CATEGORIES.map((c) => {
    const hits = KEYWORDS[c.id].filter((k) => text.includes(k))
    return { id: c.id, hits }
  }).sort((a, b) => b.hits.length - a.hits.length)
  const best = scored[0]
  const second = scored[1]?.hits.length ?? 0
  const category = best.hits.length ? best.id : 'requirements'
  const confidence = best.hits.length ? Math.min(0.94, 0.55 + 0.12 * best.hits.length - 0.06 * second) : 0.35

  const links: Suggestion['links'] = []
  const [anchor, relation] = ANCHOR[category]
  if (all.some((n) => n.id === anchor) && anchor !== node.id) links.push({ target: anchor, relation })
  // also link to any existing node whose title is mentioned in the text
  for (const n of all) {
    if (n.id === node.id || n.category === null || links.some((l) => l.target === n.id)) continue
    const key = n.title.toLowerCase().split(/[^a-z]+/).filter((w) => w.length > 5 && !GENERIC.has(w))
    if (key.some((w) => text.includes(w)) && links.length < 3) links.push({ target: n.id, relation: 'relates to' })
  }

  return {
    category,
    confidence,
    links,
    reason: best.hits.length ? `Mentions ${best.hits.slice(0, 3).join(', ')}` : 'No clear signal, best guess',
  }
}

/** Organizes every parked item. Async so a real model call can drop in. */
export async function organize(parked: GraphNode[], all: GraphNode[]): Promise<Record<string, Suggestion>> {
  await new Promise((r) => setTimeout(r, 700)) // stands in for model latency
  return Object.fromEntries(parked.map((n) => [n.id, suggestFor(n, all)]))
}
