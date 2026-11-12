#!/usr/bin/env python3
"""Factory dispatch runner: preflight, clone, checkpoint, dispatch, gate.

One job = one throwaway clone + one brief + one lane + one or more gate commands.
The supervisor runs detached from the caller, so a job outlives the chat turn and
the desktop app that started it. State is a JSON file per job; nothing lives in
memory between commands.

    dispatch.py new --lane feature --brief brief.md --gate "pytest apps/api/tests/unit/test_x.py"
    dispatch.py status                 # every job, newest first
    dispatch.py status <job>           # one job, with gate results
    dispatch.py logs <job> [--follow]
    dispatch.py gate <job>             # re-run the gates in the foreground
    dispatch.py diff <job>             # changes against the checkpoint
    dispatch.py stop <job>
    dispatch.py clean <job>            # remove the clone, keep the job record

Job status values (job.json "status"):
    created, preflight_failed, cloned, running, gating,
    passed, gate_failed, implementer_failed, no_changes, timeout, stopped

Environment (all optional):
    FACTORY_HOME             default ~/factory          jobs/ and clones/ live here
    FACTORY_SOURCE_REPO      default: the repo this script lives in
    FACTORY_ENV_FILE         default ~/codex-clones/pp-env.sh   `export K=V` lines for the implementer and gates
    FACTORY_NODE_MODULES_SRC a directory whose apps/web/node_modules may be hardlinked into web jobs
    FACTORY_CHROME_BIN       default ~/codex-clones/bin/chrome-nosandbox
    FACTORY_MIN_DISK_GB      default 8
    FACTORY_MIN_MEM_GB       default 3
    FACTORY_LANES            default ~/.config/delegate-skills/config.json
    FACTORY_SKILLS_DIR       default ~/.claude/skills   (where <implementer>-delegate/scripts/relay.mjs lives)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_SOURCE_REPO = HERE.parent.parent
HOME = Path.home()

FACTORY_HOME = Path(os.environ.get("FACTORY_HOME", HOME / "factory")).expanduser()
JOBS_DIR = FACTORY_HOME / "jobs"
CLONES_DIR = FACTORY_HOME / "clones"
SOURCE_REPO = Path(
    os.environ.get("FACTORY_SOURCE_REPO", DEFAULT_SOURCE_REPO)
).expanduser()
ENV_FILE = Path(
    os.environ.get("FACTORY_ENV_FILE", HOME / "codex-clones" / "pp-env.sh")
).expanduser()
CHROME_BIN = Path(
    os.environ.get(
        "FACTORY_CHROME_BIN", HOME / "codex-clones" / "bin" / "chrome-nosandbox"
    )
).expanduser()
LANES_FILE = Path(
    os.environ.get(
        "FACTORY_LANES", HOME / ".config" / "delegate-skills" / "config.json"
    )
).expanduser()
SKILLS_DIR = Path(
    os.environ.get("FACTORY_SKILLS_DIR", HOME / ".claude" / "skills")
).expanduser()
MIN_DISK_GB = float(os.environ.get("FACTORY_MIN_DISK_GB", "8"))
MIN_MEM_GB = float(os.environ.get("FACTORY_MIN_MEM_GB", "3"))

LFS_EXCLUDE = "docs/gtm/video"  # demo-video media: pointers are enough in a clone
HEARTBEAT_SECONDS = 15
POLL_SECONDS = 1
STALE_AFTER_SECONDS = 180
TERMINAL = {
    "preflight_failed",
    "passed",
    "gate_failed",
    "implementer_failed",
    "no_changes",
    "timeout",
    "stopped",
}

# Implementers whose relay needs a flag beyond --brief/--cd/--lane/--out-dir.
# agy: standing approval to skip permissions (headless auto-denies otherwise).
RELAY_EXTRA_ARGS = {
    "agy": ["--dangerously-skip-permissions"],
    "codex": [],
    "opencode": [],
    "claude": [],
}

BRIEF_FOOTER = """

---
## Factory gate (appended by the dispatch runner)

You are working in a throwaway clone at `{clone}` on branch `{branch}`.
Do all the work yourself in this clone; do not hand any part of it to another agent.
Do not run `pnpm install --force`, `git reset --hard`, or anything that discards work.

When you have finished, the runner will execute these gate commands in the clone,
outside your sandbox, and record the real output. Your report does not need to claim
they pass; it needs to say what you changed and what you could not run.

