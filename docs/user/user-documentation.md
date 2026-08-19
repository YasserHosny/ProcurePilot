# ProcurePilot — User Help Center

> Self-service guides for the three core jobs: compare, request, approve.

---

## Quick Start for Owners

1. **Create your account** and invite your team.
2. **Set up your catalogue** by uploading a CSV or adding products manually.
3. **Add suppliers** with their payment and delivery terms.
4. **Upload your first quotation** and review the extracted fields.
5. **Confirm or correct matches**, then view Smart Compare.
6. **Record the purchase** and watch the savings ledger update.

## Uploading a Quotation

1. Go to **Quotations** and drag a PDF, photo, Excel, or CSV onto the upload area.
2. Wait for extraction (usually under 45 seconds per page).
3. Click any low-confidence field to highlight the source region.
4. Correct values inline and click **Confirm**.

## Reviewing Matches

1. Open **Review Queue**.
2. Each line shows candidate products with score reasons (brand, size, GTIN, alias).
3. Choose:
   - **Same product** — confirm.
   - **Different pack / variant** — pick the correct one.
   - **No match** — create a new product.
4. Your correction trains the model for future documents.

## Smart Compare

- Each row is one supplier offer.
- Columns show **displayed price**, **normalised unit price**, **VAT**, **delivery**, **discounts**, and **total landed cost**.
- Use the quantity input to see thresholds, tiers, and minimum order values recalculate live.
- The AI banner shows the recommended action with evidence, confidence, and risk.

## Savings Ledger

- Every recorded purchase creates a **SavingRecord**.
- Each row shows the baseline policy used, baseline value, actual value, and verified delta.
- Click a row to open the evidence drawer: source quotation, competing offers, purchase record, and calculation.
- Export to Excel or PDF for your accountant.

## Mobile: Making a Request

1. Open the ProcurePilot app.
2. Tap **New Request**.
3. Search the catalogue, scan a barcode, or take a photo of the shelf/label.
4. Enter quantity and required-by date.
5. Tap **Submit**. If offline, the request queues and syncs automatically.

## Mobile: Approving a Request

1. You receive a push notification.
2. Open the request card to see amount, branch, budget impact, recommended supplier, and expected saving.
3. Tap **Approve**, **Reject**, or **Request Change** and add a comment.

## Mobile: Confirming Delivery

1. Open the request when goods arrive.
2. Confirm quantity received.
3. Flag shortages, damage, or quality issues and attach a photo.

## Roles & Permissions

| Role | Can do |
|---|---|
| Owner | Everything; manage billing and team |
| Buyer | Upload, compare, record purchases, manage catalogue |
| Branch Manager | Create requests, confirm deliveries |
| Approver | Approve/reject requests |
| Viewer | View dashboards and reports only |

## FAQs

**Q: Can I edit a verified saving?**  
A: No. Verified savings are immutable. If a correction is needed, a new adjustment record is created.

**Q: Why is extraction confidence low?**  
A: Usually because the document is blurry, handwritten, or uses an unfamiliar layout. Corrections teach the system.

**Q: What happens if a supplier is blocked?**  
A: The policy engine flags any offer from a blocked supplier and requires an exception justification.

**Q: Can I use ProcurePilot in Arabic?**  
A: Yes. Switch language in Settings; the layout adapts to RTL automatically.

## Getting Help

- In-app feedback: **Settings → Send Feedback**.
- Email: support@procurepilot.example.com.
- Response target: within 1 business day for paid plans.
