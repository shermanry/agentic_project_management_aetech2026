// Assembles a draft design brief (Markdown) from the shared graph. No AI involved: plain templating.
import { CATEGORIES, COMPONENTS, PROJECT } from '../data/sampleProject'
import type { GraphState } from '../model/graph'

export function generateDesignBrief(s: GraphState): string {
  const n = (id: string) => s.nodes.find((x) => x.id === id)
  const line = (id: string) => {
    const x = n(id)
    return x ? `- **${x.title}** (${x.status}): ${x.summary}` : ''
  }
  const rel = (id: string) =>
    s.edges
      .filter((e) => e.source === id || e.target === id)
      .map((e) => `${n(e.source)?.title} *${e.relation}* ${n(e.target)?.title}${e.status === 'accepted' ? ' (AI suggestion, accepted locally)' : ''}`)
  const today = new Date().toISOString().slice(0, 10)
  const open = s.nodes.filter((x) => x.openQuestion)
  const unclassified = s.nodes.filter((x) => x.category === null)

  const out: string[] = []
  out.push(`# Design brief (draft): ${PROJECT.name} ${PROJECT.title}`)
  out.push('')
  out.push(`Project ${PROJECT.code} · ${PROJECT.workspace} · generated ${today} from ${s.nodes.length} graph nodes and ${s.edges.length} relationships.`)
  out.push('')
  out.push('> **Draft built from sample data.** No live FAA determination, weather forecast, BIM upload, scan or flight authorization exists. Verify every item before use.')
  out.push('')
  out.push('## 1. Project objective')
  out.push(line('objective'))
  out.push('')
  out.push('## 2. Client and source requirements')
  out.push(line('rfp'))
  out.push(line('report'))
  rel('rfp').forEach((r) => out.push(`  - ${r}`))
  out.push('')
  out.push('## 3. Geometry and site information')
  out.push(line('site'))
  out.push(line('revit'))
  out.push('')
  out.push('Building components:')
  COMPONENTS.forEach((c) => out.push(`- **${c.label}** (${c.zone}): ${c.explanation} Related: ${c.nodes.map((id) => n(id)?.title).join(', ')}.`))
  out.push('')
  out.push('## 4. Constraints by category')
  for (const cat of CATEGORIES) {
    const items = s.nodes.filter((x) => x.category === cat.id && ['constraint', 'weather', 'note', 'decision'].includes(x.kind))
    if (!items.length) continue
    out.push(`### ${cat.label}`)
    items.forEach((x) => {
      out.push(`- **${x.title}** (${x.status}, ${x.verification}): ${x.summary}`)
      rel(x.id).forEach((r) => out.push(`  - ${r}`))
    })
  }
  out.push('')
  out.push('## 5. Preliminary technical approach')
  out.push(line('flight'))
  out.push(line('equipment'))
  out.push(line('schedule'))
  out.push('')
  out.push('## 6. Deliverables')
  out.push(line('capture'))
  out.push(line('report'))
  out.push('')
  out.push('## 7. Outstanding verifications')
  open.forEach((x) => out.push(`- [ ] **${x.title}** (owner: ${x.owner}): ${x.openQuestion}`))
  const pending = s.candidates.filter((c) => c.state === 'pending')
  pending.forEach((c) => out.push(`- [ ] Review suggested link: ${n(c.source)?.title} *${c.relation}* ${n(c.target)?.title}`))
  if (unclassified.length) out.push(`- [ ] Classify ${unclassified.length} inbox item(s): ${unclassified.map((x) => x.title).join(', ')}`)
  out.push('')
  out.push('---')
  out.push('*Draft generated in the YBuild prototype from fictional sample data. Not an operational document.*')
  return out.filter((l, i, a) => !(l === '' && a[i - 1] === '')).join('\n')
}
