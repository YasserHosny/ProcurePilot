import { defineConfig, devices } from '@playwright/test';
import { join } from 'node:path';

const authFile = join(__dirname, 'tests', 'e2e', '.auth', 'owner.json');

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
  testIgnore: ['**/global-setup.ts'],
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
  },
  projects: [
    {
      name: 'setup',
      testMatch: '**/auth.setup.ts',
    },
    {
      name: 'chrome',
      dependencies: ['setup'],
      use: {
        ...devices['Desktop Chrome'],
        channel: 'chrome',
        storageState: authFile,
      },
    },
  ],
});
