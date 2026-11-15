// Fictional sample project: 125 Hudson Street façade condition survey.
// Everything here is illustrative. No live FAA, weather, BIM, scan or AI service is connected.

export type CategoryId = 'requirements' | 'site' | 'regulatory' | 'weather' | 'safety' | 'technical' | 'schedule'

export interface Category {
  id: CategoryId
  label: string
  purpose: string
  color: string
}

export const CATEGORIES: Category[] = [
  { id: 'requirements', label: 'Requirements', purpose: 'RFP, objectives, deliverables', color: '#7F88D9' },
  { id: 'site', label: 'Site & geometry', purpose: 'Site, GIS, BIM/model', color: '#57A8A4' },
  { id: 'regulatory', label: 'Regulatory', purpose: 'FAA, airspace, permissions', color: '#BD7EC8' },
  { id: 'weather', label: 'Weather', purpose: 'Forecasts, wind exposure', color: '#67A6DB' },
  { id: 'safety', label: 'Safety & ground access', purpose: 'Pedestrians, launch/access, hazards', color: '#E5A368' },
  { id: 'technical', label: 'Technical planning', purpose: 'Equipment, method, capture plan', color: '#6E8DDD' },
  { id: 'schedule', label: 'Schedule', purpose: 'Windows, timing dependencies', color: '#D78091' },
]
export const CAT = Object.fromEntries(CATEGORIES.map((c) => [c.id, c])) as Record<CategoryId, Category>
export const UNCLASSIFIED_COLOR = '#8FA3B8'

export type NodeKind = 'document' | 'site' | 'model' | 'constraint' | 'weather' | 'decision' | 'output' | 'note' | 'file'

export interface Origin {
  kind: 'converter' | 'upload' | 'gis' | 'bim-link' | 'derived' | 'external-api-planned' | 'manual' | 'agent-proposed' | 'email' | 'ai-generated' | 'local'
  name: string
}

export interface GraphNode {
  id: string
  title: string
  kind: NodeKind
  category: CategoryId | null // null = unclassified inbox item
  status: string
  summary: string
  why: string
  origin: Origin
  owner: string
  updatedAt: string | null
  verification: string
  importance: 'high' | 'medium' | 'low'
  openQuestion?: string
  canvas: { x: number; y: number }
  pos3d: [number, number, number]
  /** Set when the node came from the converter service. */
  pkg?: { id: string; kind: string; chunks: number; warnings: number; thumbnail?: string }
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  relation: string
  status: 'approved' | 'accepted'
  provenance: 'example' | 'ai-suggestion' | 'manual'
}

export interface Candidate {
  id: string
  source: string
  target: string
  relation: string
  reason: string
  state: 'pending' | 'accepted' | 'dismissed'
}

export const PROJECT = {
  code: 'NYC-0248',
  name: '125 Hudson Street',
  title: 'Façade Condition Survey',
  city: 'New York City',
  workspace: 'Northline Studio',
  status: 'Active planning',
}

