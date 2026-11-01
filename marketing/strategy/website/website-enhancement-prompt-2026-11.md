---
scope: company (Iron Systems) website
status: prompt for the website session; copy marked "draft" needs Yasser's approval before it ships
created: 2026-11-02
based_on: strategy/b2b-focus-2026-11.md (section 2, decisions B-2 to B-4)
sources_at: website a1904c7 (lib/site.ts, app/components/Contact.tsx) · ProcurePilot docs/gtm/video/README.md (WhatsApp number)
---

# Prompt for the website session (copy everything below the line)

Yasser (2026-11-02): "give me a prompt of the site enhancement upon our plan to continue in the site session".
Paste the text below into the Claude session that works in `Website/iron-system-next`.

---

You're working on the Iron Systems website (`E:\Omar-Space\IronSystem\Website\iron-system-next`, Next.js, EN + AR,
live at www.iron-sys.com, last deployed commit a1904c7). Read the repo's README, `DEPLOY.md` and the brand rules
(Iron Systems identity v3.3, `<workspace>/Branding/Identity-v3/README.md`) before you change anything.

## Why we're changing it

Iron Systems sells to businesses (B2B). A business buyer checks our site before replying to a message or taking a
call, and today the site reads like a generic software agency: a big company name, a 3D logo, lists of services
and chips, no people, and a contact form that opens the visitor's email app. The goal is a site that feels
**natural, human and premium**: calm and specific, with fewer words but concrete ones, generous space, real
material (our own screens and video) and no claims we can't show.

## Fixed rules

- Keep the brand: dark theme by default, the current palette, no glow effects, Iron Systems identity v3.3.
- Both languages for every change. Company Arabic is Modern Standard Arabic written natively, not translated.
  RTL with logical CSS properties.
- **No invented facts:** no client names or logos, numbers, years, team size, offices, testimonials or results.
  ProcurePilot screens use demo data and are labelled as demo data.
- Copy marked **draft** below is a direction. Show it to Yasser and get his OK before it goes live.
- Work on a branch. Run the tests, check EN + AR on desktop and mobile, and send Yasser screenshots.
  **Don't deploy to www.iron-sys.com until Yasser approves the result.**

## Changes, in priority order

### 1. Contact: email + WhatsApp (decision B-4: do this now)

- Replace the form as the main action with two clear buttons:
  - **WhatsApp:** `https://wa.me/201027354140` with a short prefilled message
    (EN "Hi, I'd like to talk about a project with Iron Systems." · AR «مرحبًا، أودّ التحدث معكم عن مشروع.»).
    Add the number to `lib/site.ts` next to `EMAILS` so it's set in one place. It's the same number shown in the
    ProcurePilot demo video. Show it as `+20 102 735 4140` (LTR in the Arabic page).
  - **Email:** `hello@iron-sys.com` (already in `lib/site.ts`).
- The form can stay underneath as a secondary option, or be removed. Ask Yasser.
- **No booking link.** Add a reply-time line ("We reply within one working day") only if Yasser confirms he can
  keep it.
- Put the WhatsApp button in the footer too, and in the header on mobile if it fits without clutter.

### 2. Hero: say what we do for a business

- Replace "Powering Businesses with Intelligent Technologies" and the company-name headline.
- **Draft** headline: EN *"We build the software your operations run on, and we stay to keep it running."*
  AR «نبني البرمجيات التي تقوم عليها أعمال شركتك، ونبقى معك لتستمر في العمل.»
- One short supporting line and one action ("Talk to us" → contact). The wordmark gets smaller with more space
  around it. The 3D forge moves further down (one moment, not the first screen), or goes. Show Yasser both options.

### 3. Founder section (decision B-3: an avatar for now, no photo)

- A short section: **Dr. Yasser Hosny / «د. ياسر حسني»**, Founder, with an **avatar** where the photo will go
  later: a monogram ("YH") in the brand style. No stock photo, no AI-generated face. Build it so a real photo can
  replace the avatar later by changing one file.
- **Draft** note (three sentences, EN; write the AR natively):
  *"I started Iron Systems to build software that businesses can run on every day. We design it with the people
  who'll use it, use AI only where it saves real work, and stay after launch to keep it running. ProcurePilot,
  our own product for restaurant purchasing, is built the same way."*
- No location yet (not confirmed), no years of experience, no client claims.

### 4. One section instead of three lists

- Merge Services (4 cards), AI capabilities (6 rows) and the stack strip into one section: **the problems we
  solve**. That means documents re-typed by hand, approvals done in chats, and data spread across sheets, each
  with a sentence or two on the kind of system that fixes it. ProcurePilot is the worked example.
- Fewer tags and chips, more sentences.

### 5. ProcurePilot case page

- A new page (EN + AR, e.g. `/procurepilot` and `/ar/procurepilot`), linked from the home page as
  "See something we built".
- Sections: the problem (restaurant groups collect supplier quotes over WhatsApp and compare them in Excel), what
  we built (reads quotes, compares per pack with VAT and delivery, a manager approves from the phone, the saving
  is recorded), real screens (demo data, labelled), the demo video, and how a pilot works (free for the agreed
  pilot period, we set it up with you).
- **Video:** ask Yasser which cut to use. The latest approved demo is v2.5 in the ProcurePilot repo
  (`docs/gtm/video/`). Optimise it for the web (poster image, compressed MP4, captions) and don't autoplay
  with sound.
- **Prices are not shown** (owner decision MD-07).
- Two actions: WhatsApp us, and open procurepilot.iron-sys.com.

### 6. Calmer look

- More whitespace, larger and calmer type, fewer orange accents, slower and fewer animations.
  Respect `prefers-reduced-motion`.
- Check that the page still loads fast (Lighthouse before/after) and stays accessible (contrast, focus states,
  alt text).

## Deliver

1. A branch with the changes and passing tests.
2. EN + AR screenshots (desktop and mobile) of: hero, problems section, founder section, case page, contact.
3. A short list of the draft copy for Yasser to approve.
4. Deploy only after Yasser says so.

Out of scope here: the ProcurePilot landing page (`procurepilot.iron-sys.com`) lives in the ProcurePilot repo; its
contact step will be matched separately.
