# Order Tracking and Three-Way Match Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build R3.3 order tracking, supplier confirmation, delivery receipt, three-way reconciliation, and a read-only Xero connector while preserving QuickBooks and purchasing workflows.

**Architecture:** Extend the existing accounting connector and reconciliation boundaries. Add a focused order-tracking module for internal order and receipt evidence, tenant-scoped migrations with forced RLS, and a deterministic three-way match service. Reuse encrypted tokens, advisory-lock workers, audit events, and existing UI/API patterns.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, psycopg, Supabase Postgres/RLS, httpx, Angular 19, Angular Material, Karma/Jasmine, Playwright, axe-core, `packages/i18n`.

---

The complete task-by-task plan is maintained in [specs/016-order-tracking-three-way-match/plan.md](/media/yasserhosny/My%20Passport/Work/Projects/ProcurePilot/specs/016-order-tracking-three-way-match/plan.md), with the requirements in [spec.md](/media/yasserhosny/My%20Passport/Work/Projects/ProcurePilot/specs/016-order-tracking-three-way-match/spec.md).

Execution order:

1. Data migrations and Xero connector foundation.
2. Internal purchase-order, confirmation, and receipt workflow.
3. Deterministic three-way matching and discrepancy reopening.
4. UI, localization, isolation, E2E, accessibility, security, and G3 evidence.

No external provider write method, autonomous purchasing behavior, implicit currency, or tenant
RLS exception is permitted at any step.
