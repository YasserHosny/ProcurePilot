import { test, expect, type Browser, type BrowserContext, type Page } from '@playwright/test';

import {
  createIsolatedWorkspace,
  createMember,
  signIn,
  type CreatedMember,
  type Credentials,
} from './support/api';
import {
  apiStatus,
  grantPlatformOperator,
  openFeedbackDialog,
  revokePlatformOperator,
  signInUi,
  submitFeedback,
  t,
  uniqueText,
  useLocale,
} from './support/feedback';

/**
 * In-app feedback end to end (spec 025, T078): submit, own list, owner inbox, operator triage and
 * withdraw, against the real API.
 *
 * Two isolated workspaces, never the shared global owner:
 * - workspace A, whose owner reads the read-only inbox and whose members submit;
 * - an "ops" workspace standing in for ProcurePilot's own, whose owner is made a platform
 *   operator with the operator CLI. Feedback sent there proves triage spans workspaces and the
 *   owner inbox does not.
 *
 * Every test makes its own submitter: the API refuses a member's second submission within 30 s
 * (FR-007), so sharing one member would make the tests depend on their order and timing.
 */
const en = (key: string, params?: Record<string, string | number>) => t('en', key, params);

test.describe('In-app feedback (spec 025, T078)', () => {
  let workspaceA: Credentials;
  let ownerToken: string;
  let ops: Credentials;
  let opsToken: string;
  let opsText: string;

  test.beforeAll(async () => {
    workspaceA = await createIsolatedWorkspace();
    ownerToken = await signIn(workspaceA.ownerEmail, workspaceA.ownerPassword);

    ops = await createIsolatedWorkspace();
    grantPlatformOperator(ops.ownerEmail);
    opsToken = await signIn(ops.ownerEmail, ops.ownerPassword);
    opsText = uniqueText('Ops workspace feedback');
    await submitFeedback(opsToken, { text: opsText, category: 'other' });
  });

  test.afterAll(() => {
    if (ops) revokePlatformOperator(ops.ownerEmail);
  });

  async function newMember(role: string): Promise<CreatedMember & { token: string }> {
    const member = await createMember(role, ownerToken);
    return { ...member, token: await signIn(member.email, member.password) };
  }

  async function signInEnglish(page: Page, email: string, password: string): Promise<void> {
    await signInUi(page, email, password);
    await useLocale(page, 'en');
  }

  /** A second person in the same test gets their own browser context, so sessions never mix. */
  const extraContexts: BrowserContext[] = [];
  async function asUser(browser: Browser, email: string, password: string): Promise<Page> {
    const context = await browser.newContext();
    extraContexts.push(context);
    const page = await context.newPage();
    await signInEnglish(page, email, password);
    return page;
  }

  test.afterEach(async () => {
    await Promise.all(extraContexts.splice(0).map((context) => context.close()));
  });

  function card(page: Page, text: string) {
    return page.locator('[data-test="card"]', { hasText: text });
  }

  test('a viewer sends feedback from the widget and sees it in their own list as new (US1, FR-001/002/002a/007/010)', async ({
    page,
  }) => {
    const viewer = await newMember('viewer');
    await signInEnglish(page, viewer.email, viewer.password);

    // FR-001: the control is on every signed-in page, not only home.
    await page.goto('/feedback');
    await openFeedbackDialog(page);
    const dialog = page.locator('mat-dialog-container');

    // FR-010 / US1-7: the staff-visibility notice is shown whenever the control is open.
    await expect(dialog.locator('[data-test="notice"]')).toHaveText(en('feedback.notice'));
    await expect(dialog.locator('[data-test="counter"]')).toHaveText(
      en('feedback.widget.charsLeft', { count: 2000 }),
    );

    // US1-2: an empty or whitespace-only message is blocked with a validation message.
    await dialog.locator('textarea').fill('   ');
    await dialog.locator('[data-test="send"]').click();
    await expect(dialog.locator('[data-test="text-error"]')).toHaveText(
      en('feedback.errors.textRequired'),
    );

    // US1-1 and US1-8: a message with a chosen category is saved and confirmed.
    const text = uniqueText('Viewer widget feedback');
    await dialog.locator('textarea').fill(text);
    await dialog.locator('mat-select').click();
    await page.locator('mat-option', { hasText: en('feedback.category.bug') }).click();
    await dialog.locator('[data-test="send"]').click();
    await expect(dialog.locator('[data-test="success"]')).toContainText(
      en('feedback.widget.successTitle'),
    );

    // US1-4 / FR-007: a second send within 30 s is refused with the time left; the draft is kept.
    await dialog.locator('[data-test="close"]').click();
    await expect(dialog).toBeHidden();
    await openFeedbackDialog(page);
    const second = uniqueText('Second message inside the cooldown');
    await dialog.locator('textarea').fill(second);
    await dialog.locator('[data-test="send"]').click();
    await expect(dialog.locator('[data-test="cooldown"]')).toContainText(
      en('feedback.widget.draftKept'),
    );
    await expect(dialog.locator('[data-test="send"]')).toBeDisabled();
    await expect(dialog.locator('textarea')).toHaveValue(second);
    await dialog.locator('[data-test="close"]').click();

    // FR-012: the submission is in the sender's own list, status new, with its category,
    // and can still be withdrawn.
    await page.goto('/feedback');
    await expect(page.locator('h1')).toHaveText(en('feedback.list.myTitle'));
    const sent = card(page, text);
    await expect(sent).toBeVisible();
    await expect(sent.locator('[data-test="status"]')).toHaveText(en('feedback.status.new'));
    await expect(sent.locator('[data-test="category"]')).toHaveText(en('feedback.category.bug'));
    await expect(sent.locator('[data-test="withdraw"]')).toBeVisible();
    // The refused second send created nothing.
    await expect(card(page, second)).toHaveCount(0);
    // A viewer is not the owner, so there is no way into the workspace inbox from here.
    await expect(page.locator('[data-test="workspace-link"]')).toHaveCount(0);
  });

  test('members see only their own feedback; the owner inbox shows the whole workspace read-only (US4-1..4, FR-012/013/014)', async ({
    page,
    browser,
  }) => {
    const buyer = await newMember('buyer');
    const approver = await newMember('approver');
    const buyerText = uniqueText('Buyer inbox feedback');
    const approverText = uniqueText('Approver inbox feedback');
    await submitFeedback(buyer.token, { text: buyerText, category: 'idea' });
    await submitFeedback(approver.token, { text: approverText });

    // US4-1: the buyer's list holds their own item and not a colleague's.
    await signInEnglish(page, buyer.email, buyer.password);
    await page.goto('/feedback');
    await expect(card(page, buyerText)).toBeVisible();
    await expect(card(page, approverText)).toHaveCount(0);

    // US4-4: a buyer cannot open the workspace inbox, in the UI or through the API.
    await page.goto('/feedback/workspace');
    await expect(page).not.toHaveURL(/\/feedback\/workspace/);
    expect(await apiStatus(buyer.token, 'GET', '/feedback')).toBe(404);

    // US4-2: the owner sees both members' items, and nothing from another workspace.
    const owner = await asUser(browser, workspaceA.ownerEmail, workspaceA.ownerPassword);
    await owner.goto('/feedback');
    await owner.locator('[data-test="workspace-link"]').click();
    await owner.waitForURL('**/feedback/workspace');
    await expect(owner.locator('h1')).toHaveText(en('feedback.list.workspaceTitle'));
    const buyerCard = card(owner, buyerText);
    await expect(buyerCard).toBeVisible();
    await expect(buyerCard.locator('[data-test="category"]')).toHaveText(
      en('feedback.category.idea'),
    );
    await expect(card(owner, approverText)).toBeVisible();
    await expect(card(owner, opsText)).toHaveCount(0);

    // US4-3 / FR-014: read-only. No withdraw, and no status or label control on any card.
    await expect(owner.locator('[data-test="withdraw"]')).toHaveCount(0);
    await expect(owner.locator('[data-test="card"] button')).toHaveCount(0);
    // The owner cannot reach triage either (US5-5): the UI redirects and the API says not found.
    await owner.goto('/platform/feedback');
    await expect(owner).not.toHaveURL(/\/platform\/feedback/);
    expect(await apiStatus(ownerToken, 'GET', '/platform/feedback')).toBe(404);
  });

  test('an operator triages across workspaces; the submitter and owner see the new status but no labels (US5-1/2/5, US4-7, FR-014/017/017a/018)', async ({
    page,
    browser,
  }) => {
    const submitter = await newMember('branch_manager');
    const text = uniqueText('Triage me');
    const submitted = await submitFeedback(submitter.token, { text, category: 'question' });
    const label = `e2e-${Date.now()}`;

    // US5-5: a workspace owner cannot change status or labels through the operator route.
    expect(
      await apiStatus(ownerToken, 'PATCH', `/platform/feedback/${submitted.id}`, {
        status: 'reviewed',
      }),
    ).toBe(404);

    await signInEnglish(page, ops.ownerEmail, ops.ownerPassword);
    // The nav entry appears only for an operator.
    const nav = page.locator('.shell-sidenav').getByRole('link', {
      name: en('platform.feedback.nav'),
    });
    await nav.click();
    await page.waitForURL('**/platform/feedback');
    await expect(page.locator('.page-title')).toHaveText(en('platform.feedback.title'));

    // US5-1: feedback from both workspaces is listed.
    const row = page.locator('[data-testid="feedback-row"]', { hasText: text });
    await expect(row).toBeVisible();
    await expect(page.locator('[data-testid="feedback-row"]', { hasText: opsText })).toBeVisible();

    // FR-017a: the detail carries the submitter's email and the message.
    await row.locator('.open-row').click();
    const detail = page.locator('[data-testid="feedback-detail"]');
    await expect(detail.locator('[data-testid="detail-email"]')).toHaveText(submitter.email);
    await expect(detail.locator('[data-testid="detail-text"]')).toHaveText(text);

    // FR-018: status moves forward; labels are editable.
    await detail.locator('[data-testid="move-reviewed"]').click();
    await expect(detail.locator('.status-pill')).toHaveText(en('platform.feedback.status.reviewed'));
    await expect(row.locator('.status-pill')).toHaveText(en('platform.feedback.status.reviewed'));
    await expect(detail.locator('[data-testid="move-new"]')).toHaveCount(0);
    await detail.locator('input[name="label"]').fill(label);
    await detail.getByRole('button', { name: en('platform.feedback.labels.addAction') }).click();
    await expect(detail.locator('.label-chip', { hasText: label })).toBeVisible();

    // US5-1: filter to one workspace from the detail; the other workspace's item drops out.
    await detail.getByRole('button', { name: en('platform.feedback.detail.filterWorkspace') }).click();
    await expect(row).toBeVisible();
    await expect(page.locator('[data-testid="feedback-row"]', { hasText: opsText })).toHaveCount(0);

    // US5-2 / US4-7: the submitter sees Reviewed, no withdraw, and never the label.
    const mine = await asUser(browser, submitter.email, submitter.password);
    await mine.goto('/feedback');
    const own = card(mine, text);
    await expect(own.locator('[data-test="status"]')).toHaveText(en('feedback.status.reviewed'));
    await expect(own.locator('[data-test="withdraw"]')).toHaveCount(0);
    await expect(mine.getByText(label)).toHaveCount(0);
    // And a withdrawal through the API is refused once the item has moved past new.
    expect(await apiStatus(submitter.token, 'DELETE', `/feedback/${submitted.id}`)).toBe(409);

    // The owner's inbox shows the same status, also without the label.
    const owner = await asUser(browser, workspaceA.ownerEmail, workspaceA.ownerPassword);
    await owner.goto('/feedback/workspace');
    await expect(card(owner, text).locator('[data-test="status"]')).toHaveText(
      en('feedback.status.reviewed'),
    );
    await expect(owner.getByText(label)).toHaveCount(0);
  });

  test('a submitter withdraws a new item and it disappears from every view (US4-6/8, FR-014/015)', async ({
    page,
    browser,
  }) => {
    const submitter = await newMember('buyer');
    const text = uniqueText('Withdraw me');
    const submitted = await submitFeedback(submitter.token, { text, screenshot: true });

    // US4-8: nobody else, the owner included, can withdraw it: "not found", never "forbidden".
    expect(await apiStatus(ownerToken, 'DELETE', `/feedback/${submitted.id}`)).toBe(404);
    // FR-015: a member of another workspace cannot read it either.
    expect(await apiStatus(opsToken, 'GET', `/feedback/${submitted.id}`)).toBe(404);

    await signInEnglish(page, submitter.email, submitter.password);
    await page.goto('/feedback');
    const own = card(page, text);
    await expect(own).toBeVisible();
    // The screenshot was stored with it and is shown through a signed link.
    await expect(
      own.getByRole('img', { name: en('feedback.list.screenshotAlt', { number: 1 }) }),
    ).toBeVisible();

    await own.locator('[data-test="withdraw"]').click();
    const confirm = page.locator('mat-dialog-container');
    await expect(confirm).toContainText(en('feedback.withdraw.title'));
    await confirm.locator('[data-test="confirm"]').click();
    await expect(page.locator('mat-snack-bar-container')).toContainText(
      en('feedback.withdraw.success'),
    );
    await expect(own).toHaveCount(0);

    // Gone for the owner and the operator too.
    expect(await apiStatus(submitter.token, 'GET', `/feedback/${submitted.id}`)).toBe(404);
    expect(await apiStatus(opsToken, 'GET', `/platform/feedback/${submitted.id}`)).toBe(404);
    const owner = await asUser(browser, workspaceA.ownerEmail, workspaceA.ownerPassword);
    await owner.goto('/feedback/workspace');
    await expect(owner.locator('h1')).toHaveText(en('feedback.list.workspaceTitle'));
    await expect(card(owner, text)).toHaveCount(0);
  });
});
