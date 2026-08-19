# ProcurePilot — UI Mockup Prompts for Google Stitch

> Text prompts for generating high-fidelity web and mobile mockups in Google Stitch.
> Base style: Angular Material / Material Design 3, clean enterprise SaaS, light theme by default, WCAG 2.1 AA, bilingual (English + Arabic RTL ready).

---

## Web Prompts — Phase 1

### W1 — Login

Generate a clean, centered login screen for an Angular Material enterprise SaaS called **ProcurePilot**. Top-left logo and app name. Centered card with email and password fields, a primary "Sign in" button, a "Forgot password?" link, and a small "Don't have an account?" link. Use a light theme, subtle gradient background, and Trustpilot-style social proof row below the card. Include language switcher (EN / AR) in the top-right corner.

### W2 — Dashboard

Generate a dashboard screen for a procurement intelligence app. Top navigation bar with search, notifications bell, tenant/team switcher, and profile avatar. Below the nav, a hero band showing three KPI cards: "Verified savings this month", "Active recommendations", "Documents processed". Underneath, a two-column layout: left column shows an "Actions required" list and "Price alerts" list; right column shows a "Savings trend" line chart and a "Supplier concentration" donut chart. Use Angular Material cards, flat shadows, and a calm color palette (indigo primary, amber accents). Include a CTA button "Upload quotation".

### W3 — Quotation Inbox

Generate a list screen for an inbox of uploaded supplier quotations. Layout: page title "Quotation Inbox", a primary "Upload quotation" button top-right, filter chips (All / Pending / Extracted / Reviewed), and a data table with columns: Supplier, Date, Document, Status, Confidence, Actions. Rows show PDF icons, status badges (blue "Extracted", amber "Needs review", green "Accepted"), and a three-dot menu. Use Angular Material Table with sticky header and pagination footer.

### W4 — Extraction Review

Generate a split-screen review UI for correcting AI-extracted quotation fields. Left 50%: a document viewer showing a rendered PDF quotation with a highlighted region around a selected line. Right 50%: a form panel with confidence badges on each field (Supplier, Issue date, Currency, Line items). A line-item table with columns: Description, Qty, Unit, Unit price, VAT, Discount, Line total, Confidence. Highlight low-confidence fields in amber. Show buttons "Accept all high confidence", "Escalate", "Save corrections", and a progress bar of reviewed fields.

### W5 — Match Resolution

Generate a modal/overlay for resolving a product match. Top: original supplier text "6 x 5L Highland Spring still water". Below, a list of 3–4 candidate products as cards, each showing product image placeholder, brand, name, pack size, normalised unit price, and a match score badge. Highlight the top candidate. Include reason chips under each: "brand match", "pack-size match", "GTIN match", "alias hit". Bottom action buttons: "Confirm same product", "Different pack/variant", "No match — create new", "Skip". Keyboard shortcut hints (1, 2, 3, Enter).

### W6 — Smart Compare

Generate a comparison grid screen for supplier offers. Top: product header "Highland Spring still water — 30L equivalent", quantity input "Qty: 10". Main content: a table with rows per supplier offer and columns: Supplier, Displayed price, Normalised unit price, VAT, Delivery, Discounts, Total landed cost, Lead time, Reliability, Match confidence, Stock. Best offer row highlighted with a green left border and a "Recommended" badge. Above the table, an AI recommendation banner: "Buy 6 units from Supplier A to save £12.40 — confidence 91%, risk: price expires in 2 days". Buttons: "Create request", "Record purchase", "Export".

### W7 — Product Intelligence

Generate a product detail screen. Left column: product image placeholder, product name, pack normalisation text "6 × 5L = 30L", preferred supplier, approved substitutes. Right column: a price-history line chart with supplier series and purchase-event dots; stat cards for "Best current cost", "Last paid", "Average paid (6 mo)", "30-day change". Below the chart, a small "Recommended reorder" card with placeholder date and quantity.

### W8 — Savings Ledger

Generate a savings ledger list screen. Page title, period filter, and a table with columns: Date, Product, Supplier chosen, Baseline policy, Baseline value, Actual value, Verified saving, Status. Each row has a status badge (Verified / Pending / Disputed). Last column has an "Evidence" button that opens a drawer. Top summary cards: "Total verified", "Pending review", "Average saving per decision".

### W9 — Catalogue / Supplier Hub

Generate a catalogue list screen. Two tabs: "Products" and "Suppliers". Products tab shows a search bar, "Import CSV" button, and a table with columns: Name, Brand, Pack size, Preferred supplier, Status. Suppliers tab shows cards for each supplier with name, status badge, lead time, MOV, delivery fee, and reliability score.

