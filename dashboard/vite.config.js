import { defineConfig } from 'vite';
import { mkdirSync, copyFileSync } from 'node:fs';

export default defineConfig({
  plugins: [{ name: 'font-licenses', closeBundle() {
    mkdirSync('../blindspot/observer/dashboard_dist/licenses', { recursive: true });
    for (const family of ['mono', 'sans']) copyFileSync(`node_modules/@fontsource/ibm-plex-${family}/LICENSE`, `../blindspot/observer/dashboard_dist/licenses/IBM-Plex-${family}.txt`);
  } }],
  build: { outDir: '../blindspot/observer/dashboard_dist', emptyOutDir: true },
});
