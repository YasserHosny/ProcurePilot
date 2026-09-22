import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import {
  NegotiationBrief,
  SupplierRiskApiService,
  SupplierRiskList,
} from './supplier-risk-api';

describe('SupplierRiskApiService', () => {
  let service: SupplierRiskApiService;
  let httpMock: HttpTestingController;

  const brief: NegotiationBrief = {
    id: 'brief-001',
    supplier_id: 'supplier-001',
    snapshot_id: 'snapshot-001',
    brief_version: 'negotiation-brief-v1',
    source_fingerprint: 'fingerprint-001',
    release_posture: 'g3_unmet',
    valid_from: '2026-09-20T00:00:00Z',
    valid_until: '2026-09-21T00:00:00Z',
    status: 'prepared',
    items: [
      {
        kind: 'price_trajectory',
        rank: 1,
        value: '0.2500',
        amount: { amount: '10.0000', currency: 'GBP' },
        confidence: 'high',
        risk: '0.5000',
        valid_from: '2026-06-22',
        valid_until: '2026-09-20',
        question_i18n_key: 'negotiationBrief.priceTrajectory.question',
        calculation_version: 'supplier-risk-v2',
        metric_id: 'metric-001',
        evidence_ids: ['evidence-001'],
        evidence: [
          {
            evidence_id: 'evidence-001',
            source_kind: 'purchase_order',
            source_id: 'order-001',
          },
        ],
      },
    ],
  };

  const riskList: SupplierRiskList = {
    items: [
      {
        id: 'snapshot-001',
        supplier_id: 'supplier-001',
        supplier_name: 'Alfaisal Trade',
        window_start: '2026-03-24',
        window_end: '2026-09-20',
        state: 'provisional',
        confidence: 'medium',
        release_posture: 'g3_unmet',
        valid_from: '2026-09-20T00:00:00Z',
        valid_until: '2026-09-21T00:00:00Z',
        source_fingerprint: 'fingerprint-001',
        observed_history_days: 180,
        risk_score: {
          total: '0.4200',
          components: { concentration: '0.4000' },
          weights: { concentration: '0.3000' },
        },
        risk_level: 'medium',
        computed_at: '2026-09-20T12:00:00Z',
      },
    ],
    next_cursor: null,
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(SupplierRiskApiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('lists risks with cursor pagination', () => {
    let result: SupplierRiskList | undefined;
    service.listRisks('next page', 25).subscribe((value) => (result = value));

    const request = httpMock.expectOne('/api/v1/supplier-iq/risks?limit=25&cursor=next+page');
    expect(request.request.method).toBe('GET');
    request.flush(riskList);
    expect(result).toEqual(riskList);
  });

  it('uses the default page size and caps oversized limits', () => {
    service.listRisks().subscribe();
    const riskRequest = httpMock.expectOne('/api/v1/supplier-iq/risks?limit=50');
    expect(riskRequest.request.method).toBe('GET');
    riskRequest.flush(riskList);

    service.listBriefs(undefined, 500).subscribe();
    const briefRequest = httpMock.expectOne('/api/v1/negotiation-briefs?limit=100');
    expect(briefRequest.request.method).toBe('GET');
    briefRequest.flush({
      items: [],
      next_cursor: null,
    });
  });

  it('recomputes risks with one idempotency key', () => {
    service.recompute().subscribe();

    const request = httpMock.expectOne('/api/v1/supplier-iq/recompute');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({});
    expect(request.request.headers.get('Idempotency-Key')).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    );
    request.flush({ generated_snapshots: 2, release_posture: 'g3_unmet' });
  });

  it('prepares a supplier brief and encodes the supplier id', () => {
    service.prepareBrief('supplier/001').subscribe();

    const request = httpMock.expectOne('/api/v1/suppliers/supplier%2F001/negotiation-briefs');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({});
    expect(request.request.headers.has('Idempotency-Key')).toBeTrue();
    request.flush(brief);
  });

  it('lists and gets briefs', () => {
    service.listBriefs(undefined, 10).subscribe();
    const listRequest = httpMock.expectOne('/api/v1/negotiation-briefs?limit=10');
    expect(listRequest.request.method).toBe('GET');
    listRequest.flush({ items: [brief], next_cursor: 'brief-cursor' });

    service.getBrief('brief/001').subscribe();
    const getRequest = httpMock.expectOne('/api/v1/negotiation-briefs/brief%2F001');
    expect(getRequest.request.method).toBe('GET');
    getRequest.flush(brief);
  });

  it('acknowledges and dismisses briefs with action-specific payloads', () => {
    service.acknowledgeBrief('brief-001').subscribe();
    const acknowledgeRequest = httpMock.expectOne(
      '/api/v1/negotiation-briefs/brief-001/acknowledge',
    );
    expect(acknowledgeRequest.request.method).toBe('POST');
    expect(acknowledgeRequest.request.body).toEqual({});
    expect(acknowledgeRequest.request.headers.has('Idempotency-Key')).toBeTrue();
    acknowledgeRequest.flush({ ...brief, status: 'acknowledged' });

    service.dismissBrief('brief-001', 'Needs supplier confirmation').subscribe();
    const dismissRequest = httpMock.expectOne('/api/v1/negotiation-briefs/brief-001/dismiss');
    expect(dismissRequest.request.method).toBe('POST');
    expect(dismissRequest.request.body).toEqual({ reason: 'Needs supplier confirmation' });
    expect(dismissRequest.request.headers.has('Idempotency-Key')).toBeTrue();
    dismissRequest.flush({ ...brief, status: 'dismissed' });
  });
});