export const NODES: GraphNode[] = [
  {
    id: 'rfp', title: 'Client survey brief', kind: 'document', category: 'requirements', status: 'Source',
    summary: 'Client RFP asking for a condition survey of all four elevations and the roof parapet, with tagged defect imagery.',
    why: 'Sets scope, deliverables and acceptance criteria. Every other decision traces back to it.',
    origin: { kind: 'upload', name: 'RFP_125Hudson_v2.pdf (sample)' }, owner: 'Client · proposal coordinator',
    updatedAt: '2026-11-03', verification: 'Source document', importance: 'high',
    canvas: { x: 40, y: 70 }, pos3d: [-150, 70, 10],
  },
  {
    id: 'site', title: 'Site geometry', kind: 'site', category: 'site', status: 'Verified',
    summary: 'Lot boundary, footprint about 32 × 24 m, roughly 49 m to the parapet, adjacent street widths.',
    why: 'Determines reachable elevations, standoff distances and possible launch areas.',
    origin: { kind: 'gis', name: 'City parcel data (sample)' }, owner: 'Survey lead',
    updatedAt: '2026-11-05', verification: 'Verified against sample parcel data', importance: 'high',
    canvas: { x: 40, y: 340 }, pos3d: [-110, -60, 110],
  },
  {
    id: 'revit', title: 'Building BIM model', kind: 'model', category: 'site', status: 'Linked',
    summary: 'Revit model with façade panel zones and window schedule, linked by reference only.',
    why: 'Provides façade zones and panel IDs so captured images can be tagged to building elements.',
    origin: { kind: 'bim-link', name: 'Revit model reference (not uploaded)' }, owner: 'Architect of record',
    updatedAt: '2026-10-28', verification: 'Linked, not verified', importance: 'medium',
    openQuestion: 'Confirm the model version matches the as-built façade after the 2019 renovation.',
    canvas: { x: 40, y: 480 }, pos3d: [-150, -40, 60],
  },
  {
    id: 'objective', title: 'Inspection objectives', kind: 'document', category: 'requirements', status: 'Reviewed',
    summary: 'Find spalling, sealant failure, cracked masonry and loose elements; at least 2 mm/px imagery on north and east elevations.',
    why: 'Turns the brief into measurable capture targets.',
    origin: { kind: 'derived', name: 'Derived from client survey brief' }, owner: 'Project manager',
    updatedAt: '2026-11-06', verification: 'Reviewed by PM', importance: 'high',
    canvas: { x: 40, y: 205 }, pos3d: [-120, 100, -30],
  },
  {
    id: 'airspace', title: 'Airspace review', kind: 'constraint', category: 'regulatory', status: 'Review',
    summary: 'Site sits inside controlled airspace near heliport traffic. Authorization requirements still to be confirmed.',
    why: 'May restrict altitude and timing, or require authorization before any flight.',
    origin: { kind: 'external-api-planned', name: 'FAA airspace data (planned integration)' }, owner: 'Pilot in command',
    updatedAt: '2026-11-07', verification: 'No authoritative determination', importance: 'high',
    openQuestion: 'No authoritative airspace determination yet. Required before scheduling.',
    canvas: { x: 320, y: 70 }, pos3d: [30, 140, -110],
  },
  {
    id: 'weather', title: 'Weather window', kind: 'weather', category: 'weather', status: 'Monitor',
    summary: 'Wind and visibility thresholds for façade work. Sample outlook only.',
    why: 'Gusts at the roof edge and in the street canyon decide which days are workable.',
    origin: { kind: 'external-api-planned', name: 'Weather service (planned integration)' }, owner: 'Operations',
    updatedAt: null, verification: 'Sample, unverified', importance: 'medium',
    openQuestion: 'Sample data only. Connect a forecast before committing dates.',
    canvas: { x: 320, y: 205 }, pos3d: [140, 80, 70],
  },
  {
    id: 'safety', title: 'Safety & ground access', kind: 'constraint', category: 'safety', status: 'Review',
    summary: 'Sidewalk closure on Hudson St, pedestrian exclusion zone, launch point on the north plaza.',
    why: 'Sets launch and landing areas, spotter positions and permitted hours.',
    origin: { kind: 'manual', name: 'Site walk notes (sample)' }, owner: 'Safety officer',
    updatedAt: '2026-11-08', verification: 'In review', importance: 'high',
    openQuestion: 'Building management has not confirmed plaza access hours.',
    canvas: { x: 320, y: 340 }, pos3d: [-60, -150, -170],
  },
  {
    id: 'equipment', title: 'Equipment selection', kind: 'document', category: 'technical', status: 'Draft',
    summary: 'Enterprise quadcopter with a 20 MP zoom camera; tethered option for the street side under consideration.',
    why: 'Platform and sensor set achievable resolution and standoff.',
    origin: { kind: 'manual', name: 'Pilot draft' }, owner: 'Pilot',
    updatedAt: '2026-11-09', verification: 'Draft', importance: 'medium',
    canvas: { x: 320, y: 480 }, pos3d: [70, -70, -90],
  },
  {
    id: 'flight', title: 'Flight approach', kind: 'decision', category: 'technical', status: 'Proposed',
    summary: 'Vertical façade passes at 8–10 m standoff on north and east elevations, plus an orbit of the roof parapet.',
    why: 'Central decision: combines geometry, objectives, airspace and safety constraints.',
    origin: { kind: 'agent-proposed', name: 'Planning agent draft (simulated)' }, owner: 'Pilot',
    updatedAt: '2026-11-10', verification: 'Proposed, not approved', importance: 'high',
    openQuestion: 'Waiting on airspace review and safety sign-off before approval.',
    canvas: { x: 610, y: 140 }, pos3d: [40, 20, -10],
  },
  {
    id: 'schedule', title: 'Survey schedule', kind: 'decision', category: 'schedule', status: 'Pending',
    summary: 'Two half-day sessions on weekend mornings, with one backup day (sample dates).',
    why: 'Sequences capture around weather, access hours and authorizations.',
    origin: { kind: 'manual', name: 'PM planning notes' }, owner: 'Project manager',
    updatedAt: '2026-11-10', verification: 'Pending inputs', importance: 'medium',
    openQuestion: 'Dates are placeholders until weather and access are confirmed.',
    canvas: { x: 610, y: 340 }, pos3d: [210, -110, -40],
  },
  {
    id: 'capture', title: 'Capture plan', kind: 'output', category: 'technical', status: 'In progress',
    summary: 'Image overlap, gimbal angles and photo IDs per façade zone, mapped to BIM zones.',
    why: 'Defines exactly what gets collected; feeds the inspection package.',
    origin: { kind: 'derived', name: 'Derived from flight approach' }, owner: 'Pilot',
    updatedAt: '2026-11-11', verification: 'In progress', importance: 'medium',
    canvas: { x: 890, y: 205 }, pos3d: [110, -40, 110],
  },
  {
    id: 'report', title: 'Inspection package', kind: 'output', category: 'requirements', status: 'Planned',
    summary: 'Tagged defect imagery, elevation maps and condition ratings per façade zone.',
    why: 'The client deliverable. Must satisfy the survey brief.',
    origin: { kind: 'derived', name: 'Deliverable defined in brief' }, owner: 'Project manager',
    updatedAt: null, verification: 'Planned', importance: 'high',
    canvas: { x: 890, y: 400 }, pos3d: [-80, 50, 120],
  },
  {
    id: 'email', title: 'Site access email', kind: 'note', category: null, status: 'Unclassified',
    summary: 'Forwarded email from building management about loading-dock hours and roof access keys.',
    why: 'Might constrain launch times and roof access. Not yet reviewed.',
    origin: { kind: 'email', name: 'Forwarded email (sample)' }, owner: 'Unassigned',
    updatedAt: '2026-11-12', verification: 'Unreviewed', importance: 'low',
    openQuestion: 'Parked. Organize it into the graph, or remove it.',
    canvas: { x: 1170, y: 70 }, pos3d: [-150, -170, -90],
  },
  {
    id: 'ai', title: 'AI observation: potential roof wind exposure', kind: 'note', category: 'weather', status: 'Suggested',
    summary: 'Parapet geometry and the open river side suggest stronger gusts at roof level.',
    why: 'If confirmed, roof passes may need tighter wind limits.',
    origin: { kind: 'ai-generated', name: 'Graph assistant (simulated)' }, owner: 'AI · needs review',
    updatedAt: '2026-11-13', verification: 'AI-generated, unverified', importance: 'medium',
    openQuestion: 'AI-generated and unverified. Needs expert review.',
    canvas: { x: 1170, y: 205 }, pos3d: [180, 130, 40],
  },
]

