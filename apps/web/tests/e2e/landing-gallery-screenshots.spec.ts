/**
 * PPS-36 hosted gallery (developer machine only; never CI or local Supabase).
 *
 * From apps/web:
 *   CAPTURE_LANDING_GALLERY=1 pnpm run landing:screenshots
 *
 * Requires the untracked REPO-ROOT .env: DATABASE_URL (the demo pooler), SUPABASE_URL,
 * SUPABASE_SERVICE_ROLE_KEY. The fixture selects session mode :5432, even if .env has
 * :6543. Every Postgres connection goes through procurepilot_api.db.connect.
 * Optional E2E_BASE_URL defaults to https://procurepilot.iron-sys.com; E2E_API_URL defaults
 * to https://procurepilot-api.iron-sys.com/api/v1 (docs/quality/r4.3-release-evidence.md).
 * Both overrides must be hosted HTTPS URLs; the DB must remain the .env demo project.
 *
 * Creates/reuses ONLY slug landing-gallery-demo: one marked Auth owner, one membership,
 * three source PDFs/documents/quotations, two products/branches, budgets, a completed
 * advisory basket, a pending request, and verified/pending synthetic savings evidence.
 * Passwords are generated in memory and rotated for that marked owner on each run;
 * they never appear in argv, tracked files, traces or videos. No general seed.py/setup.
 * Extracted/reviewed rows are seeded deliberately: do not enqueue the real extraction
 * worker and introduce OCR/provider drift into this synthetic publication fixture.
 * Repeated runs reuse deterministic tenant-scoped rows and overwrite the same Storage
 * object paths. Never delete/update audit events or verified savings.
 *
 * Writes exactly ten 1440x900 JPEGs (quality 88) under public/landing/{en,ar}/.
 * Without CAPTURE_LANDING_GALLERY=1 every test is skipped and no hosted work runs.
 * --list is always offline, with or without the opt-in.
 */
import { execFileSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

import { expect, test, type Page } from '@playwright/test';

import { apiAsUser, setOwnerLocale } from './support/api';
import { settleGallery } from './support/screenshot-capture';

const ROOT = join(__dirname, '..', '..', '..', '..');
const SEED = 'apps/web/tests/e2e/support/gallery-fixtures.py';
const RUN = process.env['CAPTURE_LANDING_GALLERY'] === '1';
const WEB = process.env['E2E_BASE_URL'] ?? 'https://procurepilot.iron-sys.com';
const API = process.env['E2E_API_URL'] ?? 'https://procurepilot-api.iron-sys.com/api/v1';
const OWNER = {
  ownerEmail: 'nour.hassan@landing-gallery-demo.example.test',
  businessName: 'Fennel Courtyard · Synthetic demonstration data | فناء الشمر · بيانات اصطناعية',
};
interface GalleryState {
  token: string;
  refreshToken: string;
  quotationId: string;
  productId: string;
  basketId: string;
  savingId: string;
  verifiedDelta: string;
}
let state: GalleryState;

interface HostedManifest {
  tenantId: string;
  slug: string;
  ownerEmail: string;
  businessName: string;
  supabaseUrl: string;
  documents: { document_id: string; upload_url: string }[];
}

function requireHostedUrl(value: string): URL {
  const url = new URL(value);
  if (url.protocol !== 'https:' || ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) ||
    ['54321', '54322'].includes(url.port) || url.username || url.password) {
    throw new Error('Gallery targets must be hosted HTTPS endpoints; local Supabase is forbidden');
  }
  return url;
}

function requireHostedSetup(): void {
  if (!RUN || process.env['CI']) {
    throw new Error('Hosted gallery capture requires CAPTURE_LANDING_GALLERY=1 on a developer machine');
  }
  requireHostedUrl(WEB);
  requireHostedUrl(API);
  // Offline Python validation of .env and the session-pooler DSN, before any hosted request.
  python(['--check']);
}

function python(args: string[], input?: unknown): string {
  try {
    return execFileSync('uv', ['run', '--project', 'apps/api', 'python', SEED, ...args], {
      cwd: ROOT,
      env: { ...process.env, UV_CACHE_DIR: process.env['UV_CACHE_DIR'] ?? '/tmp/uv-cache-e2e' },
      input: input === undefined ? undefined : JSON.stringify(input),
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
      maxBuffer: 8 * 1024 * 1024,
    }).trim();
  } catch {
    // Child-process errors can embed their input or driver diagnostics. Never forward them.
    throw new Error('Gallery fixture operation failed; password and driver diagnostics omitted');
  }
}

