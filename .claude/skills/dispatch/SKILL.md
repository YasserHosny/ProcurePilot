---
name: dispatch
description: Delegate a coding task to a fleet lane through the factory dispatch runner (throwaway clone, checkpoint, relay, mandatory gate, detached supervisor). Use for any delegate / dispatch / hand-to-Codex-Agy-OpenCode ask in this repo, in place of calling a *-delegate relay directly; also for a wave of parallel jobs, "check the jobs" or a job id.
---

# dispatch

`scripts/factory/dispatch.py` runs a delegation as a **job**: a clone from origin's tip, a checkpoint,
the brief through the lane's relay, then **gates** whose recorded output decides the result. The
supervisor is detached, so the job outlives this turn. Reference: `scripts/factory/README.md`
(preflight table, job layout, gate pitfalls). `dispatch.py --help` is the flag list.

`$ARGUMENTS` is one of: a task (with or without a lane name), several tasks to run as a wave,
`status`, or a job id.

## Dispatch a task

1. **Gate first.** Write the narrowest command that exits 0 only when the task is done: the
   changed spec, a grep for the new string, a migration applied to a throwaway DB. More than one
   `--gate` runs in order. A task with no provable gate is not ready: say which observable is
   missing and stop. Gates run under `bash -o pipefail`; a `grep -v` that filters everything exits 1.
2. **Lane.** From `~/.config/delegate-skills/config.json`. The runner drives lanes whose
   implementer is `codex`, `agy`, `opencode` or `claude`, and refuses any other.
   - Backend → `feature` when it is one page or one module and clear of money, currency and
     `audit_event`. Money, currency or audit-log work, and multi-module work → `complex`.
   - Tests → `tests`; web → `ui` with `--web`; mechanical or docs → `big-pickle`; overflow →
     `fallback`.
   - `feature`, `tests` and `simple` are the **Haiku lanes**. Haiku gets a 40-turn budget, which
     covers about one page: on 2026-11-23 Haiku jobs given 3–4-page backend+web groups stopped
     at turn 41 with nothing usable. Size Haiku work to one page, or send the group to `complex`.
3. **Brief** to `~/factory/briefs/<name>.md`: the goal, the files to touch, the rules that bind
   (tenancy, i18n, money, ADRs by number), what done looks like. The runner appends the gate footer
   and the "do it yourself, nothing destructive" rules, so leave those out. Tenancy work stays in
   house: RLS, tenancy migrations, the JWT path are never dispatched.
   For Haiku, the runner appends the lane boundary after the gate footer.
4. **Run**
   ```bash
   scripts/factory/dispatch.py new --lane <lane> --brief ~/factory/briefs/<name>.md --name <name> [--web] --gate '<cmd>'
   ```
   The runner adds the turn and budget caps on Haiku lanes. Use `--relay-arg=` for per-job
   overrides.
   Relay the job id and clone path. Preflight failure (disk, memory, stale node_modules) is the
   whole answer; fix the cause, then re-run. Before a batch of Codex jobs, read the headroom with
   `dispatch.py usage`. A Codex job the quota gate refuses lands on the fallback lane with the
   reason printed; report the reroute alongside the job id.
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
   - `no_changes` or `implementer_failed`: read `relay.log`; quota, turn-cap and sandbox refusals
     look like this. Switch lane and re-run. When the clone holds partial work worth keeping,
     commit it to a `wip/<job>` branch, push, and dispatch the next lane with `--base wip/<job>`
     and a brief that opens "continue this work, don't restart".
7. **Report** in the gate's words: which gates ran, which passed, the clone path. Completion means
   the summary says `passed`, nothing earlier.

## Dispatch a wave

The runner has no wave command: a wave is one `new` per part, and the jobs run side by side
once started. Each part follows steps 1–4 above; these rules cover running them together.

1. **Name** every part `<wave>-<part>` (e.g. `pps228-w2-sourcing`) so `status` groups them.
2. **Headroom.** Check disk, memory and Codex quota before the wave.
   - `df -h ~` shows at least 8 GB plus about 1.5 GB per part. The runner reserves
     `FACTORY_CLONE_GB` (default 1.5 GB) per in-flight clone.
   - `free -g` shows at least 3 GB available plus room for every web gate (Karma + Chrome).
   - `dispatch.py usage` for any Codex part: two Codex jobs run at once, each costs about 25
     points of the 5-hour window, and a third is rerouted to `ui`. Plan Codex parts within that.
3. **Start the parts one at a time**, one `new` call after the previous one has printed its job
   id. `new` returns once its clone exists, so each preflight sees the clones before it. On
   2026-11-23 three `new` calls started in the same second all read 8.0 GB free and were refused.
4. **Wait** on one wakeup for the whole wave; `status` lists every part.
5. **Read** each part as in step 6 above. A failed part is re-dispatched on its own; the others
   carry on.
6. **Report** the wave as a table: part, lane (and any reroute), verdict, clone path.

## Check jobs

`status` lists every job; `status <job>` prints its summary. `clean --done` removes finished
clones and keeps each job's patch. Run it when the disk floor trips.
