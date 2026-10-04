import { defineConfig } from 'vite';
import { mkdirSync, copyFileSync } from 'node:fs';

export default defineConfig({
  plugins: [{ name: 'font-licenses', closeBundle() {
    mkdirSync('../blindspot/observer/dashboard_dist/licenses', { recursive: true });
    for (const family of ['ibm-plex-mono', 'eb-garamond', 'cormorant-garamond']) copyFileSync(`node_modules/@fontsource/${family}/LICENSE`, `../blindspot/observer/dashboard_dist/licenses/${family}.txt`);
  } }],
  build: { outDir: '../blindspot/observer/dashboard_dist', emptyOutDir: true },
});
