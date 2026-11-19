import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page } from '@playwright/test';

import { createIsolatedWorkspace, createMember, signIn, type Credentials } from './support/api';
import {
  ONE_PIXEL_PNG,
  grantPlatformOperator,
  openFeedbackDialog,
  revokePlatformOperator,
  signInUi,
  submitFeedback,
  t,
  uniqueText,
  useLocale,
  type Locale,
} from './support/feedback';

/**
 * Accessibility for in-app feedback (spec 025, T079, FR-011, SC-007).
 *
 * WCAG 2.1 AA, zero violations, on the feedback dialog (with a screenshot preview), the member's
 * own list, the owner's workspace inbox and the operator triage page (with a submission open), in
 * English and in Arabic (RTL). Then the 360 px check from the edge cases, in both directions: the
 * control, its previews and the lists stay usable with no horizontal scrolling.
 *
 * One isolated workspace. Its owner is also made a platform operator (an operator is an existing
 * workspace member with a live operator row), so a single sign-in reaches every surface. The
 * language is saved on the member's profile, so every test sets the one it needs.
 */
const WCAG_21_AA = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];
const LOCALES: readonly Locale[] = ['en', 'ar'];

async function scan(page: Page) {
  return new AxeBuilder({ page }).withTags(WCAG_21_AA).exclude('.nav-item.disabled').analyze();
}

function describeViolations(results: Awaited<ReturnType<typeof scan>>): string {
  return results.violations
    .map((v) => `${v.id} (${v.impact}): ${v.help} — ${v.nodes.length} node(s)`)
    .join('\n');
}

