import { test, expect } from "@playwright/test";
import { createMember, type CreatedMember } from "./support/api";

/**
 * End-to-End test suite for Bulk Catalogue Import Wizard (T034, US3, SC-002, SC-003, SC-004).
 *
 * Requirements:
 * - FR-017: Atomic all-or-nothing validation before write.
 * - FR-018: Error report showing line number in user's file with specific reason.
 * - FR-019: Missing/unrecognised columns reported separately.
 * - FR-020: Preview before confirmation — nothing saved until user confirms.
 */
test.describe("Catalogue Import Wizard (T034)", () => {
  let buyer: CreatedMember;

  test.beforeEach(async ({ page }) => {
    buyer = await createMember("buyer");
    await page.goto("/auth/sign-in");
    await page.fill('input[formControlName="email"]', buyer.email);
    await page.fill('input[formControlName="password"]', buyer.password);
    await page.click('button[type="submit"]');
    await page.waitForURL("**/home");
  });

  test("upload invalid CSV file, assert nothing saved, and assert error report with line numbers", async ({ page }) => {
    await page.goto("/import?kind=products");
    await expect(page.locator(".page-title")).toContainText("Import Wizard");

    // Prepare invalid CSV with a bad pack_count on line 3
    const invalidCsvContent =
      "tenant_name,base_unit,pack_count,unit_size\n" +
      "Valid Item,litre,6,1.0\n" +
      "Bad Pack Item,litre,-4,5.0\n";

    // Set file via input
    await page.setInputFiles('input[type="file"]', {
      name: "invalid_products.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(invalidCsvContent),
    });

    // Upload & Validate
    await page.click('button:has-text("Upload & Validate")');

    // Step 2: Validate & Preview
    await expect(page.locator(".preview-status-badge.status-invalid")).toBeVisible();
    await expect(page.locator(".error-block")).toBeVisible();

    // Assert row errors report shows line 3
    const errorRow = page.locator(".errors-table tr[mat-row]");
    await expect(errorRow).toBeVisible();
    await expect(errorRow.locator(".line-badge")).toContainText("3");

    // Confirm button must NOT be present or disabled for invalid import
    await expect(page.locator('button:has-text("Confirm & Save Import")')).not.toBeVisible();

    // Verify nothing was saved to products list
    await page.goto("/products");
    await expect(page.locator("tr[mat-row]", { hasText: "Valid Item" })).not.toBeVisible();
    await expect(page.locator("tr[mat-row]", { hasText: "Bad Pack Item" })).not.toBeVisible();
  });

  test("upload valid CSV file, preview, confirm, and assert records created", async ({ page }) => {
    await page.goto("/import?kind=products");

    const uniqueItem = `Imported Butter ${Date.now()}`;
    const validCsvContent =
      "tenant_name,base_unit,pack_count,unit_size\n" +
      `${uniqueItem},kilogram,10,0.5\n`;

    await page.setInputFiles('input[type="file"]', {
      name: "valid_products.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(validCsvContent),
    });

    await page.click('button:has-text("Upload & Validate")');

    // Assert valid preview
    await expect(page.locator(".preview-status-badge.status-valid")).toBeVisible();
    await expect(page.locator(".preview-table-section")).toBeVisible();

    // Click Confirm Import
    await page.click('button:has-text("Confirm & Save Import")');

    // Assert Result Step
    await expect(page.locator(".result-card")).toBeVisible();
    await expect(page.locator(".stat-box.created .stat-num")).toContainText("1");

    // Go to products and verify row exists
    await page.click('a:has-text("Go to Products")');
    await page.waitForURL("**/products");
    await expect(page.locator("tr[mat-row]", { hasText: uniqueItem })).toBeVisible();
  });
});
