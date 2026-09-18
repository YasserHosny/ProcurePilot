import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { type WritableSignal, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import type { Role, Supplier } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import type { CatalogueImportResult } from '../ingestion-api';
import { CATALOGUE_IMPORT_MAX_BYTES, CatalogueImportComponent } from './catalogue-import.component';

describe('CatalogueImportComponent (T025)', () => {
  let component: CatalogueImportComponent;
  let fixture: ComponentFixture<CatalogueImportComponent>;
  let httpTestingController: HttpTestingController;
  let mockRoleSignal: WritableSignal<Role | null>;

  const mockSuppliers: Supplier[] = [
    {
      id: 'supp-001',
      name: 'Acme Industrial Supplies',
      status: 'active',
      created_at: '2026-08-01T00:00:00Z',
    },
    {
      id: 'supp-002',
      name: 'Global Tech Corp',
      status: 'preferred',
      created_at: '2026-08-05T00:00:00Z',
    },
  ];

  beforeEach(async () => {
    mockRoleSignal = signal<Role | null>('buyer');

    const mockSessionService = {
      role: mockRoleSignal,
      hasRole: (...roles: readonly Role[]) => {
        const current = mockRoleSignal();
        return current !== null && roles.includes(current);
      },
    };

    await TestBed.configureTestingModule({
      imports: [CatalogueImportComponent, TranslateModule.forRoot()],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        provideRouter([]),
        { provide: SessionService, useValue: mockSessionService },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');

    httpTestingController = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(CatalogueImportComponent);
    component = fixture.componentInstance;

    fixture.detectChanges();
    const suppliersReq = httpTestingController.expectOne('/api/v1/suppliers');
    expect(suppliersReq.request.method).toBe('GET');
    suppliersReq.flush({ items: mockSuppliers, next_cursor: null });
    fixture.detectChanges();
  });

  afterEach(() => {
    httpTestingController.verify();
  });

  it('should create the component and initialize state to idle', () => {
    expect(component).toBeTruthy();
    expect(component.importState()).toBe('idle');
    expect(component.selectedFile()).toBeNull();
    expect(component.selectedSupplierId()).toBeNull();
    expect(component.errorMessage()).toBeNull();
  });

  it('should populate supplier selector from ApiService.suppliers()', () => {
    expect(component.suppliers().length).toBe(2);
    expect(component.suppliers()[0].name).toBe('Acme Industrial Supplies');
    expect(component.suppliers()[1].name).toBe('Global Tech Corp');
  });

  it('should keep file picker disabled and reject file selection when no supplier is selected', () => {
    expect(component.selectedSupplierId()).toBeNull();

    const fileInput = fixture.debugElement.query(By.css('input[type="file"]'));
    expect(fileInput.nativeElement.disabled).toBeTrue();

    const browseBtn = fixture.debugElement.query(By.css('.browse-btn'));
    expect(browseBtn.nativeElement.disabled).toBeTrue();

    const validFile = new File(['sku,name,price\n1,Widget,10.50'], 'catalogue.csv', {
      type: 'text/csv',
    });
    const accepted = component.validateAndSetFile(validFile);

    expect(accepted).toBeFalse();
    expect(component.selectedFile()).toBeNull();
    expect(component.errorMessage()).toBe('Please select a supplier before importing.');

    expect(httpTestingController.match((req) => req.url.includes('catalogue-import')).length).toBe(
      0,
    );
  });

  it('should enable file picker once a supplier is selected', () => {
    component.onSupplierChange('supp-001');
    fixture.detectChanges();

    expect(component.selectedSupplierId()).toBe('supp-001');

    const fileInput = fixture.debugElement.query(By.css('input[type="file"]'));
    expect(fileInput.nativeElement.disabled).toBeFalse();

    const browseBtn = fixture.debugElement.query(By.css('.browse-btn'));
    expect(browseBtn.nativeElement.disabled).toBeFalse();
  });

  it('should reject empty file client-side without an HTTP call', () => {
    component.onSupplierChange('supp-001');
    const emptyFile = new File([], 'empty.csv', { type: 'text/csv' });

    const accepted = component.validateAndSetFile(emptyFile);

    expect(accepted).toBeFalse();
    expect(component.selectedFile()).toBeNull();
    expect(component.errorMessage()).toBe('The selected file is empty. Please select a valid file.');

    expect(httpTestingController.match((req) => req.url.includes('catalogue-import')).length).toBe(
      0,
    );
  });

  it('should reject oversized file (>25MB) client-side without an HTTP call', () => {
    component.onSupplierChange('supp-001');
    const oversizedFile = new File([''], 'huge.csv', { type: 'text/csv' });
    Object.defineProperty(oversizedFile, 'size', { value: CATALOGUE_IMPORT_MAX_BYTES + 1 });

    const accepted = component.validateAndSetFile(oversizedFile);

    expect(accepted).toBeFalse();
    expect(component.selectedFile()).toBeNull();
    expect(component.errorMessage()).toBe('File size exceeds the 25 MB limit.');

    expect(httpTestingController.match((req) => req.url.includes('catalogue-import')).length).toBe(
      0,
    );
  });

  it('should reject unsupported file format client-side without an HTTP call', () => {
    component.onSupplierChange('supp-001');
    const txtFile = new File(['some text'], 'test.txt', { type: 'text/plain' });

    const accepted = component.validateAndSetFile(txtFile);

    expect(accepted).toBeFalse();
    expect(component.selectedFile()).toBeNull();
    expect(component.errorMessage()).toBe(
      'Unsupported file format. Please upload a CSV or XLSX file.',
    );

    expect(httpTestingController.match((req) => req.url.includes('catalogue-import')).length).toBe(
      0,
    );
  });

  it('should accept valid CSV and XLSX files when supplier is selected', () => {
    component.onSupplierChange('supp-001');

    const validCsv = new File(['sku,name,price\n1,Widget,10.0'], 'items.csv', { type: 'text/csv' });
    expect(component.validateAndSetFile(validCsv)).toBeTrue();
    expect(component.selectedFile()).toBe(validCsv);

    const validXlsx = new File(['dummy xlsx data'], 'items.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    expect(component.validateAndSetFile(validXlsx)).toBeTrue();
    expect(component.selectedFile()).toBe(validXlsx);
  });

  it('should submit valid file via submitCatalogueImport with correct supplier and FormData', () => {
    component.onSupplierChange('supp-001');
    const validCsv = new File(['sku,name,price\n1,Widget,10.0'], 'items.csv', { type: 'text/csv' });
    component.validateAndSetFile(validCsv);
    fixture.detectChanges();

    component.submit();
    expect(component.importState()).toBe('importing');

    const importReq = httpTestingController.expectOne('/api/v1/suppliers/supp-001/catalogue-import');
    expect(importReq.request.method).toBe('POST');
    expect(importReq.request.body instanceof FormData).toBeTrue();

    const formData = importReq.request.body as FormData;
    expect(formData.get('file')).toBeTruthy();

    const mockResult: CatalogueImportResult = {
      id: 'ci-123',
      supplier_id: 'supp-001',
      status: 'completed',
      total_rows: 100,
      imported_rows: 95,
      skipped_rows: 3,
      error_rows: 2,
      error_details: [
        { row: 4, column: 'price', error: 'Invalid currency format' },
        { row: 12, column: 'sku', error: 'Duplicate SKU' },
      ],
    };

    importReq.flush(mockResult);
    fixture.detectChanges();

    expect(component.importState()).toBe('success');
    expect(component.importResult()).toEqual(mockResult);
  });

  it('should display results summary with correct counts when import completes', () => {
    component.onSupplierChange('supp-001');
    const validCsv = new File(['content'], 'items.csv', { type: 'text/csv' });
    component.validateAndSetFile(validCsv);
    fixture.detectChanges();

    component.submit();
    const importReq = httpTestingController.expectOne('/api/v1/suppliers/supp-001/catalogue-import');
    const mockResult: CatalogueImportResult = {
      id: 'ci-123',
      supplier_id: 'supp-001',
      status: 'completed',
      total_rows: 100,
      imported_rows: 95,
      skipped_rows: 3,
      error_rows: 2,
      error_details: [
        { row: 4, column: 'price', error: 'Invalid currency format' },
        { row: 12, column: 'sku', error: 'Duplicate SKU' },
      ],
    };
    importReq.flush(mockResult);
    fixture.detectChanges();

    const statCards = fixture.debugElement.queryAll(By.css('.stat-card'));
    expect(statCards.length).toBe(4);

    const totalVal = fixture.debugElement.query(By.css('.stat-total .stat-value'));
    expect(totalVal.nativeElement.textContent.trim()).toBe('100');

    const importedVal = fixture.debugElement.query(By.css('.stat-imported .stat-value'));
    expect(importedVal.nativeElement.textContent.trim()).toBe('95');

    const skippedVal = fixture.debugElement.query(By.css('.stat-skipped .stat-value'));
    expect(skippedVal.nativeElement.textContent.trim()).toBe('3');

    const errorVal = fixture.debugElement.query(By.css('.stat-errors .stat-value'));
    expect(errorVal.nativeElement.textContent.trim()).toBe('2');
  });

  it('should render the expandable error list when error_rows > 0', () => {
    component.onSupplierChange('supp-001');
    const validCsv = new File(['content'], 'items.csv', { type: 'text/csv' });
    component.validateAndSetFile(validCsv);
    fixture.detectChanges();

    component.submit();
    const importReq = httpTestingController.expectOne('/api/v1/suppliers/supp-001/catalogue-import');
    const mockResult: CatalogueImportResult = {
      id: 'ci-123',
      supplier_id: 'supp-001',
      status: 'completed',
      total_rows: 50,
      imported_rows: 48,
      skipped_rows: 0,
      error_rows: 2,
      error_details: [
        { row: 4, column: 'price', error: 'Invalid currency format' },
        { row: 12, column: 'sku', error: 'Duplicate SKU' },
      ],
    };
    importReq.flush(mockResult);
    fixture.detectChanges();

    const accordion = fixture.debugElement.query(By.css('.error-accordion'));
    expect(accordion).not.toBeNull();

    const tableRows = fixture.debugElement.queryAll(By.css('.error-table tbody tr'));
    expect(tableRows.length).toBe(2);
    expect(tableRows[0].nativeElement.textContent).toContain('4');
    expect(tableRows[0].nativeElement.textContent).toContain('price');
    expect(tableRows[0].nativeElement.textContent).toContain('Invalid currency format');
    expect(tableRows[1].nativeElement.textContent).toContain('12');
    expect(tableRows[1].nativeElement.textContent).toContain('sku');
    expect(tableRows[1].nativeElement.textContent).toContain('Duplicate SKU');
  });

  it('should NOT render the expandable error list when error_rows is 0', () => {
    component.onSupplierChange('supp-001');
    const validCsv = new File(['content'], 'items.csv', { type: 'text/csv' });
    component.validateAndSetFile(validCsv);
    fixture.detectChanges();

    component.submit();
    const importReq = httpTestingController.expectOne('/api/v1/suppliers/supp-001/catalogue-import');
    const mockResult: CatalogueImportResult = {
      id: 'ci-perfect',
      supplier_id: 'supp-001',
      status: 'completed',
      total_rows: 50,
      imported_rows: 50,
      skipped_rows: 0,
      error_rows: 0,
      error_details: [],
    };
    importReq.flush(mockResult);
    fixture.detectChanges();

    const accordion = fixture.debugElement.query(By.css('.error-accordion'));
    expect(accordion).toBeNull();
    expect(component.importResult()?.error_rows).toBe(0);
  });

  it('should show translated error message when API call fails', () => {
    component.onSupplierChange('supp-001');
    const validCsv = new File(['content'], 'items.csv', { type: 'text/csv' });
    component.validateAndSetFile(validCsv);
    fixture.detectChanges();

    component.submit();
    expect(component.importState()).toBe('importing');

    const importReq = httpTestingController.expectOne('/api/v1/suppliers/supp-001/catalogue-import');
    importReq.flush(
      { message: 'Catalogue parser failure: malformed header', trace_id: 'tr-cat-err' },
      { status: 400, statusText: 'Bad Request' },
    );
    fixture.detectChanges();

    expect(component.importState()).toBe('failed');
    expect(component.errorMessage()).toBe('Catalogue parser failure: malformed header');
    expect(component.errorTraceId()).toBe('tr-cat-err');

    const failureContainer = fixture.debugElement.query(By.css('.result-container.failure'));
    expect(failureContainer).not.toBeNull();
    expect(failureContainer.nativeElement.textContent).toContain('Catalogue parser failure: malformed header');
  });

  it('should reset form and state when resetForm is invoked', () => {
    component.onSupplierChange('supp-001');
    component.importState.set('success');
    component.selectedFile.set(new File(['content'], 'test.csv', { type: 'text/csv' }));
    component.errorMessage.set('Some error');
    component.errorTraceId.set('tr-123');
    component.importResult.set({
      id: 'ci-1',
      supplier_id: 'supp-001',
      status: 'completed',
      total_rows: 10,
      imported_rows: 10,
      skipped_rows: 0,
      error_rows: 0,
      error_details: [],
    });

    component.resetForm();

    expect(component.importState()).toBe('idle');
    expect(component.selectedFile()).toBeNull();
    expect(component.selectedSupplierId()).toBeNull();
    expect(component.errorMessage()).toBeNull();
    expect(component.errorTraceId()).toBeNull();
    expect(component.importResult()).toBeNull();
  });

  it('should retry submit when retry() is invoked with an existing file and supplier', () => {
    component.onSupplierChange('supp-001');
    const validCsv = new File(['content'], 'test.csv', { type: 'text/csv' });
    component.selectedFile.set(validCsv);
    component.importState.set('failed');
    component.errorMessage.set('Previous error');

    component.retry();
    expect(component.importState()).toBe('importing');

    const retryReq = httpTestingController.expectOne('/api/v1/suppliers/supp-001/catalogue-import');
    expect(retryReq.request.method).toBe('POST');
    retryReq.flush({
      id: 'ci-retry-success',
      supplier_id: 'supp-001',
      status: 'completed',
      total_rows: 20,
      imported_rows: 20,
      skipped_rows: 0,
      error_rows: 0,
      error_details: [],
    });
    fixture.detectChanges();

    expect(component.importState()).toBe('success');
    expect(component.importResult()?.id).toBe('ci-retry-success');
  });

  it('should reset to idle when retry() is called without a selected file', () => {
    component.onSupplierChange('supp-001');
    component.selectedFile.set(null);
    component.importState.set('failed');
    component.errorMessage.set('Some error');

    component.retry();

    expect(component.importState()).toBe('idle');
    expect(component.errorMessage()).toBeNull();
    expect(httpTestingController.match((req) => req.url.includes('catalogue-import')).length).toBe(
      0,
    );
  });

  it('should hide actionable card when role is neither owner nor buyer', () => {
    mockRoleSignal.set('viewer');
    fixture.detectChanges();

    const importCard = fixture.debugElement.query(By.css('.import-card'));
    expect(importCard).toBeNull();
  });
});
