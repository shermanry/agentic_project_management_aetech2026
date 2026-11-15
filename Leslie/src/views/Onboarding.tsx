// The survey is the landing page: three questions, one per screen. Nothing else opens until it is
// answered; the app then lands on the page for the person's role (a client on the Client page).
// Answers are kept in this browser only (localStorage) and can be retaken from the end of the Overview.
import { useState } from 'react'
import { PROJECT } from '../data/sampleProject'
import type { Onboarding as Answers } from '../model/graph'

export type Start = { tab: 'client' | 'pm' | 'pilot' | 'add'; label: string; why: string; question?: string }

/** Where a person should begin, from their answers. */
// eslint-disable-next-line react-refresh/only-export-components
export function startFor(a: Answers): Start {
  if (a.goal === 'building') return { tab: 'client', label: 'Building explorer', why: 'Click any part of the building to see what is known about it.' }
  if (a.goal === 'add') return { tab: 'add', label: 'Add files', why: 'Drop files anywhere on the page, or paste a note. You approve where each one goes.' }
  if (a.goal === 'blocking')
    return { tab: a.role === 'pilot' ? 'pilot' : 'pm', label: a.role === 'pilot' ? 'Knowledge network' : 'Project tree', why: 'We will ask the guide what is still open and show you where.', question: 'What still needs checking?' }
  if (a.role === 'client') return { tab: 'client', label: 'Building explorer', why: 'The simplest way in: explore the building, then draft a brief.' }
  if (a.role === 'pilot') return { tab: 'pilot', label: 'Knowledge network', why: 'Every piece of project knowledge in one view. Ask a question to find your way.' }
  return { tab: 'pm', label: 'Project tree', why: 'Everything laid out left to right. Ask a question in plain words to find things.' }
}

/** Where a person lands after the survey: the page for their role. */
// eslint-disable-next-line react-refresh/only-export-components
export function landFor(a: Answers): 'overview' | 'client' | 'pm' | 'pilot' {
  return a.role === 'client' ? 'client' : a.role === 'pm' ? 'pm' : a.role === 'pilot' ? 'pilot' : 'overview'
}

const STEPS = [
  {
    key: 'role' as const,
    q: 'What best describes you?',
    options: [
      ['client', 'Client', 'I want to follow the project and see what I am getting'],
      ['pm', 'Project manager', 'I keep the pieces moving and decide what happens next'],
      ['pilot', 'Expert', 'I plan and carry out the technical work'],
      ['explore', 'Just looking', 'Show me around'],
    ],
  },
  {
    key: 'goal' as const,
    q: 'What would you like to do first?',
    options: [
      ['building', 'See the building', 'Explore it part by part'],
      ['blocking', 'Find out what is holding things up', 'Open questions and things to check'],
      ['find', 'Find a piece of information', 'Ask a question in plain words'],
      ['add', 'Add something new', 'A file, an email, a note'],
    ],
  },
  {
    key: 'level' as const,
    q: 'How well do you know this project?',
    options: [
      ['new', 'New to it', 'Keep it simple and guide me'],
      ['some', 'I know the basics', ''],
      ['expert', 'I know it well', 'Get out of my way'],
    ],
  },
]

interface Props {
  /** Called with the answers once the last question is answered. */
  onDone: (a: Answers) => void
  /** Open the Add page (drag and drop). */
  onAdd: () => void
}

export default function Onboarding({ onDone, onAdd }: Props) {
  const [step, setStep] = useState(0)
  const [ans, setAns] = useState<Partial<Answers>>({})

  return (
    <div className="ed-page ob">
      <header className="ob-top">
        <span className="ed-meta">
          {PROJECT.name} — Question {step + 1} of {STEPS.length}
        </span>
        <span className="ob-bar" aria-hidden>
          {STEPS.map((_, i) => (
            <i key={i} className={i < step ? 'on' : ''} />
          ))}
        </span>
      </header>

      <div className="ob-drop">
        <button className="ed-cta" onClick={onAdd}>
          + Add files
        </button>
        <p>
          <b>Have material already?</b> Drag files anywhere onto this page, at any time: emails, drawings, photos, notes. They are read and you choose where they go.
        </p>
      </div>

      <section className="ob-step" key={step}>
        <h1 className="ed-display md">{STEPS[step].q}</h1>
        <ul className="ed-rows ob-options">
          {STEPS[step].options.map(([value, label, hint]) => (
            <li key={value}>
              <button
                className="ed-row"
                onClick={() => {
                  const next = { ...ans, [STEPS[step].key]: value }
                  setAns(next)
                  if (step + 1 < STEPS.length) setStep(step + 1)
                  else onDone(next as Answers)
                }}
              >
                <span className="t">
                  {label}
                  {hint && <span className="ob-hint">{hint}</span>}
                </span>
                <span className="side">
                  <span className="go" aria-hidden>
                    →
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
        {step > 0 && (
          <button className="ed-link dim" onClick={() => setStep(step - 1)}>
            Back
          </button>
        )}
      </section>
    </div>
  )
}
