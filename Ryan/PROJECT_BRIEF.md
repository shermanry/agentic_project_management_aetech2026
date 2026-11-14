# Drone Project Management Brief

_As of 2026-11-14 · AEC Tech NYC Hackathon 2026_

We're building a knowledge-graph project system for drone flight work such as architectural surveys. Users drag anything onto a canvas, an AI turns it into connected nodes, and each role gets a view matched to how much they can decide.

Live, editable version: https://claude.ai/artifact/9WeSiyWzfTkoRnuSaeL2Wn

## Graph and data model

Every piece of project information becomes a node; nodes are linked by typed edges, stored as JSON.

- **Nodes:** documents, decisions, weather, regulations, RFIs, emails, Slack messages, models.
- **JSON metadata** for crisp facts: author, file type, links to files, whether it needs a decision, tags. A model picks the tags.
- **Embeddings** for meaning across text, images and video. Items that land near each other are linked automatically and power semantic search. Candidate: Google's open embedding model (name to confirm).
- **Hybrid links:** model-assigned semantic relationships plus embedding-proximity relationships.
- **Version control:** a Git-style backbone so the team can explore alternatives without committing to them.

## Inputs

| Source | Examples | How it enters |
| --- | --- | --- |
| External APIs | FAA airspace and rules, Google Maps, satellite imagery, weather forecasts, regulations, Revit models | Pulled automatically |
| Internal (subject experts) | Drone purpose, flight type, schedule, constraints | Added by users |
| Passive streams | Slack, Teams, email, RFIs | Suggested, not auto-placed ("you haven't put this on the canvas") |
| AI-generated | Wind CFD, collision checks, suggested observation points, prepared documents | Agent adds nodes |

## Canvas

The canvas is both a collaborative workspace and the project's decision record.

- Dropping a file starts parsing; for long material (e.g. 10 pages of research) the system proposes the useful pieces as separate nodes.
- **Core nodes** (site, etc.) are defined up front. New items can sit as **floating nodes** until the AI suggests a placement and the user approves.
- **Node temperature:** colour shows importance. The AI sets it; users override per project (e.g. RFIs matter on one job, not another). Time-sensitive items flash red.
- Graph view similar to Obsidian or a 3D clustered layout; clicking a node opens its details and links.

## Role-based views

| Level | Example user | Can do |
| --- | --- | --- |
| Basic | Client, proposal coordinator | View only: trace decisions, judge whether goals are realistic |
| Medium | Project manager | Detailed decision history; edit schedule, team and other non-technical inputs |
| Advanced | Drone pilot or solution designer | Full control of the technical pipeline and which nodes feed the project |

## Agents

- **Q&A first:** client questions and contractor RFIs hit the system before a person.
- **Group agent:** watches Slack for uncertainty, answers what it can, and routes true unknowns to whoever owns them.
- **Scheduling:** finds the next date with suitable weather for each flight type (e.g. every 2 weeks during construction) and replans when a storm or a temporary flight restriction hits.

## Open questions and next step

- How do nodes get placed: by tags, a phase/task hierarchy, or user choice? Which algorithm?
- Is canvas plus decision record too much scope for the hackathon?
- Beyond the graph, what other interactive views does each role need?

**Next step:** build three example project cards (inspection, monitoring, manufacturing), list every input each would use, and reverse-engineer the node types and APIs from them.

- [ ] Inspection project card
- [ ] Monitoring project card
- [ ] Manufacturing project card
