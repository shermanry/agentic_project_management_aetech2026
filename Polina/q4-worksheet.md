# Q4 worksheet — who decides what, and what the client traces

_Fill this in directly. Answers get folded into [sme-answers.md](sme-answers.md)._
_Source question: [../Ryan/plan.md](../Ryan/plan.md) §12, drone question 4._

Every decision below is a real one from the two projects in Q3 — the facade inspection
(one-time) and the construction monitoring job (recurrent).

**How to fill it in:** shorthand is fine. Partial is fine. Leave anything blank that does not
apply and it will get picked up in conversation. Rough is more useful than polished.

---

## Role codes

Use these in the table, or write names if that is easier.

| Code | Means |
| --- | --- |
| `RPIC` | pilot in command |
| `PM` | project manager on this project |
| `OPM` | project manager of a *different* project, whose staff you need |
| `CL` | client |
| `LEG` | legal team |
| `OWN` | property owner |
| `AUTH` | authority — NYPD, FAA, DHS |
| `VO` | visual observer |
| `PROC` | whoever runs photogrammetry processing |
| `ME` | you, in whatever role you were holding at the time |

---

## Part A — Decision ownership

For each decision: **who decides**, **who has to approve it**, **who has to be told**, and
**whether it is written down anywhere today** (yes / no / where).

A fifth column — **Consulted** — was added during the interview. The operator introduced it
unprompted on decision 1: the RPIC neither decides nor approves project scope, but scope
cannot be set without a feasibility check from them. "Consulted" is where technical reality
constrains a commercial decision, and it is a distinct edge type from the other three.

| # | Decision | Decides | Approves | Consulted | Informed | Recorded today? |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Accept project scope and deliverables | `PM` | `CL` | `RPIC` — is it possible? |  |  |
| 2 | Decide which permits are required | `RPIC` | `RPIC` | `PM` | `CL` |  |
| 3 | **Choose the permit dates** (chosen blind, 30 days out) | `RPIC` | `PM` — **agrees; there is no other option** | `LEG` — can it be expedited? | `CL` |  |
| 4 | Submit the document package to the authority | `RPIC` | `RPIC` | `PM` on staffing | `CL` |  |
| 5 | Fly 1 of 5 permitted days vs. wait for a better window | `RPIC` | `PM` | — | `CL` |  |
| 6 | Release a crew member from another project | `PM` | **`OPM`** | `RPIC` requests it, and says who is needed | |  |
| 7–18 | — | \* | \* | \* | \* |  |

\* Rows 7–18 follow the general rule below rather than being enumerated. The operator stopped
the row-by-row here, correctly: the pattern had begun repeating, and the general rule plus its
exceptions carries more information than twelve near-identical rows.

### The general rule

> **The RPIC provides the plan and determines what actions are needed. The PM helps make it
> work. The client is informed when needed. Other people are pulled in as required.**

This is the default governance model for everything in a drone project. It is worth stating
plainly because it is not what an outside observer would assume: the technical authority
originates the plan, and the project manager is the enabling function, not the directing one.

### The three places the rule breaks

The exceptions carry the information. Each one breaks the rule in a different way, and each
one maps to a different failure mode the product can address.

| # | Decision | How it departs from the rule | Why it matters |
| --- | --- | --- | --- |
| 1 | **Accept scope and deliverables** | The only decision where the RPIC is *not* driving. `PM` decides, `CL` approves, `RPIC` is consulted for feasibility only | Commercial commitments can be made that technical reality will later refuse. The feasibility consultation is the only guard, and it is advisory |
| 3 | **Choose permit dates** | `PM` approves, but **cannot refuse** — no alternative exists | An approval with no alternatives is not a decision. Recording it as one hides the real cause of downstream slippage |
| 6 | **Release a crew member** | Approved by **`OPM`, who is outside the project** and has no stake in its success | The only external veto in the chain. It can be refused for reasons entirely unrelated to this project, and it gates the flight |

### Schema consequences from Part A

1. **A revision needs an `alternatives_available` field.** "None" is a real and frequent
   value, and it is the single most useful thing to show a client asking why a project ran
   long — not "we chose badly" but "there was no choice to make."