{gates}
"""


# ---------------------------------------------------------------- utilities


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def age(iso: str | None) -> str:
    if not iso:
        return "-"
    secs = int(time.time() - datetime.fromisoformat(iso).timestamp())
    if secs < 90:
        return f"{secs}s"
    if secs < 5400:
        return f"{secs // 60}m"
    if secs < 172800:
        return f"{secs // 3600}h"
    return f"{secs // 86400}d"


def die(msg: str, code: int = 2) -> None:
    print(f"dispatch: {msg}", file=sys.stderr)
    sys.exit(code)


def run(
    cmd: list[str],
    cwd: Path | None = None,
    check: bool = True,
    env: dict | None = None,
    capture: bool = True,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=check,
        env=env,
        text=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )


def git(clone: Path, *args: str, check: bool = True) -> str:
    return run(["git", "-C", str(clone), *args], check=check).stdout.strip()


class Job:
    def __init__(self, job_id: str):
        self.id = job_id
        self.dir = JOBS_DIR / job_id
        self.file = self.dir / "job.json"
        self.data: dict = {}

    @classmethod
    def load(cls, job_id: str) -> Job:
        job = cls(job_id)
        if not job.file.exists():
            die(f"no such job: {job_id} (looked in {job.file})")
        job.data = json.loads(job.file.read_text())
        return job

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, self.file)

    def event(self, status: str | None, note: str = "") -> None:
        if status:
            self.data["status"] = status
        self.data.setdefault("events", []).append(
            {"at": now(), "status": status, "note": note}
        )
        self.data["updated_at"] = now()
        self.save()

    @property
    def clone(self) -> Path:
        return Path(self.data["clone"])

    @property
    def log(self) -> Path:
        return self.dir / "supervisor.log"


def list_jobs() -> list[Job]:
    if not JOBS_DIR.exists():
        return []
    jobs = []
    for d in JOBS_DIR.iterdir():
        if (d / "job.json").exists():
            jobs.append(Job.load(d.name))
    jobs.sort(key=lambda j: j.data.get("created_at", ""), reverse=True)
    return jobs


# ---------------------------------------------------------------- preflight


def check_resources() -> list[str]:
    problems = []
    FACTORY_HOME.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(FACTORY_HOME)
    free_gb = usage.free / 1e9
    if free_gb < MIN_DISK_GB:
        problems.append(
            f"only {free_gb:.1f} GB free on {FACTORY_HOME} (floor {MIN_DISK_GB:g} GB): "
            f"clean old clones first (`dispatch.py clean --done`)"
        )
    try:
        meminfo = Path("/proc/meminfo").read_text()
        avail_kb = int(re.search(r"MemAvailable:\s+(\d+)", meminfo).group(1))
        if avail_kb / 1e6 < MIN_MEM_GB:
            problems.append(
                f"only {avail_kb / 1e6:.1f} GB memory available (floor {MIN_MEM_GB:g} GB)"
            )
    except (OSError, AttributeError):
        pass
    return problems


def load_env_file(path: Path) -> dict[str, str]:
    """Read `export K=V` / `K=V` lines. Values are never printed by this tool."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k.strip()] = v
    return out


def lanes() -> dict:
    if not LANES_FILE.exists():
        die(f"lane config not found: {LANES_FILE}")
    return json.loads(LANES_FILE.read_text()).get("lanes", {})


def resolve_lane(lane: str) -> dict:
    table = lanes()
    if lane not in table:
        die(f"unknown lane '{lane}'. Known: {', '.join(sorted(table))}")
    spec = dict(table[lane])
    impl = spec.get("implementer")
    if impl not in RELAY_EXTRA_ARGS:
        die(
            f"lane '{lane}' uses implementer '{impl}', which has no relay this runner knows how to drive "
            f"(supported: {', '.join(RELAY_EXTRA_ARGS)})"
        )
    relay = SKILLS_DIR / f"{impl}-delegate" / "scripts" / "relay.mjs"
    if not relay.exists():
        die(f"relay for '{impl}' not found at {relay}")
    spec["relay"] = str(relay)
    return spec


def angular_version(root: Path) -> str | None:
    pkg = root / "apps" / "web" / "node_modules" / "@angular" / "core" / "package.json"
    try:
        return json.loads(pkg.read_text())["version"]
    except (OSError, KeyError, ValueError):
        return None