export const EDGES: GraphEdge[] = [
  ['rfp', 'defines', 'objective'],
  ['site', 'informs', 'safety'],
  ['revit', 'shapes', 'flight'],
  ['objective', 'drives', 'flight'],
  ['airspace', 'constrains', 'flight'],
  ['weather', 'constrains', 'schedule'],
  ['safety', 'constrains', 'flight'],
  ['equipment', 'enables', 'capture'],
  ['flight', 'produces', 'capture'],
  ['schedule', 'sequences', 'capture'],
  ['capture', 'feeds', 'report'],
  ['rfp', 'specifies', 'report'],
].map(([source, relation, target]) => ({
  id: `${source}-${relation}-${target}`,
  source,
  target,
  relation,
  status: 'approved' as const,
  provenance: 'example' as const,
}))

export const CANDIDATES: Candidate[] = [
  { id: 'c-email-safety', source: 'email', target: 'safety', relation: 'informs', reason: 'Mentions loading-dock hours and roof access keys, which affect ground access.', state: 'pending' },
  { id: 'c-ai-weather', source: 'ai', target: 'weather', relation: 'refines', reason: 'Adds a roof-level wind exposure the general weather window does not cover.', state: 'pending' },
  { id: 'c-ai-flight', source: 'ai', target: 'flight', relation: 'affects', reason: 'Roof parapet orbit may need tighter wind limits if the exposure is real.', state: 'pending' },
  { id: 'c-weather-flight', source: 'weather', target: 'flight', relation: 'constrains', reason: 'Wind thresholds limit standoff and pass speed, not only the schedule.', state: 'pending' },
]

