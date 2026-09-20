import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import type {
  CatalogueImportResult,
  CatalogueImportSummaryList,
  CaptureResult,
  IngestionEmailLogList,
  IngestionStats,
  TenantEmailConfig,
  TenantEmailConfigUpdate,
} from './ingestion-api';
import { IngestionApiService } from './ingestion-api';

describe('IngestionApiService', () => {
  let service: IngestionApiService;
  let httpMock: HttpTestingController;

  const mockEmailConfig: TenantEmailConfig = {
    id: 'cfg-001',
    forwarding_address: 'tenant-orders@inbound.procurepilot.com',
    enabled: true,
    domain_allowlist: ['supplier.com', 'vendor.org'],
    daily_limit: 500,
    daily_count: 12,
    daily_count_date: '2026-09-17',
    spf_dkim_required: true,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-17T08:00:00Z',
  };

  const mockEmailLogList: IngestionEmailLogList = {
    items: [
      {
        id: 'log-001',
        message_id: '<msg-001@vendor.org>',
        from_address: 'sales@vendor.org',
        from_domain: 'vendor.org',
        subject: 'Quotation Q-9872',
        received_at: '2026-09-17T09:00:00Z',
        processed_at: '2026-09-17T09:00:05Z',
        status: 'completed',
        error_message: null,
        attachment_count: 1,
        quotation_id: 'quot-001',
        supplier_id: 'supp-001',
        match_method: 'domain',
        created_at: '2026-09-17T09:00:00Z',
      },
    ],
    next_cursor: 'cur-002',
  };

  const mockCatalogueImportResult: CatalogueImportResult = {
    id: 'import-001',
    supplier_id: 'supp-001',
    status: 'completed',
    total_rows: 50,
    imported_rows: 45,
    skipped_rows: 3,
    error_rows: 2,
    error_details: [
      { row: 12, column: 'unit_price', error: 'Invalid decimal value' },
      { row: 34, column: 'sku', error: 'SKU already exists' },
    ],
  };

  const mockCatalogueImportList: CatalogueImportSummaryList = {
    items: [
      {
        id: 'import-001',
        supplier_id: 'supp-001',
        file_name: 'pricelist.csv',
        file_path: 'tenant-1/catalogue/pricelist.csv',
        file_size_bytes: 10240,
        file_format: 'csv',
        status: 'completed',
        total_rows: 50,
        imported_rows: 45,
        skipped_rows: 3,
        error_rows: 2,
        error_details: [
          { row: 12, column: 'unit_price', error: 'Invalid decimal value' },
        ],
        column_mapping: { sku: 'ItemCode', price: 'UnitPrice' },
        created_at: '2026-09-16T12:00:00Z',
        completed_at: '2026-09-16T12:00:10Z',
        created_by: 'user-001',
      },
    ],
    next_cursor: null,
  };

  const mockStats: IngestionStats = {
    emails_received_today: 15,
    emails_received_week: 95,
    emails_received_month: 412,
    capture_uploads_total: 28,
    catalogue_imports_total: 10,
    supplier_match_rate: 0.88,
    extraction_success_rate: 0.94,
    active_quotation_count: 50,
    integration_sourced_quotation_count: 20,
    integration_sourced_share: 0.4,
    purchase_history_days: 90,
    g3_history_ready: false,
    active_refresh_schedule_count: 3,
    linked_refresh_schedule_count: 0,
    refresh_pilot_ready: false,
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });

    service = TestBed.inject(IngestionApiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  describe('getEmailConfig', () => {
    it('should issue GET /tenants/email-config and return config', () => {
      let result: TenantEmailConfig | undefined;
      service.getEmailConfig().subscribe((data) => {
        result = data;
      });

      const req = httpMock.expectOne('/api/v1/tenants/email-config');
      expect(req.request.method).toBe('GET');
      req.flush(mockEmailConfig);

      expect(result).toEqual(mockEmailConfig);
    });
  });

  describe('updateEmailConfig', () => {
    it('should issue PUT /tenants/email-config with payload and return updated config', () => {
      const payload: Partial<TenantEmailConfigUpdate> = {
        domain_allowlist: ['newvendor.com'],
        daily_limit: 1000,
      };
      const updatedConfig: TenantEmailConfig = {
        ...mockEmailConfig,
        domain_allowlist: ['newvendor.com'],
        daily_limit: 1000,
      };

      let result: TenantEmailConfig | undefined;
      service.updateEmailConfig(payload).subscribe((data) => {
        result = data;
      });

      const req = httpMock.expectOne('/api/v1/tenants/email-config');
      expect(req.request.method).toBe('PUT');
      expect(req.request.body).toEqual(payload);
      req.flush(updatedConfig);

      expect(result).toEqual(updatedConfig);
    });
  });

  describe('enableEmailConfig', () => {
    it('should issue POST /tenants/email-config/enable with empty body and return config', () => {
      let result: TenantEmailConfig | undefined;
      service.enableEmailConfig().subscribe((data) => {
        result = data;
      });

      const req = httpMock.expectOne('/api/v1/tenants/email-config/enable');
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual({});
      req.flush(mockEmailConfig);

      expect(result).toEqual(mockEmailConfig);
    });
  });

  describe('disableEmailConfig', () => {
    it('should issue POST /tenants/email-config/disable with empty body and return config', () => {
      const disabledConfig: TenantEmailConfig = { ...mockEmailConfig, enabled: false };
      let result: TenantEmailConfig | undefined;
      service.disableEmailConfig().subscribe((data) => {
        result = data;
      });

      const req = httpMock.expectOne('/api/v1/tenants/email-config/disable');
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual({});
      req.flush(disabledConfig);

      expect(result).toEqual(disabledConfig);
    });
  });

  describe('listEmailLogs', () => {
    it('should issue GET /ingestion/emails without query string when params are empty', () => {
      let result: IngestionEmailLogList | undefined;
      service.listEmailLogs().subscribe((data) => {
        result = data;
      });

      const req = httpMock.expectOne('/api/v1/ingestion/emails');
      expect(req.request.method).toBe('GET');
      req.flush(mockEmailLogList);

      expect(result).toEqual(mockEmailLogList);
    });

    it('should append query parameters when provided', () => {
      let result: IngestionEmailLogList | undefined;
      service
        .listEmailLogs({
          cursor: 'cur_abc',
          limit: 25,
          status: 'completed',
          from_domain: 'vendor.org',
          date_from: '2026-09-01',
          date_to: '2026-09-17',
        })
        .subscribe((data) => {
          result = data;
        });

      const req = httpMock.expectOne(
        '/api/v1/ingestion/emails?cursor=cur_abc&limit=25&status=completed&from_domain=vendor.org&date_from=2026-09-01&date_to=2026-09-17'
      );
      expect(req.request.method).toBe('GET');
      req.flush(mockEmailLogList);

      expect(result).toEqual(mockEmailLogList);
    });

    it('should only append parameters that are set', () => {
      service.listEmailLogs({ status: 'failed' }).subscribe();

      const req = httpMock.expectOne('/api/v1/ingestion/emails?status=failed');
      expect(req.request.method).toBe('GET');
      req.flush(mockEmailLogList);
    });
  });

  describe('submitCapture', () => {
    it('should send multipart FormData with file, supplier_id, and notes', () => {
      const file = new File(['sample content'], 'receipt.pdf', {
        type: 'application/pdf',
      });
      let result: CaptureResult | undefined;

      service.submitCapture(file, 'supp-001', 'Urgent invoice').subscribe((data) => {
        result = data;
      });

      const req = httpMock.expectOne('/api/v1/capture');
      expect(req.request.method).toBe('POST');
      expect(req.request.body instanceof FormData).toBeTrue();

      const formData = req.request.body as FormData;
      expect(formData.has('file')).toBeTrue();
      expect(formData.has('supplier_id')).toBeTrue();
      expect(formData.has('notes')).toBeTrue();

      req.flush({ quotation_id: 'quot-001', status: 'pending' });
      expect(result).toEqual({ quotation_id: 'quot-001', status: 'pending' });
    });

    it('should omit supplier_id and notes from FormData when not provided', () => {
      const file = new File(['img content'], 'photo.jpg', { type: 'image/jpeg' });

      service.submitCapture(file).subscribe();

      const req = httpMock.expectOne('/api/v1/capture');
      expect(req.request.method).toBe('POST');
      expect(req.request.body instanceof FormData).toBeTrue();

      const formData = req.request.body as FormData;
      expect(formData.has('file')).toBeTrue();
      expect(formData.has('supplier_id')).toBeFalse();
      expect(formData.has('notes')).toBeFalse();

      req.flush({ quotation_id: 'quot-002', status: 'pending' });
    });
  });

  describe('submitCatalogueImport', () => {
    it('should send multipart FormData with file to /suppliers/{supplierId}/catalogue-import', () => {
      const file = new File(['sku,name,price\n1,Widget,10'], 'catalog.csv', {
        type: 'text/csv',
      });
      let result: CatalogueImportResult | undefined;

      service.submitCatalogueImport('supp-001', file).subscribe((data) => {
        result = data;
      });

      const req = httpMock.expectOne('/api/v1/suppliers/supp-001/catalogue-import');
      expect(req.request.method).toBe('POST');
      expect(req.request.body instanceof FormData).toBeTrue();

      const formData = req.request.body as FormData;
      expect(formData.has('file')).toBeTrue();

      req.flush(mockCatalogueImportResult);
      expect(result).toEqual(mockCatalogueImportResult);
    });
  });

  describe('listCatalogueImports', () => {
    it('should issue GET /suppliers/{supplierId}/catalogue-imports without params', () => {
      let result: CatalogueImportSummaryList | undefined;
      service.listCatalogueImports('supp-001').subscribe((data) => {
        result = data;
      });

      const req = httpMock.expectOne('/api/v1/suppliers/supp-001/catalogue-imports');
      expect(req.request.method).toBe('GET');
      req.flush(mockCatalogueImportList);

      expect(result).toEqual(mockCatalogueImportList);
    });

    it('should append cursor and limit query parameters when supplied', () => {
      service
        .listCatalogueImports('supp-001', { cursor: 'imp_cur_9', limit: 15 })
        .subscribe();

      const req = httpMock.expectOne(
        '/api/v1/suppliers/supp-001/catalogue-imports?cursor=imp_cur_9&limit=15'
      );
      expect(req.request.method).toBe('GET');
      req.flush(mockCatalogueImportList);
    });
  });

  describe('getStats', () => {
    it('should issue GET /ingestion/stats and return stats', () => {
      let result: IngestionStats | undefined;
      service.getStats().subscribe((data) => {
        result = data;
      });

      const req = httpMock.expectOne('/api/v1/ingestion/stats');
      expect(req.request.method).toBe('GET');
      req.flush(mockStats);

      expect(result).toEqual(mockStats);
    });
  });

  describe('error handling', () => {
    it('should propagate 4xx error response to observer error callback', () => {
      let errorStatus: number | undefined;
      let errorCode: string | undefined;

      service.getEmailConfig().subscribe({
        next: () => fail('Expected getEmailConfig to fail with 404'),
        error: (err) => {
          errorStatus = err.status;
          errorCode = err.error?.code;
        },
      });

      const req = httpMock.expectOne('/api/v1/tenants/email-config');
      req.flush(
        {
          code: 'not_found',
          message: 'Tenant email configuration not found',
          trace_id: 'tr-404-001',
        },
        { status: 404, statusText: 'Not Found' }
      );

      expect(errorStatus).toBe(404);
      expect(errorCode).toBe('not_found');
    });
  });
});
