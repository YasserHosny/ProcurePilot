# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`GLOSSARY.md`** at the repo root.
- **`docs/architecture/adrs.md`**: the single ADR log. Read the ADRs that touch the area you're about to work in.

If `GLOSSARY.md` doesn't exist, **proceed silently**. Don't flag its absence; don't suggest creating it upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates it lazily when terms actually get resolved.

## File structure

Single-context repo:

```
/
├── GLOSSARY.md
└── docs/architecture/adrs.md   ← ADR-001, ADR-002, … as sections in one file
```

## Recording a new ADR

Append it to `docs/architecture/adrs.md` as the next `## ADR-0NN — <title>` section, numbered after the last one, in the existing format: **Status**, **Context**, **Options considered**, **Decision**, **Consequences**. Don't create a separate `docs/adr/` directory.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `GLOSSARY.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-019 (guardrails evaluated at match-decision time), but worth reopening because…_
