import { execFileSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { join } from 'node:path';

/**
 * Creates the workspace and owner the E2E specs sign in as.
 *
 * The specs were originally written against a hardcoded `owner@example.com` that nothing in the
 * project ever created — every one of them failed in beforeEach, at sign-in. Rather than seed a
 * user straight into the database, this drives the real sign-up endpoint: the fixture is built by
 * the same path a customer takes, so a broken sign-up fails the suite loudly instead of being
 * bypassed by a fixture that knows too much.
 *
 * Sign-up is invitation-gated, so we mint a fresh platform invitation first.
 */

const REPO_ROOT = join(__dirname, '..', '..', '..', '..');
const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000/api/v1';

export interface E2ECredentials {
  ownerEmail: string;
  ownerPassword: string;
  businessName: string;
}

function mintInvitation(
  forEmail: string,
): { invitation_token: string; region: string; currency: string; tax_model: string } {
  const raw = execFileSync(
    'uv',
    ['run', '--project', 'apps/api', 'python', 'apps/api/scripts/seed.py', '--json'],
    {
      cwd: REPO_ROOT,
      env: {
        ...process.env,
        DATABASE_URL:
          process.env['E2E_DATABASE_URL'] ??
          'postgresql://postgres:postgres@localhost:54322/postgres',
        // The invitation must be addressed to the account that will redeem it: sign-up refuses
        // an email mismatch (403 invitation.refused), which is the behaviour we want — holding a
        // token is not authority to register as anyone.
        SEED_INVITATION_EMAIL: forEmail,
      },
      encoding: 'utf-8',
    },
  );
  return JSON.parse(raw.trim().split('\n').pop() ?? '{}');
}

async function globalSetup(): Promise<void> {
  const stamp = Date.now();
  const credentials: E2ECredentials = {
    ownerEmail: `e2e.owner.${stamp}@example.test`,
    ownerPassword: 'E2ePassword123!',
    businessName: `E2E Test Co ${stamp}`,
  };

  const invitation = mintInvitation(credentials.ownerEmail);

  const response = await fetch(`${API}/auth/signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      invitation_token: invitation.invitation_token,
      email: credentials.ownerEmail,
      password: credentials.ownerPassword,
      business_name: credentials.businessName,
      region: invitation.region,
      currency: invitation.currency,
      tax_model: invitation.tax_model,
      default_locale: 'en',
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(
      `E2E setup could not create a workspace (${response.status}): ${body}\n` +
        'The stack must be running with migrations applied — see quickstart.md.',
    );
  }

  writeFileSync(join(__dirname, '.credentials.json'), JSON.stringify(credentials, null, 2));
}

export default globalSetup;
