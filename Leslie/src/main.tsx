import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import ShotView from './ShotView.tsx'
import type { ComponentId } from './data/sampleProject'

const shot = new URLSearchParams(location.search).get('shot') as ComponentId | null

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {shot ? <ShotView id={shot} /> : <App />}
  </StrictMode>,
)
