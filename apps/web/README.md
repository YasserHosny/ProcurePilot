# ProcurePilot Web

Angular 19 single-page application — the primary ProcurePilot interface (Phase 1 is web-only).

## Install

```bash
pnpm install
```

## Run

```bash
npx ng serve          # http://localhost:4200
```

For the full local app with the API and workers, follow
[`docs/operations/local-dev.md`](../../../docs/operations/local-dev.md). Local development uses the
hosted Supabase project; do not start a local Supabase database.

## Test and lint

```bash
npx ng test           # Karma + Jasmine
npx ng lint           # ESLint; `any` is an error, not a warning
npx ng build          # production build
```

## Structure

```text
src/app/
├── core/        cross-cutting: auth guard and interceptor, session, API client, i18n
├── layout/      the authenticated shell: navigation, workspace switcher, account menu
└── features/    feature areas: auth, onboarding, team, settings
```

## Conventions

- Standalone components only — no NgModules.
- Strict TypeScript. No `any`.
- Every user-facing string comes from `packages/i18n` (en + ar). No hardcoded copy.
- Use CSS logical properties (`margin-inline-start`, not `margin-left`) — the app must work in RTL.