2. **Participation is not binary.** Decides / approves / **consulted** / informed are four
   distinct relationships. The consulted edge is where technical feasibility constrains a
   commercial decision, and it has no veto power — which is itself worth modelling.
3. **Approvers can be external to the project.** `OPM` on decision 6 is the clearest case.
   An approval gate held by someone with different incentives is a structural risk the graph
   should be able to surface.
4. **Document dependencies span three external parties** — client, legal team, property owner
   — each outside the drone team and each with independent lead times.

### Findings so far from Part A

**Authority inverts between commercial and regulatory decisions.** Scope is `PM`-decided and
`CL`-approved. The permit list and the document submission are `RPIC`-decided *and*
`RPIC`-approved, with no external gate at all. Regulatory determination sits wholly with
technical authority; commercial determination does not.

**Some approvals are structurally forced.** On decision 3 the `PM` approves the blind date
selection "because there is no other option." Recording that as a plain approval
misrepresents it — a decision with no alternatives is a different kind of event from a
decision where someone chose between options.

> **Schema consequence:** a revision needs a field for *alternatives available*. "None" is a
> real and common value. This is also the single most useful thing a client can be shown when
> asking why a project ran long: not "we chose badly" but "there was no choice to make."

**Document dependencies span three external parties**, each outside the drone team and each
with their own lead time: the **client** supplies some documents, the **legal team** supplies
insurance and other non-technical paperwork, and the **property owner** supplies the letter of
authorization to fly over their property.

### Anything missing?

Add rows for decisions that mattered and are not listed.

| # | Decision | Decides | Approves | Informed | Recorded today? |
| --- | --- | --- | --- | --- | --- |
| 19 |  |  |  |  |  |
| 20 |  |  |  |  |  |
| 21 |  |  |  |  |  |

---

## Part A follow-ups

**A1. Which of these have you ever had taken away from you, or had overruled?**

> _answer here_

**A2. Which ones does somebody *think* they own, but actually do not?**

> _answer here_

**A3. Which ones get made by nobody in particular — they just happen by default because time
runs out or the window closes?**

> _answer here_

**A4. Which decisions require *two* parties to agree before anything can move, and how is that
agreement reached today?**

> _answer here_

---

## Part B — What the client wants to trace

**B1. Has a client ever come back weeks or months later and challenged a decision?**
What did they ask, and what did you have to dig up to answer them?

> **Yes.** When a client challenges a decision, the response is to explain all the factors
> that produced the change **and provide references to those factors** — the weather forecast
> at the time, the NOTAM that was active.

### The requirement this creates: evidence must be snapshotted, not linked

Citing the evidence only works if the evidence still exists in the form it had when the
decision was made. It usually does not:

- A **weather forecast** for a date three months ago is gone. The historical record of what
  actually happened is not the same artifact as the forecast that was used to decide.
- **NOTAMs and TFRs expire** and drop out of the active feed.
- **Regulations change** — Q3A has a case where the rules changed mid-application because of
  an unrelated public event.

> **Schema consequence:** `revision.evidence` in `plan.md` §9 points at node IDs. That is only
> sufficient if those nodes are **immutable point-in-time captures**, not live feeds that
> refresh in place. A node for "weather at this site" that updates is useless as evidence; a
> node for "the forecast we held on 14 Nov for 19 Nov" is exactly what is needed.
>
> This argues for storing fetched external data as versioned snapshots, with the decision
> pointing at the specific version it rested on.

This also sharpens *why* the decision record is worth building. Two distinct uses, and both
are real:

| Use | Direction | Evidence from this interview |
| --- | --- | --- |
| Explain a change to a client who challenges it | backward-looking | B1, above — happens, and the answer is cited factors |
| Make the next decision without the dependencies living in one person's head | forward-looking | Q3A — named unprompted as the thing that would have helped most |

**How this is done today:** by **digging through old emails**. The evidence exists, scattered
across inboxes, with no index and no guarantee the original forecast or NOTAM is still
retrievable at all.

> **Operator's verdict, verbatim: "Snapshot feature is a must."**
>
> This is a requirement confirmed by the subject-matter expert, not a feature inferred by the
> product team. It should carry more weight than the latter in scoping discussions.

