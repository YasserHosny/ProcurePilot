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

const REPO_ROOT = join(__dirname, '..', '..', '..', '..', '..');

/**
 * Creates a brand-new business + owner, isolated from the shared global-setup workspace every
 * other spec file signs in as.
 *
 * Specs that mutate real membership rows (role changes, removals) must not share the global
 * owner: a run that exercises those mutations against the one workspace every other file also
 * signs in as risks leaving that shared owner in a state later files cannot recover from. One
 * extra sign-up per FILE (not per test) keeps this well within the auth rate limit.
 */
export async function createIsolatedWorkspace(): Promise<Credentials> {
  const stamp = `${Date.now()}.${Math.floor(Math.random() * 10000)}`;
  const creds: Credentials = {
    ownerEmail: `e2e.isolated.owner.${stamp}@example.test`,
    ownerPassword: 'E2eIsolatedPassword123!',
    businessName: `E2E Isolated Co ${stamp}`,
  };

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
        SEED_INVITATION_EMAIL: creds.ownerEmail,
      },
      encoding: 'utf-8',
    },
  );
  const invitation = JSON.parse(raw.trim().split('\n').pop() ?? '{}') as {
    invitation_token: string;
    region: string;
    currency: string;
    tax_model: string;
  };

  await call('/auth/signup', {
    method: 'POST',
    body: JSON.stringify({
      invitation_token: invitation.invitation_token,
      email: creds.ownerEmail,
      password: creds.ownerPassword,
      business_name: creds.businessName,
      region: invitation.region,
      currency: invitation.currency,
      tax_model: invitation.tax_model,
      default_locale: 'en',
    }),
  });

  return creds;
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

/**
 * Authenticated API call AS AN ARBITRARY MEMBER — the caller supplies whose token to use.
 *
 * Everything else here either acts as the global owner or creates state; this is for proving
 * what a SPECIFIC member's own session can and cannot see at the enforcement point itself
 * (branch-scoped visibility, T038), where signing in through the UI first would prove nothing
 * extra — the token IS the session.
 */
export async function apiAsUser<T>(
  token: string,
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  path: string,
  body?: unknown,
): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`${method} ${path} → ${response.status}: ${await response.text()}`);
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
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
export async function createMember(role = 'buyer', ownerTokenOverride?: string): Promise<CreatedMember> {
  const ownerToken = ownerTokenOverride ?? (await signInOwner());
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
  ownerTokenOverride?: string,
): Promise<{ email: string; id: string; token: string }> {
  const ownerToken = ownerTokenOverride ?? (await signInOwner());
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

/**
 * Value-proof helpers (T006).
 */
export async function createTestProduct(
  token: string,
  data?: Partial<{
    tenant_name: string;
    base_unit: string;
    pack_count: number;
    unit_size: string;
    brand?: string;
  }>,
): Promise<{ id: string; tenant_name: string }> {
  const uniqueName = data?.tenant_name ?? `Product ${Date.now()}_${Math.floor(Math.random() * 1000)}`;
  return call<{ id: string; tenant_name: string }>('/products', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({
      tenant_name: uniqueName,
      base_unit: data?.base_unit ?? 'each',
      pack: {
        pack_count: data?.pack_count ?? 1,
        unit_size: data?.unit_size ?? '1',
      },
      brand: data?.brand ?? null,
    }),
  });
}

export async function createTestSupplier(
  token: string,
  name?: string,
): Promise<{ id: string; name: string }> {
  const uniqueName = name ?? `Supplier ${Date.now()}_${Math.floor(Math.random() * 1000)}`;
  // No status field: SupplierCreate is a strict model and rejects it, and the supplier table
  // defaults to 'active' anyway.
  return call<{ id: string; name: string }>('/suppliers', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({
      name: uniqueName,
    }),
  });
}

export async function recordPurchaseOutcome(
  token: string,
  data: {
    workspace_product_id: string;
    supplier_id?: string | null;
    quotation_line_id?: string | null;
    match_decision_id?: string | null;
    landed_cost_id?: string | null;
    quantity: string;
    base_unit: string;
    unit_price: { amount: string; currency: string };
    total_paid: { amount: string; currency: string };
    delivery_result: string;
    ordered_at?: string | null;
    delivered_at?: string | null;
    notes?: string | null;
  },
): Promise<{
  purchase_record: { id: string; workspace_product_id: string; quantity: string };
  saving_record: {
    id: string;
    status: string;
    baseline_policy: string;
    actual_value: { amount: string; currency: string };
    delta: { amount: string; currency: string } | null;
  };
}> {
  return call('/purchases', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(data),
  });
}

export async function verifySaving(
  token: string,
  savingId: string,
): Promise<{ id: string; status: string; verified_at: string; verified_by: string }> {
  return call(`/savings/${encodeURIComponent(savingId)}/verify`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function createExportJob(
  token: string,
  data: {
    kind: 'savings_ledger';
    format: 'xlsx' | 'pdf';
    filters: {
      period_start: string;
      period_end: string;
      supplier_id?: string | null;
      branch_id?: string | null;
    };
  },
): Promise<{
  id: string;
  kind: string;
  format: string;
  status: string;
  row_count?: number | null;
  download_url?: string | null;
}> {
  return call('/exports', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(data),
  });
}

export async function fetchBillingAccount(token: string): Promise<{
  id: string;
  plan: {
    code: string;
    name: string;
    limits: { active_catalogue_products: number };
  };
  status: string;
}> {
  return call('/billing/account', {
    method: 'GET',
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function fetchLimitCheck(token: string): Promise<{
  resource: string;
  plan_code: string;
  limit: number | null;
  used: number;
  allowed: boolean;
  remaining: number | null;
}> {
  return call('/billing/limits/active-catalogue-products', {
    method: 'GET',
    headers: { Authorization: `Bearer ${token}` },
  });
}

/**
 * Canonical-path helpers (T075): read back the state a confirmed quotation produced, so a spec
 * can link a purchase to the exact quotation line / match decision / landed cost the pipeline
 * created — the same ids the Smart Compare "Record Purchase" button passes along.
 */
export interface QuotationMatchLineState {
  line: { id: string; line_number: number; original_text: string };
  task: { id: string; status: string } | null;
  decision: {
    id: string;
    outcome: string;
    matched_product: { id: string; tenant_name: string };
  } | null;
  landed_cost: { id: string } | null;
}

export async function fetchQuotationMatches(
  token: string,
  quotationId: string,
): Promise<{ quotation_id: string; lines: QuotationMatchLineState[] }> {
  return call(`/quotations/${encodeURIComponent(quotationId)}/matches`, {
    method: 'GET',
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function findProductByName(
  token: string,
  tenantName: string,
): Promise<{ id: string; tenant_name: string; base_unit: string }> {
  const res = await call<{
    items: Array<{ id: string; tenant_name: string; base_unit: string }>;
  }>('/products?limit=100&status=active', {
    method: 'GET',
    headers: { Authorization: `Bearer ${token}` },
  });
  const found = res.items.find((p) => p.tenant_name === tenantName);
  if (!found) {
    throw new Error(`No active product named "${tenantName}" exists in the workspace`);
  }
  return found;
}

