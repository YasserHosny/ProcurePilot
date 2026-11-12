# Factory dispatch runner

`dispatch.py` turns a delegation into a job: a throwaway clone, a checkpoint, a brief sent
through a fleet lane, and one or more **gate commands** that must pass in the clone after the
implementer exits. The gate runs outside the implementer's sandbox and its real output is
recorded, so "done" means the gate passed, not that the implementer said so.

The supervisor runs detached from the shell that started it. A job keeps going when the chat
turn ends or the desktop app closes, and `status` reads its state back from disk.

```bash
# one job
scripts/factory/dispatch.py new --lane feature --brief ~/factory/brief-pps-170.md --name pps-170 \
  --gate '.venv/bin/pytest apps/api/tests/unit/test_rfq_split.py -q'

# a web job: hardlinks a verified apps/web/node_modules and clears .angular
scripts/factory/dispatch.py new --lane ui --brief brief.md --web \
  --gate 'cd apps/web && npx ng test --watch=false --include="**/quotation-review/**"'

scripts/factory/dispatch.py status                 # every job, newest first
scripts/factory/dispatch.py status <job>           # summary with gate output
scripts/factory/dispatch.py logs <job> --follow    # supervisor log (--relay for the implementer's)
scripts/factory/dispatch.py diff <job> [--patch]   # changes against the checkpoint
scripts/factory/dispatch.py gate <job>             # re-run the gates in the foreground
scripts/factory/dispatch.py stop <job> [--force]
scripts/factory/dispatch.py clean <job> | --done   # remove clones; job records and patches stay
```

## What a job looks like

```text
~/factory/
  jobs/<job>/
    job.json          state: status, lane, checkpoint, relay status, gate results, events
    brief.md          your brief + the appended "Factory gate" footer
    preflight.log
    supervisor.log
    relay.log         implementer stdout/stderr
    relay/            the relay's own artifacts (result.json, final.txt, events)
    gate-N.log        one per gate, real output
    changes.patch     diff against the checkpoint, including untracked files
    changes.stat
    summary.md        written on every terminal state
    STOP              sentinel written by `stop`
  clones/<job>/       the working tree, branch factory/<job>, tag factory/checkpoint
```

Status values: `created` → `cloned` → `running` → `gating` → `passed` | `gate_failed`, or
`implementer_failed`, `no_changes`, `timeout`, `stopped`, `preflight_failed`. `status` marks a
running job `(stale)` when its heartbeat is older than three minutes and `(supervisor dead)`
when the process is gone.

## What preflight enforces

Each of these came from a real failure in this project's delegation history.

| Check | Why |
|---|---|
| Free disk and memory floors (`FACTORY_MIN_DISK_GB`, `FACTORY_MIN_MEM_GB`) | the root disk hit 100% mid-dispatch, twice |
| Clone from **origin**, objects shared with the local checkout | clones based on a stale local `main` rebuilt a commit that reverted newer work |
| `lfs.fetchexclude docs/gtm/video` | demo video stays as pointers; git-lfs is installed, so they are never re-committed as raw files |
| Git identity copied into the clone | fresh clones had none, and the checkpoint check failed |
| Checkpoint commit tagged `factory/checkpoint` before the implementer starts | a forced `pnpm install` once wiped a clone with no recoverable base |
| `--web`: hardlink `apps/web/node_modules` only from a source whose `@angular/core` matches `apps/web/package.json`; clear `.angular` | the main checkout carried Angular 19 under an Angular 22 lockfile; a bloated cache made Agy's workspace scan time out |
| Env from `FACTORY_ENV_FILE` (default `~/codex-clones/pp-env.sh`), plus `PYTHONPATH=<clone>/apps/api/src`, the main `.venv/bin` on `PATH`, and `CHROME_BIN` | DB tests skip silently without `TEST_DATABASE_URL`; the main venv imports main's `src`; Karma needs the no-sandbox Chrome |
| Relay launched with stdin closed, in its own session | Codex hangs forever reading stdin when backgrounded |
| Brief footer: do the work yourself, no destructive commands, the gates are listed | repo `AGENTS.md` makes Codex hand frontend work to Agy and stop |

## Lanes and relays

Lanes come from `~/.config/delegate-skills/config.json` (the same file `delegate-setup`
writes). The runner maps the lane's implementer to its relay at
`~/.claude/skills/<implementer>-delegate/scripts/relay.mjs` and passes `--lane`, so model and
effort dials still apply. Supported implementers: `codex`, `agy`, `opencode`, `claude`. The
`agy` relay gets `--dangerously-skip-permissions` (standing approval; headless Agy auto-denies
otherwise). Add anything else per job with `--relay-arg`.

## Writing a gate

- Name the narrowest command that proves the brief: the changed spec, not the suite.
- Gates run with `bash -o pipefail -c`, cwd at the clone root, in order, stopping at the first failure.
  Under `pipefail` a `grep -v` that filters out every line exits 1 and fails the gate even when the
  last command passes (the first smoke run tripped on this). Write "nothing else changed" as
  `[ -z "$(git status --porcelain | grep -v '^?? FACTORY_SMOKE.md$')" ]` instead.
- A gate that needs the hosted DB needs `TEST_DATABASE_URL` in the env file (port 5432, session mode).
- Prefer a mutation check for security controls: a gate that breaks the control and expects the test to fail.
- Keep each gate under the per-gate timeout (`--gate-timeout`, default 60 minutes). Each gate runs
  in its own process group; a timeout or a `stop` kills the whole group, Karma and Chrome included.
- Changes are measured against the recorded checkpoint sha, not the `factory/checkpoint` tag, so an
  implementer that moves the tag still shows its diff.

## After a job

The runner never commits or pushes. Read `summary.md`, read the patch, run the gates yourself if
anything looks off, then commit from the clone or apply `changes.patch` onto a branch in the main
checkout. `clean --done` removes finished clones; the patch stays in the job directory.

## Testing the runner itself

Point `FACTORY_HOME`, `FACTORY_SKILLS_DIR` and `FACTORY_LANES` at scratch locations with a fake
`<implementer>-delegate/scripts/relay.mjs` that writes `result.json` and a file in `--cd`. That
exercises clone, checkpoint, gate pass and fail, `no_changes`, `stop` and `clean` without
spending quota.
