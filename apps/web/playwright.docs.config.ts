import baseConfig from './playwright.config';

import { defineConfig } from '@playwright/test';

export default defineConfig({
  ...baseConfig,
  globalSetup: undefined,
  testMatch: ['**/user-documentation-screenshots.spec.ts'],
});
