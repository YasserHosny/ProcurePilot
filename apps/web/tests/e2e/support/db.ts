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

/** Associates a seeded quotation with the matching sent RFQ recipient for prepare-request E2E. */
export function seedRfqResponse(
  ownerEmail: string,
  rfqId: string,
  supplierId: string,
  quotationId: string,
): void {
  const sql = [
    'insert into rfq_response (tenant_id, rfq_recipient_id, quotation_id)',
    'select m.tenant_id, rr.id, q.id from membership m',
    'join rfq r on r.id=' + `${sqlLiteral(rfqId)}::uuid` + ' and r.tenant_id=m.tenant_id',
    'join rfq_recipient rr on rr.rfq_id=r.id and rr.supplier_id=' + `${sqlLiteral(supplierId)}::uuid`,
    'join quotation q on q.id=' + `${sqlLiteral(quotationId)}::uuid` + ' and q.tenant_id=m.tenant_id',
    `where lower(m.email)=lower(${sqlLiteral(ownerEmail)}) and m.status='active'`,
  ].join(' ');
  const url = process.env['E2E_DATABASE_URL'];
  const psqlArgs = url ? [url, '-t', '-A', '-c', sql] : ['-U', 'postgres', '-t', '-A', '-c', sql];
  const stdout = execFileSync('docker', ['exec', DB_CONTAINER, 'psql', ...psqlArgs], {
    encoding: 'utf-8',
  }).trim();
  if (stdout !== 'INSERT 0 1') {
    throw new Error(`seedRfqResponse expected one association, got ${stdout || 'none'}`);
  }
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
export interface SeededLandedCost {
  id: string;
}

/** Sets deterministic review gate data on a quotation owned by this E2E buyer. */
export function seedQuotationReviewCase(
  ownerEmail: string,
  quotationId: string,
  lowConfidenceField: 'supplier_name' | 'unit_price',
): void {
  const sql = [
    'with owner as (select m.tenant_id from membership m',
    `where lower(m.email)=lower(${sqlLiteral(ownerEmail)}) and m.status='active' limit 1),`,
    'supplier as (insert into supplier (id,tenant_id,name)',
    `select gen_random_uuid(),tenant_id,${sqlLiteral(`E2E Review Supplier ${Date.now()}`)} from owner returning id,tenant_id),`,
    'quote as (update quotation q set supplier_id=supplier.id,currency=\'GBP\',stated_total_amount=75.00,stated_total_currency=\'GBP\',arithmetic_status=\'reconciled\'',
    `from supplier where q.id=${sqlLiteral(quotationId)}::uuid and q.tenant_id=supplier.tenant_id returning q.id,q.tenant_id),`,
    'raised as (update field_extraction f set confidence=0.9900 from quote',
    'where f.quotation_id=quote.id and f.tenant_id=quote.tenant_id returning f.id),',
    'target as (update field_extraction f set confidence=0.6000,extracted_value=',
    lowConfidenceField === 'supplier_name'
      ? `to_jsonb(${sqlLiteral('الأمانة للتجارة\nEl-Amana Trading')}::text)`
      : `coalesce(f.extracted_value,'{"amount":"12.00","currency":"EGP"}'::jsonb)`,
    'from quote where f.id=(select candidate.id from field_extraction candidate',
    'where candidate.quotation_id=quote.id and candidate.tenant_id=quote.tenant_id',
    `and candidate.field_name=${sqlLiteral(lowConfidenceField)}`,
    lowConfidenceField === 'unit_price'
      ? "and candidate.entity_type='quotation_line' order by candidate.created_at limit 1)"
      : "and candidate.entity_type='quotation' order by candidate.created_at limit 1)",
    'returning f.id) select count(*) from target',
  ].join(' ');
  // An explicit E2E_DATABASE_URL (e.g. the hosted demo/test DB the API under test points at) wins
  // over the local container, which would otherwise seed a database the API never reads.
  const url = process.env['E2E_DATABASE_URL'];
  const psqlArgs = url
    ? [url, '-t', '-A', '-c', sql]
    : ['-U', 'postgres', '-t', '-A', '-c', sql];
  const stdout = execFileSync('docker', ['exec', DB_CONTAINER, 'psql', ...psqlArgs], {
    encoding: 'utf-8',
  }).trim();
  if (stdout !== '1') throw new Error(`seedQuotationReviewCase expected one target field, got ${stdout || 'none'}`);
}

/**
 * Seeds a landed_cost row for a product so purchase-request valuation produces a real estimate.
 *
 * The estimate pipeline reads from match_decision + landed_cost, but the product catalogue UI does
 * not yet expose a way to record price history. This helper creates the minimal append-only chain
 * (document, quotation, quotation_line, match_decision, landed_cost) via SQL so tests can exercise
 * value-based routing and budget status without driving the full quotation/matching UI — same
 * docker-exec-psql pattern as createBranchCostCentre below, not a separate mechanism.
 */
export function seedLandedCost(
  ownerEmail: string,
  workspaceProductId: string,
  unitPrice: string,
  currency: string,
): SeededLandedCost {
  if (!/^\d+(\.\d{1,4})?$/.test(unitPrice)) {
    throw new Error(`seedLandedCost: invalid unitPrice "${unitPrice}"`);
  }
  if (!/^[A-Z]{3}$/.test(currency)) {
    throw new Error(`seedLandedCost: invalid currency "${currency}"`);
  }

  // Postgres RETURNING can only surface columns that actually exist on the table just written to
  // — not arbitrary columns carried in from the feeding SELECT. document/quotation have no
  // membership_id column of their own (it lands in created_by/reviewed_by, write-only), so each
  // stage below re-joins `owner` directly wherever it needs the membership id again, rather than
  // trying to thread it forward through a RETURNING list where it doesn't belong. Every RETURNING
  // here names only `id`/`tenant_id` (or, for match_decision, `quotation_line_id` — a genuine
  // column of match_decision itself), which every one of these tables actually has.
  const sql = [
    'with owner as (',
    '  select m.tenant_id, m.id as membership_id',
    '  from membership m',
    `  where lower(m.email) = lower(${sqlLiteral(ownerEmail)}) and m.status = 'active'`,
    '  limit 1',
    '),',
    'doc as (',
    '  insert into document (id, tenant_id, storage_bucket, storage_path, mime_type, source_channel, status, created_by)',
    `  select gen_random_uuid(), tenant_id, ${sqlLiteral('quotations')}, 'tenants/' || tenant_id || '/quotations/' || gen_random_uuid(), ${sqlLiteral('text/csv')}, 'upload', 'uploaded', membership_id`,
    '  from owner',
    '  returning id, tenant_id',
    '),',
    'quote as (',
    '  insert into quotation (id, tenant_id, document_id, status, reviewed_by, reviewed_at, currency)',
    '  select gen_random_uuid(), doc.tenant_id, doc.id, \'reviewed\', owner.membership_id, now(), ' +
      sqlLiteral(currency),
    '  from doc, owner',
    '  returning id, tenant_id',
    '),',
    'line as (',
    '  insert into quotation_line (id, tenant_id, quotation_id, line_number, original_text, quantity, unit_price_amount, unit_price_currency)',
    `  select gen_random_uuid(), tenant_id, id, 1, 'E2E fixture', 1, ${unitPrice}, ${sqlLiteral(currency)}`,
    '  from quote',
    '  returning id, tenant_id',
    '),',
    'decision as (',
    '  insert into match_decision (id, tenant_id, quotation_line_id, matched_workspace_product_id, outcome, is_automatic, decided_by, confidence)',
    `  select gen_random_uuid(), line.tenant_id, line.id, ${sqlLiteral(workspaceProductId)}::uuid, 'no_match_new_product', false, owner.membership_id, 1`,
    '  from line, owner',
    '  returning id, tenant_id, quotation_line_id',
    ')',
    'insert into landed_cost (id, tenant_id, quotation_line_id, match_decision_id, quantity, normalised_base_quantity, base_unit, unit_price_amount, unit_price_currency, vat_amount, vat_currency, delivery_fee_amount, delivery_fee_currency, discount_amount, discount_currency, other_charges_amount, other_charges_currency, total_amount, total_currency, raw_inputs, rule_version, valid_from)',
    `select gen_random_uuid(), tenant_id, quotation_line_id, id, 1, 1, 'each', ${unitPrice}, ${sqlLiteral(currency)}, 0, ${sqlLiteral(currency)}, 0, ${sqlLiteral(currency)}, 0, ${sqlLiteral(currency)}, 0, ${sqlLiteral(currency)}, ${unitPrice}, ${sqlLiteral(currency)}, '{}'::jsonb, 'landed-cost-v1', now()`,
    'from decision',
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
      `seedLandedCost inserted nothing — no active membership for "${ownerEmail}" exists.`,
    );
  }
  return { id };
}

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