async function buildGallery(): Promise<GalleryState> {
  requireHostedSetup();
  const password = `${randomBytes(32).toString('base64url')}aA1!`;
  const manifest = JSON.parse(python(['--bootstrap'], { password })) as HostedManifest;
  expect(manifest.slug).toBe('landing-gallery-demo');
  expect(manifest.ownerEmail).toBe(OWNER.ownerEmail);
  expect(manifest.businessName).toBe(OWNER.businessName);
  const storageOrigin = requireHostedUrl(manifest.supabaseUrl).origin;
  let session: { access_token: string; refresh_token: string };
  try {
    // Existing E2E login/API helpers; no shared owner, global setup, invitation seeder or file.
    session = await apiAsUser('', 'POST', '/auth/login', { email: OWNER.ownerEmail, password });
  } catch {
    throw new Error('Gallery owner API login failed (credentials omitted)');
  }
  const token = session.access_token;
  const tenant = await apiAsUser<{ id: string; slug: string }>(token, 'GET', '/tenant');
  expect(tenant.id).toBe(manifest.tenantId);
  expect(tenant.slug).toBe(manifest.slug);
  expect(manifest.documents).toHaveLength(3);
  for (let index = 0; index < manifest.documents.length; index++) {
    const bytes = Buffer.from(python(['--pdf', String(index)]), 'base64');
    const document = manifest.documents[index];
    const storage = requireHostedUrl(document.upload_url);
    expect(storage.origin).toBe(storageOrigin);
    expect(storage.pathname).toContain(`/quotation-documents/tenants/${manifest.tenantId}/quotations/${document.document_id}/`);
    // Plain Storage object URL, authorised by the fixture owner's JWT (SEND_SESSION_TOKEN
    // equivalent). Upsert replaces the same three owned objects, including after a partial run.
    const upload = await fetch(storage, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/pdf', 'x-upsert': 'true' },
      body: new Uint8Array(bytes),
    });
    expect(upload.ok, `Authenticated PDF upload failed (${upload.status})`).toBeTruthy();
    const { download_url } = await apiAsUser<{ download_url: string }>(token, 'GET', `/documents/${document.document_id}/download`);
    const downloadUrl = requireHostedUrl(download_url);
    expect(downloadUrl.origin).toBe(storageOrigin);
    expect(downloadUrl.pathname).toContain(`/tenants/${manifest.tenantId}/quotations/${document.document_id}/`);
    const download = await fetch(downloadUrl);
    expect(download.ok).toBeTruthy();
    expect(download.headers.get('content-type')).toContain('application/pdf');
    expect(Buffer.from(await download.arrayBuffer()).equals(bytes)).toBeTruthy();
  }
  const seeded = JSON.parse(python([], { tenantId: manifest.tenantId, ownerEmail: OWNER.ownerEmail })) as Omit<GalleryState, 'token' | 'refreshToken'>;
  // Publication checks on the real API: failures in evidence or pricing cannot be hidden by UI.
  const evidence = await apiAsUser<{
    saving_record: { status: string; delta: { amount: string; currency: string } };
    quotation: unknown;
    match_decision: unknown;
    calculation: { source_landed_cost_ids: string[] };
  }>(token, 'GET', `/savings/${seeded.savingId}/evidence`);
  expect(evidence.saving_record.status).toBe('verified');
  expect(Number(evidence.saving_record.delta.amount)).toBeGreaterThan(0);
  expect(evidence.saving_record.delta.currency).toBe('EGP');
  expect(evidence.quotation).toBeTruthy();
  expect(evidence.match_decision).toBeTruthy();
  expect(evidence.calculation.source_landed_cost_ids.length).toBeGreaterThan(0);
  const comparison = await apiAsUser<{
    offers: { landed_cost: { amount: string; currency: string } }[];
    recommendation: { recommended_offer_id: string } | null;
  }>(token, 'GET', `/offers/compare?product_id=${seeded.productId}&quantity=50`);
  expect(comparison.offers).toHaveLength(3);
  expect(comparison.offers.map(offer => offer.landed_cost.currency)).toEqual(['EGP', 'EGP', 'EGP']);
  expect(comparison.offers.map(offer => Number(offer.landed_cost.amount)).sort((a, b) => a - b)).toEqual([2040, 2250, 2360]);
  expect(comparison.recommendation).toBeTruthy();
  return { ...seeded, token, refreshToken: session.refresh_token };
}

