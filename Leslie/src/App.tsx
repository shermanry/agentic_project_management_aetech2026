import { useEffect, useState } from 'react'
import './design/ui.css'
import { PROJECT, type ComponentId } from './data/sampleProject'
import { GraphProvider, useGraph } from './model/graph'
import OverviewView from './views/OverviewView'
import ClientView from './views/ClientView'
import PMView from './views/PMView'
import PilotView from './views/PilotView'
import Onboarding, { landFor } from './views/Onboarding'
import { Monogram, Wordmark } from './components/Logo'
import Intake from './components/Intake'
import { isParked } from './model/graph'

type View = 'overview' | 'client' | 'pm' | 'pilot'
const VIEWS: { id: View; label: string; crumb: string; desc: string }[] = [
  { id: 'overview', label: 'Overview', crumb: 'Overview', desc: 'Project twin board: status of every node, open questions and proposed links.' },
  { id: 'client', label: 'Client', crumb: 'Building explorer', desc: 'Explore the building, see what is known about each part, and draft a design brief.' },
  { id: 'pm', label: 'PM', crumb: 'Knowledge canvas', desc: 'Arrange, filter and review project information by constraint category.' },
  { id: 'pilot', label: 'Expert', crumb: '3D network', desc: 'Every node and relationship in space, colour-matched to the PM categories.' },
]

const readView = (): View => {
  try {
    const h = location.hash.slice(1)
    return (VIEWS.find((v) => v.id === h)?.id ?? 'overview') as View
  } catch {
    return 'overview'
  }
}

function Clock() {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  const tz = 'America/New_York'
  const f = (o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat(undefined, { timeZone: tz, ...o }).format(now)
  return (
    <div className="clock">
      <span className="clock-t">{f({ hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}</span>
      <span className="clock-z">{f({ weekday: 'short', day: 'numeric', month: 'short' })} · New York</span>
    </div>
  )
}

function Shell() {
  const { state, dispatch } = useGraph()
  const parkedCount = state.nodes.filter(isParked).length
  const [view, setViewState] = useState<View>(readView)
  const [clientComp, setClientComp] = useState<ComponentId>()
  const [shared, setShared] = useState(false)
  const [intake, setIntake] = useState(false)
  const setView = (v: View) => {
    setViewState(v)
    try {
      history.replaceState(null, '', '#' + v)
    } catch {
      /* hash unavailable */
    }
  }
  useEffect(() => {
    const on = () => setViewState(readView())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  const info = VIEWS.find((v) => v.id === view)!
  // The survey is the landing page: until it is answered, no tab or feature can be opened.
  const gate = !state.onboarding

  return (
    <div className={`app light ${gate ? 'tab-overview view-monitor ob-gate' : `tab-${view} view-${view === 'overview' ? 'monitor' : view === 'pm' ? 'pm' : 'twin'}`}`}>
      <header className="topbar">
        <a className="brand" href="#overview" aria-label="YBuild, go to overview">
          <span className="brand-full">
            <Wordmark height={24} />
          </span>
          <span className="brand-mono">
            <Monogram height={24} />
          </span>
        </a>

        <nav className="crumbs" aria-label="Breadcrumb">
          <span>Projects</span>
          <span className="sl">›</span>
          <span>{PROJECT.name}</span>
          <span className="sl">›</span>
          <b>{info.crumb}</b>
        </nav>

        <nav className="seg views" aria-label="Role view">
          {VIEWS.map((v) => (
            <button key={v.id} className={view === v.id ? 'on' : ''} onClick={() => setView(v.id)}>
              {v.label}
            </button>
          ))}
        </nav>

        <div className="status-area">
          <button className="add-btn" onClick={() => setIntake(true)} aria-haspopup="dialog">
            + Add{parkedCount > 0 && <sup className="tab-count">{parkedCount}</sup>}
          </button>
          <button
            className="btn sm"
            onClick={() => {
              navigator.clipboard
                ?.writeText(location.href)
                .then(() => setShared(true))
                .catch(() => setShared(false))
              setTimeout(() => setShared(false), 1800)
            }}
          >
            {shared ? 'Link copied' : 'Share'}
          </button>
          <Clock />
        </div>
      </header>

      <div className="project-strip">
        <span className="mono code">{PROJECT.code}</span>
        <span className="badge t-info">{PROJECT.status}</span>
        <b>
          {PROJECT.name} · {PROJECT.title}
        </b>
        <span className="dim">{info.desc}</span>
      </div>

      {gate && (
        <Onboarding
          onAdd={() => setIntake(true)}
          onDone={(a) => {
            dispatch({ type: 'setOnboarding', onboarding: a })
            const land = landFor(a)
            // their first goal still counts on arrival: open the Add page, or ask the guide what is open
            if (a.goal === 'add') setIntake(true)
            if (a.goal === 'blocking' && (land === 'pm' || land === 'pilot')) dispatch({ type: 'setQuery', query: 'What still needs checking?' })
            setView(land)
            window.scrollTo({ top: 0 })
          }}
        />
      )}
      {!gate && view === 'overview' && (
        <OverviewView
          openPM={(id) => (dispatch({ type: 'select', id }), setView('pm'))}
          openClient={(c) => (setClientComp(c), setView('client'))}
          openPilot={(id) => (dispatch({ type: 'select', id }), setView('pilot'))}
          goTo={(s) => {
            if (s.tab === 'add') return setIntake(true)
            if (s.question) dispatch({ type: 'setQuery', query: s.question })
            setView(s.tab)
          }}
        />
      )}
      {!gate && view === 'client' && <ClientView key={clientComp} initial={clientComp} />}
      {!gate && view === 'pm' && <PMView />}
      {!gate && view === 'pilot' && <PilotView />}
      <Intake open={intake} setOpen={setIntake} scene3d={gate ? undefined : view === 'pilot' ? 'network' : view === 'client' ? 'building' : undefined} reveal={(id) => (dispatch({ type: 'select', id }), setView('pm'), setIntake(false))} />
    </div>
  )
}

export default function App() {
  return (
    <GraphProvider>
      <Shell />
    </GraphProvider>
  )
}
