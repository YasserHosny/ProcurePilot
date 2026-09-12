# ProcurePilot Mobile App User Documentation

> Screen-by-screen guide to the ProcurePilot mobile app (Flutter, iOS + Android).
> Last updated: 12 Sep 2026.

---

## Table of Contents

1. [What the mobile app does today](#1-what-the-mobile-app-does-today)
2. [Sign In](#2-sign-in)
3. [Enable Biometric Unlock](#3-enable-biometric-unlock)
4. [App Launch (Splash / Returning-Device Unlock)](#4-app-launch-splash--returning-device-unlock)
5. [Home](#5-home)
6. [Sign Out](#6-sign-out)
7. [Language](#7-language)
8. [FAQ](#8-faq)
9. [Known Limitations](#9-known-limitations)
10. [Design Preview — Coming in Later Releases](#10-design-preview--coming-in-later-releases)

---

**About the images in this doc:** the screenshots below are mockups from the ProcurePilot
Mobile Stitch design system (`stitch_design_system_implementation`), not live captures from a
running device or simulator — this pass reviewed the app's actual source and its own widget
test suite, not a live build. They're a close visual reference for the shipped screens in
sections 2–5, and each one is followed by a **"Shipped vs. mockup"** note calling out anything
in the image that the current build doesn't actually do yet. Section 10 uses the remaining
mockups to preview screens that don't exist in the app at all yet.

For the web app's screens, see [ProcurePilot User Documentation](user-documentation.md). For
route-by-route web navigation paths, see [ProcurePilot User Flows](user-flows.md).

---

## 1. What the mobile app does today

The mobile app is deliberately narrow in this release. It covers:

- Signing in with the same workspace credentials used on web, with an optional biometric
  unlock for return visits.
- A role-aware home screen: everyone sees their role; approvers additionally see a live count
  of requests awaiting their decision.
- Signing out, which also removes the device's push-notification registration.
- Full English/Arabic support, including right-to-left layout in Arabic.

**What it deliberately does not do yet:** it cannot submit a purchase request, and it cannot
approve or reject one. Both are real, visible UI decisions rather than missing screens — see
section 9. The full target experience — request submission, a requests list, low-stock
reporting, and an in-app Settings screen — is previewed in section 10, but none of it is built
yet.

---

## 2. Sign In

**First screen after Splash on a fresh install, or whenever there's no valid stored session.**

![Sign In — design mockup](screenshots/mobile/01-sign-in-mockup.png)

| # | Element | Description |
|---|---------|-------------|
| 1 | **App bar — brand name** | Confirms you're in the ProcurePilot app. |
| 2 | **Email Address field** | Your workspace email. Validated as non-empty and containing `@` before submitting. |
| 3 | **Password field** | Your account password. The eye icon toggles visibility. |
| 4 | **Sign In button** | Authenticates against the same Supabase-backed workspace as the web app. Shows "Signing in..." while in flight. |

**On success:** if the device supports biometric authentication (fingerprint/face), you're taken
to the biometric enrolment offer (section 3); otherwise you go straight to Home.

**On failure:** an inline error message appears above the Sign In button (invalid credentials,
rate-limited, or a generic connection error) — the form stays filled in so you can correct and
retry.

There is no "create workspace" or "forgot password" flow on mobile in this release — use the web
app for those (section 1 of the web documentation).

**Shipped vs. mockup:** the mockup's "Forgot password?" link and EN/AR language segmented
control aren't wired up in the shipped screen — password reset and account creation stay
web-only, and language follows the device locale (section 7). The "Need an account? Contact your
procurement administrator" footer and the SSO/SOC2 badges are mockup chrome only.

---

## 3. Enable Biometric Unlock

**Shown once, immediately after a successful sign-in, only on a device that supports biometrics.**

![Enable Biometric Unlock — design mockup](screenshots/mobile/02-biometric-enable-mockup.png)

| # | Element | Description |
|---|---------|-------------|
| 1 | **Fingerprint icon + "Enable biometric unlock?"** | Explains that enabling lets you unlock the app next time with your device's fingerprint or face recognition instead of typing your password. |
| 2 | **Enable button** | Turns the preference on and proceeds to Home. |
| 3 | **Not now button** | Declines. Proceeds to Home; you're offered this again after your next credential sign-in (the preference is only ever set to "on" explicitly). |

Neither choice blocks you from reaching Home — biometric unlock is a convenience layered on top
of your stored session, never a replacement for it or a requirement to use the app.

**Shipped vs. mockup:** the shipped sheet is simpler than the mockup — no branded top app bar,
no "hardware security module" footnote, and the copy is a shorter, more direct sentence.

---

## 4. App Launch (Splash / Returning-Device Unlock)

A brief loading screen shown every time the app starts, before Sign In or Home.

![Returning-device biometric unlock — design mockup](screenshots/mobile/03-biometric-unlock-mockup.png)

You won't normally interact with it — it decides where to send you:

1. No stored session at all -> Sign In.
2. A stored session, but biometric unlock isn't enabled -> Sign In (re-enter your password).
3. A stored session with biometric unlock enabled -> your device's biometric prompt runs
   automatically. Success refreshes your session silently and takes you to Home; a cancelled,
   failed, or unavailable biometric check falls back to Sign In rather than blocking you.

**Shipped vs. mockup:** the mockup's personalized "Welcome back, Sarah K." branch-header card,
"Use password instead" link, and EN/AR switcher aren't in the shipped screen — today it's a
plain loading indicator while the biometric check runs, with silent fallback to Sign In on
anything other than success.

---

## 5. Home

**Landing screen after sign-in or a successful biometric unlock.**

![Home — Branch Manager, design mockup](screenshots/mobile/04-home-branch-manager-mockup.png)
![Home — Approver, design mockup](screenshots/mobile/04b-home-approver-mockup.png)

| # | Element | Description |
|---|---------|-------------|
| 1 | **App bar — "Home"** | With a sign-out icon button in the top-right corner. |
| 2 | **Your role** | Shows your workspace role (Owner, Buyer, Branch Manager, Approver, or Viewer) — the same roles as the web app (section 21 of the web documentation). |
| 3 | **Request items button** | Visible to Owner, Buyer, and Branch Manager roles. **Currently shown disabled** — a deliberate placeholder rather than a fake working flow. Request submission from mobile is a later release. |
| 4 | **Pending decisions count** | Visible only to Approver (and Owner) roles: a card reading "N request(s) awaiting your decision," loaded from the same pending-approvals list used by the web Approval Queue. Shows a spinner while loading and an inline error message if the count can't be fetched. |

**What's deliberately absent:** there is no approve, reject, or any other decision control on
this screen or anywhere else in the app — see section 9. The pending count is read-only; to act
on a request, use the web app's Approval Queue (section 18 of the web documentation).

**Shipped vs. mockup:** this is the biggest gap between mockup and shipped build on this page.
The shipped Home screen is just a role label, the (disabled) Request items button, and — for
approvers — a single plain count card. The mockup's bottom navigation bar (Home / Requests /
Settings), "New request" hero card, Low-stock report tile, "My requests" tile, and recent-activity
feed are all target design for later releases — see section 10. One thing the mockup gets
right, though: its approver card explicitly says pending approvals are reviewed on a "desktop
authorization terminal" — the same no-mobile-decisions constraint the shipped app enforces.

---

## 6. Sign Out

Tap the sign-out icon in the Home app bar. This:

1. Best-effort deregisters this device from push notifications (a failure here doesn't block
   sign-out — you're still signed out even if the deregistration call fails).
2. Clears the biometric-unlock preference, so the next sign-in starts fresh.
3. Clears the locally stored session and returns you to Sign In.

---

## 7. Language

The app follows the same shared English/Arabic translation catalogue as the web app
(`packages/i18n`). Arabic renders the entire layout right-to-left. There is no in-app language
switcher yet on mobile — language currently follows the device/system locale. (The target
Settings screen previewed in section 10 adds one.)

---

## 8. FAQ

**Q: Why can't I submit a purchase request from my phone?**
A: That flow hasn't shipped yet. For now, create and submit requests from the web app
(sections 16–17 of the web documentation); the mobile app will grow this capability in a later
release. The "Request items" button on Home is a visible placeholder, not a bug.

**Q: I'm an approver — why can't I approve or reject from my phone?**
A: This is an intentional constraint, not a gap: ProcurePilot never allows autonomous or
mobile-only purchasing decisions in this release. The Home screen shows you *how many* requests
are waiting, so you know to go make the decision on the web app's Approval Queue.

**Q: Do I need to sign in every time I open the app?**
A: Only if you haven't enabled biometric unlock, or your device doesn't support it. Otherwise, a
fingerprint or face check unlocks your existing session.

**Q: What happens if I decline biometric unlock?**
A: Nothing is lost — you're taken to Home immediately, and you can still use the app normally
with password sign-in each time. You'll see the offer again after your next credential sign-in.

**Q: The screenshots show a "New request" screen, a requests list, and a Settings tab — where
are those in my app?**
A: Not shipped yet. Those images are design mockups for upcoming releases, shown for reference in
section 10 — the current app is Sign In, biometric unlock, and Home only.

---

## 9. Known Limitations

| # | Area | Limitation |
|---|------|-----------|
| 1 | Home | "Request items" is a disabled placeholder — no request-submission flow exists on mobile yet. |
| 2 | Home / Approvals | No approve/reject control exists anywhere in the app, by design (see FR-009 in the FAQ above) — only a read-only pending count for approvers. |
| 3 | Navigation | No bottom navigation, requests list, or Settings screen exists yet — Home is the only screen after sign-in. |
| 4 | Language | No in-app language switcher; the app follows the device locale. |
| 5 | Sessions | If a session is revoked server-side, the mobile client's own refresh-token exchange happens directly against Supabase Auth rather than through ProcurePilot's API — this path has a documented gap in test coverage, not a confirmed bug (see the engineering notes in `apps/api/tests/integration/test_session_revocation.py`). |

If you hit anything beyond this list, flag it to the product team.

---

## 10. Design Preview — Coming in Later Releases

**None of the screens in this section exist in the app yet.** They're shown here as design
mockups from the Stitch design system so you know what's coming and can plan around it — treat
every image below as a target design, not a feature you can use today.

### New Request

![New Request — design mockup](screenshots/mobile/05-new-request-mockup.png)

Mobile-native request submission: destination branch, required-by date, a product search/catalogue
picker, quantity steppers per line, and a budget pre-check before submitting. This is the mobile
equivalent of the web app's New Purchase Request screen (section 17 of the web documentation).

### My Requests

![My Requests — design mockup](screenshots/mobile/06-my-requests-list-mockup.png)
![My Requests — empty state, design mockup](screenshots/mobile/06b-my-requests-empty-mockup.png)

A requester's own request history on mobile, with status filters (Draft, Submitted, Approved,
Rejected, Withdrawn, and an offline "Queued" state for drafts captured without connectivity) and
an empty state guiding a first-time user to create a request.

### Request Detail & Decision

![Request Detail & Decision — design mockup](screenshots/mobile/07-request-detail-decision-mockup.png)

A read-only, requester-facing view of a decided request: line items, the approver's decision
comment, and a lifecycle timeline (Submitted → In Review → Approved/Rejected). This mirrors the
Approval section already shown on the web request detail view (section 17 of the web
documentation) — it does not add any approve/reject control on mobile.

### Low-Stock Report

![Low-Stock Report — design mockup](screenshots/mobile/08-low-stock-report-mockup.png)
![Low-Stock Report — success and offline-queued states, design mockup](screenshots/mobile/08b-low-stock-report-states-mockup.png)

A lightweight "shelf is running low" signal a branch user can send straight to dispatch — no
photo, no requisition paperwork, distinct from submitting a full purchase request. Note the
"Queued (offline)" state: like the rest of the mobile app's offline-tolerant design, a report
made without connectivity is stored locally and sent automatically once the device is back
online. The backend schema for this (`low_stock_report`) already exists (shipped as part of the
R2.2 mobile schema); only the mobile screen itself is still to come.

### Settings

![Settings — design mockup](screenshots/mobile/09-settings-mockup.png)

A dedicated Settings screen: account info, assigned branch, a notification toggle, an in-app
language switcher, help/feedback, app version, and sign-out. Today, the only settings-like
control in the app is the sign-out icon in the Home app bar (section 6); language follows the
device locale (section 7).
