import type { BulkApprovalDecisionInput, PurchaseRequest } from '../../../core/api/models';
import enCatalog from '../../../../../../../packages/i18n/en.json';
import arCatalog from '../../../../../../../packages/i18n/ar.json';
import { bulkAttemptSignature, bulkFailureKey, selectionCurrencyTotals } from './bulk-selection';

function request(amount: string | null, currency = 'EGP'): PurchaseRequest {
  return {id: 'request', branch_id: 'branch', requested_by_membership_id: 'member', required_by_date: '2026-11-10', status: 'submitted', created_at: '2026-11-01', lines: [], has_incomplete_estimate: false, estimated_total: amount === null ? null : {amount, currency}};
}

describe('bulk selection helpers', () => {
  it('adds decimals exactly inside each currency and never combines currencies', () => {
    expect(selectionCurrencyTotals([request('0.1'), request('0.2'), request('3.0001', 'SAR'), request(null)])).toEqual([{amount: '0.3', currency: 'EGP'}, {amount: '3.0001', currency: 'SAR'}]);
  });
  it('preserves large and signed decimal amounts without floating-point arithmetic', () => {
    expect(selectionCurrencyTotals([request('9007199254740993.0001'), request('-0.0001')])).toEqual([{amount: '9007199254740993', currency: 'EGP'}]);
  });
  it('matches identical selection independent of order and differentiates decision and comment', () => {
    const body: BulkApprovalDecisionInput = {decision: 'approved', comment: null, request_ids: ['b', 'a']};
    expect(bulkAttemptSignature(body)).toBe(bulkAttemptSignature({...body, request_ids: ['a', 'b']}));
    for (const other of [{...body, decision: 'rejected' as const}, {...body, comment: 'Reason'}, {...body, request_ids: ['a']}]) expect(bulkAttemptSignature(other)).not.toBe(bulkAttemptSignature(body));
    expect(body.request_ids).toEqual(['b', 'a']);
  });
  for (const code of ['group_request_use_group_decision', 'self_decision_not_allowed', 'not_found', 'unavailable', 'conflict', 'not_submitted', 'no_pending_approval', 'auth.permission_denied', 'unknown', null]) {
    it(`provides translated safe reasons for ${code}`, () => {
      const key = bulkFailureKey(code);
      expect(key).toMatch(/^approvals\.bulk\.reasons\./);
      const leaf = key.split('.').at(-1)!;
      for (const catalogue of [enCatalog, arCatalog]) {
        const reasons: Record<string, string> = catalogue.approvals.bulk.reasons;
        expect(reasons[leaf]).toBeTruthy();
        if (code?.includes('_') || code === 'unknown') expect(reasons[leaf]).not.toContain(code);
      }
      if (code === 'unknown' || code === null) expect(key).toBe('approvals.bulk.reasons.generic');
    });
  }
});
