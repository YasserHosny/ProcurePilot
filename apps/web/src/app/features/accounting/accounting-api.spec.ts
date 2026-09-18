import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import type { AccountingConnection, StartConnectionResponse } from './accounting-api';
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
});
