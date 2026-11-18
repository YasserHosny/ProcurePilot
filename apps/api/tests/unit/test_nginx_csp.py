"""PPS-224: verify Content-Security-Policy configuration in nginx.conf."""

from __future__ import annotations

from pathlib import Path
import re


def _find_repo_root() -> Path:
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / "infra" / "nginx" / "nginx.conf").exists():
            return p
        p = p.parent
    raise FileNotFoundError("Could not find repository root containing infra/nginx/nginx.conf")


def _parse_directives(csp_policy: str) -> dict[str, list[str]]:
    directives: dict[str, list[str]] = {}
    for entry in csp_policy.strip().strip(";").split(";"):
        tokens = entry.strip().split()
        if tokens:
            directives[tokens[0]] = tokens[1:]
    return directives


def test_nginx_csp_configuration() -> None:
    repo_root = _find_repo_root()
    nginx_conf = (repo_root / "infra" / "nginx" / "nginx.conf").read_text(encoding="utf-8")

    csp_values = re.findall(r'add_header\s+Content-Security-Policy\s+"([^"]+)"', nginx_conf)

    assert len(csp_values) == 3, f"Expected exactly 3 Content-Security-Policy headers, found {len(csp_values)}"
    assert csp_values[0] == csp_values[1] == csp_values[2], "All 3 CSP headers must be identical"

    for csp_policy in csp_values:
        directives = _parse_directives(csp_policy)

        # img-src contains blob:
        assert "img-src" in directives, "img-src directive missing from CSP"
        assert "blob:" in directives["img-src"], "img-src must contain blob:"

        # media-src exists and contains 'self', blob: and https://*.supabase.co
        assert "media-src" in directives, "media-src directive missing from CSP"
        media_src_tokens = directives["media-src"]
        assert "'self'" in media_src_tokens, "media-src must contain 'self'"
        assert "blob:" in media_src_tokens, "media-src must contain blob:"
        assert "https://*.supabase.co" in media_src_tokens, "media-src must contain https://*.supabase.co"

        # script-src is exactly 'self'
        assert "script-src" in directives, "script-src directive missing from CSP"
        assert directives["script-src"] == ["'self'"], "script-src must be exactly 'self'"

        # blob: appears in neither default-src nor script-src
        assert "default-src" in directives, "default-src directive missing from CSP"
        assert "blob:" not in directives["default-src"], "blob: must not appear in default-src"
        assert "blob:" not in directives["script-src"], "blob: must not appear in script-src"
