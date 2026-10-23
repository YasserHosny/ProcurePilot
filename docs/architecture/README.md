# Architecture

> Design documents and flow diagrams for ProcurePilot. The code and `specs/` win where they disagree.

---

## Documents

- [`tech-stack-blueprint.md`](tech-stack-blueprint.md) — Technologies, versions and repository structure.
- [`adrs.md`](adrs.md) — Architecture Decision Records and their rationale.
- [`engineering-spec.md`](engineering-spec.md) — Low-level design: service boundaries, API patterns, data layer, security model.
- [`api-specification.md`](api-specification.md) — OpenAPI-style contract for the Phase 1–2 endpoints.
- [`data-dictionary.md`](data-dictionary.md) — Field-level definitions for the core entities.

## Flow diagrams

Interactive HTML diagrams: open them in a browser. Every box links to the source lines it describes, at the commit
named in its `.json` source.

| Diagram | Shows | Source commit |
|---|---|---|
| [Quotation extraction flow](quotation-extraction-flow.html) | Web, email and mobile intake → extraction worker → readers (CSV/XLSX, Bedrock, Azure DI) → review gate → extracted / in review / refused | `78eb1b6` |
| [RFQ sourcing flow](rfq-sourcing-flow.html) | Draft RFQ → Mailgun → supplier reply matched by email threading → draft purchase request, manually or by guarded auto-preparation | `eaccf18` |
| [Purchase request approval lifecycle](purchase-request-approval-lifecycle.html) | Draft → submitted → ordered → delivered, reject and withdraw exits, approver routing | `9fcd827` |

The diagrams are snapshots and drift as the code changes. To redraw one, edit its `.json` source (re-check the cited
line ranges against the current code and update `meta.repository.revision`), then run Archify's `finalize` from the
repository root:

```bash
node <archify>/bin/archify.mjs finalize workflow docs/architecture/rfq-sourcing-flow.workflow.json docs/architecture/rfq-sourcing-flow.html --repo-root . --quality showcase --out-dir .archify/rfq-review
```

Use the subcommand that matches the file's suffix: `workflow`, `lifecycle`, `architecture` or `sequence`. `--out-dir` moves the browser-check and finalize
receipts into the ignored `.archify/` folder; the `*.delivery.json` receipt is still written next to the HTML, so
delete it rather than commit it.
