---
name: dispatch
description: Delegate a coding task to a fleet lane through the factory dispatch runner (throwaway clone, checkpoint, relay, mandatory gate, detached supervisor). Use for any delegate / dispatch / hand-to-Codex-Agy-OpenCode ask in this repo, in place of calling a *-delegate relay directly; also for "check the jobs" or a job id.
---

# dispatch

`scripts/factory/dispatch.py` runs a delegation as a **job**: a clone from origin's tip, a checkpoint,
the brief through the lane's relay, then **gates** whose recorded output decides the result. The
supervisor is detached, so the job outlives this turn. Reference: `scripts/factory/README.md`
(preflight table, job layout, gate pitfalls). `dispatch.py --help` is the flag list.

`$ARGUMENTS` is one of: a task (with or without a lane name), `status`, or a job id.

## Dispatch a task

1. **Gate first.** Write the narrowest command that exits 0 only when the task is done: the
   changed spec, a grep for the new string, a migration applied to a throwaway DB. More than one
   `--gate` runs in order. A task with no provable gate is not ready: say which observable is
   missing and stop. Gates run under `bash -o pipefail`; a `grep -v` that filters everything exits 1.
2. **Lane.** From `~/.config/delegate-skills/config.json`: backend → `feature` (`complex` for
   multi-module work), tests and web → `tests` or `ui` with `--web`, mechanical or docs →
   `big-pickle`, overflow → `fallback`. `mid` (Cursor) has no relay; the runner refuses it.
3. **Brief** to `~/factory/briefs/<name>.md`: the goal, the files to touch, the rules that bind
   (tenancy, i18n, money, ADRs by number), what done looks like. The runner appends the gate footer
   and the "do it yourself, nothing destructive" rules, so leave those out. Tenancy work stays in
   house: RLS, tenancy migrations, the JWT path are never dispatched.
4. **Run**
   ```bash
   scripts/factory/dispatch.py new --lane <lane> --brief ~/factory/briefs/<name>.md --name <name> [--web] --gate '<cmd>'
   ```
   Relay the job id and clone path. Preflight failure (disk, memory, stale node_modules) is the
   whole answer; fix the cause, then re-run.
5. **Wait** with a scheduled wakeup or a background `status` watch, never a sleep loop. A job
   marked `(stale)` or `(supervisor dead)` needs a look at `logs <job>`, not a restart.
6. **Read the result** from `status <job>` (summary.md). The verdict is the gate table. The
   implementer's final message is marked untrusted; quote it only beside the gate that contradicts
   or confirms it.
   - `passed`: review `changes.patch` for scope creep and constitution breaches, commit from the
     clone on its `factory/<job>` branch, PR as usual.
   - `gate_failed`: read `gate-N.log`. A wrong gate command → `gate <job> --gate '<fixed cmd>'`,
     which replaces the saved gates and re-runs in the foreground. A failure from outside the
     command (env file, clone state) → plain `gate <job>`. Wrong work → a new job whose brief
     opens with the failing output.
   - `no_changes` or `implementer_failed`: read `relay.log`; quota and sandbox refusals look like
     this. Switch lane and re-run.
7. **Report** in the gate's words: which gates ran, which passed, the clone path. Completion means
   the summary says `passed`, nothing earlier.

## Check jobs

`status` lists every job; `status <job>` prints its summary. `clean --done` removes finished
clones and keeps each job's patch. Run it when the disk floor trips.
