# ProcurePilot Mobile

Flutter app for branch managers and approvers: submit purchase requests, report low stock, and
stay informed of decisions on the move — R2.2 Mobile MVP (roadmap §7.2/§12). Approving from
mobile, delivery confirmation, and camera/barcode capture are explicitly out of scope this
release (R2.3); see `specs/009-mobile-app-mvp/spec.md`.

Builds entirely on R2.1's existing request/approval data model and API — `/requests` and
`/approvals/*` are reused unchanged. The only new backend surfaces are device push-token
registration (`/devices`) and the low-stock report (`/low-stock-reports`); see
`specs/009-mobile-app-mvp/contracts/mobile.openapi.yaml`.

## Structure

```text
lib/
  core/
    auth/           Sign-in/refresh against the same Supabase Auth endpoint web uses;
                     biometric unlock only ever gates use of an already-valid refresh token
    i18n/           Reads the shared packages/i18n/{en,ar}.json catalogue as a bundled asset —
                     no forked mobile-only string catalogue
    offline_queue/  Local persistence for a queued request/low-stock submission; the
                     Idempotency-Key is stamped at creation time, not send time
    api/            Typed client for /devices and /low-stock-reports
```

See `specs/009-mobile-app-mvp/research.md` for the design decisions behind each of these
(R1: push delivery via a durable outbox + retry sweep; R3: auth reuse; R4: offline idempotency;
R6: i18n asset loading) and `specs/009-mobile-app-mvp/tasks.md` for the task breakdown this
scaffold implements (T004-T006, T013 Dart half, T015-T017).

## Development

```bash
flutter pub get
flutter analyze
flutter test
```

Local persistence uses Hive (not sqflite) — a pure-Dart key-value store with no native SQLite
dependency, so `flutter test` runs deterministically without an Android/iOS toolchain.
