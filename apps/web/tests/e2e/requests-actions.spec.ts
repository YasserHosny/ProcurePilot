import { randomUUID } from 'node:crypto';
import { test, expect, type Page } from '@playwright/test';
import { authFile } from '../../playwright.config';
import { apiAsUser, createTestProduct, signInOwner } from './support/api';
import { openAsyncSelect } from './support/select';

test.use({ storageState: authFile });

interface Seed { id: string; note: string; date: string }
interface RequestRecord { id: string; status: string }

test.describe('Purchase request actions and URL state', () => {
  let token: string;
  let branch: { id: string; name: string };
  let product: { id: string; tenant_name: string };
  const seeds: Record<string, Seed> = {};
  const createdIds = new Set<string>();

  test.beforeAll(async () => {
    token = await signInOwner();
    const marker = `actions-${randomUUID()}`;
    branch = await apiAsUser(token, 'POST', '/organisation/branches', {
      name: marker, address: '10 Request Lane', region: 'GB',
    });
    product = await createTestProduct(token, { tenant_name: marker });
    let day = 10;
    for (const name of ['withdraw', 'keyboard', 'discard', 'duplicate', 'url']) {
      const note = `${marker}-${name}`;
      const date = `2031-06-${day++}`;
      const request = await apiAsUser<RequestRecord>(token, 'POST', '/requests', {
        branch_id: branch.id, required_by_date: date,
        lines: [{ workspace_product_id: product.id, quantity: '7', note }],
      });
      createdIds.add(request.id);
      seeds[name] = { id: request.id, note, date };
      if (name === 'withdraw' || name === 'keyboard') {
        await apiAsUser(token, 'POST', `/requests/${request.id}/submit`);
      } else if (name === 'duplicate') {
        await apiAsUser(token, 'POST', `/requests/${request.id}/withdraw`);
      }
    }
  });

  test.afterAll(async () => {
    // Only IDs returned by this suite's create calls are eligible for cleanup.
    for (const id of createdIds) {
      const request = await apiAsUser<RequestRecord>(token, 'GET', `/requests/${id}`);
      if (request.status === 'draft' || request.status === 'submitted') {
        await apiAsUser(token, 'POST', `/requests/${id}/withdraw`);
      }
    }
    if (product) await apiAsUser(token, 'DELETE', `/products/${product.id}`);
    if (branch) await apiAsUser(token, 'PATCH', `/organisation/branches/${branch.id}`, { is_active: false, confirm_dependents: true });
  });

  test.beforeEach(async ({ page }) => {
    await page.goto('/home');
    await expect(page.getByRole('button', { name: /account options|خيارات الحساب/i })).toBeVisible();
    if ((await page.locator('html').getAttribute('dir')) === 'rtl') {
      await page.getByRole('button', { name: /account options|خيارات الحساب/i }).click();
      await page.getByRole('menuitem', { name: 'English', exact: true }).click();
    }
    await expect(page.locator('html')).toHaveAttribute('dir', 'ltr');
  });

  async function openSeed(page: Page, seed: Seed) {
    await page.goto(`/requests?q=${encodeURIComponent(seed.note)}`);
    const row = page.locator('tr.clickable-row');
    await expect(row).toHaveCount(1);
    await expect(row).toContainText(branch.name);
    // Confirm the search resolved to our seed before interacting with the row.
    const matches = await apiAsUser<{ items: RequestRecord[] }>(token, 'GET', `/requests?q=${encodeURIComponent(seed.note)}`);
    expect(matches.items.map((item) => item.id)).toEqual([seed.id]);
    return row;
  }

  async function expectStatus(id: string, status: string) {
    await expect.poll(async () => (await apiAsUser<RequestRecord>(token, 'GET', `/requests/${id}`)).status).toBe(status);
  }

  test('list Withdraw confirms or cancels without navigating (PPS-188)', async ({ page }) => {
    const seed = seeds['withdraw']!;
    const row = await openSeed(page, seed);
    const listUrl = page.url();
    const dialog = page.getByRole('dialog');
    await row.getByRole('button', { name: 'Withdraw request', exact: true }).click();
    await expect(dialog).toBeVisible();
    await expect(page).toHaveURL(listUrl);
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(dialog).toBeHidden();
    await expect(row).toContainText('Submitted');
    await expectStatus(seed.id, 'submitted');
    await expect(page).toHaveURL(listUrl);
    await row.getByRole('button', { name: 'Withdraw request', exact: true }).click();
    await expect(dialog).toBeVisible();
    await expect(page).toHaveURL(listUrl);
    await dialog.getByRole('button', { name: 'Withdraw request', exact: true }).click();
    await expect(dialog).toBeHidden();
    await expect(row).toContainText('Withdrawn');
    await expect(page).toHaveURL(listUrl);
    await expectStatus(seed.id, 'withdrawn');
  });

  test('Enter navigates from the row but opens confirmation from its Withdraw button', async ({ page }) => {
    const seed = seeds['keyboard']!;
    let row = await openSeed(page, seed);
    await row.focus();
    await expect(row).toBeFocused();
    await row.press('Enter');
    await expect(page).toHaveURL(new RegExp(`/requests/${seed.id}$`));
    row = await openSeed(page, seed);
    const listUrl = page.url();
    const withdraw = row.getByRole('button', { name: 'Withdraw request', exact: true });
    await withdraw.focus();
    await expect(withdraw).toBeFocused();
    await withdraw.press('Enter');
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(page).toHaveURL(listUrl);
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(dialog).toBeHidden();
    await expectStatus(seed.id, 'submitted');
  });

  test('Discard draft returns to the list and withdraws the draft (PPS-190)', async ({ page }) => {
    const seed = seeds['discard']!;
    await page.goto(`/requests/${seed.id}`);
    await page.getByRole('button', { name: 'Discard draft', exact: true }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: 'Discard draft', exact: true }).click();
    await expect(page).toHaveURL(/\/requests$/);
    await expectStatus(seed.id, 'withdrawn');
  });

  test('Duplicate as new draft prefills lines but requires a new date (PPS-190)', async ({ page }) => {
    const seed = seeds['duplicate']!;
    await page.goto(`/requests/${seed.id}`);
    await page.getByRole('button', { name: 'Duplicate as new draft', exact: true }).click();
    await expect(page).toHaveURL((url) => url.pathname === '/requests/new' && url.searchParams.get('duplicate_from') === seed.id);
    await expect(page.getByRole('combobox', { name: 'Branch', exact: true })).toContainText(branch.name);
    const line = page.getByRole('group', { name: 'Line 1', exact: true });
    await expect(line.getByRole('combobox', { name: 'Product', exact: true })).toContainText(product.tenant_name);
    await expect(line.getByLabel('Quantity', { exact: true })).toHaveValue('7');
    await expect(page.getByLabel('Required By', { exact: true })).toHaveValue('');
    await expect(page.getByRole('status').filter({ hasText: 'Copied from a Withdrawn request.' })).toBeVisible();
    await page.getByLabel('Required By', { exact: true }).fill('2031-07-20');
    // Capture the actual create response so cleanup also runs if navigation assertions fail.
    const responsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/requests' && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Save Draft', exact: true }).click();
    const response = await responsePromise;
    expect(response.ok()).toBeTruthy();
    const created = await response.json() as RequestRecord;
    createdIds.add(created.id);
    expect(created.id).not.toBe(seed.id);
    await expect(page).toHaveURL(new RegExp(`/requests/${created.id}$`));
    await expectStatus(created.id, 'draft');
    await expectStatus(seed.id, 'withdrawn');
  });

  test('list search, sort, mine and status survive reload and history navigation (PPS-193)', async ({ page }) => {
    const seed = seeds['url']!;
    await page.goto('/requests');
    const search = page.getByRole('searchbox', { name: 'Search requests' });
    const sort = page.getByRole('combobox', { name: 'Sort by' });
    const mine = page.getByRole('switch', { name: 'My requests' });
    await search.fill(seed.note);
    await expect(page).toHaveURL((url) => url.searchParams.get('q') === seed.note);
    await expect(page.locator('tr.clickable-row')).toHaveCount(1);
    await expect(page.locator('tr.clickable-row')).toContainText(branch.name);
    await page.getByRole('button', { name: 'Clear search', exact: true }).click();
    await expect(search).toHaveValue('');
    await expect(page).toHaveURL((url) => !url.searchParams.has('q'));
    await openAsyncSelect(page, sort);
    await page.getByRole('option', { name: 'Oldest first', exact: true }).click();
    await expect(page).toHaveURL((url) => url.searchParams.get('sort') === 'created_asc');
    await openAsyncSelect(page, sort);
    await page.getByRole('option', { name: 'Newest first', exact: true }).click();
    await expect(page).toHaveURL((url) => !url.searchParams.has('sort'));
    await openAsyncSelect(page, sort);
    await page.getByRole('option', { name: 'Oldest first', exact: true }).click();
    await mine.check();
    await expect(page).toHaveURL((url) => url.searchParams.get('mine') === 'true');
    await search.fill(seed.note);
    await expect(page).toHaveURL((url) => url.searchParams.get('q') === seed.note);
    await openAsyncSelect(page, page.locator('.status-filter'));
    await page.getByRole('option', { name: 'Draft', exact: true }).click();
    await expect(page).toHaveURL((url) => url.searchParams.get('status') === 'draft');
    const filteredUrl = page.url();
    await page.reload();
    async function expectFilters() {
      await expect(page).toHaveURL(filteredUrl);
      await expect(search).toHaveValue(seed.note);
      await expect(sort).toContainText('Oldest first');
      await expect(mine).toBeChecked();
      await expect(page.locator('.status-filter')).toContainText('Draft');
      await expect(page.locator('tr.clickable-row')).toHaveCount(1);
    }
    await expectFilters();
    // Filter updates replace history. A new navigation supplies a second real entry.
    await page.goto('/requests');
    await expect(search).toHaveValue('');
    await expect(sort).toContainText('Newest first');
    await expect(mine).not.toBeChecked();
    await page.goBack();
    await expectFilters();
    await page.goForward();
    await expect(page).toHaveURL(/\/requests$/);
    await expect(search).toHaveValue('');
    await expect(sort).toContainText('Newest first');
    await expect(mine).not.toBeChecked();
    await expect(page.locator('.status-filter')).not.toContainText('Draft');
  });
});
