# NewsFeed Mobile App — Full Pages & Functions Description

> **Source:** Figma design file `NewsFeed_mobile` (Idealo_adapt canvas)
> **Platform:** Mobile (360×640pt viewport)
> **Design System:** Roboto font family, black/white primary palette, 12px horizontal padding, 6–8px border radius, emoji-based iconography

---

## Table of Contents

1. [Global UI Components](#1-global-ui-components)
2. [Search Products Page](#2-search-products-page)
3. [Tracking List Page](#3-tracking-list-page)
4. [Contact Us Page](#4-contact-us-page)
5. [Report Error Page](#5-report-error-page)
6. [Push Notifications (Notification Manager) Page](#6-push-notifications-notification-manager-page)
7. [Navigation Structure](#7-navigation-structure)
8. [Design Tokens & Styling](#8-design-tokens--styling)

---

## 1. Global UI Components

### 1.1 Status Bar
- Positioned at the very top of every screen (24px height)
- Contains: **time** (right-aligned), **battery** icon, **cellular signal** icon, **Wi-Fi** icon
- White background

### 1.2 Top Bar / App Bar
- Height: 48px content area below status bar (total 72px including status bar)
- **Back button** (left arrow icon, 24×24px) — navigates to previous screen
- **Title text** — Roboto Medium, 20px, black, left-aligned next to back button
- **Action icons** (optional, right-aligned) — e.g., undo icon, overflow menu (⋮)
- White background with subtle drop shadow (`0px 0px 3px rgba(0,0,0,0.12)`)

### 1.3 Bottom Navigation Bar
- Fixed at the bottom of every screen (50px height)
- White background with top shadow (`0px 0px 6px rgba(0,0,0,0.12)`)
- Each tab: emoji icon (28×28px, 20px font) + label text (10px, Roboto Regular)
- Tabs vary per screen context (see Navigation Structure below)

### 1.4 Primary Button
- Full-width (with 12px side margins), 42px height
- Black background, white text (Roboto Medium, 16px), 8px border radius
- Centered text label

### 1.5 Text Input Field
- Label: Roboto Medium, 14px, black
- Input container: 36px height, 6px border radius, 1px border `rgba(0,0,0,0.1)`
- Placeholder text: Roboto Regular, 14px, `rgba(0,0,0,0.5)`
- Helper/info text (optional): Roboto Regular, 12px, `rgba(0,0,0,0.5)`

### 1.6 Chip / Tag Selector
- Label above chip group: Roboto Medium, 14px, black
- Individual chips: `rgba(0,0,0,0.05)` background, 6px border radius, 8px padding
- Chip text: Roboto Regular, 14px, black
- Single-select or multi-select behavior depending on context

### 1.7 Product Card
- Width: 150px, border: 1px solid `rgba(0,0,0,0.1)`, 6px border radius, overflow hidden
- **Image area:** 150×150px, light gray background `rgba(0,0,0,0.05)`, centered product name placeholder
- **Tag badge** (top-left corner): rounded bottom-right, 4px padding, shows contextual info (e.g., price change, seller name)
- **Text content area:** 8px padding
  - Product name: Roboto Regular, 12px, black
  - Price: Roboto Medium, 16px, black (e.g., "From £17.99" or "$XX.XX")

### 1.8 Metric Card
- Full-width, 1px border `rgba(0,0,0,0.1)`, 6px border radius
- 12px internal padding
- Title: Roboto Regular, 14px, `rgba(0,0,0,0.5)`
- Value: Roboto Medium, 20px, black

### 1.9 Toggle Switch
- iOS-style toggle, 51×31px, green (`#34C759`) when ON
- White circular knob (27×27px) with subtle shadow
- Used for on/off notification preferences

### 1.10 Section Title
- Roboto Medium, 18px, black
- 16px top padding before title text

### 1.11 List Item with Toggle
- Left: emoji icon in rounded container (32×32px, `rgba(0,0,0,0.05)` bg, 16px border radius)
- Center: title (Roboto Regular, 14px, black) + description (Roboto Regular, 12px, `rgba(0,0,0,0.5)`)
- Right: toggle switch
- Divider line at bottom of each item

---

## 2. Search Products Page

**Screen title:** "Search Products"

### Layout (top to bottom)
1. **Top Bar** — back button + title "Search Products"
2. **Search Input** — label: "Search by name or paste a product link", placeholder repeats same text
3. **Filters Section** — section title "Filters", 2×2 grid of filter chips:
   - 🏷️ **Category** — filter products by category
   - 🛒 **Platform** — filter by shopping platform/seller
   - 💵 **Price range** — filter by price bracket
   - 🔍 **Sort by** — sort results (e.g., price low-to-high, relevance)
4. **Search Results** — horizontal scrollable row of product cards:
   - Each card shows: product image, seller tag (e.g., "Sold by Amazon", "Sold by Noon", "Sold by Jumia"), product name, price
5. **"Track" Button** — primary CTA, allows user to start tracking the selected product's price

### Functions
- `searchProducts(query: string)` — search by product name or pasted URL
- `applyFilter(type: 'category' | 'platform' | 'priceRange' | 'sortBy', value: string)` — apply search filters
- `trackProduct(productId: string)` — add product to user's tracking list

### Bottom Navigation (6 tabs)
Home | Search | History | Alerts | Deals | Settings

---

## 3. Tracking List Page

**Screen title:** "Tracking List"

### Layout (top to bottom)
1. **Top Bar** — back button + title "Tracking List" + action icons (undo 🔙, overflow menu ⋮)
2. **Tracked Products Metric** — section title "Tracked Products", metric card showing "Total Products: 3 Products"
3. **Product Cards Row** — horizontal scrollable row of tracked product cards, each showing:
   - Product image placeholder with product name
   - **Price change tag** (top-left): e.g., "Change: £4.50 since added", "Change: £2.00 since added", "Change: £1.50 since added"
   - Product name below image
   - Current best price (e.g., "From £17.99", "From £13.99", "From £12.50")
4. **Target Price Row** — list item showing:
   - Label "Target Price"
   - Value "Target price: £17.00"
   - Alert bell icon (🔔) — indicates notification will trigger when target is reached

### Sample Data
| Product | Current Price | Change Since Added |
|---|---|---|
| Ecover Non-Bio Laundry Liquid (5 L) | From £17.99 | £4.50 |
| Persil Non-Bio Liquid (3 L) | From £13.99 | £2.00 |
| Ariel Powder (10 Washes) | From £12.50 | £1.50 |

### Functions
- `getTrackedProducts()` — retrieve user's tracked product list
- `removeTrackedProduct(productId: string)` — remove a product from tracking
- `setTargetPrice(productId: string, price: number)` — set desired target price for alerts
- `undoAction()` — undo last action (undo icon in top bar)

### Bottom Navigation (4 tabs)
Home | Tracking List | Alerts | Settings

---

## 4. Contact Us Page

**Screen title:** "Contact us"

### Layout (top to bottom)
1. **Top Bar** — back button + title "Contact us"
2. **Subject Input** — label: "How can we help you?", empty text field
3. **Topic Selection** — label: "Topic", horizontal chip group with options:
   - Product Inquiry
   - Feedback
   - Technical Support
   - Other
4. **Message Input** — label: "Message", placeholder: "Enter your message or feedback here..."
5. **Email Input** — label: "Email address", placeholder: "youremail@example.com"
   - Helper text: "Your email address will be used solely for feedback to your query."
6. **Send Button** — primary button labeled "Send"
7. **Alternative Contact Info** — section text: "Alternatively, you can also contact us by email at" + subtitle "[support@email.com]"

### Functions
- `submitContactForm(data: { subject: string, topic: string, message: string, email: string })` — validate and submit the contact form
- `selectTopic(topic: 'Product Inquiry' | 'Feedback' | 'Technical Support' | 'Other')` — select a contact topic chip
- `validateEmail(email: string): boolean` — validate email format before submission

### Validation Rules
- Subject field: required
- Topic: exactly one must be selected
- Message: required
- Email: required, must be valid email format

### Bottom Navigation (4 tabs)
Home | Search | Alerts | Settings

---

## 5. Report Error Page

**Screen title:** "Report an error"

### Layout (top to bottom)
1. **Top Bar** — back button + title "Report an error"
2. **Product Name Display** — label: "Product Name", read-only value showing the product context (e.g., "Ecover Delicate and wool detergent water lily & honeydew melon")
3. **Error Type Selection** — label: "Select error:", vertical chip group (single-select) with options:
   - "App shows the wrong image"
   - "App shows the wrong specifications"
   - "Something else"
   - Helper text: "Choose one option."
4. **Error Description** — label: "Describe the error", multiline text area (116px height), placeholder: "You can describe the error here"
   - Helper text: "This is required if 'Something else' is selected."
5. **Send Button** — primary button labeled "Send"

### Functions
- `submitErrorReport(data: { productId: string, errorType: string, description?: string })` — submit the error report
- `selectErrorType(type: 'wrong_image' | 'wrong_specifications' | 'something_else')` — select an error category
- `validateErrorForm(): boolean` — ensure error type is selected; if "Something else" is chosen, description is required

### Validation Rules
- Error type: required (exactly one chip)
- Description: conditionally required — mandatory when "Something else" is selected, optional otherwise
- Product name: pre-populated, read-only (passed from the product detail context)

### Bottom Navigation (4 tabs)
Home | Search | Alerts | Settings

---

## 6. Push Notifications (Notification Manager) Page

**Screen title:** "Push Notifications"

### Layout (top to bottom)
1. **Top Bar** — back button + title "Push Notifications"
2. **Section Title** — "Notification Preferences"
3. **Notification Toggle List** — each item has: emoji icon, title, description, and iOS-style toggle switch

### Notification Items

| Icon | Title | Description | Default |
|------|-------|-------------|---------|
| 🔔 | Price Updates | Lets you know when there are price drops for recently viewed products | ON |
| 📈 | Information about your Price Alerts | Receive updates on your active price alerts | ON |
| ⭐ | Favourites | Get notified when your favourite products go on sale | ON |
| 🛒 | Shopping Tips | Tips and tricks for smarter shopping | ON |
| 🤖 | Product Recommendations | Get personalized product suggestions based on your interests | ON |
| 📰 | [App Name] and me | News and tips for better laundry practices | ON |
| 🎉 | Promotions | Exclusive promotional offers and discounts | ON |

### Functions
- `getNotificationPreferences()` — fetch current toggle states from server/local storage
- `toggleNotification(type: string, enabled: boolean)` — update a specific notification preference
- `saveNotificationPreferences(preferences: Record<string, boolean>)` — persist all preferences

### Bottom Navigation (4 tabs)
Home | Search | Alerts | Settings

---

## 7. Navigation Structure

The app uses two bottom navigation variants depending on context:

### Variant A — 4-Tab Navigation (Settings / Detail pages)
| Tab | Icon | Label |
|-----|------|-------|
| 1 | 🏠 | Home |
| 2 | 🔍 | Search |
| 3 | 🔔 | Alerts |
| 4 | ⚙️ | Settings |

**Used on:** Contact Us, Report Error, Notification Manager

### Variant B — 4-Tab Navigation (Tracking context)
| Tab | Icon | Label |
|-----|------|-------|
| 1 | 🏠 | Home |
| 2 | 📈 | Tracking List |
| 3 | 🔔 | Alerts |
| 4 | ⚙️ | Settings |

**Used on:** Tracking List

### Variant C — 6-Tab Navigation (Full app)
| Tab | Icon | Label |
|-----|------|-------|
| 1 | 🏠 | Home |
| 2 | 🔍 | Search |
| 3 | 🕒 | History |
| 4 | 🔔 | Alerts |
| 5 | 💰 | Deals |
| 6 | ⚙️ | Settings |

**Used on:** Search Products

---

## 8. Design Tokens & Styling

### Colors
| Token | Value | Usage |
|-------|-------|-------|
| `color-primary` | `#000000` (black) | Primary text, buttons, icons |
| `color-background` | `#FFFFFF` (white) | Page & card backgrounds |
| `color-text-secondary` | `rgba(0,0,0,0.5)` | Placeholder text, helper text, subtitles |
| `color-surface` | `rgba(0,0,0,0.05)` | Chip backgrounds, icon containers, image placeholders |
| `color-border` | `rgba(0,0,0,0.1)` | Input borders, card borders, dividers |
| `color-toggle-on` | `#34C759` | Toggle switch active state |
| `color-shadow-light` | `rgba(0,0,0,0.12)` | Top bar & bottom nav shadows |

### Typography
| Style | Font | Weight | Size | Line Height |
|-------|------|--------|------|-------------|
| Page Title | Roboto | Medium (500) | 20px | 24px |
| Section Title | Roboto | Medium (500) | 18px | 24px |
| Button Text | Roboto | Medium (500) | 16px | 22px |
| Price / Metric Value | Roboto | Medium (500) | 16–20px | 24–28px |
| Body / Label | Roboto | Medium (500) | 14px | 20px |
| Body Regular | Roboto | Regular (400) | 14px | 20px |
| Caption / Small | Roboto | Regular (400) | 12px | 16px |
| Tab Label | Roboto | Regular (400) | 10px | 14px |

### Spacing
| Token | Value |
|-------|-------|
| `spacing-page-horizontal` | 12px |
| `spacing-gap-default` | 8–12px |
| `spacing-section-top` | 16px |
| `spacing-card-padding` | 8px |
| `spacing-chip-padding` | 8px |
| `spacing-input-padding` | 12px horizontal, 8px vertical |

### Border Radius
| Token | Value |
|-------|-------|
| `radius-card` | 6px |
| `radius-input` | 6px |
| `radius-chip` | 6px |
| `radius-button` | 8px |
| `radius-icon-container` | 16px |
| `radius-toggle` | 100px (full round) |

### Shadows
| Element | Shadow |
|---------|--------|
| Top Bar | `0px 0px 3px rgba(0,0,0,0.12)` |
| Bottom Nav | `0px 0px 6px rgba(0,0,0,0.12)` |
| Toggle Knob | `0px 3px 8px rgba(0,0,0,0.15), 0px 3px 1px rgba(0,0,0,0.06)` |

---

## App Summary

This is a **price comparison and tracking mobile app** (similar to Idealo) that allows users to:

1. **Search** for products across multiple online platforms (Amazon, Noon, Jumia, etc.)
2. **Compare prices** from different sellers displayed as product cards with seller tags
3. **Track products** by adding them to a personal tracking list with price change monitoring
4. **Set target prices** and receive alerts when prices drop to desired levels
5. **Manage notification preferences** for price updates, alerts, recommendations, and promotions
6. **Contact support** for product inquiries, feedback, or technical issues
7. **Report errors** in product data (wrong images, specifications, etc.)

The app's core value proposition is helping users find the best prices and get notified when products become more affordable.
