# Quickstart: In-App User Feedback

Run and verify spec 025 locally once implemented. Commands are from `CLAUDE.md`; nothing here applies until
the migrations and code from `tasks.md` exist.

## 1. Bring up the stack and apply migrations

```bash
docker compose up --build
pnpm db:migrate            # applies 20261118000100..000700 and ends with db:check-privileges
```

`db:check-privileges` must pass: both feedback tables forced-RLS, `platform_operator` unreachable by client
roles, no client mutation of `audit_event`.

## 2. Seed users

Use the existing seed (`pnpm db:seed`) so two workspaces exist, each with an owner and members of several
roles. Mark one workspace as demo:

```sql
update tenant set is_demo = true where slug = '<demo-slug>';
```

## 3. Make yourself a platform operator (service role, audited)

```bash
cd apps/api
uv run python -m procurepilot_api.workers.platform_operator_cli grant you@example.com
uv run python -m procurepilot_api.workers.platform_operator_cli list
uv run python -m procurepilot_api.workers.platform_operator_cli revoke you@example.com
```

The user must already be a member of a workspace.

## 4. Walk the stories

| Story | Steps | Expect |
|---|---|---|
| 1 Text | Sign in as a `viewer`, open the widget, send text with a category | Success message, item in `/feedback` with status `new`; notice about staff visibility shown |
| 1 Cooldown | Send again within 30 s | Refused with seconds left; draft kept |
| 2 Screenshots | Add 5 images by picker, drop and paste; try a 6th and a renamed `.exe` | 6th refused; bad file rejected before upload |
| 3 Audio | Record, replay, re-record; upload an MP3 | Playback works; 2-minute cap stops recording |
| 4 Own and owner | As owner of the same workspace open `/feedback/workspace`; as the other workspace's owner do the same | Sees the first workspace's items only; no controls to change anything |
| 4 Withdraw | As the submitter withdraw a `new` item; try one already `reviewed` | First removed everywhere; second refused |
| 5 Triage | As operator open `/platform/feedback`, filter by status, category, workspace; open an item; mark reviewed, add a label | Name and email visible; both changes saved; owner and submitter see the new status, not the label |
| 5 Revoke | Revoke the operator, reload the triage page | 404 on the next request |
| 5 Digest | Turn the digest on, run the worker once | One email with workspace, category, excerpt, link; no email address or attachments |

## 5. Worker

```bash
cd apps/api
uv run python -m procurepilot_api.workers.feedback_worker --once
```

Runs the digest, the 12-month retention purge and the orphan-object sweep once.

## 6. Test suites

```bash
pnpm test:isolation        # includes the new feedback tables
pnpm test:api              # unit, contract, integration (needs TEST_DATABASE_URL)
pnpm test:web              # Karma
pnpm test:e2e              # Playwright: submit, own list, owner inbox, triage, withdraw
pnpm test:a11y             # axe-core in en and ar
pnpm lint                  # ruff, Angular lint, i18n key check
```

## 7. Docs screenshots

The widget changes every shell screenshot slightly. Before opening the PR:

```bash
pnpm --filter web docs:screenshots
python scripts/docs_screenshots_diff.py
```

If the diff exceeds the 1% threshold, commit the regenerated images in `docs/user/screenshots/`.
