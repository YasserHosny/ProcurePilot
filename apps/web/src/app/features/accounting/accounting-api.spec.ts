import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import type {
  AccountingConnection,
  StartConnectionResponse,
  SyncedBillList,
  TriggerSyncResponse,
} from './accounting-api';
import { AccountingApiService } from './accounting-api';

describe('AccountingApiService (T017)', () => {
  let service: AccountingApiService;
  let httpMock: HttpTestingController;

  const mockConnection: AccountingConnection = {
    id: 'conn-001',
    provider: 'quickbooks',
    display_name: 'Acme Corp QuickBooks',
    status: 'active',
    connected_at: '2026-09-18T10:00:00Z',
    last_synced_at: null,
    disconnected_at: null,
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        AccountingApiService,
      ],
    });

    service = TestBed.inject(AccountingApiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should call startConnection() with POST /accounting/connect', () => {
    const mockResponse: StartConnectionResponse = {
      authorization_url: 'https://appcenter.intuit.com/connect/oauth2?client_id=123',
    };

    service.startConnection().subscribe((res) => {
      expect(res).toEqual(mockResponse);
    });

    const req = httpMock.expectOne('/api/v1/accounting/connect');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({});
    req.flush(mockResponse);
  });

  it('should call getConnection() with GET /accounting/connection', () => {
    service.getConnection().subscribe((res) => {
      expect(res).toEqual(mockConnection);
    });

    const req = httpMock.expectOne('/api/v1/accounting/connection');
    expect(req.request.method).toBe('GET');
    req.flush(mockConnection);
  });

  it('should call disconnect() with POST /accounting/disconnect', () => {
    const disconnectedConnection: AccountingConnection = {
      ...mockConnection,
      status: 'disconnected',
      disconnected_at: '2026-09-18T12:00:00Z',
    };

    service.disconnect().subscribe((res) => {
      expect(res).toEqual(disconnectedConnection);
    });

    const req = httpMock.expectOne('/api/v1/accounting/disconnect');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({});
    req.flush(disconnectedConnection);
  });

  it('should call triggerSync() with POST /accounting/sync', () => {
    const mockSyncResponse: TriggerSyncResponse = { status: 'enqueued' };

    service.triggerSync().subscribe((res) => {
      expect(res).toEqual(mockSyncResponse);
    });

    const req = httpMock.expectOne('/api/v1/accounting/sync');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({});
    req.flush(mockSyncResponse, { status: 202, statusText: 'Accepted' });
  });

  it('should call listBills() without params using GET /accounting/bills', () => {
    const mockBillList: SyncedBillList = {
      items: [
        {
          id: 'bill-1',
          vendor_name: 'Acme Supplies',
          matched_supplier_id: 'sup-1',
          amount: '1250.50',
          currency: 'USD',
          bill_date: '2026-09-15',
          provider_status: 'open',
          matched: true,
          purchase_record_id: 'pr-1',
        },
      ],
      next_cursor: 'cur_abc',
    };

    service.listBills().subscribe((res) => {
      expect(res).toEqual(mockBillList);
    });

    const req = httpMock.expectOne('/api/v1/accounting/bills');
    expect(req.request.method).toBe('GET');
    req.flush(mockBillList);
  });

  it('should call listBills() with all query params when provided', () => {
    const mockBillList: SyncedBillList = {
      items: [],
      next_cursor: null,
    };

    service
      .listBills({ cursor: 'cur_xyz', limit: 25, match_status: 'matched' })
      .subscribe((res) => {
        expect(res).toEqual(mockBillList);
      });

    const req = httpMock.expectOne(
      '/api/v1/accounting/bills?cursor=cur_xyz&limit=25&match_status=matched',
    );
    expect(req.request.method).toBe('GET');
    req.flush(mockBillList);
  });

  it('should call listBills() with only provided query params', () => {
    const mockBillList: SyncedBillList = {
      items: [],
      next_cursor: null,
    };

    service.listBills({ match_status: 'unmatched' }).subscribe((res) => {
      expect(res).toEqual(mockBillList);
    });

    const req = httpMock.expectOne('/api/v1/accounting/bills?match_status=unmatched');
    expect(req.request.method).toBe('GET');
    req.flush(mockBillList);
  });
});
