/**
 * Helpers for the in-app feedback specs (spec 025, T078 and T079).
 *
 * Seeding goes through the real API, as the rest of `support/` does: a submission made here is
 * stored, audited and cooled down exactly as one sent from the widget. Operator access has no
 * API or UI by design (research D2), so it is granted with the same operator CLI the team uses,
 * which writes the `platform_operator` row and its audit event in one transaction.
 */

import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { expect, type Page } from '@playwright/test';

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000/api/v1';

// support/ -> e2e -> tests -> web -> apps -> repo root.
const REPO_ROOT = join(__dirname, '..', '..', '..', '..', '..');

export type FeedbackCategory = 'bug' | 'idea' | 'question' | 'other';
export type Locale = 'en' | 'ar';

export interface SeededSubmission {
  id: string;
  text: string;
  status: 'new' | 'reviewed' | 'resolved';
  category: FeedbackCategory | null;
  can_withdraw: boolean;
}

/** A valid 1x1 PNG: the API checks the type from the bytes, so a fake image would be refused. */
export const ONE_PIXEL_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64',
);

/** A unique marker for one test's feedback text, so a list holding other runs' items stays unambiguous. */
export function uniqueText(prefix: string): string {
  return `${prefix} ${Date.now()}-${Math.floor(Math.random() * 100000)}`;
}

/**
 * Sends feedback as `token`'s member through `POST /feedback` (multipart, with an Idempotency-Key).
 * Each member is subject to the 30 s cooldown, so a spec uses one member per seeded submission.
 */
export async function submitFeedback(
  token: string,
  options: { text: string; category?: FeedbackCategory; screenshot?: boolean },
): Promise<SeededSubmission> {
  const form = new FormData();
  form.append('text', options.text);
  if (options.category) form.append('category', options.category);
  if (options.screenshot) {
    form.append('images', new Blob([ONE_PIXEL_PNG], { type: 'image/png' }), 'screenshot.png');
  }
  const response = await fetch(`${API}/feedback`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Idempotency-Key': crypto.randomUUID() },
    body: form,
  });
  if (!response.ok) {
    throw new Error(`POST /feedback → ${response.status}: ${await response.text()}`);
  }
  return (await response.json()) as SeededSubmission;
}