export type ComponentId = 'north' | 'east' | 'roof' | 'entrance' | 'upper'

export interface BuildingComponent {
  id: ComponentId
  label: string
  zone: string
  explanation: string
  concerns: string[]
  verification: string
  nodes: string[]
}

export const COMPONENTS: BuildingComponent[] = [
  {
    id: 'north', label: 'North façade', zone: 'Levels 2–11 · faces Hudson St',
    explanation: 'Primary street elevation with the most visible masonry and window sealant. Highest priority in the brief.',
    concerns: ['Pedestrian exclusion needed on the sidewalk below', 'Glare from late-morning sun on glazing'],
    verification: 'Geometry from sample parcel data; condition unknown until capture',
    nodes: ['site', 'safety', 'capture'],
  },
  {
    id: 'east', label: 'East elevation', zone: 'Levels 2–11 · side street',
    explanation: 'Secondary elevation with BIM panel zones defined. Narrow street limits standoff distance.',
    concerns: ['Narrow street canyon funnels wind', 'BIM zones need as-built confirmation'],
    verification: 'BIM linked, not verified',
    nodes: ['revit', 'weather', 'flight'],
  },
  {
    id: 'roof', label: 'Roof & parapet', zone: 'Roof level · about 49 m',
    explanation: 'Parapet coping and rooftop equipment. Most exposed to wind and closest to controlled airspace limits.',
    concerns: ['Possible elevated gusts (AI observation, unverified)', 'Airspace review still open'],
    verification: 'Exposure is an unverified AI observation',
    nodes: ['weather', 'airspace', 'ai'],
  },
  {
    id: 'entrance', label: 'Ground-level entrance', zone: 'Ground floor · north plaza',
    explanation: 'Main entrance and plaza used as the candidate launch area. Busy with pedestrians on weekdays.',
    concerns: ['Plaza access hours not confirmed', 'Loading dock activity mentioned in an unreviewed email'],
    verification: 'Access details pending building management',
    nodes: ['safety', 'email', 'schedule'],
  },
  {
    id: 'upper', label: 'Upper façade', zone: 'Levels 12–13 · setback',
    explanation: 'Setback upper storeys with terracotta cladding. Objectives call for close-up imagery here.',
    concerns: ['Setback geometry complicates standoff', 'Needs 2 mm/px resolution per objectives'],
    verification: 'Objectives reviewed; geometry from BIM reference',
    nodes: ['objective', 'revit', 'capture'],
  },
]

/** Sample-only outlook used on the overview board. Not a forecast. */
export const SAMPLE_WINDOW = [
  { day: 'Mon 16', tone: 'warn', note: 'Gusty afternoon' },
  { day: 'Tue 17', tone: 'ok', note: 'Calm morning' },
  { day: 'Wed 18', tone: 'bad', note: 'Rain band' },
  { day: 'Thu 19', tone: 'warn', note: 'Low cloud early' },
  { day: 'Fri 20', tone: 'ok', note: 'Light wind' },
  { day: 'Sat 21', tone: 'ok', note: 'Planned session 1' },
  { day: 'Sun 22', tone: 'warn', note: 'Backup day' },
] as const

export const INITIAL_LOG = [
  { at: '2026-11-13 09:12', who: 'Graph assistant (simulated)', text: 'Suggested a roof wind exposure note and 3 relationships' },
  { at: '2026-11-12 16:40', who: 'Inbox', text: 'Site access email arrived as an unclassified item' },
  { at: '2026-11-11 11:05', who: 'Pilot', text: 'Started the capture plan' },
  { at: '2026-11-10 14:22', who: 'Planning agent (simulated)', text: 'Proposed the flight approach' },
  { at: '2026-11-08 10:00', who: 'Safety officer', text: 'Logged site walk notes' },
]