**B2. What does the client see today** — a report, emails, a meeting?
How much of the *reasoning* actually reaches them, as opposed to just the outcome?

> _answer here_

**B3. The facade job ran significantly over on both schedule and budget.**
When you explained that to the client, what did you have to show? Was any of it
reconstructible from records, or did you rebuild the story from memory?

> _answer here_

**B4. Which decisions does the client have a genuine right to influence**, versus the ones
they only need to be told about? What goes wrong when that line is drawn in the wrong place?

The client can:

- **cancel the job**
- **push the schedule further out**
- **adjust flight frequency**
- **change scope** — the number and type of flights

**But they cannot do any of it independently.** Each is a request that has to be assessed and
agreed, not an action the client takes alone.

### The boundary

> **The client owns the commercial envelope — *what* and *when*.
> The RPIC owns the operational method — *how*, and *whether it is safe*.**

Cancel, delay, frequency, scope: the client's to influence. Flight path, camera selection,
crew composition, go/no-go: never. The two sets do not overlap, and the line is clean enough
to encode.

### Consequence: the client view is not read-only

`plan.md` §5 describes the basic/client view as view-only — trace decisions, change nothing.
That is not quite right. The client has real influence over four things, so the view needs a
**request** action distinct from an **edit** action:

| | Edit | Request |
| --- | --- | --- |
| Who can | `RPIC`, `PM` within their scope | `CL` |
| Effect | changes the plan directly | creates a proposal for assessment |
| Becomes a revision | immediately | once assessed and agreed |

A read-only client view pushes these four conversations back into email — which is precisely
where the evidence currently goes to die (see B1). Capturing the request *in the system*, with
the assessment attached, is how the reasoning stays with the decision.

**Suggested flow:** client submits a request → `RPIC` assesses feasibility → `PM` resources it
→ agreed or declined, with a reason → revision recorded. The decline case matters as much as
the approve case; `plan.md` §3 already says rejected suggestions are kept with their reason,
and this is the same mechanism applied to the client.

**B5. Is there anything you deliberately do *not* show the client**, and why?

Not withheld permanently. Withheld **while live**, and redacted **in content**. Two separate
axes, and the distinction matters:

#### Axis 1 — timing: embargo until resolved

Issues in the **process of being resolved** are not shown live. Scope risks, staffing
conflicts, legal documentation and the permit document package stay internal while the team
is still working the problem.

**Once resolved, the full picture should be published and available**, listing all the
challenges the project absorbed.

#### Axis 2 — content: never posted automatically

Regardless of timing, two things are never published automatically:

- **Specific names**
- **Budget figures**

#### The governing principle, in the operator's words

> **"It should be transparent but not exposing the information that can be used against the
> team by the client."**

### This strengthens the transparency pitch rather than limiting it

The second team's framing — educate the client on how many decisions a project requires — is
fully compatible with this. The client *does* eventually see the complete record of
challenges. They simply do not watch the team fight them in real time, and they do not get
names and dollar figures attached.

| Dimension | While unresolved | Once resolved |
| --- | --- | --- |
| That a challenge exists | internal | **published** |
| What caused it | internal | **published** |
| How it was resolved | internal | **published** |
| Who specifically was involved | internal | **redacted to role** |
| Budget impact | internal | **not automatic** |

### Visibility is a state machine, not a permission flag

This is the real finding. `plan.md` §5 models visibility as a fixed three-tier permission
scheme: a node is either visible to a role or it is not. That cannot express "internal now,
client-visible once closed."

> **Schema consequence:** client visibility depends on the node's **resolution state**, not
> only on its type. An open staffing conflict and a closed one are the same node type with
> different audiences.

Two things follow for the build:

1. **Nodes carrying an issue need a resolution state**, and the client view filters on it.
   Publication is a consequence of closure, not a separate manual act.
2. **Redaction rules are per-field, not per-node.** A resolved staffing conflict is publishable
   with the names stripped to roles. Treating redaction as all-or-nothing at node level would
   force the team to withhold the whole item and lose the transparency the operator actively
   wants.

The demo counter — "23 decisions, 16 resolved from data, 7 required human expertise" —
survives intact, because it reports the **shape** of the record rather than its contents.

---

## Free notes

Anything the questions above did not reach.

> _answer here_
