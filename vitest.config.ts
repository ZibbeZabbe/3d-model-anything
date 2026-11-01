import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    exclude: ['tests/visual/**', '**/node_modules/**', '**/mutants/**', '.stryker-tmp/**'],
    include: ['packages/**/*.test.ts', 'demos/**/*.test.ts', 'apps/room-viewer/**/*.test.ts', '.agents/**/*.test.mjs'],
    environment: 'node',
    coverage: {
      provider: 'v8',
      include: ['packages/**/*.ts'],
      exclude: ['**/*.test.ts'],
      reporter: ['text', 'html'],
      reportsDirectory: 'coverage',
    },
  },
});
