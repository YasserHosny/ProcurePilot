import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import type { Role, Supplier } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { CAPTURE_MAX_BYTES, CaptureComponent } from './capture.component';

describe('CaptureComponent (T024)', () => {
  let component: CaptureComponent;
  let fixture: ComponentFixture<CaptureComponent>;
  let httpTestingController: HttpTestingController;
  let mockRoleSignal: ReturnType<typeof signal<Role | null>>;

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
      imports: [CaptureComponent, TranslateModule.forRoot()],
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
    fixture = TestBed.createComponent(CaptureComponent);
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
    expect(component.uploadState()).toBe('idle');
    expect(component.selectedFile()).toBeNull();
    expect(component.errorMessage()).toBeNull();
  });

  it('should populate supplier selector from ApiService.suppliers()', () => {
    expect(component.suppliers().length).toBe(2);
    expect(component.suppliers()[0].name).toBe('Acme Industrial Supplies');
    expect(component.suppliers()[1].name).toBe('Global Tech Corp');
  });

  it('should reject empty file without calling capture API', () => {
    const emptyFile = new File([], 'empty.pdf', { type: 'application/pdf' });
    const accepted = component.validateAndSetFile(emptyFile);

    expect(accepted).toBeFalse();
    expect(component.selectedFile()).toBeNull();
    expect(component.errorMessage()).toBe('The selected file is empty. Please select a valid document.');

    httpTestingController.expectNone('/api/v1/capture');
    expect(httpTestingController.match('/api/v1/capture').length).toBe(0);
  });

  it('should reject oversized file (>10MB) without calling capture API', () => {
    const oversizedFile = new File([''], 'huge.pdf', { type: 'application/pdf' });
    Object.defineProperty(oversizedFile, 'size', { value: CAPTURE_MAX_BYTES + 1 });

    const accepted = component.validateAndSetFile(oversizedFile);

    expect(accepted).toBeFalse();
    expect(component.selectedFile()).toBeNull();
    expect(component.errorMessage()).toBe('File size exceeds the 10 MB limit.');

    httpTestingController.expectNone('/api/v1/capture');
    expect(httpTestingController.match('/api/v1/capture').length).toBe(0);
  });

  it('should reject unsupported format without calling capture API', () => {
    const textFile = new File(['hello world'], 'notes.txt', { type: 'text/plain' });
    const accepted = component.validateAndSetFile(textFile);

    expect(accepted).toBeFalse();
    expect(component.selectedFile()).toBeNull();
    expect(component.errorMessage()).toBe(
      'Unsupported file format. Please upload a PDF, JPEG, PNG, or HEIC file.'
    );

    httpTestingController.expectNone('/api/v1/capture');
    expect(httpTestingController.match('/api/v1/capture').length).toBe(0);
  });

  it('should accept valid PDF file and update selectedFile', () => {
    const validPdf = new File(['%PDF-1.4 dummy content'], 'quote.pdf', {
      type: 'application/pdf',
    });

    const accepted = component.validateAndSetFile(validPdf);

    expect(accepted).toBeTrue();
    expect(component.selectedFile()).toBe(validPdf);
    expect(component.errorMessage()).toBeNull();
  });

  it('should accept image files (JPEG, PNG, HEIC) by MIME or extension', () => {
    const validJpeg = new File(['jpeg data'], 'invoice.jpg', { type: 'image/jpeg' });
    expect(component.validateAndSetFile(validJpeg)).toBeTrue();

    const validPng = new File(['png data'], 'invoice.png', { type: 'image/png' });
    expect(component.validateAndSetFile(validPng)).toBeTrue();

    const validHeic = new File(['heic data'], 'invoice.heic', { type: '' });
    expect(component.validateAndSetFile(validHeic)).toBeTrue();
    expect(component.selectedFile()).toBe(validHeic);
  });

  it('should submit valid file via submitCapture and transition to success state', () => {
    const validFile = new File(['valid content'], 'invoice.pdf', { type: 'application/pdf' });
    component.validateAndSetFile(validFile);
    component.selectedSupplierId.set('supp-001');
    component.notes.set('Special quotation for project X');
    fixture.detectChanges();

    component.submit();
    expect(component.uploadState()).toBe('uploading');

    const captureReq = httpTestingController.expectOne('/api/v1/capture');
    expect(captureReq.request.method).toBe('POST');
    expect(captureReq.request.body instanceof FormData).toBeTrue();

    const formData = captureReq.request.body as FormData;
    expect(formData.get('supplier_id')).toBe('supp-001');
    expect(formData.get('notes')).toBe('Special quotation for project X');

    captureReq.flush({ quotation_id: 'quot-xyz-789', status: 'pending' });
    fixture.detectChanges();

    expect(component.uploadState()).toBe('success');
    expect(component.captureResult()).toEqual({
      quotation_id: 'quot-xyz-789',
      status: 'pending',
    });

    const successContainer = fixture.debugElement.query(By.css('.result-container.success'));
    expect(successContainer).not.toBeNull();
    const routerLink = fixture.debugElement.query(By.css('a[mat-flat-button]'));
    expect(routerLink).not.toBeNull();
    expect(routerLink.attributes['ng-reflect-router-link']).toContain('quot-xyz-789');
  });

  it('should show error message and failed state when API returns an error', () => {
    const validFile = new File(['valid content'], 'invoice.pdf', { type: 'application/pdf' });
    component.validateAndSetFile(validFile);
    fixture.detectChanges();

    component.submit();
    expect(component.uploadState()).toBe('uploading');

    const captureReq = httpTestingController.expectOne('/api/v1/capture');
    expect(captureReq.request.method).toBe('POST');
    captureReq.flush(
      { message: 'Extraction worker failure', trace_id: 'tr-999' },
      { status: 500, statusText: 'Internal Server Error' }
    );
    fixture.detectChanges();

    expect(component.uploadState()).toBe('failed');
    expect(component.errorMessage()).toBe('Extraction worker failure');
    expect(component.errorTraceId()).toBe('tr-999');

    const failureContainer = fixture.debugElement.query(By.css('.result-container.failure'));
    expect(failureContainer).not.toBeNull();
  });

  it('should reset form and state when resetForm is invoked', () => {
    component.uploadState.set('success');
    component.selectedFile.set(new File(['abc'], 'test.pdf', { type: 'application/pdf' }));
    component.selectedSupplierId.set('supp-001');
    component.notes.set('Some notes');
    component.errorMessage.set('Some error');
    component.errorTraceId.set('trace-1');
    component.captureResult.set({ quotation_id: 'q-1', status: 'completed' });

    component.resetForm();

    expect(component.uploadState()).toBe('idle');
    expect(component.selectedFile()).toBeNull();
    expect(component.selectedSupplierId()).toBeNull();
    expect(component.notes()).toBe('');
    expect(component.errorMessage()).toBeNull();
    expect(component.errorTraceId()).toBeNull();
    expect(component.captureResult()).toBeNull();
  });

  it('should retry submit when retry() is invoked with an existing file', () => {
    const validFile = new File(['valid content'], 'invoice.pdf', { type: 'application/pdf' });
    component.selectedFile.set(validFile);
    component.uploadState.set('failed');
    component.errorMessage.set('Initial failure');

    component.retry();
    expect(component.uploadState()).toBe('uploading');

    const captureReq = httpTestingController.expectOne('/api/v1/capture');
    expect(captureReq.request.method).toBe('POST');
    captureReq.flush({ quotation_id: 'quot-retry-success', status: 'pending' });

    expect(component.uploadState()).toBe('success');
    expect(component.captureResult()?.quotation_id).toBe('quot-retry-success');
  });

  it('should handle retry when no file is present by resetting to idle', () => {
    component.selectedFile.set(null);
    component.uploadState.set('failed');
    component.errorMessage.set('Some error');

    component.retry();

    expect(component.uploadState()).toBe('idle');
    expect(component.errorMessage()).toBeNull();
  });

  it('should remove selected file when removeFile is called', () => {
    const validFile = new File(['content'], 'file.pdf', { type: 'application/pdf' });
    component.selectedFile.set(validFile);
    component.errorMessage.set('error');
    component.errorTraceId.set('trace');

    component.removeFile();

    expect(component.selectedFile()).toBeNull();
    expect(component.errorMessage()).toBeNull();
    expect(component.errorTraceId()).toBeNull();
  });

  it('should format file size correctly across B, KB, and MB', () => {
    expect(component.formatFileSize(500)).toBe('500 B');
    expect(component.formatFileSize(2048)).toBe('2.0 KB');
    expect(component.formatFileSize(5 * 1024 * 1024)).toBe('5.00 MB');
  });

  it('should gate actionable card by role (*appRole owner/buyer)', () => {
    mockRoleSignal.set('buyer');
    fixture.detectChanges();
    let card = fixture.debugElement.query(By.css('.capture-card'));
    expect(card).not.toBeNull();

    mockRoleSignal.set('owner');
    fixture.detectChanges();
    card = fixture.debugElement.query(By.css('.capture-card'));
    expect(card).not.toBeNull();

    mockRoleSignal.set('viewer');
    fixture.detectChanges();
    card = fixture.debugElement.query(By.css('.capture-card'));
    expect(card).toBeNull();
  });

  it('should handle file input change event', () => {
    const validFile = new File(['invoice content'], 'scanned.pdf', {
      type: 'application/pdf',
    });
    const fakeInput = { files: [validFile], value: 'scanned.pdf' };
    const event = { target: fakeInput } as unknown as Event;

    component.onFileSelected(event);

    expect(component.selectedFile()).toBe(validFile);
    expect(fakeInput.value).toBe('');
  });

  it('should handle drag and drop events', () => {
    const dragOverEvent = { preventDefault: jasmine.createSpy('preventDefault') } as unknown as DragEvent;
    component.onDragOver(dragOverEvent);
    expect(dragOverEvent.preventDefault).toHaveBeenCalled();
    expect(component.isDragOver()).toBeTrue();

    const dragLeaveEvent = { preventDefault: jasmine.createSpy('preventDefault') } as unknown as DragEvent;
    component.onDragLeave(dragLeaveEvent);
    expect(dragLeaveEvent.preventDefault).toHaveBeenCalled();
    expect(component.isDragOver()).toBeFalse();

    const validFile = new File(['dropped png'], 'receipt.png', { type: 'image/png' });
    const dropEvent = {
      preventDefault: jasmine.createSpy('preventDefault'),
      dataTransfer: { files: [validFile] },
    } as unknown as DragEvent;

    component.onDropFile(dropEvent);
    expect(dropEvent.preventDefault).toHaveBeenCalled();
    expect(component.selectedFile()).toBe(validFile);
    expect(component.isDragOver()).toBeFalse();
  });

  it('should handle supplier load failure gracefully', () => {
    component.loadSuppliers();
    const req = httpTestingController.expectOne('/api/v1/suppliers');
    expect(req.request.method).toBe('GET');
    req.error(new ProgressEvent('Network error'));

    expect(component.suppliers()).toEqual([]);
    expect(component.isLoadingSuppliers()).toBeFalse();
  });
});
