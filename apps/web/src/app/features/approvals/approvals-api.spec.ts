import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting, HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ApprovalsApiService } from './approvals-api';
import type { BulkApprovalDecisionInput } from '../../core/api/models';

describe('ApprovalsApiService bulk decisions', () => {
  it('posts the typed body with the provided batch key', () => {
    TestBed.configureTestingModule({providers: [provideHttpClient(), provideHttpClientTesting()]});
    const api = TestBed.inject(ApprovalsApiService);
    const http = TestBed.inject(HttpTestingController);
    const body: BulkApprovalDecisionInput = {decision: 'rejected', comment: 'Reason', request_ids: ['request-1']};
    api.bulkDecide(body, 'batch-key').subscribe(response => expect(response.failed_count).toBe(1));
    const request = http.expectOne(req => req.url.endsWith('/approvals/bulk-decisions'));
    expect(request.request.method).toBe('POST'); expect(request.request.body).toEqual(body);
    expect(request.request.headers.get('Idempotency-Key')).toBe('batch-key');
    request.flush({results: [{request_id: 'request-1', outcome: 'failed', error_code: 'not_found', request: null}], decided_count: 0, failed_count: 1});
    http.verify();
  });
});
