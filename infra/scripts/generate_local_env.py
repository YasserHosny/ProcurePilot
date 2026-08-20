"""Generate a working local .env — JWT secret plus the anon and service_role keys derived from it.

WHY THIS EXISTS
`.env.example` ships placeholder strings, correctly: it is committed, so it must never contain a
credential. But that made the documented setup — copy the example, start the stack — produce a
system where nothing can authenticate. Every service was handed the literal string
`replace-with-local-jwt-secret`, and the API answered 500 with 'Invalid API key'.

The anon and service_role keys are not arbitrary secrets: they are JWTs signed with the project's
JWT secret, carrying a `role` claim. They therefore cannot be written into a template by hand —
they only make sense once a secret exists. So we generate all three together.

The secret is random per developer, so no shared key is baked into the repository and a local
value cannot be mistaken for a production one.

    python infra/scripts/generate_local_env.py          # write .env if absent
    python infra/scripts/generate_local_env.py --force  # regenerate (invalidates existing sessions)
"""

from __future__ import annotations

import argparse
import re
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jose import jwt

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = REPO_ROOT / ".env"
EXAMPLE_PATH = REPO_ROOT / ".env.example"

# Ten years: these are local development keys, and an expiry that lapses mid-project is a
# confusing failure that looks like a code bug.
KEY_LIFETIME = timedelta(days=3650)


def make_key(secret: str, role: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "role": role,
            "iss": "supabase-local",
            "iat": int(now.timestamp()),
            "exp": int((now + KEY_LIFETIME).timestamp()),
        },
        secret,
        algorithm="HS256",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="overwrite an existing .env")
    args = parser.parse_args()

    if ENV_PATH.exists() and not args.force:
        print(f"{ENV_PATH.name} already exists. Use --force to regenerate.", file=sys.stderr)
        print("Regenerating changes the JWT secret and invalidates every existing session.")
        return 1

    if not EXAMPLE_PATH.exists():
        print(".env.example is missing; cannot generate .env from it.", file=sys.stderr)
        return 1

    jwt_secret = secrets.token_urlsafe(48)
    anon_key = make_key(jwt_secret, "anon")
    service_key = make_key(jwt_secret, "service_role")

    replacements = {
        "SUPABASE_JWT_SECRET": jwt_secret,
        "SUPABASE_ANON_KEY": anon_key,
        "SUPABASE_SERVICE_ROLE_KEY": service_key,
    }

    lines: list[str] = []
    for line in EXAMPLE_PATH.read_text().splitlines():
        match = re.match(r"^([A-Z_]+)=", line)
        if match and match.group(1) in replacements:
            lines.append(f"{match.group(1)}={replacements[match.group(1)]}")
        else:
            lines.append(line)

    ENV_PATH.write_text("\n".join(lines) + "\n")
    ENV_PATH.chmod(0o600)

    print(f"Wrote {ENV_PATH.name} with a freshly generated JWT secret and matching keys.")
    print()
    print("These are LOCAL development keys. They are unique to this machine, and .env is")
    print("git-ignored, so they cannot reach the repository or be confused with production.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
