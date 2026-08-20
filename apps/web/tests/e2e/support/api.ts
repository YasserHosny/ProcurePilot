/**
 * API helpers so each E2E test can build the state it needs.
 *
 * The team specs originally ran as a chain: one test invited a colleague, the next accepted the
 * invitation, and three more acted on the member those two produced. Any failure early on took
 * four tests down with it, and none of them could be run alone. Worse, the accept step used a
 * hardcoded fake token, so the member it was supposed to create never existed at all.
 *
 * These helpers drive the real API, so a test that needs a member gets a real one — created the
 * way a customer would, through invite and accept — without depending on another test having run.
 */

import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000/api/v1';

export interface Credentials {
  ownerEmail: string;
  ownerPassword: string;
  businessName: string;
}

export function credentials(): Credentials {
  return JSON.parse(
    readFileSync(join(__dirname, '..', '.credentials.json'), 'utf-8'),
  ) as Credentials;
}

async function call<T>(path: string, init: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
  });
  if (!response.ok) {
    throw new Error(`${init.method ?? 'GET'} ${path} → ${response.status}: ${await response.text()}`);
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

export async function signIn(email: string, password: string): Promise<string> {
  const session = await call<{ access_token: string }>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
  return session.access_token;
}

/**
 * Cached for the run. Every helper needs the owner's token, and signing in afresh each time hit
 * the auth rate limit (10/minute) part-way through the suite — the limiter behaving exactly as
 * intended against a caller that was simply wasteful. One sign-in per run is also faster.
 */
let cachedOwnerToken: string | null = null;

export async function signInOwner(): Promise<string> {
  if (cachedOwnerToken) {
    return cachedOwnerToken;
  }
  const { ownerEmail, ownerPassword } = credentials();
  cachedOwnerToken = await signIn(ownerEmail, ownerPassword);
  return cachedOwnerToken;
}

export interface CreatedMember {
  email: string;
  password: string;
  role: string;
}

/**
 * Invite someone and accept on their behalf, yielding a real member of the owner's workspace.
 *
 * The address is unique per call: the server allows only one pending invitation per address per
 * workspace, so reusing a fixed address makes a suite that passes once and 409s ever after.
 */
export async function createMember(role = 'buyer'): Promise<CreatedMember> {
  const ownerToken = await signInOwner();
  const email = `e2e.member.${Date.now()}.${Math.floor(Math.random() * 10000)}@example.test`;
  const password = 'E2eMemberPassword123!';

  const invitation = await call<{ token?: string }>('/invitations', {
    method: 'POST',
    headers: { Authorization: `Bearer ${ownerToken}` },
    body: JSON.stringify({ email, role }),
  });

  if (!invitation.token) {
    throw new Error('POST /invitations did not return a token; cannot accept the invitation');
  }

  await call('/invitations/accept', {
    method: 'POST',
    body: JSON.stringify({ token: invitation.token, password }),
  });

  return { email, password, role };
}

/** Invite without accepting — for tests about pending invitations rather than members. */
export async function createPendingInvitation(
  role = 'buyer',
): Promise<{ email: string; id: string; token: string }> {
  const ownerToken = await signInOwner();
  const email = `e2e.pending.${Date.now()}.${Math.floor(Math.random() * 10000)}@example.test`;
  const invitation = await call<{ id: string; token?: string }>('/invitations', {
    method: 'POST',
    headers: { Authorization: `Bearer ${ownerToken}` },
    body: JSON.stringify({ email, role }),
  });
  if (!invitation.token) {
    throw new Error('POST /invitations did not return a token');
  }
  return { email, id: invitation.id, token: invitation.token };
}


/**
 * Force the owner's persisted locale back to a known value.
 *
 * The locale is stored per member, so a test that switches to Arabic leaves it that way for every
 * later test and every later RUN. That made the RTL specs order-dependent: whichever ran second
 * signed in already in Arabic and failed its "starts in English" assertion. Each test normalises
 * the state it depends on instead of assuming it.
 */
export async function setOwnerLocale(locale: 'en' | 'ar'): Promise<void> {
  const token = await signInOwner();
  await call('/me', {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ preferred_locale: locale }),
  });
}


/**
 * Mint a platform invitation addressed to a specific email, for tests that drive sign-up through
 * the UI. Sign-up is invitation-gated and refuses an address mismatch, so the invitation must be
 * issued to the account that will redeem it.
 */
export function mintPlatformInvitation(forEmail: string): {
  invitation_token: string;
  region: string;
  currency: string;
  tax_model: string;
} {
  const raw = execFileSync(
    'uv',
    ['run', '--project', 'apps/api', 'python', 'apps/api/scripts/seed.py', '--json'],
    {
      // support/ -> e2e -> tests -> web -> apps -> repo root. Five levels, not four: this helper
      // lives one directory deeper than global-setup.ts, which is where the pattern came from.
      cwd: join(__dirname, '..', '..', '..', '..', '..'),
      env: {
        ...process.env,
        DATABASE_URL:
          process.env['E2E_DATABASE_URL'] ??
          'postgresql://postgres:postgres@localhost:54322/postgres',
        SEED_INVITATION_EMAIL: forEmail,
        // uv's default cache lives under $HOME and is not always writable where CI or a sandbox
        // runs this. Point it somewhere we know we can write.
        UV_CACHE_DIR: process.env['UV_CACHE_DIR'] ?? '/tmp/uv-cache-e2e',
      },
      encoding: 'utf-8',
    },
  );
  return JSON.parse(raw.trim().split('\n').pop() ?? '{}');
}
