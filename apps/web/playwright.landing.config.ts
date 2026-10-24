import { defineConfig, devices } from '@playwright/test';

/** Hosted gallery only: deliberately no general E2E global setup or auth dependencies. */
export default defineConfig({
  testDir: './tests/e2e',
  testMatch: '**/landing-gallery-screenshots.spec.ts',
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: process.env['E2E_BASE_URL'] ?? 'https://procurepilot.iron-sys.com',
    actionTimeout: 20_000,
    reducedMotion: 'reduce',
    // Sign-in credentials exist only in memory; never put them into traces or videos.
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
  projects: [{ name: 'chrome', use: { ...devices['Desktop Chrome'], channel: 'chrome' } }],
});
