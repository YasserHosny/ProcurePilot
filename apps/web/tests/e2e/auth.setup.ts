import { mkdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { test as setup, expect } from '@playwright/test';

import { credentials } from './support/api';

const authFile = join(__dirname, '.auth', 'owner.json');

setup('authenticate shared owner once', async ({ page }) => {
  const { ownerEmail, ownerPassword } = credentials();
  await page.goto('/auth/sign-in');
  await page.fill('input[formControlName="email"]', ownerEmail);
  await page.fill('input[formControlName="password"]', ownerPassword);
  await page.click('button[type="submit"]');
  await page.waitForURL('**/home');
  await expect(page).toHaveURL(/\/home$/);

  // Ensure authenticated storage state explicitly carries English locale preference
  await page.evaluate(() => {
    localStorage.setItem('pp.locale', 'en');
    localStorage.setItem('pp.locale.chosen', 'en');
  });

  await mkdir(dirname(authFile), { recursive: true });
  await page.context().storageState({ path: authFile });
});
