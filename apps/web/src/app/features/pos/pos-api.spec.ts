import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import type {
  PosConnection,
  StartConnectionResponse,
} from './pos-api';
import { PosApiService } from './pos-api';

describe('PosApiService (T015)', () => {
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
});
