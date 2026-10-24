import baseConfig from './playwright.config';

import { defineConfig } from '@playwright/test';

export default defineConfig({
  ...baseConfig,
  testMatch: ['**/user-documentation-screenshots.spec.ts'],
  // Never retry a capture. The spec runs serially and seeds its sample data in the run itself,
  // so a retry re-runs the whole group and seeds a second copy. The screenshots then show
  // duplicated products, suppliers and quotations (PPS-46). A failed capture must fail the run,
  // not produce images that look right but carry doubled sample data.
  retries: 0,
});
