// First-run questionnaire on the Overview. Three questions, one per screen, then a suggested start.
// Answers are kept in this browser only (localStorage) and can be retaken any time.
import { useState } from 'react'
import { PROJECT } from '../data/sampleProject'
import type { Onboarding as Answers } from '../model/graph'

export type Start = { tab: 'client' | 'pm' | 'pilot' | 'data' | 'overview'; label: string; why: string; question?: string }

/** Where a person should begin, from their answers. */
// eslint-disable-next-line react-refresh/only-export-components
export function startFor(a: Answers): Start {
  if (a.goal === 'building') return { tab: 'client', label: 'Building explorer', why: 'Click any part of the building to see what is known about it.' }
  if (a.goal === 'add') return { tab: 'data', label: 'Parking lot', why: 'Drop files or paste notes. They get sorted into the project for you to approve.' }
  if (a.goal === 'blocking')
    return { tab: a.role === 'pilot' ? 'pilot' : 'pm', label: a.role === 'pilot' ? 'Knowledge network' : 'Project tree', why: 'We will ask the guide what is still open and show you where.', question: 'What still needs checking?' }
  if (a.role === 'client') return { tab: 'client', label: 'Building explorer', why: 'The simplest way in: explore the building, then draft a brief.' }
  if (a.role === 'pilot') return { tab: 'pilot', label: 'Knowledge network', why: 'Every piece of project knowledge in one view. Ask a question to find your way.' }
  return { tab: 'pm', label: 'Project tree', why: 'Everything laid out left to right. Ask a question in plain words to find things.' }
}

const STEPS = [
  {
    key: 'role' as const,
    q: 'What best describes you?',
    options: [
      ['client', 'Client', 'I want to follow the project and see what I am getting'],
      ['pm', 'Project manager', 'I keep the pieces moving and decide what happens next'],
      ['pilot', 'Pilot or specialist', 'I plan and carry out the technical work'],
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
  onDone: (a: Answers, go: Start | null) => void
  onSkip: () => void
}

export default function Onboarding({ onDone, onSkip }: Props) {
  const [step, setStep] = useState(0)
  const [ans, setAns] = useState<Partial<Answers>>({})
  const done = step >= STEPS.length
  const answers = ans as Answers
  const start = done ? startFor(answers) : undefined

  return (
    <div className="ed-page ob">
      <header className="ob-top">
        <span className="ed-meta">
          {PROJECT.name} — {done ? 'Ready' : `Question ${step + 1} of ${STEPS.length}`}
        </span>
        <span className="ob-bar" aria-hidden>
          {STEPS.map((_, i) => (
            <i key={i} className={i < step ? 'on' : ''} />
          ))}
        </span>
        <button className="ed-link dim" onClick={onSkip}>
          Skip
        </button>
      </header>

      {!done ? (
        <section className="ob-step" key={step}>
          <h1 className="ed-display md">{STEPS[step].q}</h1>
          <ul className="ed-rows ob-options">
            {STEPS[step].options.map(([value, label, hint]) => (
              <li key={value}>
                <button
                  className="ed-row"
                  onClick={() => {
                    setAns({ ...ans, [STEPS[step].key]: value })
                    setStep(step + 1)
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
      ) : (
        <section className="ob-step">
          <span className="ed-meta">Start here</span>
          <h1 className="ed-display md">{start!.label}</h1>
          <p className="ed-lede">{start!.why}</p>
          <div className="ob-actions">
            <button className="ed-cta" onClick={() => onDone(answers, start!)}>
              Take me there
            </button>
            <button className="ed-link" onClick={() => onDone(answers, null)}>
              Show the overview first
            </button>
            <button className="ed-link dim" onClick={() => setStep(0)}>
              Start again
            </button>
          </div>
        </section>
      )}
    </div>
  )
}
