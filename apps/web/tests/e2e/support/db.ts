/**
 * Direct-database helpers for E2E state the product cannot create yet.
 *
 * The dependents-confirmation flow needs a cost centre linked to a branch, but the cost-centre
 * UI and API arrive with User Story 2 — shelling into the local Supabase Postgres is the honest
 * stopgap until then. This is deliberately narrow: the moment US2 ships, this helper should be
 * deleted and the spec switched to whatever it exports.
 */

import { execFileSync } from 'node:child_process';

/**
 * The local Supabase CLI stack names its Postgres container after the project
 * (`supabase_db_ProcurePilot`). The root docker-compose.yml names it differently
 * (`procurepilot-db`), so allow an override rather than assuming either one everywhere.
 */
const DB_CONTAINER = process.env['E2E_DB_CONTAINER'] ?? 'supabase_db_ProcurePilot';

/** Single quotes are the one way user-supplied text could break out of a SQL literal. */
function sqlLiteral(value: string): string {
  return `'${value.replace(/'/g, "''")}'`;
}

export interface CreatedCostCentre {
  id: string;
}

/**
 * Inserts a cost centre linked to the named branch, in the workspace whose active membership
 * carries `ownerEmail`.
 *
 * The ids cannot be passed in as literals the way seed.py-style callers usually would: the branch
 * is created through the real UI, so the test never learns its id. One statement therefore
 * resolves tenant_id from the owner's membership and branch_id from the branch name, and
 * `returning id` turns "nothing matched" into an empty result we can fail on loudly instead of a
 * silently useless fixture. Values are interpolated only through sqlLiteral and passed to docker
 * exec as argv (never a shell string), so there is no shell injection path.
 */
export function createBranchCostCentre(
  ownerEmail: string,
  branchName: string,
): CreatedCostCentre {
  const code = `E2E-CC-${Date.now()}-${Math.floor(Math.random() * 10000)}`;
  const sql = [
    'insert into cost_centre (id, tenant_id, name, code, branch_id)',
    `select gen_random_uuid(), m.tenant_id, ${sqlLiteral('Test Cost Centre')}, ${sqlLiteral(code)}, b.id`,
    'from membership m',
    `join branch b on b.tenant_id = m.tenant_id and b.name = ${sqlLiteral(branchName)}`,
    `where lower(m.email) = lower(${sqlLiteral(ownerEmail)}) and m.status = 'active'`,
    'limit 1',
    'returning id',
  ].join(' ');

  const stdout = execFileSync(
    'docker',
    ['exec', DB_CONTAINER, 'psql', '-U', 'postgres', '-t', '-A', '-c', sql],
    { encoding: 'utf-8' },
  ).trim();

  const id = stdout.split('\n')[0] ?? '';
  if (!id) {
    throw new Error(
      `createBranchCostCentre inserted nothing — no active membership for "${ownerEmail}" ` +
        `with a branch named "${branchName}" exists. Did the branch get created first?`,
    );
  }
  return { id };
}
