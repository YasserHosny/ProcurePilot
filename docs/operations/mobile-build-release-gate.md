# Mobile build-size and cold-start gate (T046, `009-mobile-app-mvp`)

`specs/009-mobile-app-mvp/plan.md`'s own Performance Goals: **cold start under 2.5s** on a
mid-range Android device, **app size under 30MB** download (roadmap §12.4). Both must be checked
before any store submission is attempted — this document is that check.

## Why this is a manual gate, not a CI job

This repo's own `.github/workflows/ci.yml` states its standing rule plainly: *"Every check here
is required to merge. A gate nobody has watched fail is not a gate, so each job below has been run
locally against the real stack before being wired in."* Two things prevent that standard being met
here today:

1. **Cold start cannot be measured without a running device or emulator.** A headless CI runner
   has neither by default. Faking a number that always "passes" would be worse than no check at
   all — this project already learned that lesson the hard way with `_send_to_device`'s old
   "always sent" stub (Wave 5/6 of this feature's own build).
2. **The build-size half is plausibly automatable** (GitHub's `ubuntu-latest` runners ship the
   Android SDK), but this repo has no existing CI job that builds `apps/mobile/` at all, and this
   environment has no local Android SDK to verify `flutter build apk --release` actually succeeds
   here before wiring it in as a required, PR-blocking check. A companion workflow
   (`.github/workflows/mobile-build-size-check.yml`) exists as a **manually-triggered, optional**
   check for exactly this reason — run it once yourself against a real GitHub Actions runner
   and confirm it both builds and correctly fails on an oversized APK before ever promoting it
   into `ci.yml`'s required set.

**Status (2026-11-19): size budget met, both paths proven.**

- **Failure path:** proven on 2026-10-17 (runs `39075120933`, `39075595173`). That build made one
  "fat" APK carrying the engine and app code for every CPU type: 54,438,989 bytes, over budget.
- **Pass path:** proven on 2026-11-19 (run `44432335292`). The budget is a *download* size and a
  device downloads one per-ABI build (from a Play app bundle, or a per-ABI APK), never the fat APK.
  So the workflow now builds `--split-per-abi` (with `--split-debug-info`) and checks each APK:

  | APK | Bytes | MB |
  |---|---|---|
  | `app-arm64-v8a-release.apk` (nearly all current phones) | 19,135,243 | 18.2 |
  | `app-armeabi-v7a-release.apk` (older 32-bit phones) | 16,689,669 | 15.9 |
  | `app-x86_64-release.apk` (emulators, Chromebooks) | 20,436,194 | 19.5 |

- **Mobile suite in CI:** the same workflow now runs `flutter analyze --no-fatal-infos` and
  `flutter test` (290 tests passing) first, and it runs on every PR that touches `apps/mobile/` as
  well as on demand. It is still not a required check.
- **Toolchain:** current stable Flutter needs Android Gradle Plugin 9.1.1 or later (bumped from
  9.1.0 in `android/settings.gradle.kts`). It also reports every `package:flutter/material.dart`
  import as deprecated in favour of `package:material_ui`; that migration is separate work, so
  analyze does not fail on infos. The app itself has shipped
(auth, home, requests, approvals, low-stock, delivery); this gate is about store submission. Push
notifications are not delivered yet: the server-side sender is a stub with no FCM/APNs
credentials (runbook §3.5), so a store release would ship without working pushes.

Until both of those are true, this checklist is the actual gate. Run it before any store
submission — not on every PR, not on a schedule, but as a deliberate release-readiness step.

## 1. App size

```bash
cd apps/mobile
flutter build apk --release --split-per-abi --split-debug-info=build/debug-info
ls -la build/app/outputs/flutter-apk/app-*-release.apk
```

- **Budget: under 30MB per ABI** — each `app-<abi>-release.apk` is what a device downloads. A
  plain `flutter build apk --release` makes one fat APK for all CPU types (54MB on 2026-10-17);
  that number is not the download size and is not the budget. For a store release, upload an app
  bundle (`flutter build appbundle`), from which the store serves the per-ABI split. If a split APK
  grows past budget, check the usual causes (unused asset bundling, a debug-only dependency leaking
  into the release build) before revisiting the budget.
- Keep `build/debug-info` (the workflow uploads it as the `mobile-debug-info` artifact): it is what
  turns a release crash stack trace back into readable frames.
- For iOS, the equivalent is `flutter build ipa --release` and the resulting `.ipa` size — this
  project has not yet needed an iOS release build, so no local recipe for it is recorded here yet;
  add one when that day comes rather than guessing at it now.

## 2. Cold start

Requires a real or emulated **mid-range** Android device — not a high-end host machine, which
will pass trivially and tell you nothing about the actual target hardware the 2.5s budget is
written for.

```bash
# Install the release build from step 1, then:
adb shell am start -W <package-name>/<launch-activity>
```

- Read the `TotalTime` field from `adb`'s own output — that is the cold-start figure, in
  milliseconds, measured by the Android platform itself, not a guess.
- **Budget: under 2500ms.** Run this from a genuinely cold state (`adb shell am force-stop
  <package-name>` first, or a device reboot) — a warm start will read faster and tell you nothing
  about the number this budget actually cares about.
- Record the actual measured figure (not just pass/fail) in the release notes or PR description
  for whichever release this gate is being run for, so a regression between releases is visible
  later even if each individual release passed.

## When this can become a real CI job

Once someone has:
1. ~~Run `.github/workflows/mobile-build-size-check.yml` against a live runner and seen it both
   fail on an oversized APK and pass~~ — done (2026-10-17 failure, 2026-11-19 pass), and
2. Found a reliable, non-flaky way to automate the cold-start measurement (a proven Android
   emulator GitHub Action, or accepted that it stays manual indefinitely because device-level
   timing in CI is inherently unreliable),

promote the build-size job into `ci.yml`'s required set and update this document to say so. Until
then, treat this checklist as the actual gate, not the workflow file.
