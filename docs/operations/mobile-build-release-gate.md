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

Until both of those are true, this checklist is the actual gate. Run it before any store
submission — not on every PR, not on a schedule, but as a deliberate release-readiness step.

## 1. App size

```bash
cd apps/mobile
flutter build apk --release
ls -la build/app/outputs/flutter-apk/app-release.apk
```

- **Budget: under 30MB.** If the release APK exceeds this, check for the usual causes first
  (unused asset bundling, a debug-only dependency that leaked into the release build, missing
  `--split-per-abi`) before assuming the budget itself needs revisiting.
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
1. Run `.github/workflows/mobile-build-size-check.yml` manually at least once against a live
   GitHub Actions runner and confirmed it builds successfully and correctly fails when the APK
   exceeds budget (e.g., by temporarily lowering the threshold to prove the failure path works),
   and
2. Found a reliable, non-flaky way to automate the cold-start measurement (a proven Android
   emulator GitHub Action, or accepted that it stays manual indefinitely because device-level
   timing in CI is inherently unreliable),

promote the build-size job into `ci.yml`'s required set and update this document to say so. Until
then, treat this checklist as the actual gate, not the workflow file.
