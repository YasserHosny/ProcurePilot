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

export async function signInOwner(): Promise<string> {
  const { ownerEmail, ownerPassword } = credentials();
  return signIn(ownerEmail, ownerPassword);
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
