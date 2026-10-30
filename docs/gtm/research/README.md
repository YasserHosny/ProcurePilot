# Customer research: discovery calls → ICP and pains

**Written**: 2026-10-30 · **Jira**: PPS-116 (P-85) · **Built with**: the `customer-research` skill (mode 3: primary research, analysed with mode 1)

The ICP and pain list in [`first-customer-gtm-plan.md`](../first-customer-gtm-plan.md) are **hypotheses**. Nobody outside the team has confirmed them yet. This folder is how we turn G-9's discovery calls into evidence.

| File | What it is | Committed? |
|---|---|---|
| `README.md` (this file) | The method | Yes |
| [`call-notes-template.md`](call-notes-template.md) | One copy per call | Yes (the blank template) |
| `calls/YYYY-MM-DD-<company-slug>.md` | Filled-in notes | **No.** Local only: `calls/` is in `.git/info/exclude` (named people; the repo is public), like `prospects/` |
| `synthesis-YYYY-MM-DD.md` | Themes after 5+ calls, nobody named | Yes, once it exists (phase 2) |

## Phase 1 — capture every call the same way (now)

1. Before the call: copy the template to `calls/`, fill in the header from the SP Lead.
2. During the call: use the [discovery call script](../outreach/discovery-demo-call-script.md). Write **exact words**, in the language they used (Arabic as Arabic). A paraphrase loses the signal.
3. Within 24 hours: finish the extraction section and score the pilot criteria. Copy the one-line summary into the SP Lead comment.

**Two rules from the skill that matter most here**
- **Try to prove the hypothesis wrong.** The question is not "do they like it?" but "is the pain we assumed really there, and does it cost them something?" Write down the calls where it isn't.
- **Don't talk about research.** A discovery call is a conversation about how they buy, not an interview. People perform for interviews.

Consent: say at the start that you take notes and that nothing they say is shared with their name on it. Never record without asking.

## Phase 2 — synthesis (after 5 calls; blocked by G-9, PPS-19)

The skill's minimum is **5 independent data points per segment** before drawing conclusions. Below that, findings are signals to watch, not facts.

1. **Code each call** with the theme tags from the template (pain, trigger, outcome, alternative, objection). One person codes, so tags mean the same thing throughout.
2. **Cluster** similar quotes under a theme. Name each theme in the buyer's words where possible.
3. **Score** each theme: frequency (in how many calls?) × intensity (said unprompted, with a story or a number = high; agreed when asked = low).
4. **Segment before counting**: owner vs. purchasing manager; 2–4 branches vs. 5+; Egypt vs. KSA. A theme that holds in one segment only is still useful, but say which.
5. **Confidence label** on every finding:

| Confidence | When |
|---|---|
| High | 3+ calls, unprompted, holds across segments |
| Medium | 2 calls, or only when prompted, or one segment only |
| Low | 1 call; could be an outlier |

6. **Flag contradictions**: "says the WhatsApp process is fine" but "can't name last week's cheapest supplier".
7. **Money quotes**: the 5–10 verbatim lines that best show each theme (no names; role and branch count only).

### What phase 2 updates
| Finding | Goes to |
|---|---|
| Confirmed or killed pains | ICP and pain sections of `first-customer-gtm-plan.md`; `marketing/ProcurePilot/knowledge/target-audience.md` |
| New objections | The matching battlecard ("heard N times") |
| Buyer vocabulary | DM script, cold email, LinkedIn posts (exact phrases) |
| Disqualifying patterns | Wave 2 prospect criteria |
| Product gaps that block a pilot | PPS tasks labelled `from-demo` |

No personas before 5 calls in one segment. Don't fill a persona field without evidence; leave it blank.

## Synthesis template (phase 2)
```
## Theme: [name, in the buyer's words]
Summary: [1–2 sentences]
Frequency: N of M calls · Intensity: high / medium / low · Confidence: high / medium / low
Segments: [where it holds]
Quotes:
- «...» — [role], [n] branches, [date]
Implication: [messaging / product / ICP / nothing yet]
```
