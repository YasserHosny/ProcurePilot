import { HttpErrorResponse } from '@angular/common/http';
import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { signal } from '@angular/core';
import { ActivatedRoute, ParamMap, Router, convertToParamMap, provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { BehaviorSubject, of, throwError } from 'rxjs';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { ApiService } from '../../../core/api/api.service';
import type { Job, PresignResponse, Quotation, Role } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { QuotationUploadComponent } from './quotation-upload.component';

describe('QuotationUploadComponent (T036)', () => {
  let component: QuotationUploadComponent;
  let fixture: ComponentFixture<QuotationUploadComponent>;
  let apiService: jasmine.SpyObj<ApiService>;
  let queryParamMapSubject: BehaviorSubject<ParamMap>;
  let router: Router;

  const mockPresignResponse: PresignResponse = {
    document_id: 'doc-123',
    storage_bucket: 'quotations',
    storage_path: 'tenant-1/doc-123.pdf',
    upload_url: 'https://storage.example.com/upload/doc-123',
    expires_at: '2026-08-21T02:00:00Z',
  };

  const mockQuotation: Quotation = {
    id: 'q-123',
    document_id: 'doc-123',
    status: 'pending',
    created_at: '2026-08-21T01:50:00Z',
  };

  const mockJobQueued: Job = {
    id: 'job-123',
    quotation_id: 'q-123',
    status: 'queued',
    created_at: '2026-08-21T01:50:00Z',
  };

  const mockJobSucceeded: Job = {
    id: 'job-123',
    quotation_id: 'q-123',
    status: 'succeeded',
    created_at: '2026-08-21T01:50:00Z',
    result_url: '/api/v1/quotations/q-123',
  };

  beforeEach(async () => {
    apiService = jasmine.createSpyObj('ApiService', [
      'presignDocument',
      'uploadFileToStorage',
      'createQuotation',
      'extractQuotation',
      'getJob',
    ]);

    const mockSession = {
      hasRole: jasmine.createSpy('hasRole').and.returnValue(true),
      role: signal<Role | null>('buyer'),
      currentMember: signal(null),
      isAuthenticated: signal(true),
      tenant: signal(null),
      activeLocale: signal('en'),
    };

    queryParamMapSubject = new BehaviorSubject<ParamMap>(convertToParamMap({}));

    await TestBed.configureTestingModule({
      imports: [QuotationUploadComponent],
      providers: [
        provideTranslateService(),
        provideRouter([]),
        { provide: ApiService, useValue: apiService },
        { provide: SessionService, useValue: mockSession },
        {
          provide: ActivatedRoute,
          useValue: {
            queryParamMap: queryParamMapSubject.asObservable(),
            snapshot: {
              get queryParamMap() {
                return queryParamMapSubject.value;
              },
            },
          },
        },
      ],
    }).compileComponents();

    router = TestBed.inject(Router);
    spyOn(router, 'navigate');
    spyOn(router, 'navigateByUrl').and.returnValue(Promise.resolve(true));

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(QuotationUploadComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should initialize in idle state with no selected file', () => {
    expect(component.uploadState()).toBe('idle');
    expect(component.selectedFile()).toBeNull();
  });

  it('should refuse unsupported file formats client-side without calling the API', () => {
    const invalidFile = new File(['bad'], 'test.exe', { type: 'application/x-msdownload' });
    const event = { target: { files: [invalidFile] } } as unknown as Event;

    component.onFileSelected(event);

    expect(component.selectedFile()).toBeNull();
    expect(component.errorMessage()).toContain('Unsupported file format');
    expect(apiService.presignDocument).not.toHaveBeenCalled();
  });

  it('should accept supported formats and start upload automatically', fakeAsync(() => {
    apiService.presignDocument.and.returnValue(of(mockPresignResponse));
    apiService.uploadFileToStorage.and.returnValue(of(undefined));
    apiService.createQuotation.and.returnValue(of(mockQuotation));
    apiService.extractQuotation.and.returnValue(of(mockJobQueued));
    spyOn(component as unknown as { computeContentHash: (file: File) => Promise<string> }, 'computeContentHash')
      .and.returnValue(Promise.resolve('abc123hash'));

    const validFile = new File(['%PDF-1.4...'], 'quote.pdf', { type: 'application/pdf' });
    const event = { target: { files: [validFile] } } as unknown as Event;

    component.onFileSelected(event);
    tick();

    expect(component.selectedFile()).toBe(validFile);
    expect(component.errorMessage()).toBeNull();
    expect(apiService.presignDocument).toHaveBeenCalledWith({
      filename: 'quote.pdf',
      mime_type: 'application/pdf',
      size_bytes: validFile.size,
      content_hash: 'abc123hash',
    });
    expect(apiService.extractQuotation).toHaveBeenCalledWith(mockQuotation.id);
  }));

  it('should execute direct-to-storage upload and poll job to extracted state', fakeAsync(() => {
    apiService.presignDocument.and.returnValue(of(mockPresignResponse));
    apiService.uploadFileToStorage.and.returnValue(of(undefined));
    apiService.createQuotation.and.returnValue(of(mockQuotation));
    apiService.extractQuotation.and.returnValue(of(mockJobQueued));
    apiService.getJob.and.returnValue(of(mockJobSucceeded));
    spyOn(component as unknown as { computeContentHash: (file: File) => Promise<string> }, 'computeContentHash')
      .and.returnValue(Promise.resolve('abc123hash'));

    const validFile = new File(['dummy pdf content'], 'supplier_quote.pdf', {
      type: 'application/pdf',
    });
    component.selectedFile.set(validFile);

    component.startUpload();
    tick();

    expect(apiService.presignDocument).toHaveBeenCalledWith({
      filename: 'supplier_quote.pdf',
      mime_type: 'application/pdf',
      size_bytes: validFile.size,
      content_hash: 'abc123hash',
    });
    expect(apiService.uploadFileToStorage).toHaveBeenCalledWith(
      mockPresignResponse.upload_url,
      validFile,
      undefined,
    );
    expect(apiService.createQuotation).toHaveBeenCalledWith({
      document_id: mockPresignResponse.document_id,
    });
    expect(apiService.extractQuotation).toHaveBeenCalledWith(mockQuotation.id);

    // Wait for the polling interval to trigger getJob
    tick(1500);
    expect(apiService.getJob).toHaveBeenCalledWith(mockJobQueued.id);
    expect(component.uploadState()).toBe('extracted');
    expect(component.createdQuotation()?.id).toBe('q-123');
  }));

  it('should transition to failed state if presign fails', fakeAsync(() => {
    apiService.presignDocument.and.returnValue(
      throwError(
        () =>
          new HttpErrorResponse({
            error: { code: 'UNSUPPORTED_MEDIA', message: 'Format error', trace_id: 'tr-999' },
            status: 415,
          }),
      ),
    );
    spyOn(component as unknown as { computeContentHash: (file: File) => Promise<string> }, 'computeContentHash')
      .and.returnValue(Promise.resolve('abc123hash'));

    const validFile = new File(['dummy'], 'quote.pdf', { type: 'application/pdf' });
    component.selectedFile.set(validFile);

    component.startUpload();
    tick();

    expect(component.uploadState()).toBe('failed');
    expect(component.errorMessage()).toBe('Format error');
    expect(component.errorTraceId()).toBe('tr-999');
  }));

  describe('Re-quote source linking (PPS-160 / P-128)', () => {
    const validUuid = 'c49d6c29-373f-4e02-9844-33d3d7890abc';

    it('reads requote_from query param if UUID-shaped and renders review anchor with requote_from query param', () => {
      queryParamMapSubject.next(convertToParamMap({ requote_from: validUuid }));
      fixture.detectChanges();

      expect(component.requoteFrom()).toBe(validUuid);

      component.createdQuotation.set(mockQuotation);
      component.uploadState.set('extracted');
      fixture.detectChanges();

      const anchor = fixture.nativeElement.querySelector('a.action-btn') as HTMLAnchorElement;
      expect(anchor).not.toBeNull();
      const href = anchor.getAttribute('href') ?? '';
      expect(href).toContain(`/quotations/${mockQuotation.id}/review`);
      expect(href).toContain(`requote_from=${validUuid}`);
    });

    it('ignores non-UUID requote_from query param and renders review anchor without requote_from', () => {
      queryParamMapSubject.next(convertToParamMap({ requote_from: 'not-a-valid-uuid' }));
      fixture.detectChanges();

      expect(component.requoteFrom()).toBeNull();

      component.createdQuotation.set(mockQuotation);
      component.uploadState.set('extracted');
      fixture.detectChanges();

      const anchor = fixture.nativeElement.querySelector('a.action-btn') as HTMLAnchorElement;
      expect(anchor).not.toBeNull();
      const href = anchor.getAttribute('href') ?? '';
      expect(href).toContain(`/quotations/${mockQuotation.id}/review`);
      expect(href).not.toContain('requote_from');
    });

    it('clears requoteFrom and removes requote_from query param on resetUpload so next upload carries no requote_from', () => {
      queryParamMapSubject.next(convertToParamMap({ requote_from: validUuid }));
      fixture.detectChanges();

      expect(component.requoteFrom()).toBe(validUuid);

      component.createdQuotation.set(mockQuotation);
      component.uploadState.set('extracted');
      fixture.detectChanges();

      const anchor1 = fixture.nativeElement.querySelector('a.action-btn') as HTMLAnchorElement;
      expect(anchor1.getAttribute('href')).toContain(`requote_from=${validUuid}`);

      const activatedRoute = TestBed.inject(ActivatedRoute);
      component.resetUpload();

      expect(component.requoteFrom()).toBeNull();
      expect(router.navigate).toHaveBeenCalledWith([], {
        queryParams: { requote_from: null },
        queryParamsHandling: 'merge',
        replaceUrl: true,
        relativeTo: activatedRoute,
      });

      // Next upload and review link
      component.createdQuotation.set({ ...mockQuotation, id: 'q-999' });
      component.uploadState.set('extracted');
      fixture.detectChanges();

      const anchor2 = fixture.nativeElement.querySelector('a.action-btn') as HTMLAnchorElement;
      expect(anchor2).not.toBeNull();
      const href2 = anchor2.getAttribute('href') ?? '';
      expect(href2).toContain('/quotations/q-999/review');
      expect(href2).not.toContain('requote_from');
    });

    it('handles unmodified click on review link via router.navigateByUrl and prevents default navigation', () => {
      queryParamMapSubject.next(convertToParamMap({ requote_from: validUuid }));
      fixture.detectChanges();

      component.createdQuotation.set(mockQuotation);
      component.uploadState.set('extracted');
      fixture.detectChanges();

      const anchor = fixture.nativeElement.querySelector('a.action-btn') as HTMLAnchorElement;
      expect(anchor).not.toBeNull();

      let recordedDefaultPrevented: boolean | null = null;
      const clickListener = (event: MouseEvent): void => {
        recordedDefaultPrevented = event.defaultPrevented;
        event.preventDefault();
      };

      document.addEventListener('click', clickListener, false);
      try {
        const clickEvent = new MouseEvent('click', {
          bubbles: true,
          cancelable: true,
        });
        anchor.dispatchEvent(clickEvent);
      } finally {
        document.removeEventListener('click', clickListener, false);
      }

      expect(recordedDefaultPrevented).toBeTrue();
      expect(router.navigateByUrl).toHaveBeenCalled();
      const calledUrl = (router.navigateByUrl as jasmine.Spy).calls.mostRecent().args[0].toString();
      expect(calledUrl).toContain(`/quotations/${mockQuotation.id}/review`);
      expect(calledUrl).toContain(`requote_from=${validUuid}`);
    });

    it('does not prevent default on review link when clicked with ctrlKey, metaKey, or shiftKey', () => {
      queryParamMapSubject.next(convertToParamMap({ requote_from: validUuid }));
      fixture.detectChanges();

      component.createdQuotation.set(mockQuotation);
      component.uploadState.set('extracted');
      fixture.detectChanges();

      const anchor = fixture.nativeElement.querySelector('a.action-btn') as HTMLAnchorElement;
      expect(anchor).not.toBeNull();

      let recordedCtrlDefaultPrevented: boolean | null = null;
      let recordedMetaDefaultPrevented: boolean | null = null;
      let recordedShiftDefaultPrevented: boolean | null = null;

      const clickListener = (event: MouseEvent): void => {
        if (event.ctrlKey) {
          recordedCtrlDefaultPrevented = event.defaultPrevented;
        } else if (event.metaKey) {
          recordedMetaDefaultPrevented = event.defaultPrevented;
        } else if (event.shiftKey) {
          recordedShiftDefaultPrevented = event.defaultPrevented;
        }
        // Neutralise actual browser navigation so Karma does not follow the href and reload
        event.preventDefault();
      };

      document.addEventListener('click', clickListener, false);
      try {
        const ctrlClickEvent = new MouseEvent('click', {
          ctrlKey: true,
          bubbles: true,
          cancelable: true,
        });
        anchor.dispatchEvent(ctrlClickEvent);

        const metaClickEvent = new MouseEvent('click', {
          metaKey: true,
          bubbles: true,
          cancelable: true,
        });
        anchor.dispatchEvent(metaClickEvent);

        const shiftClickEvent = new MouseEvent('click', {
          shiftKey: true,
          bubbles: true,
          cancelable: true,
        });
        anchor.dispatchEvent(shiftClickEvent);
      } finally {
        document.removeEventListener('click', clickListener, false);
      }

      expect(recordedCtrlDefaultPrevented).toBeFalse();
      expect(recordedMetaDefaultPrevented).toBeFalse();
      expect(recordedShiftDefaultPrevented).toBeFalse();
    });
  });
});
