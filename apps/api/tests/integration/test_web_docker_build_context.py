"""Guards against the `.dockerignore` regression found live on hosted (2026-09-27).

`apps/web/public/samples/*` are real, git-tracked, user-facing sample files: the
"Download Sample" links on `/quotations/upload` serve them, and the frontend also lets users
re-upload them straight into the extraction pipeline. A `.dockerignore` entry meant to exclude
the *unrelated* top-level QA-fixture directory (`samples/quotations/*.pdf`, real vendor quotes
used for manual walkthroughs, never meant to ship in the web image) used the bare/recursive
patterns `samples` and `**/samples`, which — per Docker's `.dockerignore` matching (the same
gitignore-style semantics: a pattern with no `/` matches at *any* depth) — also matched
`apps/web/public/samples/`, silently dropping it from every web image's build context.

Real-world impact confirmed live on hosted: `GET https://procurepilot.iron-sys.com/
samples/sample-quotation-al-faisal-trading.pdf` returned the Angular SPA's `index.html`
(nginx's `try_files ... /index.html` fallback, because the file was never in the served
image) instead of a PDF. A real user downloaded that mislabeled "sample", re-uploaded it, and
got `extraction_job.status='failed'` with Azure DI's `InvalidContent: The file is corrupted or
format is unsupported` — three times in a row (`quotation` ids `2d9525cb…`, `8f341ac3…`,
`9e59c47c…` on the hosted DB), because the "PDF" was actually HTML.

This test drives the real Docker `.dockerignore` engine (not a reimplementation of its
matching rules, which is exactly where the original bug hid) against a disposable image build,
to prove the fix holds and stays held.
"""

from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]

DOCKER_AVAILABLE = shutil.which("docker") is not None


def _docker_daemon_reachable() -> bool:
    if not DOCKER_AVAILABLE:
        return False
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


pytestmark = pytest.mark.skipif(
    not _docker_daemon_reachable(),
    reason="docker CLI/daemon not available in this environment",
)


CONTEXT_CHECK_DOCKERFILE = """
FROM alpine:3.20
COPY . /ctx
RUN test -f /ctx/apps/web/public/samples/sample-quotation-al-faisal-trading.pdf \
    || (echo "MISSING: apps/web/public/samples was excluded from the build context" && exit 1)
RUN test ! -d /ctx/samples/quotations \
    || (echo "UNEXPECTED: top-level QA-fixture samples/quotations/ leaked into the build \
context" && exit 1)
"""


def test_web_public_samples_survive_dockerignore(tmp_path: Path) -> None:
    """The real user-facing sample assets must reach the Docker build context.

    Without the fix (bare `samples` / `**/samples` patterns in `.dockerignore`), this build
    fails at the first RUN step because `apps/web/public/samples/` never lands in `/ctx`.

    Builds a SANITIZED, minimal context — not `REPO_ROOT` — so this never sends a developer's
    real working tree (a `.env`, `*.pem`, `*.key`, `*.tfvars`, or anything else untracked and
    ignored-by-git-but-not-by-.dockerignore) to the Docker daemon or a configured remote
    `DOCKER_HOST`. `.dockerignore`'s pattern MATCHING only cares about relative paths, not file
    contents, so a context containing just the real `.dockerignore` plus two empty placeholder
    files at the exact paths under test proves the same thing a full-repo build would, without
    the exposure. (Codex review of PR #44.)
    """
    context_dir = tmp_path / "context"
    (context_dir / "apps" / "web" / "public" / "samples").mkdir(parents=True)
    (
        context_dir
        / "apps"
        / "web"
        / "public"
        / "samples"
        / "sample-quotation-al-faisal-trading.pdf"
    ).write_bytes(b"")
    (context_dir / "samples" / "quotations").mkdir(parents=True)
    (context_dir / "samples" / "quotations" / "placeholder.pdf").write_bytes(b"")
    shutil.copy(REPO_ROOT / ".dockerignore", context_dir / ".dockerignore")

    dockerfile_path = tmp_path / "Dockerfile.contextcheck"
    dockerfile_path.write_text(CONTEXT_CHECK_DOCKERFILE)

    tag = f"procurepilot-dockerignore-contextcheck-{uuid.uuid4().hex[:8]}"
    try:
        result = subprocess.run(
            [
                "docker",
                "build",
                "--no-cache",
                "-f",
                str(dockerfile_path),
                "-t",
                tag,
                str(context_dir),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, (
            "Docker build context check failed — apps/web/public/samples is being excluded "
            f"by .dockerignore again.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    finally:
        # The context is sanitized (no real secrets ever enter it), so there is nothing sensitive
        # left in BuildKit's cache to worry about clearing beyond the tagged image itself.
        subprocess.run(["docker", "rmi", "-f", tag], capture_output=True, check=False)


def test_dockerignore_excludes_qa_fixture_samples_specifically() -> None:
    """The fix must stay scoped: only the top-level QA-fixture `samples/` is excluded.

    `apps/web/public/samples/` (nested) must NOT match — regression-proofs the specific
    `/samples` anchored pattern rather than a bare recursive one.
    """
    dockerignore = (REPO_ROOT / ".dockerignore").read_text().splitlines()
    stripped = [line.strip() for line in dockerignore if line.strip() and not line.startswith("#")]

    assert "/samples" in stripped, (
        ".dockerignore should anchor the QA-fixture exclusion to the repo root with `/samples` "
        "— a bare `samples` or `**/samples` pattern also matches apps/web/public/samples/."
    )
    assert "samples" not in stripped, "bare `samples` pattern matches at any depth — see docstring"
    assert "**/samples" not in stripped, (
        "`**/samples` matches at any depth, including apps/web/public/samples/"
    )