/** Chrome's native PDF viewer must finish loading, not merely attach its iframe. */
async function expectRenderedPdf(page: Page): Promise<void> {
  await expect(page.locator('.pdf-preview-frame')).toBeVisible();
  await expect.poll(async () => {
    for (const frame of page.frames()) {
      const ready = await frame.evaluate(() => {
        const viewer = document.querySelector('pdf-viewer') as (HTMLElement & {
          loadProgress?: number;
          loadProgress_?: number;
          loadState?: string;
          loadState_?: string;
        }) | null;
        return viewer !== null && (viewer.loadProgress === 100 || viewer.loadProgress_ === 100 ||
          viewer.loadState === 'success' || viewer.loadState_ === 'success');
      }).catch(() => false);
      if (ready) return true;
    }
    return false;
  }, { message: 'Source PDF must render successfully in the native Chrome viewer', timeout: 30_000 }).toBeTruthy();
}

async function zoomDenseWorkspace(page: Page): Promise<void> {
  await page.evaluate(() => {
    const zoom = 0.8;
    document.documentElement.style.zoom = String(zoom);
    // CSS zoom scales vh too. Keep the existing flex shell filling the 900px capture,
    // as browser zoom would, instead of leaving an empty strip below a 720px shell.
    const shell = document.querySelector<HTMLElement>('.shell-container');
    if (!shell) throw new Error('The application shell did not render');
    shell.style.blockSize = `${window.innerHeight / zoom}px`;
  });
}

async function capture(page: Page, locale: 'en' | 'ar', name: string): Promise<void> {
  await settleGallery(page);
  await expect(page.locator('html')).toHaveAttribute('dir', locale === 'ar' ? 'rtl' : 'ltr');
  await expect(page.locator('html')).toHaveAttribute('lang', locale);
  await expect(page.locator('.workspace-badge')).toContainText('Synthetic demonstration data');
  await expect(page.locator('.workspace-badge')).toBeInViewport({ ratio: 1 });
  const directory = join(ROOT, 'apps/web/public/landing', locale);
  mkdirSync(directory, { recursive: true });
  await page.screenshot({ path: join(directory, `${name}.jpg`), type: 'jpeg', quality: 88, fullPage: false, animations: 'disabled' });
}

test.use({ trace: 'off', video: 'off', screenshot: 'off' });

