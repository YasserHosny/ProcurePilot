import AxeBuilder from '@axe-core/playwright';
import { test, expect, type BrowserContext, type Page } from '@playwright/test';

import {
  createIsolatedWorkspace,
  setOwnerLocale,
  signIn,
  type Credentials,
} from './support/api';
import { uploadQuotationAndOpenReview, waitForPreviewToSettle } from './support/canonical-flow';

/**
 * Accessibility and RTL for the populated quotation screens (PPS-162, P-130).
 *
 * quotation-a11y.spec.ts only scans empty and unknown states. This covers WCAG 2.1 AA in English
 * and in Arabic (RTL) on the review queue with a row and a filter chip, and on a real quotation in
 * review with its Retry-extraction and Archive confirmations open. One isolated workspace, one
 * sign-in, so the auth rate limit stays out of the way.
 */
const WCAG_21_AA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];
const BASE_URL = process.env['E2E_BASE_URL'] ?? 'http://localhost:4200';
const HEADER_FIELD_COUNT = 6;

interface ReviewLabels {
  readonly retryButton: string;
  readonly retryDialog: string;
  readonly archiveButton: string;
  readonly archiveDialog: string;
}

const ENGLISH_LABELS: ReviewLabels = {
  retryButton: 'Retry Extraction',
  retryDialog: 'Re-run extraction?',
  archiveButton: 'Archive',
  archiveDialog: 'Archive this quotation?',
};

const ARABIC_LABELS: ReviewLabels = {
  retryButton: 'إعادة الاستخراج',
  retryDialog: 'إعادة تشغيل الاستخراج؟',
  archiveButton: 'أرشفة',
  archiveDialog: 'أرشفة عرض السعر هذا؟',
};

async function scan(page: Page) {
  return new AxeBuilder({ page }).withTags(WCAG_21_AA).exclude('.nav-item.disabled').analyze();
}

function describeViolations(results: Awaited<ReturnType<typeof scan>>): string {
  return results.violations
    .map((v) => `${v.id} (${v.impact}): ${v.help} — ${v.nodes.length} node(s): ${v.nodes
      .slice(0, 3)
      .map((n) => n.target.join(' '))
      .join(' | ')}`)
    .join('\n');
}

test.describe.configure({ mode: 'serial' });

test.describe('Populated quotation screens accessibility @a11y', () => {
  let context: BrowserContext;
  let page: Page;
  let credentials: Credentials;
  let token: string;
  let quotationId: string;

  test.beforeAll(async ({ browser }) => {
    test.setTimeout(300_000);
    credentials = await createIsolatedWorkspace();
    token = await signIn(credentials.ownerEmail, credentials.ownerPassword);

    context = await browser.newContext({ baseURL: BASE_URL });
    page = await context.newPage();
    await page.goto('/auth/sign-in');
    await page.evaluate(() => localStorage.clear());
    await page.fill('input[formControlName="email"]', credentials.ownerEmail);
    await page.fill('input[formControlName="password"]', credentials.ownerPassword);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/home');

    // The stub extraction always leaves an arithmetic mismatch, so this one upload is both the
    // quotation in review and the row in the review queue.
    quotationId = await uploadQuotationAndOpenReview(page, 'quotation_detail_a11y.pdf');
  });

  test.afterAll(async () => {
    await context?.close();
  });

  async function expectNoViolations(): Promise<void> {
    const results = await scan(page);
    expect(results.violations, describeViolations(results)).toEqual([]);
  }

  async function open(url: string, ready: string, dir: 'ltr' | 'rtl'): Promise<void> {
    await page.goto(url);
    await expect(page.locator('html')).toHaveAttribute('dir', dir);
    await expect(page.locator(ready).first()).toBeVisible();
    await page.waitForLoadState('networkidle');
  }

  async function openDetail(dir: 'ltr' | 'rtl'): Promise<void> {
    await open(`/quotations/${quotationId}/review`, '.header-form-grid', dir);
    await expect(page.locator('.header-form-grid .field-box')).toHaveCount(HEADER_FIELD_COUNT);
    // Chrome's PDF viewer can take focus as it loads, which would break the focus-return checks.
    await waitForPreviewToSettle(page);
  }

  /** Scans with the confirmation open, then closes it with Escape and checks focus comes back. */
  async function expectAccessibleConfirmation(
    buttonName: string,
    dialogName: string,
    dir: 'ltr' | 'rtl',
  ): Promise<void> {
    await openDetail(dir);
    const trigger = page.locator('.header-actions').getByRole('button', { name: buttonName, exact: true });
    await trigger.click();

    const dialog = page.getByRole('dialog', { name: dialogName, exact: true });
    await expect(dialog).toBeVisible();
    // Focus lands on the first button once the dialog has finished opening.
    await expect(dialog.getByRole('button').first()).toBeFocused();
    await expectNoViolations();

    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  }

  function suite(label: string, dir: 'ltr' | 'rtl', labels: ReviewLabels): void {
    test(`the review queue with a row and a filter chip in ${label} has no WCAG 2.1 AA violations @a11y`, async () => {
      await open('/quotations?status=all', 'tr.clickable-row', dir);
      await expect(page.locator('[data-testid="chip-status"]')).toBeVisible();
      await expectNoViolations();
    });

    // Selecting a file starts the upload in the same tick, so the file card and its remove button never render.
    test.fixme(`the upload page with a chosen file in ${label} has no WCAG 2.1 AA violations @a11y`, async () => {
      await open('/quotations/upload', 'input.file-input', dir);
      await page.setInputFiles('input.file-input', {
        name: 'chosen_file_a11y.pdf',
        mimeType: 'application/pdf',
        buffer: Buffer.from(`%PDF-1.4\n% ${Date.now()}\n%%EOF`),
      });
      await expect(page.locator('.selected-file-card button')).toBeVisible();
      await expectNoViolations();
    });

    test(`a quotation in review in ${label} has no WCAG 2.1 AA violations @a11y`, async () => {
      await openDetail(dir);
      await expectNoViolations();
    });

    test(`the Retry-extraction confirmation in ${label} has no violations and returns focus @a11y`, async () => {
      await expectAccessibleConfirmation(labels.retryButton, labels.retryDialog, dir);
    });

    test(`the Archive confirmation in ${label} has no violations and returns focus @a11y`, async () => {
      await expectAccessibleConfirmation(labels.archiveButton, labels.archiveDialog, dir);
    });
  }

  suite('English', 'ltr', ENGLISH_LABELS);

  test('switch the workspace to Arabic', async () => {
    await setOwnerLocale('ar', token);
    await page.goto('/home');
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  });

  suite('Arabic (RTL)', 'rtl', ARABIC_LABELS);

  test('the document is RTL and the header field boxes keep their group names in Arabic @a11y', async () => {
    await openDetail('rtl');
    expect(await page.evaluate(() => document.documentElement.dir)).toBe('rtl');

    const groups = page.locator('.header-form-grid').getByRole('group');
    await expect(groups).toHaveCount(HEADER_FIELD_COUNT);
    for (const group of await groups.all()) {
      // Arabic script, so an untranslated key or an English fallback does not pass as a name.
      await expect(group).toHaveAttribute('aria-label', /[؀-ۿ]/);
    }
  });

  test.afterAll(async () => {
    if (token) await setOwnerLocale('en', token);
  });
});
