import { defineConfig } from '@playwright/test';

/**
 * Visual regression of the public office demo through the capture page.
 * Baselines are rendered on Linux with SwiftShader: run `npm run test:visual` (Docker) locally
 * so they match CI. `npm run test:visual:update` rewrites them after an intended change.
 */
const PREVIEW_PORT = 4188;

export default defineConfig({
  testDir: 'tests/visual',
  snapshotPathTemplate: '{testDir}/__screenshots__/{arg}{ext}',
  timeout: 600_000,
  // Each software-rendered view saturates the CPU; running them side by side only slows all of them.
  workers: 1,
  expect: { toHaveScreenshot: { maxDiffPixelRatio: 0.01, threshold: 0.2 } },
  use: {
    baseURL: `http://127.0.0.1:${PREVIEW_PORT}`,
    launchOptions: { args: ['--ignore-gpu-blocklist', '--enable-unsafe-swiftshader'] },
  },
  webServer: {
    command: `npm run build && npx vite preview --config apps/room-viewer/vite.config.ts --host 127.0.0.1 --port ${PREVIEW_PORT} --strictPort`,
    url: `http://127.0.0.1:${PREVIEW_PORT}/tools/capture.html`,
    timeout: 180_000,
    reuseExistingServer: false,
  },
});