def wanted_angular_version(clone: Path) -> str | None:
    try:
        deps = json.loads((clone / "apps" / "web" / "package.json").read_text())
        return (
            deps.get("dependencies", {}).get("@angular/core", "").lstrip("^~") or None
        )
    except (OSError, ValueError):
        return None


def find_node_modules_source(clone: Path) -> Path | None:
    """A node_modules whose @angular/core matches the clone's package.json. Never the main checkout
    blindly: it has been found stale (Angular 19 under an Angular 22 lockfile)."""
    want = wanted_angular_version(clone)
    candidates: list[Path] = []
    if os.environ.get("FACTORY_NODE_MODULES_SRC"):
        candidates.append(Path(os.environ["FACTORY_NODE_MODULES_SRC"]).expanduser())
    for root in (CLONES_DIR, HOME / "codex-clones", HOME / "agy-clones"):
        if root.exists():
            candidates.extend(
                sorted(
                    (p for p in root.iterdir() if p.is_dir()),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
            )
    candidates.append(SOURCE_REPO)
    for c in candidates:
        v = angular_version(c)
        if v and (want is None or v == want):
            return c
    return None


def prepare_web(clone: Path, log: list[str]) -> None:
    src = find_node_modules_source(clone)
    if src is None:
        raise RuntimeError(
            "no node_modules with a matching @angular/core version found; set FACTORY_NODE_MODULES_SRC "
            "or run `pnpm install --ignore-workspace --frozen-lockfile` in a clone once"
        )
    dest = clone / "apps" / "web" / "node_modules"
    log.append(
        f"hardlinking apps/web/node_modules from {src} (@angular/core {angular_version(src)})"
    )
    run(["cp", "-al", str(src / "apps" / "web" / "node_modules"), str(dest)])
    cache = clone / "apps" / "web" / ".angular"
    if cache.exists():
        shutil.rmtree(cache)
        log.append("cleared apps/web/.angular")


def make_clone(job: Job, base: str, local_base: bool, log: list[str]) -> None:
    clone = job.clone
    if clone.exists():
        raise RuntimeError(f"clone path already exists: {clone}")
    clone.parent.mkdir(parents=True, exist_ok=True)
    if not (SOURCE_REPO / ".git").exists():
        raise RuntimeError(f"source repo has no .git: {SOURCE_REPO}")

    if local_base:
        url = str(SOURCE_REPO)
        log.append(f"cloning from the local checkout ({url}) at {base}")
    else:
        url = git(SOURCE_REPO, "remote", "get-url", "origin")
        log.append(
            f"cloning from origin ({url}) at {base}, objects shared with {SOURCE_REPO}"
        )
    # LFS: keep video media as pointers; git-lfs is installed so the clean filter keeps them pointers.
    run(
        [
            "git",
            "-c",
            f"lfs.fetchexclude={LFS_EXCLUDE}",
            "clone",
            "-q",
            "--reference-if-able",
            str(SOURCE_REPO),
            "--branch",
            base,
            url,
            str(clone),
        ]
    )
    git(clone, "config", "lfs.fetchexclude", LFS_EXCLUDE)

    name = git(SOURCE_REPO, "config", "user.name", check=False)
    email = git(SOURCE_REPO, "config", "user.email", check=False)
    if not name or not email:
        raise RuntimeError(
            "source repo has no git identity; the clone would not be able to commit"
        )
    git(clone, "config", "user.name", name)
    git(clone, "config", "user.email", email)

    branch = f"factory/{job.id}"
    git(clone, "checkout", "-q", "-b", branch)
    sha = git(clone, "rev-parse", "HEAD")
    git(clone, "tag", "-f", "factory/checkpoint", sha)
    job.data.update(
        {"branch": branch, "checkpoint_sha": sha, "base": base, "base_url": url}
    )
    log.append(f"checkpoint {sha[:12]} tagged factory/checkpoint on {branch}")


def job_env(job: Job) -> dict[str, str]:
    env = dict(os.environ)
    env.update(load_env_file(ENV_FILE))
    clone = job.clone
    env["PYTHONPATH"] = str(clone / "apps" / "api" / "src")
    venv_bin = SOURCE_REPO / ".venv" / "bin"
    if venv_bin.exists():
        env["PATH"] = f"{venv_bin}{os.pathsep}{env.get('PATH', '')}"
    if CHROME_BIN.exists():
        env["CHROME_BIN"] = str(CHROME_BIN)
    env["FACTORY_JOB"] = job.id
    env["FACTORY_CLONE"] = str(clone)
    return env


# ---------------------------------------------------------------- commands


def cmd_new(args: argparse.Namespace) -> None:
    brief_path = Path(args.brief).expanduser().resolve()
    if not brief_path.exists():
        die(f"brief not found: {brief_path}")
    if not args.gate:
        die(
            "at least one --gate command is required; the gate is the point of this runner"
        )

    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M")
    slug = (
        re.sub(r"[^a-z0-9]+", "-", (args.name or brief_path.stem).lower()).strip("-")[
            :40
        ]
        or "job"
    )
    job_id = f"{stamp}-{slug}"
    job = Job(job_id)
    if job.dir.exists():
        die(f"job already exists: {job_id}")

    lane = resolve_lane(args.lane)
    job.data = {
        "id": job_id,
        "created_at": now(),
        "lane": args.lane,
        "implementer": lane["implementer"],
        "relay": lane["relay"],
        "clone": str(CLONES_DIR / job_id),
        "brief_source": str(brief_path),
        "gates": args.gate,
        "gate_timeout_seconds": args.gate_timeout * 60,
        "relay_timeout": args.timeout,
        "web": bool(args.web),
        "relay_extra_args": RELAY_EXTRA_ARGS[lane["implementer"]]
        + (args.relay_arg or []),
        "status": "created",
        "events": [],
    }
    job.event("created", f"lane {args.lane} -> {lane['implementer']}")

    log: list[str] = []
    try:
        problems = check_resources()
        if problems:
            raise RuntimeError("; ".join(problems))
        make_clone(job, args.base, args.local_base, log)
        if args.web:
            prepare_web(job.clone, log)
        if not ENV_FILE.exists():
            log.append(
                f"warning: env file {ENV_FILE} not found; gates run with the caller's environment only"
            )
        gates_md = "\n".join(f"{i + 1}. `{g}`" for i, g in enumerate(args.gate))
        brief = brief_path.read_text().rstrip("\n") + BRIEF_FOOTER.format(
            clone=job.clone, branch=job.data["branch"], gates=gates_md
        )
        (job.dir / "brief.md").write_text(brief)
        (job.dir / "preflight.log").write_text("\n".join(log) + "\n")
        job.event("cloned", "preflight ok")
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        detail = (
            exc.stdout
            if isinstance(exc, subprocess.CalledProcessError) and exc.stdout
            else str(exc)
        )
        (job.dir / "preflight.log").write_text("\n".join(log) + f"\nFAILED: {detail}\n")
        job.event("preflight_failed", detail.strip()[:500])
        print("\n".join(log))
        die(f"preflight failed for {job_id}: {detail.strip()[:500]}", 1)

    print("\n".join(log))
    print(
        f"job {job_id}\n  clone  {job.clone}\n  brief  {job.dir / 'brief.md'}\n  gates  {len(args.gate)}"
    )
    if args.no_start:
        print(f"not started; run: dispatch.py start {job_id}")
        return
    start_supervisor(job)


def start_supervisor(job: Job) -> None:
    if job.data["status"] in {"running", "gating"} and pid_alive(
        job.data.get("supervisor_pid")
    ):
        die(
            f"job {job.id} is already {job.data['status']} (pid {job.data['supervisor_pid']})"
        )
    (job.dir / "STOP").unlink(missing_ok=True)
    with open(job.log, "ab") as log:
        proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "_supervise", job.id],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
            cwd=str(job.clone),
        )
    # From here the supervisor owns job.json. It records its own pid first thing;
    # wait for that instead of writing a snapshot that could clobber its state.
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            recorded = json.loads(job.file.read_text()).get("supervisor_pid")
        except (OSError, ValueError):
            recorded = None
        if recorded == proc.pid:
            break
        if proc.poll() is not None:
            die(
                f"supervisor exited early with code {proc.returncode}; see {job.log}", 1
            )
        time.sleep(0.2)
    else:
        print(
            f"warning: supervisor pid {proc.pid} has not recorded itself yet; check `status`",
            file=sys.stderr,
        )
    print(f"supervisor pid {proc.pid}; follow with: dispatch.py logs {job.id} --follow")


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def cmd_start(args: argparse.Namespace) -> None:
    job = Job.load(args.job)
    if not job.clone.exists():
        die(f"clone is gone: {job.clone}; create a new job")
    start_supervisor(job)