test.describe('PPS-36 landing gallery: synthetic Cairo restaurant procurement', () => {
  test.skip(!RUN, 'Set CAPTURE_LANDING_GALLERY=1 to regenerate publication captures');
  test.describe.configure({ mode: 'serial', timeout: 120_000 });
  test.use({ viewport: { width: 1440, height: 900 }, timezoneId: 'Africa/Cairo', baseURL: WEB });
  test.beforeAll(async () => { state = await buildGallery(); });

  for (const locale of ['en', 'ar'] as const) {
    test.describe(`${locale} gallery`, () => {
      test.use({ locale: locale === 'ar' ? 'ar-EG' : 'en-GB' });
      test.beforeEach(async ({ page }) => {
        await setOwnerLocale(locale, state.token);
        await page.clock.setFixedTime(new Date('2026-10-22T09:00:00Z'));
        // Restore the real API-issued session in memory. No password enters the browser,
        // and ten captures do not require ten rate-limited login requests.
        await page.addInitScript(({ origin, accessToken, refreshToken }) => {
          if (location.origin === origin) {
            localStorage.setItem('pp.access_token', accessToken);
            localStorage.setItem('pp.refresh_token', refreshToken);
          }
        }, { origin: new URL(WEB).origin, accessToken: state.token, refreshToken: state.refreshToken });
        await page.goto('/home');
        await expect(page.locator('html')).toHaveAttribute('dir', locale === 'ar' ? 'rtl' : 'ltr');
        // Real navigation control: retain the application toolbar and give its tables space.
        await page.locator('.shell-toolbar > button').first().click();
        await expect(page.locator('.shell-sidenav')).not.toBeVisible();
      });

      test('01 quotation review: rendered source and extracted evidence', async ({ page }) => {
        await page.goto(`/quotations/${state.quotationId}/review`);
        await expect(page.locator('.status-reviewed')).toBeVisible();
        await expectRenderedPdf(page);
        await settleGallery(page);
        // 80% page zoom is applied to this dense review workspace; it
        // exposes both columns without masking fields or rearranging the shipped interface.
        await zoomDenseWorkspace(page);
        await page.locator('.side-by-side-layout').evaluate((element) => element.scrollIntoView({ block: 'start' }));
        await expect(page.locator('.pdf-preview-frame')).toBeInViewport({ ratio: 0.7 });
        await expect(page.locator('.line-panel').first()).toBeInViewport();
        await expect(page.locator('.provenance-card')).toBeInViewport();
        await expect(page.locator('.line-panel .confidence-pill').first()).toContainText('98%');
        await capture(page, locale, '01-quotation-review');
      });

      test('02 smart compare: three offers, conversion and recommendation evidence', async ({ page }) => {
        await page.goto(`/offers/compare?product_id=${state.productId}&quantity=2`);
        await expect(page.locator('.offers-table tr[mat-row]')).toHaveCount(3);
        // Match the dense quotation workspace's page zoom, retaining all controls and columns.
        await zoomDenseWorkspace(page);
        await expect(page.locator('.recommendation-card')).toBeVisible();
        await expect(page.locator('.evidence-chips')).toBeVisible();
        await expect(page.locator('.quantity-field mat-hint')).toContainText(locale === 'ar' ? '٢٥' : '25');
        await expect(page.locator('.cost-amount')).toContainText(locale === 'ar' ? '٢٬٠٤٠' : '2,040');
        await expect(page.locator('.expired-row')).toHaveCount(0);
        await expect(page.locator('.offers-table tr[mat-row]').last()).toBeInViewport({ ratio: 1 });
        await capture(page, locale, '02-smart-compare');
      });

      test('03 basket split: completed feasible allocation and recorded delivery', async ({ page }) => {
        await page.goto(`/offers/basket-split/${state.basketId}`);
        await expect(page.locator('.result-summary-card .status-pill.feasible')).toBeVisible();
        await expect(page.locator('.allocation-card')).toHaveCount(2);
        await expect(page.locator('.applied-constraints li')).toHaveCount(2);
        await expect(page.locator('.total-val')).toContainText(locale === 'ar' ? '٣٬٢٩٠' : '3,290');
        await expect(page.locator('.allocation-card').last()).toBeInViewport({ ratio: 1 });
        await capture(page, locale, '03-basket-split');
      });

      test('04 approval queue: priced branch request, budget and human actions', async ({ page }) => {
        await page.goto('/approvals');
        await expect(page.locator('tr.request-row')).toHaveCount(1);
        await expect(page.locator('.requester-cell')).toContainText('nour.hassan');
        await expect(page.locator('.branch-cell')).toContainText('المعادي');
        await expect(page.locator('.total-amount')).toContainText(locale === 'ar' ? '٣٬٢٩٠' : '3,290');
        await expect(page.locator('.incomplete-badge')).toHaveCount(0);
        await expect(page.locator('.budget-status-within')).toBeVisible();
        await expect(page.locator('.budget-remaining')).toContainText(locale === 'ar' ? '٢٠٬٠٠٠' : '20,000');
        await expect(page.locator('.approve-btn')).toBeEnabled();
        await expect(page.locator('.reject-btn')).toBeEnabled();
        await page.locator('.expand-lines-btn').click();
        await expect(page.locator('.detail-row-collapsed')).toHaveCount(0);
        await capture(page, locale, '04-approval-queue');
      });

      test('05 savings ledger: verified evidence and distinct pending outcome', async ({ page }) => {
        await page.goto('/savings');
        await expect(page.locator('.savings-table tr[mat-row]')).toHaveCount(2);
        await expect(page.locator('.savings-table .status-verified')).toHaveCount(1);
        await expect(page.locator('.savings-table .status-pending')).toHaveCount(1);
        await expect(page.locator('.total-savings-card .stat-value')).toContainText(locale === 'ar' ? '٥٦٠' : '560');
        await expect(page.locator('.savings-table [data-testid="baseline-policy"]')).toHaveCount(2);
        await expect(page.locator(`a[href="/savings/${state.savingId}/evidence"]`)).toBeVisible();
        await expect(page.locator('.savings-table tr[mat-row]').last()).toBeInViewport({ ratio: 1 });
        await capture(page, locale, '05-savings-ledger');
      });
    });
  }
});
