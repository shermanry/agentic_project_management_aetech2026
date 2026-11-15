import { useMemo, useState } from 'react'
import BuildingScene, { type Preset } from '../components/BuildingScene'
import { Badge, CatLabel } from '../components/ui'
import { COMPONENTS, PROJECT, type ComponentId } from '../data/sampleProject'
import { generateDesignBrief } from '../features/generateDesignBrief'
import { useGraph } from '../model/graph'

export default function ClientView({ initial }: { initial?: ComponentId }) {
  const { state, byId } = useGraph()
  const [comp, setComp] = useState<ComponentId | undefined>(initial ?? 'north')
  const [openNode, setOpenNode] = useState<string>()
  const [labels, setLabels] = useState(true)
  const [orbit, setOrbit] = useState(false)
  const [preset, setPreset] = useState<Preset>({ name: 'persp', n: 0 })
  const [brief, setBrief] = useState<string>()
  const c = COMPONENTS.find((x) => x.id === comp)

  return (
    <div className="twin">
      <div className="twin-canvas">
        <BuildingScene mono selected={comp} onSelect={(id) => (setComp(id), setOpenNode(undefined))} labels={labels} orbit={orbit} preset={preset} />
      </div>

      <div className="hud">
        <div className="hud-col left">
          <section className="glass">
            <div className="eyebrow">
              {PROJECT.code} · Building explorer
            </div>
            <h1 className="site-name">{PROJECT.name}</h1>
            <div className="coords">{PROJECT.title} · {PROJECT.city}</div>
            <p className="disclaimer">Illustrative model, not a scan. Sample data.</p>
            <button className="btn primary wide" onClick={() => setBrief(generateDesignBrief(state))}>
              Generate design brief
            </button>
          </section>
          <section className="glass">
            <div className="glass-h">
              <h2>Building components</h2>
              <span className="mono dim">{COMPONENTS.length}</span>
            </div>
            <ul className="comp-list">
              {COMPONENTS.map((x) => (
                <li key={x.id}>
                  <button className={x.id === comp ? 'on' : ''} onClick={() => (setComp(x.id), setOpenNode(undefined))}>
                    <span>{x.label}</span>
                    <span className="dim small">{x.nodes.length} linked</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        </div>

        <div className="hud-top">
          <div className="toolbar glass" role="toolbar" aria-label="Model view">
            <div className="seg sm">
              {(['persp', 'front', 'top'] as const).map((v) => (
                <button key={v} className={preset.name === v ? 'on' : ''} onClick={() => setPreset((s) => ({ name: v, n: s.n + 1 }))}>
                  {v === 'persp' ? '3D' : v === 'front' ? 'Street' : 'Plan'}
                </button>
              ))}
            </div>
            <span className="sep" />
            <label className={`toggle ${labels ? 'on' : ''}`}>
              <input type="checkbox" checked={labels} onChange={() => setLabels(!labels)} />
              Labels
            </label>
            <label className={`toggle ${orbit ? 'on' : ''}`}>
              <input type="checkbox" checked={orbit} onChange={() => setOrbit(!orbit)} />
              Auto-orbit
            </label>
            <span className="sep hint" />
            <span className="dim small hint">Click a surface</span>
          </div>
        </div>

        <div className="hud-col right">
          {c ? (
            <section className="glass">
              <div className="eyebrow">{c.zone}</div>
              <h2 className="comp-title">{c.label}</h2>
              <p className="body">{c.explanation}</p>
              <h4 className="sub">Concerns</h4>
              <ul className="notes">
                {c.concerns.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
              <h4 className="sub">Source & verification</h4>
              <p className="body dim">{c.verification}</p>
              <h4 className="sub">Related project information</h4>
              <ul className="related">
                {c.nodes.map((id) => {
                  const n = byId(id)
                  if (!n) return null
                  const open = openNode === id
                  return (
                    <li key={id} className={open ? 'open' : ''}>
                      <button onClick={() => setOpenNode(open ? undefined : id)} aria-expanded={open}>
                        <CatLabel node={n} />
                        <span className="rel-title">{n.title}</span>
                        <Badge status={n.status} />
                      </button>
                      {open && (
                        <div className="rel-body">
                          <p>{n.summary}</p>
                          <dl className="specs">
                            <dt>Source</dt>
                            <dd>{n.origin.name}</dd>
                            <dt>Verification</dt>
                            <dd>{n.verification}</dd>
                            <dt>Owner</dt>
                            <dd>{n.owner}</dd>
                          </dl>
                          {n.openQuestion && <div className="open-q">{n.openQuestion}</div>}
                        </div>
                      )}
                    </li>
                  )
                })}
              </ul>
            </section>
          ) : (
            <section className="glass">
              <p className="body dim">Select a component on the model or from the list to see related information.</p>
            </section>
          )}
        </div>
      </div>

      {brief && <BriefModal md={brief} onClose={() => setBrief(undefined)} />}
    </div>
  )
}

function BriefModal({ md, onClose }: { md: string; onClose: () => void }) {
  const [copied, setCopied] = useState(false)
  const html = useMemo(() => renderMd(md), [md])
  const download = () => {
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([md], { type: 'text/markdown' }))
    a.download = '125-hudson-design-brief-draft.md'
    a.click()
  }
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal" role="dialog" aria-label="Design brief draft" onClick={(e) => e.stopPropagation()}>
        <header>
          <div>
            <div className="eyebrow">Generated from the project graph</div>
            <h2 className="modal-title">Design brief · draft</h2>
          </div>
          <div className="modal-act">
            <button
              className="btn sm"
              onClick={() =>
                navigator.clipboard
                  .writeText(md)
                  .then(() => setCopied(true))
                  .catch(() => setCopied(false))
              }
            >
              {copied ? 'Copied' : 'Copy Markdown'}
            </button>
            <button className="btn sm primary" onClick={download}>
              Download .md
            </button>
            <button className="icon-btn" onClick={onClose} aria-label="Close">
              ×
            </button>
          </div>
        </header>
        <article className="md" dangerouslySetInnerHTML={{ __html: html }} />
      </div>
    </div>
  )
}

/** Tiny Markdown renderer for the brief preview (headings, lists, bold/italic, quotes). */
function renderMd(md: string) {
  const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;')
  const inline = (s: string) => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\*(.+?)\*/g, '<i>$1</i>')
  const out: string[] = []
  let list = 0
  const close = (to: number) => {
    while (list > to) {
      out.push('</ul>')
      list--
    }
  }
  for (const raw of md.split('\n')) {
    const m = raw.match(/^(\s*)- (\[ \] )?(.*)$/)
    if (m) {
      const depth = m[1].length >= 2 ? 2 : 1
      while (list < depth) {
        out.push('<ul>')
        list++
      }
      close(depth)
      out.push(`<li>${m[2] ? '<span class="cb"></span>' : ''}${inline(m[3])}</li>`)
      continue
    }
    close(0)
    if (raw.startsWith('### ')) out.push(`<h4>${inline(raw.slice(4))}</h4>`)
    else if (raw.startsWith('## ')) out.push(`<h3>${inline(raw.slice(3))}</h3>`)
    else if (raw.startsWith('# ')) out.push(`<h2>${inline(raw.slice(2))}</h2>`)
    else if (raw.startsWith('> ')) out.push(`<blockquote>${inline(raw.slice(2))}</blockquote>`)
    else if (raw === '---') out.push('<hr/>')
    else if (raw.trim()) out.push(`<p>${inline(raw)}</p>`)
  }
  close(0)
  return out.join('')
}
