// Internal: renders one still of the building for the image tiles (open with ?shot=<component>).
// Used only to generate src/assets/comp-*.jpg; not linked from the app.
import BuildingScene from './components/BuildingScene'
import type { ComponentId } from './data/sampleProject'

// eslint-disable-next-line react-refresh/only-export-components
export const SHOTS: Record<ComponentId, { pos: [number, number, number]; target: [number, number, number] }> = {
  north: { pos: [-48, 30, -98], target: [0, 22, 0] },
  east: { pos: [104, 32, -34], target: [0, 22, 0] },
  roof: { pos: [52, 108, -62], target: [0, 44, 0] },
  entrance: { pos: [-30, 10, -64], target: [0, 7, -8] },
  upper: { pos: [62, 64, -64], target: [0, 42, 0] },
}

export default function ShotView({ id }: { id: ComponentId }) {
  return (
    <div style={{ position: 'fixed', inset: 0, background: '#fff' }}>
      <BuildingScene mono selected={id} labels={false} interactive={false} view={SHOTS[id]} />
    </div>
  )
}