/** The HTTP status of an authenticated call, for asserting refusals ("not found", never "forbidden"). */
export async function apiStatus(
  token: string,
  method: 'GET' | 'PATCH' | 'DELETE',
  path: string,
  body?: unknown,
): Promise<number> {
  const response = await fetch(`${API}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...(method === 'GET' ? {} : { 'Idempotency-Key': crypto.randomUUID() }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return response.status;
}

/**
 * Environment for the operator CLI. It loads the API's full Settings, not only DATABASE_URL, so it
 * gets the same values CI's "Start the API" step gives the API under test. Anything already in
 * the environment wins; the Supabase keys are required by Settings but never used by the CLI,
 * which only talks to Postgres.
 */
function operatorCliEnv(): NodeJS.ProcessEnv {
  const supabaseUrl = process.env['SUPABASE_URL'] ?? 'http://127.0.0.1:54321';
  return {
    API_HOST: '127.0.0.1',
    API_PORT: '8000',
    API_ENV: 'local',
    API_LOG_LEVEL: 'info',
    API_CORS_ORIGINS: 'http://localhost:4200',
    SUPABASE_JWT_AUDIENCE: 'authenticated',
    SUPABASE_JWT_ISSUER: `${supabaseUrl}/auth/v1`,
    PLATFORM_INVITATION_TTL_DAYS: '7',
    MEMBER_INVITATION_TTL_DAYS: '7',
    RATE_LIMIT_AUTH: '60/minute',
    SUPABASE_ANON_KEY: 'unused-by-platform-operator-cli',
    SUPABASE_SERVICE_ROLE_KEY: 'unused-by-platform-operator-cli',
    ...process.env,
    SUPABASE_URL: supabaseUrl,
    // Same database the other fixtures seed (seed.py, db.ts): the one the API under test reads.
    DATABASE_URL:
      process.env['E2E_DATABASE_URL'] ?? 'postgresql://postgres:postgres@localhost:54322/postgres',
    UV_CACHE_DIR: process.env['UV_CACHE_DIR'] ?? '/tmp/uv-cache-e2e',
  };
}

function runOperatorCli(command: 'grant' | 'revoke', email: string): string {
  const args = ['run', '--project', 'apps/api', 'python', '-m',
    'procurepilot_api.workers.platform_operator_cli', command, email];
  if (command === 'grant') args.push('--granted-by', 'e2e');
  return execFileSync('uv', args, { cwd: REPO_ROOT, env: operatorCliEnv(), encoding: 'utf-8' });
}

/** Makes an existing workspace member a platform operator. Grant before the member signs in. */
export function grantPlatformOperator(email: string): void {
  const out = runOperatorCli('grant', email);
  if (!out.includes('granted:')) {
    throw new Error(`platform_operator_cli grant ${email} did not confirm: ${out}`);
  }
}

/** Withdraws operator access; a no-op when there is none, so it is safe in afterAll. */
export function revokePlatformOperator(email: string): void {
  runOperatorCli('revoke', email);
}

type Catalogue = Record<string, unknown>;
const catalogues = new Map<Locale, Catalogue>();

function catalogue(locale: Locale): Catalogue {
  let loaded = catalogues.get(locale);
  if (!loaded) {
    loaded = JSON.parse(
      readFileSync(join(REPO_ROOT, 'packages', 'i18n', `${locale}.json`), 'utf-8'),
    ) as Catalogue;
    catalogues.set(locale, loaded);
  }
  return loaded;
}

/** The catalogue string for `key` (dotted), with `{{param}}` interpolation as ngx-translate does it. */
export function t(locale: Locale, key: string, params: Record<string, string | number> = {}): string {
  let node: unknown = catalogue(locale);
  for (const part of key.split('.')) {
    node = typeof node === 'object' && node !== null ? (node as Catalogue)[part] : undefined;
  }
  if (typeof node !== 'string') {
    throw new Error(`i18n key ${key} is missing from ${locale}.json`);
  }
  return node.replace(/\{\{\s*(\w+)\s*\}\}/g, (match, name: string) =>
    name in params ? String(params[name]) : match,
  );
}

/** Signs in through the UI and waits for the shell, as every other spec does. */
export async function signInUi(page: Page, email: string, password: string): Promise<void> {
  await page.goto('/auth/sign-in');
  await page.fill('input[formControlName="email"]', email);
  await page.fill('input[formControlName="password"]', password);
  await page.click('button[type="submit"]');
  await page.waitForURL('**/home');
}

/**
 * Puts the signed-in member in `locale` through the account menu, the way the other a11y specs
 * switch. The choice is saved on the member's profile, so a spec reusing one member calls this
 * every test instead of assuming the last test's language.
 */
export async function useLocale(page: Page, locale: Locale): Promise<void> {
  const dir = locale === 'ar' ? 'rtl' : 'ltr';
  if ((await page.locator('html').getAttribute('dir')) !== dir) {
    await page.click('.account-btn');
    await page.click(locale === 'ar' ? 'button:has-text("العربية")' : 'button:has-text("English")');
  }
  await expect(page.locator('html')).toHaveAttribute('dir', dir);
}

/** Opens the feedback dialog from the shell's floating control and waits for it to settle. */
export async function openFeedbackDialog(page: Page): Promise<void> {
  await page.locator('app-feedback-widget [data-test="fab"]').click();
  await expect(page.locator('mat-dialog-container')).toBeVisible();
  await page.evaluate(() =>
    Promise.all(
      document
        .getAnimations()
        .filter((animation) => animation.effect?.getComputedTiming().iterations !== Infinity)
        .map((animation) => animation.finished.catch(() => undefined)),
    ),
  );
}
