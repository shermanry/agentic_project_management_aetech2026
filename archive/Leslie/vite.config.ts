import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { viteSingleFile } from 'vite-plugin-singlefile'

// `npm run build:single` bundles everything into one HTML file (handy for sharing a demo).
const converter = { '/api': 'http://127.0.0.1:8765', '/files': 'http://127.0.0.1:8765' }

export default defineConfig(({ mode }) => ({
  plugins: [react(), ...(mode === 'single' ? [viteSingleFile()] : [])],
  // The converter service (Minh/converter): `python -m converter serve` listens on 8765.
  server: { proxy: converter },
  preview: { proxy: converter },
}))
