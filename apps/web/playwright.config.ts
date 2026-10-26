import { defineConfig, devices } from '@playwright/test';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

export const authFile = join(__dirname, 'tests', 'e2e', '.auth', 'owner.json');
export const baseStorageStateFile = join(__dirname, 'tests', 'e2e', '.auth', 'base-locale.json');

const baseURL = process.env['E2E_BASE_URL'] ?? 'http://localhost:4200';

export function createBaseStorageState(originUrl: string = baseURL): {
  cookies: never[];
  origins: { origin: string; localStorage: { name: string; value: string }[] }[];
} {
  return {
    cookies: [],
    origins: [
      {
        origin: new URL(originUrl).origin,
        localStorage: [
          { name: 'pp.locale', value: 'en' },
          { name: 'pp.locale.chosen', value: 'en' },
        ],
      },
    ],
  };
}

// Ensure the base storage state file exists before Playwright starts workers/projects
if (!existsSync(baseStorageStateFile)) {
  try {
    mkdirSync(dirname(baseStorageStateFile), { recursive: true });
    writeFileSync(baseStorageStateFile, JSON.stringify(createBaseStorageState(baseURL), null, 2));
  } catch {
    // Ignore static analysis write errors
  }
}

/**
 * End-to-end configuration.
 *
 * Uses the system Chrome via `channel: 'chrome'` rather than Playwright's bundled browsers.
 * That keeps the download out of CI images and off developer machines that are short on disk;
 * the trade-off is that a machine without Chrome installed cannot run these, so CI must
 * provide it.
 *
 * The stack must already be running — `docker compose up` plus `pnpm db:migrate` and
 * `pnpm db:seed`. These specs deliberately do not start it: an E2E suite that boots its own
 * infrastructure tends to test the boot script rather than the product.
 */
export default defineConfig({
  testDir: './tests/e2e',
  testMatch: '**/*.spec.ts',
  globalSetup: require.resolve('./tests/e2e/global-setup'),
  testIgnore: ['**/global-setup.ts', '**/landing-gallery-screenshots.spec.ts'],
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: process.env['CI'] ? 1 : 0,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: process.env['E2E_BASE_URL'] ?? 'http://localhost:4200',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    actionTimeout: 15_000,
    // PPS-34: Material 22 fades a closing mat-select panel for 100 ms, during which the
    // fading panel still intercepts clicks. If an E2E re-opens a select right after picking
    // an option, it clicks the old panel. Reduced motion makes Material detach panels immediately.
    reducedMotion: 'reduce',
  },
  projects: [
    {
      name: 'setup',
      testMatch: '**/auth.setup.ts',
      use: {
        ...devices['Desktop Chrome'],
        channel: 'chrome',
        storageState: baseStorageStateFile,
      },
    },
    {
      // No auth storageState here: setting it project-wide would silently hand the shared owner's
      // session to every spec using this project.
      // Only approval-queue.spec.ts and purchase-request-submission.spec.ts opt in, via their own `test.use({ storageState })`.
      // The baseStorageStateFile supplies 'pp.locale'='en' and 'pp.locale.chosen'='en' so unauthenticated
      // English E2E flows start in English without inheriting an authenticated session.
      name: 'chrome',
      dependencies: ['setup'],
      use: {
        ...devices['Desktop Chrome'],
        channel: 'chrome',
        storageState: baseStorageStateFile,
      },
    },
  ],
});
