"""FR-014 session-revocation proof belongs with a real Supabase Auth service.

The ProcurePilot API verifies access tokens statelessly: it checks signature and required JWT
claims, but it does not own refresh-token exchange and has no local session/revocation table.
Mobile refreshes are performed against Supabase Auth's GoTrue endpoint directly
(`POST /auth/v1/token?grant_type=refresh_token`), with biometric unlock acting only as a local
client-side gate before the stored refresh token is used.

Therefore the guarantee from research.md R3 -- a revoked refresh token fails to refresh even
after a valid biometric match -- cannot be proven by apps/api's current bare-Postgres integration
suite. That suite intentionally does not run GoTrue. A mocked apps/api test would only prove that
the mock was configured to reject the token, not that Supabase Auth revocation works.

Move the runnable proof to the E2E/Supabase-CLI path, or add a dedicated GoTrue service to this
integration harness before replacing this skip with a live test.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "FR-014 refresh-token revocation is enforced by Supabase Auth/GoTrue, not by apps/api; "
        "the backend integration harness starts bare Postgres only"
    )
)


def test_revoked_refresh_token_forces_mobile_reauthentication_after_biometric_unlock() -> None:
    """Placeholder for the real GoTrue/E2E proof of FR-014."""
