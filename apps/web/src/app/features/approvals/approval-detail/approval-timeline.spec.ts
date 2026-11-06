import type { PurchaseRequest } from '../../../core/api/models';
import { buildApprovalTimeline } from './approval-timeline';

const request: PurchaseRequest = {
  id: 'request', branch_id: 'branch', requested_by_membership_id: 'requester',
  requester_name: 'Sara', status: 'submitted', required_by_date: '2026-11-10',
  created_at: '2026-11-01T10:00:00Z', submitted_at: '2026-11-01T11:00:00Z',
  has_incomplete_estimate: false, lines: [],
  approval_step: {id: 'step', assigned_membership_id: 'assignee', assigned_name: 'Layla',
    source: 'threshold_match', status: 'pending'},
};

describe('approval timeline derivation', () => {
  it('places submitted, routed and awaiting events in causal order without a routing time', () => {
    const events = buildApprovalTimeline(request, 'Unavailable');
    expect(events.map(event => event.key)).toEqual(['submitted', 'routed', 'awaiting']);
    expect(events.map(event => event.at)).toEqual([request.submitted_at!, undefined, undefined]);
  });
  for (const status of ['approved', 'rejected'] as const) {
    it(`retains the ${status} decision with its actor, comment, timestamp and self mark`, () => {
      const events = buildApprovalTimeline({...request, status,
        approval_step: {...request.approval_step!, status, decided_name: 'Omar', comment: 'Reason',
          decided_at: '2026-11-02T11:00:00Z', self_approval: true}}, 'Unavailable');
      expect(events.map(event => event.key)).toEqual(['submitted', 'routed', status]);
      expect(events[2].name).toBe('Omar'); expect(events[2].comment).toBe('Reason');
      expect(events[2].at).toBe('2026-11-02T11:00:00Z');
      expect(events[2].selfMark).toBe(status === 'approved' ? 'requests.approval.selfApproved' : 'requests.approval.selfRejected');
    });
  }
  it('sorts timestamped events chronologically and puts withdrawal last', () => {
    const events = buildApprovalTimeline({...request, status: 'withdrawn',
      submitted_at: '2026-11-03T11:00:00Z', withdrawn_at: '2026-11-04T11:00:00Z',
      approval_step: {...request.approval_step!, status: 'approved', decided_at: '2026-11-02T11:00:00Z'}}, 'Unavailable');
    expect(events.filter(event => event.at).map(event => event.key)).toEqual(['approved', 'submitted', 'withdrawn']);
  });
  it('omits missing timestamps and falls back to the recorded email rather than the assignee', () => {
    const events = buildApprovalTimeline({...request, submitted_at: null, status: 'approved',
      approval_step: {...request.approval_step!, status: 'approved', decided_email: 'decider@example.test'}}, 'Unavailable');
    expect(events.map(event => event.key)).toEqual(['routed', 'approved']);
    expect(events.every(event => !event.at)).toBeTrue();
    expect(events[1].name).toBe('decider@example.test');
  });
  it('marks self-approval pending and omits awaiting on withdrawn requests', () => {
    const pending = {...request, approval_step: {...request.approval_step!, self_approval: true}};
    expect(buildApprovalTimeline(pending, 'Unavailable')[2].selfMark).toBe('requests.approval.selfApprovalPending');
    expect(buildApprovalTimeline({...pending, status: 'withdrawn'}, 'Unavailable').map(event => event.key)).toEqual(['submitted', 'routed']);
  });
  it('returns no events before a request is loaded', () => {
    expect(buildApprovalTimeline(null, 'Unavailable')).toEqual([]);
  });
});