async function expectNoHorizontalScroll(page: Page): Promise<void> {
  const size = await page.evaluate(() => ({
    content: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(size.content, 'the page scrolls horizontally').toBeLessThanOrEqual(size.viewport);
}

/** The box sits inside the viewport horizontally, whichever side it is anchored to. */
async function expectWithinViewport(page: Page, selector: string): Promise<void> {
  const box = await page.locator(selector).first().boundingBox();
  const width = page.viewportSize()?.width ?? 0;
  expect(box, `${selector} has no layout box`).not.toBeNull();
  if (!box) return;
  expect(box.x, `${selector} starts off-screen`).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width, `${selector} ends off-screen`).toBeLessThanOrEqual(width + 0.5);
}

test.describe('In-app feedback accessibility @a11y', () => {
  let workspace: Credentials;
  let ownerText: string;
  let memberText: string;

  test.beforeAll(async () => {
    workspace = await createIsolatedWorkspace();
    // Before the first UI sign-in: the shell reads operator status once per signed-in user.
    grantPlatformOperator(workspace.ownerEmail);
    const ownerToken = await signIn(workspace.ownerEmail, workspace.ownerPassword);

    // One item of the owner's own (with a screenshot, so the list renders a signed-URL image) and
    // one from a colleague, so the inbox shows the "From name (role)" line.
    ownerText = uniqueText('A11y owner feedback');
    await submitFeedback(ownerToken, { text: ownerText, category: 'bug', screenshot: true });
    const member = await createMember('buyer', ownerToken);
    memberText = uniqueText('A11y member feedback');
    await submitFeedback(await signIn(member.email, member.password), {
      text: memberText,
      category: 'idea',
    });
  });

  test.afterAll(() => {
    if (workspace) revokePlatformOperator(workspace.ownerEmail);
  });

  async function signInAs(page: Page, locale: Locale): Promise<void> {
    await signInUi(page, workspace.ownerEmail, workspace.ownerPassword);
    await useLocale(page, locale);
  }

  async function openDialogWithScreenshot(page: Page): Promise<void> {
    await openFeedbackDialog(page);
    const dialog = page.locator('mat-dialog-container');
    await dialog.locator('[data-test="image-input"]').setInputFiles({
      name: 'screenshot.png',
      mimeType: 'image/png',
      buffer: ONE_PIXEL_PNG,
    });
    await expect(dialog.locator('[data-test="thumb"]')).toHaveCount(1);
  }

  async function openOwnList(page: Page, locale: Locale): Promise<void> {
    await page.goto('/feedback');
    await expect(page.locator('h1')).toHaveText(t(locale, 'feedback.list.myTitle'));
    const own = page.locator('[data-test="card"]', { hasText: ownerText });
    await expect(own).toBeVisible();
    await expect(own.locator('img')).toBeVisible();
  }

  async function openInbox(page: Page, locale: Locale): Promise<void> {
    await page.goto('/feedback/workspace');
    await expect(page.locator('h1')).toHaveText(t(locale, 'feedback.list.workspaceTitle'));
    await expect(page.locator('[data-test="card"]', { hasText: memberText })).toBeVisible();
    await expect(page.locator('[data-test="submitter"]').first()).toBeVisible();
  }

  for (const locale of LOCALES) {
    const language = locale === 'en' ? 'English' : 'Arabic';

    test(`the feedback dialog in ${language} has no WCAG 2.1 AA violations @a11y`, async ({
      page,
    }) => {
      await signInAs(page, locale);
      await openDialogWithScreenshot(page);
      await expect(page.locator('[data-test="notice"]')).toHaveText(t(locale, 'feedback.notice'));
      const results = await scan(page);
      expect(results.violations, describeViolations(results)).toEqual([]);
    });

    test(`the own feedback list in ${language} has no WCAG 2.1 AA violations @a11y`, async ({
      page,
    }) => {
      await signInAs(page, locale);
      await openOwnList(page, locale);
      await page.waitForLoadState('networkidle');
      const results = await scan(page);
      expect(results.violations, describeViolations(results)).toEqual([]);
    });

    test(`the workspace feedback inbox in ${language} has no WCAG 2.1 AA violations @a11y`, async ({
      page,
    }) => {
      await signInAs(page, locale);
      await openInbox(page, locale);
      await page.waitForLoadState('networkidle');
      const results = await scan(page);
      expect(results.violations, describeViolations(results)).toEqual([]);
    });

    test(`the operator triage page in ${language} has no WCAG 2.1 AA violations @a11y`, async ({
      page,
    }) => {
      await signInAs(page, locale);
      await page.goto('/platform/feedback');
      await expect(page.locator('.page-title')).toHaveText(t(locale, 'platform.feedback.title'));
      const row = page.locator('[data-testid="feedback-row"]', { hasText: ownerText });
      await row.locator('.open-row').click();
      const detail = page.locator('[data-testid="feedback-detail"]');
      await expect(detail.locator('[data-testid="detail-email"]')).toHaveText(workspace.ownerEmail);
      await expect(detail.locator('.screenshots img')).toBeVisible();
      await page.waitForLoadState('networkidle');
      const results = await scan(page);
      expect(results.violations, describeViolations(results)).toEqual([]);
    });

    test(`at 360 px in ${language} (${locale === 'ar' ? 'RTL' : 'LTR'}) the control, previews and lists need no horizontal scrolling @a11y`, async ({
      page,
    }) => {
      // Language first, at the default size: the account menu is the switch the other specs use.
      await signInAs(page, locale);
      await page.setViewportSize({ width: 360, height: 740 });
      await page.reload();
      await expect(page.locator('html')).toHaveAttribute('dir', locale === 'ar' ? 'rtl' : 'ltr');

      await expectNoHorizontalScroll(page);
      await expectWithinViewport(page, 'app-feedback-widget [data-test="fab"]');

      await openDialogWithScreenshot(page);
      await expectWithinViewport(page, 'mat-dialog-container');
      await expectWithinViewport(page, '[data-test="thumb"]');
      await expectWithinViewport(page, 'mat-dialog-container [data-test="send"]');
      await expectNoHorizontalScroll(page);
      await page.locator('mat-dialog-container [data-test="close"]').click();
      await expect(page.locator('mat-dialog-container')).toBeHidden();

      await openOwnList(page, locale);
      await expectWithinViewport(page, '[data-test="card"]');
      await expectNoHorizontalScroll(page);

      await openInbox(page, locale);
      await expectWithinViewport(page, '[data-test="card"]');
      await expectNoHorizontalScroll(page);
    });
  }
});
