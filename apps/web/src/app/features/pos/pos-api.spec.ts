import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import type {
  PosConnection,
  PosProductMatch,
  StartConnectionResponse,
  SyncedProductSignalList,
  TriggerSyncResponse,
} from './pos-api';
import { PosApiService } from './pos-api';

describe('PosApiService (T015, T028)', () => {
  let service: PosApiService;
  let httpMock: HttpTestingController;

  const mockConnection: PosConnection = {
    id: 'pos-conn-001',
    provider: 'square',
    display_name: 'Square Coffee Shop',
    status: 'active',
    connected_at: '2026-09-19T10:00:00Z',
    last_synced_at: null,
    disconnected_at: null,
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        PosApiService,
      ],
    });

  service = TestBed.inject(PosApiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should call startConnection() with POST /pos/connect', () => {
    const mockResponse: StartConnectionResponse = {
      authorization_url: 'https://connect.squareup.com/oauth2/authorize?client_id=sq-123',
    };

    service.startConnection().subscribe((res) => {
      expect(res).toEqual(mockResponse);
    });

    const req = httpMock.expectOne('/api/v1/pos/connect');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({});
    req.flush(mockResponse);
  });

  it('should call connect() alias with POST /pos/connect', () => {
    const mockResponse: StartConnectionResponse = {
      authorization_url: 'https://connect.squareup.com/oauth2/authorize?client_id=sq-123',
    };

    service.connect().subscribe((res) => {
      expect(res).toEqual(mockResponse);
    });

    const req = httpMock.expectOne('/api/v1/pos/connect');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({});
    req.flush(mockResponse);
  });

  it('should call getConnection() with GET /pos/connection', () => {
    service.getConnection().subscribe((res) => {
      expect(res).toEqual(mockConnection);
    });

    const req = httpMock.expectOne('/api/v1/pos/connection');
    expect(req.request.method).toBe('GET');
    req.flush(mockConnection);
  });

  it('should call disconnect() with POST /pos/disconnect', () => {
    const disconnectedConnection: PosConnection = {
      ...mockConnection,
      status: 'disconnected',
      disconnected_at: '2026-09-19T12:00:00Z',
    };

    service.disconnect().subscribe((res) => {
      expect(res).toEqual(disconnectedConnection);
    });

    const req = httpMock.expectOne('/api/v1/pos/disconnect');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({});
    req.flush(disconnectedConnection);
  });

  it('should call triggerSync() with POST /pos/sync', () => {
    const mockResponse: TriggerSyncResponse = { status: 'enqueued' };

    service.triggerSync().subscribe((res) => {
      expect(res).toEqual(mockResponse);
    });

    const req = httpMock.expectOne('/api/v1/pos/sync');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({});
    req.flush(mockResponse);
  });

  it('should call listSignals() without params with GET /pos/signals', () => {
    const mockList: SyncedProductSignalList = {
      items: [
        {
          id: 'sig-001',
          external_item_name: 'Espresso Beans 1kg',
          matched: true,
          matched_workspace_product_id: 'prod-001',
          stock_on_hand: '15.000',
          stock_synced_at: '2026-09-19T10:00:00Z',
          sales_velocity_per_day: '2.500',
          velocity_window_days: 30,
          velocity_window_days_observed: 30,
          velocity_computed_at: '2026-09-19T10:00:00Z',
        },
      ],
      next_cursor: null,
    };

    service.listSignals().subscribe((res) => {
      expect(res).toEqual(mockList);
    });

    const req = httpMock.expectOne('/api/v1/pos/signals');
    expect(req.request.method).toBe('GET');
    req.flush(mockList);
  });

  it('should call listSignals() with params with filtered query string', () => {
    const mockList: SyncedProductSignalList = {
      items: [],
      next_cursor: 'cursor-123',
    };

    service
      .listSignals({
        cursor: 'cur-1',
        limit: 20,
        matchStatus: 'unmatched',
        workspaceProductId: 'prod-999',
      })
      .subscribe((res) => {
        expect(res).toEqual(mockList);
      });

    const req = httpMock.expectOne(
      '/api/v1/pos/signals?cursor=cur-1&limit=20&match_status=unmatched&workspace_product_id=prod-999',
    );
    expect(req.request.method).toBe('GET');
    req.flush(mockList);
  });

  it('should call manuallyMatchSignal() with POST /pos/signals/{signal_id}/match', () => {
    const mockMatch: PosProductMatch = {
      id: 'match-001',
      synced_product_signal_id: 'sig-001',
      workspace_product_id: 'prod-001',
      match_method: 'manual',
      matched_at: '2026-09-19T11:00:00Z',
    };

    service.manuallyMatchSignal('sig-001', 'prod-001').subscribe((res) => {
      expect(res).toEqual(mockMatch);
    });

    const req = httpMock.expectOne('/api/v1/pos/signals/sig-001/match');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ workspace_product_id: 'prod-001' });
    req.flush(mockMatch);
  });
});
