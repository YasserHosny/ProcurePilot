import { test, expect } from "@playwright/test";
import { createMember, type CreatedMember } from "./support/api";

/**
 * End-to-End test suite for Catalogue Product Master (T018, US1, SC-001).
 *
 * Requirements:
 * - FR-001: Create product with name, base unit, brand, variant, GTIN.
 * - FR-002: Define pack count and unit size, show derived base quantity live.
 * - SC-001: Buyer creates product with pack definition and sees normalised quantity in under 90s.
 */
test.describe("Catalogue Product Master (T018)", () => {
  let buyer: CreatedMember;

  test.beforeEach(async ({ page }) => {
    buyer = await createMember("buyer");
    await page.goto("/auth/sign-in");
    await page.fill('input[formControlName="email"]', buyer.email);
    await page.fill('input[formControlName="password"]', buyer.password);
    await page.click('button[type="submit"]');
    await page.waitForURL("**/home");
  });

  test("buyer creates product, asserts live normalised quantity, and finishes within 90s budget (SC-001)", async ({ page }) => {
    const started = Date.now();

    // Navigate to Products
    await page.click('a[routerLink="/products"]');
    await page.waitForURL("**/products");
    await expect(page.locator(".page-title")).toContainText("Product Master");

    // Click Create New Product
    await page.click('a[routerLink="/products/new"]');
    await page.waitForURL("**/products/new");

    const productName = `Whole Milk 5L ${Date.now()}`;
    await page.fill('input[formControlName="tenant_name"]', productName);

    // Select base unit
    await page.click('mat-select[formControlName="base_unit"]');
    await page.click('mat-option:has-text("Litre")');

    // Enter pack definition: 6 x 5.0
    await page.fill('input[formControlName="pack_count"]', "6");
    await page.fill('input[formControlName="unit_size"]', "5.0");

    // Assert live normalised quantity preview displays 30 before saving (FR-002, SC-001)
    const livePreview = page.locator('[data-testid="live-normalised-quantity"]');
    await expect(livePreview).toContainText("30");
    await expect(livePreview).toContainText("litre");

    // Submit form
    await page.click('button[type="submit"]');
    await page.waitForURL("**/products");

    // Assert product appears in list with normalised base quantity
    const productRow = page.locator("tr[mat-row]", { hasText: productName });
    await expect(productRow).toBeVisible();
    await expect(productRow.locator(".normalised-cell")).toContainText("30");

    // SC-001: Under 90 seconds
    const elapsedSeconds = (Date.now() - started) / 1000;
    expect(
      elapsedSeconds,
      `SC-001 requires product creation under 90s; took ${elapsedSeconds.toFixed(1)}s`,
    ).toBeLessThan(90);
  });
});
