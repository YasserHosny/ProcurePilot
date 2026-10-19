# Codex review of the video plan (2026-10-19)

Codex was given `README.md`, `generation-plan.md`, the stills, the card sources, the edit scripts and a frame every 5 s of each finished cut. It was asked to agree or disagree with nine production decisions and to propose prioritised changes that the existing pipeline can implement. It ran read-only and changed no files. Its answer is below, unedited.

---

The strongest asset is the traceable procurement journey. The main weakness is readability: the contact sheets show small interfaces, while the vertical cut accelerates important actions further. I reviewed the supplied documents, scripts and stills; audio judgments below concern the mix specification, not listening verification. No files changed.

1. **Sidebar — AGREE. P3: enforce the stated treatment.**  
   Keep navigation for orientation, then prioritise content. However, `s1-rfq-85.jpg` and the finished RFQ sequence still show the sidebar, so the implementation differs from the plan. In full-cut EDL #6, retain a brief establishing frame, then crop to the form. **Pipeline: yes**—split the segment and use ffmpeg `crop,scale`; a small HTML-rendered scene label can preserve orientation.

2. **Up to 3×, without zooms — DISAGREE. P2: cut repetition and hold decisions.**  
   Full-cut #6, #12 and #18 need readable pauses on selected suppliers, the recommendation, the generated PO and recorded outcome. Remove most typing, cursor travel and loading; hold each decisive result for roughly 2–3 seconds. Enlarge the landscape phone screens too. **Pipeline: yes**—shorter source selections, separate `setpts` speeds, `tpad` holds, crop/scale and restrained `zoompan`. Label accelerated sequences once. The vertical comparison is actually **3.83×** and draft **4×**, exceeding the debated 3×.

3. **Seven separate 3.2-second cards — DISAGREE. P2: integrate most explanations.**  
   These consume **22.4 seconds**, excluding notification and counter. The opening delays the first product shot until **16.4 seconds**; vertical waits **9.4 seconds**. Put the problem/promise over the opening footage, then reach the app by about second 4. Replace intermediate cards with short captions that remain through the relevant action. Keep a distinct savings payoff. **Pipeline: yes**—render transparent Arabic/English PNG overlays in Chrome and composite with ffmpeg; redistribute time to readable result holds.

4. **English cards over Arabic screens — DISAGREE for non-Arabic viewers. P2: translate the evidence.**  
   English viewers can follow the chapter titles but cannot independently understand the supplier comparison, approval state or ledger. Across those scenes, add English callouts translating the actual visible fields, amounts and statuses; identify the interface as Arabic. **Pipeline: yes**, using manually authored HTML overlays anchored to enlarged screen regions. This needs no new product recording or OCR.

5. **Smart Compare instead of RFQ comparison — DISAGREE as the sole comparison beat. P1: reconcile the promise with the evidence.**  
   Full-cut #12 promises “line-by-line,” but demonstrates **oil ×8**, not the complete three-item request. Show the recorded RFQ replies briefly, then Smart Compare as an oil example. Alternatively, change the caption explicitly to “Compare oil offers.” **Pipeline: yes**—insert selected `s3b` footage and crop/highlight relevant rows. Explain that **12,880 versus 13,080 EGP** is a different comparison from the **460 EGP** historical-baseline saving.

6. **Vertical phone fill and fixed web crops — DISAGREE. P1: reframe around evidence.**  
   Around **20–38 seconds**, web screens remain small inside large navy areas; the approval control approaches the bottom edge. Also, Smart Compare uses a **1350-wide** source crop, not 1080. Use successive close crops of photo → extracted total → supplier prices → draft status. Fit the phone proportionally when necessary to retain controls. **Pipeline: yes**—per-shot crop coordinates, scale/pad and HTML captions. Keep critical content inside the documented top/bottom safe areas; inspect actual-size frames.

7. **460 EGP, then 1,060 EGP — AGREE with qualification. P1: distinguish their scope.**  
   At full-cut #19–20, label **460 EGP: this demo order, versus last PO prices**; **1,060 EGP: demo ledger including the earlier dry run**. Hold the counter’s final value for two seconds. In vertical, insert a brief PO/outcome proof before the counter: approval alone does not establish savings. **Pipeline: yes**—revise HTML cards, shorten count-up and replace some opening/card time with existing #18 footage.

8. **Fixed music, no body effects — AGREE. P3: verify the complete export.**  
   Without narration, continuous ducking is unnecessary; body effects add little to muted viewing. However, −6.6 dB gain does not guarantee perceived continuity. **Pipeline: yes**—measure whole-cut loudness/true peak and audition the seam; apply a short gain ramp only if needed. Preserve readable pacing over beat alignment.

9. **Mask email before public posting — AGREE. P1: finish before distributing any version.**  
   Cover identity fields in `s2/s2b`, `s3` and `s4`, including scrolling transitions. **Pipeline: yes**—opaque `drawbox` masks before cropping/scaling; use separate timed boxes when positions move. NumPy template matching can assist detection, but cannot replace frame-by-frame inspection. Check thumbnails and all four exports too.

Additional publication risks: disclose **demo data**, **email-forwarded WhatsApp photo**, and **illustrative notification**; the recorded phone web build did not receive push notifications. State “automatic extraction, then human review”; preserve human RFQ sending and purchase approval. “Verified” means owner-verified records, not independent audit or proven cash recovery. Confirm the two-week offer and supplier-data permissions. Retain licence/download evidence for every stock/audio asset; checksums establish identity, not usage rights. The documented Content ID registration warrants claim preparation, not a promise of claim-free publication.

**Top five, in order:** email masking; accurate savings/demo provenance; vertical reframing; comparison-claim alignment; faster opening with readable decision holds.