def kill_group(pid: int, grace: int = 20) -> None:
    """SIGTERM the process group, then SIGKILL whatever is left after `grace` seconds."""
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.time() + grace
    while time.time() < deadline:
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.5)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def wait_child(job: Job, proc: subprocess.Popen, timeout_seconds: float | None) -> str:
    """Poll a child started with start_new_session until it exits, the STOP sentinel appears,
    or the timeout passes. Heartbeats job.json while waiting. Returns exited | stopped | timeout."""
    deadline = time.time() + timeout_seconds if timeout_seconds else None
    last_beat = 0.0
    while proc.poll() is None:
        time.sleep(POLL_SECONDS)
        if time.time() - last_beat >= HEARTBEAT_SECONDS:
            job.data["heartbeat_at"] = now()
            job.save()
            last_beat = time.time()
        if (job.dir / "STOP").exists():
            kill_group(proc.pid)
            proc.wait()
            return "stopped"
        if deadline and time.time() > deadline:
            kill_group(proc.pid)
            proc.wait()
            return "timeout"
    return "exited"


def supervise(job_id: str) -> None:
    """Runs detached. Everything it learns goes into job.json and the job dir."""
    job = Job.load(job_id)
    job.data["supervisor_pid"] = os.getpid()
    job.event(None, f"supervisor started pid {os.getpid()}")
    env = job_env(job)
    relay_dir = job.dir / "relay"
    relay_dir.mkdir(exist_ok=True)
    cmd = [
        "node",
        job.data["relay"],
        "--brief",
        str(job.dir / "brief.md"),
        "--cd",
        str(job.clone),
        "--lane",
        job.data["lane"],
        "--out-dir",
        str(relay_dir),
    ]
    if job.data.get("relay_timeout"):
        cmd += ["--timeout", job.data["relay_timeout"]]
    cmd += job.data.get("relay_extra_args", [])
    job.data["relay_cmd"] = shlex.join(cmd)
    job.data["started_at"] = now()
    job.event("running", "relay launched")
    print(f"[{now()}] {shlex.join(cmd)}", flush=True)

    with open(job.dir / "relay.log", "ab") as relay_log:
        proc = subprocess.Popen(
            cmd,
            cwd=str(job.clone),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=relay_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    job.data["relay_pid"] = proc.pid
    job.save()
    # The relay enforces its own --timeout, so no second deadline here.
    if wait_child(job, proc, None) == "stopped":
        job.event("stopped", "stop requested while the implementer was running")
        write_summary(job)
        return
    job.data["relay_exit_code"] = proc.returncode

    result_file = relay_dir / "result.json"
    relay_status = "unknown"
    if result_file.exists():
        try:
            relay_status = json.loads(result_file.read_text()).get("status", "unknown")
        except ValueError:
            relay_status = "unreadable"
    job.data["relay_status"] = relay_status
    print(f"[{now()}] relay exit {proc.returncode}, status {relay_status}", flush=True)

    try:
        changed = record_changes(job)
    except RuntimeError as exc:
        job.event(
            "implementer_failed", f"could not diff against the checkpoint: {exc}"[:500]
        )
        write_summary(job)
        return
    if relay_status == "timeout":
        job.event("timeout", "relay watchdog fired")
    elif relay_status != "completed":
        job.event(
            "implementer_failed", f"relay status {relay_status}, exit {proc.returncode}"
        )
    elif not changed:
        job.event(
            "no_changes",
            "implementer completed but the clone is identical to the checkpoint",
        )
    else:
        job.event("gating", f"{changed} files changed")
        run_gates(job, env)
    write_summary(job)


def record_changes(job: Job) -> int:
    """Diff the clone against the recorded checkpoint sha (not the tag, which the implementer
    could move). Raises RuntimeError when git cannot answer, instead of parsing error text."""
    clone = job.clone
    base = job.data["checkpoint_sha"]

    def g(*args: str) -> str:
        res = subprocess.run(
            ["git", "-C", str(clone), *args],
            text=True,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
        )
        if res.returncode != 0:
            raise RuntimeError(f"git {args[0]} failed: {res.stderr.strip()[:300]}")
        return res.stdout

    # Stage everything briefly so untracked files show in the patch, then unstage.
    g("add", "-A")
    try:
        stat = g("diff", "--cached", "--stat", base).strip()
        patch = g("diff", "--cached", "--binary", base)
        files = g("diff", "--cached", "--name-only", base).splitlines()
        commits = int(g("rev-list", "--count", f"{base}..HEAD").strip() or "0")
    finally:
        subprocess.run(
            ["git", "-C", str(clone), "reset", "-q"],
            stdin=subprocess.DEVNULL,
            check=False,
        )
    (job.dir / "changes.patch").write_text(patch)
    (job.dir / "changes.stat").write_text(stat + "\n")
    job.data["changed_files"] = files
    job.data["commits_since_checkpoint"] = commits
    job.save()
    return len(files) + commits


def run_gates(job: Job, env: dict[str, str]) -> str:
    """Run the gates in order in their own process groups. Returns passed | gate_failed | stopped."""
    results = []
    all_ok = True
    for i, gate in enumerate(job.data["gates"], start=1):
        log_path = job.dir / f"gate-{i}.log"
        started = time.time()
        print(f"[{now()}] gate {i}: {gate}", flush=True)
        with open(log_path, "wb") as fh:
            fh.write(f"$ {gate}\n(cwd {job.clone})\n\n".encode())
            fh.flush()
            proc = subprocess.Popen(
                ["bash", "-o", "pipefail", "-c", gate],
                cwd=str(job.clone),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=fh,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            outcome = wait_child(job, proc, job.data["gate_timeout_seconds"])
            if outcome == "exited":
                code = proc.returncode
            elif outcome == "timeout":
                code = -1
                fh.write(b"\n[gate timed out; process group killed]\n")
            else:
                code = -2
                fh.write(b"\n[stopped; process group killed]\n")
        ok = code == 0
        all_ok &= ok
        results.append(
            {
                "n": i,
                "cmd": gate,
                "exit": code,
                "ok": ok,
                "seconds": round(time.time() - started),
                "log": str(log_path),
            }
        )
        job.data["gate_results"] = results
        job.save()
        print(f"[{now()}] gate {i} exit {code} ({outcome})", flush=True)
        if outcome == "stopped":
            job.event("stopped", f"stop requested during gate {i}")
            return "stopped"
        if not ok:
            break  # later gates usually depend on earlier ones
    status = "passed" if all_ok else "gate_failed"
    job.event(
        status, f"{sum(r['ok'] for r in results)}/{len(job.data['gates'])} gates passed"
    )
    return status


def tail(path: Path, lines: int = 40) -> str:
    try:
        return "\n".join(path.read_text(errors="replace").splitlines()[-lines:])
    except OSError:
        return "(no log)"


def write_summary(job: Job) -> None:
    d = job.data
    out = [
        f"# Job {job.id}",
        "",
        f"- status: **{d['status']}**",
        f"- lane: {d['lane']} ({d['implementer']})",
        f"- clone: `{d['clone']}` branch `{d.get('branch')}`",
        f"- checkpoint: `{d.get('checkpoint_sha')}`",
        f"- relay status: {d.get('relay_status')} (exit {d.get('relay_exit_code')})",
        f"- commits since checkpoint: {d.get('commits_since_checkpoint', 0)}",
        f"- changed files: {len(d.get('changed_files', []))}",
        "",
    ]
    if d.get("changed_files"):
        out += [
            "## Changes",
            "",
            "```",
            (job.dir / "changes.stat").read_text().rstrip(),
            "```",
            "",
        ]
    if d.get("gate_results"):
        out += ["## Gates", ""]
        for r in d["gate_results"]:
            mark = "PASS" if r["ok"] else "FAIL"
            out.append(f"- {mark} ({r['seconds']}s, exit {r['exit']}): `{r['cmd']}`")
            if not r["ok"]:
                out += ["", "```", tail(Path(r["log"])), "```", ""]
        out.append("")
    relay_final = job.dir / "relay" / "final.txt"
    if relay_final.exists():
        out += [
            "## Implementer's final message (untrusted; verify against the gates)",
            "",
            "```",
            relay_final.read_text(errors="replace").strip()[-4000:],
            "```",
            "",
        ]
    out += [
        "## Files",
        "",
        f"- brief: `{job.dir / 'brief.md'}`",
        f"- patch: `{job.dir / 'changes.patch'}`",
        f"- relay artifacts: `{job.dir / 'relay'}`",
        f"- supervisor log: `{job.log}`",
    ]
    (job.dir / "summary.md").write_text("\n".join(out) + "\n")


def cmd_status(args: argparse.Namespace) -> None:
    if args.job:
        job = Job.load(args.job)
        if args.json:
            print(json.dumps(job.data, indent=2, sort_keys=True))
            return
        summary = job.dir / "summary.md"
        if summary.exists() and job.data["status"] in TERMINAL:
            print(summary.read_text())
        else:
            d = job.data
            print(
                f"{job.id}: {d['status']} ({effective_status(job)}), lane {d['lane']}, "
                f"heartbeat {age(d.get('heartbeat_at'))} ago, clone {d['clone']}"
            )
            print(tail(job.log, 15))
        return
    jobs = list_jobs()
    if args.json:
        print(json.dumps([j.data for j in jobs], indent=2, sort_keys=True))
        return
    if not jobs:
        print(f"no jobs under {JOBS_DIR}")
        return
    rows = [("JOB", "LANE", "STATUS", "AGE", "HB", "GATES", "FILES")]
    for j in jobs:
        d = j.data
        gates = d.get("gate_results")
        gate_txt = (
            f"{sum(r['ok'] for r in gates)}/{len(d['gates'])}"
            if gates
            else f"-/{len(d.get('gates', []))}"
        )
        rows.append(
            (
                j.id,
                d["lane"],
                effective_status(j),
                age(d.get("created_at")),
                age(d.get("heartbeat_at")),
                gate_txt,
                str(len(d.get("changed_files", []))),
            )
        )
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for r in rows:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip())


def effective_status(job: Job) -> str:
    d = job.data
    st = d["status"]
    if st in {"running", "gating"}:
        if not pid_alive(d.get("supervisor_pid")):
            return f"{st} (supervisor dead)"
        hb = d.get("heartbeat_at")
        if (
            hb
            and time.time() - datetime.fromisoformat(hb).timestamp()
            > STALE_AFTER_SECONDS
        ):
            return f"{st} (stale)"
    return st


def cmd_logs(args: argparse.Namespace) -> None:
    job = Job.load(args.job)
    target = job.dir / "relay.log" if args.relay else job.log
    if not target.exists():
        die(f"no log yet at {target}")
    if args.follow:
        os.execvp("tail", ["tail", "-n", str(args.lines), "-F", str(target)])
    print(tail(target, args.lines))


def cmd_gate(args: argparse.Namespace) -> None:
    job = Job.load(args.job)
    if not job.clone.exists():
        die(f"clone is gone: {job.clone}")
    if job.data["status"] in {"running", "gating"} and pid_alive(
        job.data.get("supervisor_pid")
    ):
        die("job is still running; stop it first or wait")
    try:
        record_changes(job)
    except RuntimeError as exc:
        die(str(exc), 1)
    job.event("gating", "manual gate run")
    ok = run_gates(job, job_env(job)) == "passed"
    write_summary(job)
    print((job.dir / "summary.md").read_text())
    sys.exit(0 if ok else 1)


def cmd_diff(args: argparse.Namespace) -> None:
    job = Job.load(args.job)
    if not job.clone.exists():
        die(
            f"clone is gone: {job.clone}; the last recorded patch is {job.dir / 'changes.patch'}"
        )
    try:
        record_changes(job)
    except RuntimeError as exc:
        die(str(exc), 1)
    if args.patch:
        print((job.dir / "changes.patch").read_text())
    else:
        print((job.dir / "changes.stat").read_text())
        n = job.data.get("commits_since_checkpoint", 0)
        if n:
            print(f"{n} commit(s) since checkpoint:")
            print(git(job.clone, "log", "--oneline", "factory/checkpoint..HEAD"))


def cmd_stop(args: argparse.Namespace) -> None:
    job = Job.load(args.job)
    pid = job.data.get("supervisor_pid")
    if job.data["status"] not in {"running", "gating"} or not pid_alive(pid):
        die(f"job is not running (status {job.data['status']})")
    (job.dir / "STOP").write_text(now() + "\n")
    print(
        f"stop requested; the supervisor (pid {pid}) will kill the implementer or the running gate within a few seconds"
    )
    if args.force:
        for key in ("relay_pid", "supervisor_pid"):
            p = job.data.get(key)
            if pid_alive(p):
                try:
                    os.killpg(p, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        job.event("stopped", "force killed")
        write_summary(job)


def cmd_clean(args: argparse.Namespace) -> None:
    targets = []
    if args.done:
        targets = [
            j
            for j in list_jobs()
            if j.data["status"] in TERMINAL and Path(j.data["clone"]).exists()
        ]
    elif args.job:
        targets = [Job.load(args.job)]
    else:
        die("give a job id or --done")
    for job in targets:
        if job.data["status"] in {"running", "gating"} and pid_alive(
            job.data.get("supervisor_pid")
        ):
            print(f"skip {job.id}: still running")
            continue
        clone = job.clone
        if clone.exists():
            if (
                clone.resolve() == SOURCE_REPO.resolve()
                or CLONES_DIR.resolve() not in clone.resolve().parents
            ):
                die(f"refusing to remove {clone}: not under {CLONES_DIR}")
            if (clone / ".git").exists():
                try:
                    record_changes(job)
                except RuntimeError as exc:
                    print(f"warning: could not save a final patch for {job.id}: {exc}")
            shutil.rmtree(clone)
            job.event(None, "clone removed")
            print(f"removed {clone} (patch kept at {job.dir / 'changes.patch'})")
        else:
            print(f"{job.id}: clone already gone")


def main() -> None:
    p = argparse.ArgumentParser(
        prog="dispatch.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new", help="preflight, clone, checkpoint and start a job")
    n.add_argument("--lane", required=True)
    n.add_argument(
        "--brief",
        required=True,
        help="brief file; the gate footer is appended to a copy",
    )
    n.add_argument(
        "--gate",
        action="append",
        help="command that must exit 0 in the clone; repeatable",
    )
    n.add_argument("--name", help="job slug (default: brief file name)")
    n.add_argument("--base", default="main", help="branch to clone (default main)")
    n.add_argument(
        "--local-base",
        action="store_true",
        help="clone the local checkout instead of origin",
    )
    n.add_argument(
        "--web",
        action="store_true",
        help="hardlink a verified apps/web/node_modules and clear .angular",
    )
    n.add_argument(
        "--timeout", default="90m", help="relay watchdog, h/m/s (default 90m)"
    )
    n.add_argument(
        "--gate-timeout", type=int, default=60, help="minutes per gate (default 60)"
    )
    n.add_argument(
        "--relay-arg",
        action="append",
        help="extra argument passed to the relay; repeatable",
    )
    n.add_argument("--no-start", action="store_true")
    n.set_defaults(fn=cmd_new)

    s = sub.add_parser(
        "start", help="start (or restart) the supervisor for an existing job"
    )
    s.add_argument("job")
    s.set_defaults(fn=cmd_start)

    st = sub.add_parser("status", help="list jobs, or show one")
    st.add_argument("job", nargs="?")
    st.add_argument("--json", action="store_true")
    st.set_defaults(fn=cmd_status)

    lg = sub.add_parser(
        "logs", help="supervisor log (or --relay for the implementer's)"
    )
    lg.add_argument("job")
    lg.add_argument("--follow", "-f", action="store_true")
    lg.add_argument("--relay", action="store_true")
    lg.add_argument("--lines", "-n", type=int, default=60)
    lg.set_defaults(fn=cmd_logs)

    g = sub.add_parser("gate", help="re-run the gates in the foreground")
    g.add_argument("job")
    g.set_defaults(fn=cmd_gate)

    df = sub.add_parser("diff", help="changes against the checkpoint")
    df.add_argument("job")
    df.add_argument("--patch", action="store_true")
    df.set_defaults(fn=cmd_diff)

    sp = sub.add_parser("stop", help="stop a running job")
    sp.add_argument("job")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(fn=cmd_stop)

    c = sub.add_parser(
        "clean", help="remove a job's clone (the job record and patch stay)"
    )
    c.add_argument("job", nargs="?")
    c.add_argument("--done", action="store_true", help="every finished job's clone")
    c.set_defaults(fn=cmd_clean)

    sv = sub.add_parser("_supervise")
    sv.add_argument("job")
    sv.set_defaults(fn=lambda a: supervise(a.job))

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