### W10 — Settings — Team

Generate a settings screen with a left sidebar menu (Organisation, Team, Policies, Billing, Integrations). Main area: "Team" tab showing a table of users with columns: Name, Email, Role, Status, Last active, Actions. A primary "Invite user" button opens a modal with email and role selector.

---

## Mobile Prompts — Phase 2

### M1 — Login / Biometric Unlock

Generate a mobile login screen for a Flutter app. Top: app logo and tagline. Center: biometric icon (fingerprint/face) with "Unlock with biometrics" label. Fallback: email/password fields and "Sign in" button. Bottom: language toggle (EN / AR). Use Material Design 3, light theme, rounded corners, and large touch targets.

### M2 — Home (Branch Manager)

Generate a role-aware mobile home screen for a branch manager. Top greeting "Good morning, Khaled". Three large tappable cards: "New request", "Low stock report", "My requests". Below, a recent activity list with icons and timestamps. A floating action button for quick request. Bottom navigation bar: Home, Requests, Alerts, Settings.

### M3 — Home (Approver)

Generate the same home screen but for an approver. Top card shows a large number "3" with "Pending approvals" label and a primary "Review now" button. Secondary cards: "Alerts", "Recent requests". Bottom nav: Home, Approvals, Alerts, Settings.

### M4 — Quick Request

Generate a mobile screen for creating a purchase request. Top search bar with placeholder "Search catalogue or scan barcode". Below, "Recent items" horizontal chips. Main form: product name field, quantity stepper, required-by date picker, branch selector, optional note, and an "Attach photo" button showing a camera icon. Bottom sticky bar with "Save draft" and "Submit request" buttons.

### M5 — Scan / Photo Capture

Generate a mobile screen with a camera viewfinder overlay. Bottom sheet with two tabs: "Barcode" and "Photo". In barcode mode, show a scanning reticle and a hint "Point camera at product barcode". In photo mode, show a capture button and a hint "Photo of shelf or label". Include a flashlight toggle and a close button.

### M6 — Low-Stock Report

Generate a mobile screen for a low-stock report. List of products with stock indicator dots (green/amber/red). Each row shows product name, pack size, current stock level input, and a note field. Top "Select all running low" quick action. Bottom sticky "Submit report" button.

### M7 — My Requests

Generate a mobile screen showing a request timeline. Vertical list of requests with status chips (Draft / Submitted / Approved / Ordered / Delivered). Each card shows product(s), quantity, branch, required-by date, and a small progress stepper. Tapping a card opens detail.

### M8 — Approval Queue

Generate a mobile approval queue. Stack of cards, top card prominently displayed. Each card: requester name, branch, total amount, budget impact percentage, recommended supplier, expected saving, and policy exception warnings. Three large bottom buttons: green "Approve", red "Reject", grey "Request change". Swipe left/right gestures indicated.

### M9 — Approval Detail

Generate a mobile approval detail screen. Top: request summary and amount. Scrollable content: landed-cost comparison mini-table (recommended supplier vs alternatives), confidence badge, risk note, and a comment thread. Bottom sticky decision bar.

### M10 — Delivery Confirmation

Generate a mobile screen for confirming a delivery. Top: order summary. Form fields: quantity received (numeric stepper), quality rating (1–5 stars), checkboxes for "Shortage" / "Damage" / "Wrong item". Photo gallery with "Add photo" placeholder. Bottom sticky "Confirm delivery" button.

### M11 — Alerts

Generate a mobile alerts list. Grouped by date. Each row: alert icon, title (e.g. "Price spike on A4 paper"), urgency badge, timestamp, and a chevron. Pull-to-refresh indicator at top. Empty state illustration for no alerts.

### M12 — Settings

Generate a mobile settings screen. Grouped list: Account, Branch context, Notifications, Language (EN / AR with RTL preview), Help & feedback, Sign out. Use Material list tiles with icons and switches. Include a dark/light toggle if theme switching is supported.

---

## Global style notes for all prompts

- Use **light theme by default**; dark mode optional.
- Primary color: indigo `#4F46E5`; accent: amber `#F59E0B`; success: green `#10B981`; warning: amber; error: red `#EF4444`.
- Fonts: Inter for web, Roboto for mobile.
- Maintain **WCAG 2.1 AA contrast**; no text below 12px/14sp.
- Layouts must be **RTL-ready**; avoid left/right directional labels, use start/end.
- Mobile touch targets minimum 44×44 dp; web interactive elements minimum 32×32 px.
- Use real-ish placeholder data relevant to small-business procurement (cleaning supplies, packaging, office products).
