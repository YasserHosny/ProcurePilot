import { ComponentFixture, TestBed } from '@angular/core/testing';
import { RfqCreateComponent } from './create.component';
import { RfqApi, Rfq, RfqDetail } from '../rfq-api';
import { ApiService } from '../../../core/api/api.service';
import { provideHttpClient, HttpErrorResponse } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ActivatedRoute, Router, provideRouter } from '@angular/router';
import { MatSnackBar } from '@angular/material/snack-bar';
import { of, throwError } from 'rxjs';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { Product, Supplier } from '../../../core/api/models';

describe('RfqCreateComponent', () => {
  let component: RfqCreateComponent;
  let fixture: ComponentFixture<RfqCreateComponent>;
  let rfqApiSpy: jasmine.SpyObj<RfqApi>;
  let apiSpy: jasmine.SpyObj<ApiService>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;
  let router: Router;
  let translate: TranslateService;
  let routeId: string | null;

  beforeEach(async () => {
    routeId = null;
    rfqApiSpy = jasmine.createSpyObj('RfqApi', ['createRfq', 'getRfq', 'updateRfq', 'sendRfq']);
    apiSpy = jasmine.createSpyObj('ApiService', ['products', 'suppliers']);
    snackBarSpy = jasmine.createSpyObj('MatSnackBar', ['open']);

    apiSpy.products.and.returnValue(
      of({ items: [{ id: 'prod-1', tenant_name: 'Product 1' } as Product], next_cursor: null }),
    );
    apiSpy.suppliers.and.returnValue(
      of({
        items: [{ id: 'sup-1', name: 'Supplier 1', contact_email: 'sup@test.com' } as Supplier],
        next_cursor: null,
      }),
    );

    await TestBed.configureTestingModule({
      imports: [RfqCreateComponent, TranslateModule.forRoot()],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        provideRouter([]),
        { provide: RfqApi, useValue: rfqApiSpy },
        { provide: ApiService, useValue: apiSpy },
        { provide: MatSnackBar, useValue: snackBarSpy },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              paramMap: {
                get: (key: string) => (key === 'id' ? routeId : null),
              },
            },
          },
        },
      ],
    })
      .overrideProvider(MatSnackBar, { useValue: snackBarSpy })
      .compileComponents();

    router = TestBed.inject(Router);
    spyOn(router, 'navigate').and.returnValue(Promise.resolve(true));

    translate = TestBed.inject(TranslateService);
    translate.setTranslation(
      'en',
      {
        rfq: {
          create: {
            title: 'Create RFQ',
            editTitle: 'Edit RFQ draft',
            draftSaved: 'Draft saved',
            sentSuccess: 'RFQ sent to {{count}} suppliers',
            notDraftTitle: 'RFQ cannot be edited',
            notDraftMessage: 'Only draft RFQs can be edited. This RFQ has already been sent.',
            backToHistory: 'Back to RFQ History',
            validationError: 'Please check the following RFQ fields:',
            neededByDateLabel: 'Needed By Date',
            saveError: 'SAVE FALLBACK',
            errors: { notFound: 'The requested RFQ resource could not be found.' },
          },
          history: {
            dismiss: 'Close',
            status_draft: 'Draft',
            status_sent: 'Sent',
          },
        },
      },
      true,
    );
    translate.use('en');

    fixture = TestBed.createComponent(RfqCreateComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('rejects tenant terms over 4000 characters and accepts exactly 4000', () => {
    component.form.patchValue({
      lines: [{ workspace_product_id: 'prod-1', quantity: '10' }],
      supplierIds: ['sup-1'],
      neededByDate: new Date(2026, 11, 1),
      tenantTerms: 'x'.repeat(4001),
    });

    fixture.detectChanges();
    expect(component.form.controls.tenantTerms.invalid).toBeTrue();
    expect(
      (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('button[type="submit"]')
        ?.disabled,
    ).toBeTrue();

    component.form.controls.tenantTerms.setValue('x'.repeat(4000));
    fixture.detectChanges();
    expect(component.form.controls.tenantTerms.valid).toBeTrue();
    expect(component.form.valid).toBeTrue();
  });

  it('should show rejection reason for suppliers without email, show snackbar, and switch to edit mode on second save', () => {
    rfqApiSpy.createRfq.and.returnValue(
      of({
        rfq: { id: 'rfq-1', status: 'draft' } as Rfq,
        lines: [],
        recipients: [],
        rejected_recipients: [{ supplier_id: 'sup-1', reason: 'missing_contact_email' }],
      }),
    );

    component.form.patchValue({
      lines: [{ workspace_product_id: 'prod-1', quantity: '10' }],
      supplierIds: ['sup-1'],
      neededByDate: new Date(2026, 11, 1),
    });

    component.onSave();

    expect(component.rejectedSuppliers().length).toBe(1);
    expect(component.rejectedSuppliers()[0].reason).toBe('missing_contact_email');
    expect(component.rfqId()).toBe('rfq-1');
    expect(snackBarSpy.open).toHaveBeenCalledWith('Draft saved', 'Close', { duration: 4000 });
    expect(router.navigate).toHaveBeenCalledWith(['/rfq', 'rfq-1', 'edit'], { replaceUrl: true });

    // A second save updates via PUT instead of creating a duplicate
    rfqApiSpy.updateRfq.and.returnValue(
      of({
        rfq: { id: 'rfq-1', status: 'draft' } as Rfq,
        lines: [],
        recipients: [],
        rejected_recipients: [],
      }),
    );
    component.onSave();
    expect(rfqApiSpy.updateRfq).toHaveBeenCalledWith(
      'rfq-1',
      jasmine.objectContaining({ needed_by_date: '2026-12-01' }),
    );
  });

  it('should call sendRfq when explicit send is triggered, show snackbar, and navigate to history', () => {
    component.rfqId.set('rfq-1');
    rfqApiSpy.sendRfq.and.returnValue(
      of({
        rfq: { id: 'rfq-1', status: 'sent' } as Rfq,
        recipients: [{ id: 'rec-1' }, { id: 'rec-2' }] as never[],
      }),
    );

    component.onSend();
    expect(rfqApiSpy.sendRfq).toHaveBeenCalledWith('rfq-1');
    expect(snackBarSpy.open).toHaveBeenCalledWith('RFQ sent to 2 suppliers', 'Close', {
      duration: 5000,
    });
    expect(router.navigate).toHaveBeenCalledWith(['/rfq/history']);
  });

  it('prefills form in edit mode with local date and calls updateRfq (PUT) on save', () => {
    routeId = 'rfq-edit-1';
    const mockDetail: RfqDetail = {
      rfq: {
        id: 'rfq-edit-1',
        tenant_id: 't-1',
        created_by_membership_id: 'm-1',
        status: 'draft',
        needed_by_date: '2026-11-15',
        tenant_terms: 'Net 30 delivery',
        idempotency_key: 'k-1',
        created_at: '2026-10-01T00:00:00Z',
      },
      lines: [
        {
          id: 'line-1',
          tenant_id: 't-1',
          rfq_id: 'rfq-edit-1',
          workspace_product_id: 'prod-1',
          quantity: '25',
          created_at: '2026-10-01T00:00:00Z',
        },
      ],
      recipients: [
        {
          id: 'rec-1',
          tenant_id: 't-1',
          rfq_id: 'rfq-edit-1',
          supplier_id: 'sup-1',
          status: 'draft',
          outbound_message_id: null,
          sent_at: null,
          created_at: '2026-10-01T00:00:00Z',
        },
      ],
    };
    rfqApiSpy.getRfq.and.returnValue(of(mockDetail));
    rfqApiSpy.updateRfq.and.returnValue(
      of({
        rfq: mockDetail.rfq,
        lines: mockDetail.lines,
        recipients: mockDetail.recipients,
        rejected_recipients: [],
      }),
    );

    const editFixture = TestBed.createComponent(RfqCreateComponent);
    const editComp = editFixture.componentInstance;
    editFixture.detectChanges();

    expect(rfqApiSpy.getRfq).toHaveBeenCalledWith('rfq-edit-1');
    expect(editComp.isEditMode()).toBeTrue();
    expect(editComp.form.getRawValue().lines).toEqual([
      { workspace_product_id: 'prod-1', quantity: '25' },
    ]);
    expect(editComp.form.controls.supplierIds.value).toEqual(['sup-1']);
    expect(editComp.form.controls.tenantTerms.value).toBe('Net 30 delivery');

    const dateVal = editComp.form.controls.neededByDate.value;
    expect(dateVal?.getFullYear()).toBe(2026);
    expect(dateVal?.getMonth()).toBe(10); // November is 10 in 0-indexed local month
    expect(dateVal?.getDate()).toBe(15);

    const heading = (editFixture.nativeElement as HTMLElement).querySelector('h2');
    expect(heading?.textContent).toContain('Edit RFQ draft');

    editComp.onSave();
    expect(rfqApiSpy.updateRfq).toHaveBeenCalledWith('rfq-edit-1', {
      lines: [{ workspace_product_id: 'prod-1', quantity: '25' }],
      recipient_supplier_ids: ['sup-1'],
      needed_by_date: '2026-11-15',
      tenant_terms: 'Net 30 delivery',
    });
    expect(snackBarSpy.open).toHaveBeenCalledWith('Draft saved', 'Close', { duration: 4000 });
  });

  it('shows non-draft message and hides editable form when RFQ is not a draft', () => {
    routeId = 'rfq-sent-1';
    const sentDetail: RfqDetail = {
      rfq: {
        id: 'rfq-sent-1',
        tenant_id: 't-1',
        created_by_membership_id: 'm-1',
        status: 'sent',
        needed_by_date: '2026-11-15',
        tenant_terms: null,
        idempotency_key: 'k-1',
        created_at: '2026-10-01T00:00:00Z',
      },
      lines: [],
      recipients: [],
    };
    rfqApiSpy.getRfq.and.returnValue(of(sentDetail));

    const sentFixture = TestBed.createComponent(RfqCreateComponent);
    sentFixture.detectChanges();

    const el = sentFixture.nativeElement as HTMLElement;
    const notice = el.querySelector('[data-testid="rfq-not-draft-notice"]');
    expect(notice).not.toBeNull();
    expect(notice?.textContent).toContain('Only draft RFQs can be edited');
    expect(el.querySelector('form')).toBeNull();
  });

  it('sends the picked local calendar date and uses the fallback for an unknown error code', () => {
    rfqApiSpy.createRfq.and.returnValue(
      throwError(
        () =>
          new HttpErrorResponse({
            status: 422,
            error: { code: 'invalid_date', message: 'Invalid needed-by date' },
          }),
      ),
    );
    component.form.patchValue({
      lines: [{ workspace_product_id: 'prod-1', quantity: '10' }],
      supplierIds: ['sup-1'],
      neededByDate: new Date(2026, 9, 20),
    });
    component.onSave();
    expect(rfqApiSpy.createRfq).toHaveBeenCalledWith(
      jasmine.objectContaining({ needed_by_date: '2026-10-20' }),
    );
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alert"]')?.textContent).toContain(
      'SAVE FALLBACK',
    );
    expect(fixture.nativeElement.querySelector('[role="alert"]')?.textContent).not.toContain(
      'Invalid needed-by date',
    );
  });

  it('translates validation errors and known field labels', () => {
    rfqApiSpy.createRfq.and.returnValue(
      throwError(
        () =>
          new HttpErrorResponse({
            status: 422,
            error: {
              code: 'validation.invalid_request',
              message: 'Request validation failed.',
              details: [{ loc: ['body', 'needed_by_date'], msg: 'Invalid date', type: 'date_parsing' }],
            },
          }),
      ),
    );
    component.form.patchValue({
      lines: [{ workspace_product_id: 'prod-1', quantity: '10' }],
      supplierIds: ['sup-1'],
      neededByDate: new Date(2026, 9, 20),
    });

    component.onSave();
    fixture.detectChanges();

    const alert = fixture.nativeElement.querySelector('[role="alert"]') as HTMLElement;
    expect(alert.textContent).toContain('Please check the following RFQ fields:');
    expect(alert.textContent).toContain('Needed By Date');
    expect(alert.textContent).not.toContain('Request validation failed.');
  });

  it('shows translated not-found text instead of the server message', () => {
    rfqApiSpy.createRfq.and.returnValue(
      throwError(
        () =>
          new HttpErrorResponse({
            status: 404,
            error: { code: 'not_found', message: 'Resource was not found.' },
          }),
      ),
    );
    component.form.patchValue({
      lines: [{ workspace_product_id: 'prod-1', quantity: '10' }],
      supplierIds: ['sup-1'],
      neededByDate: new Date(2026, 9, 20),
    });
    component.onSave();
    fixture.detectChanges();

    const alert = fixture.nativeElement.querySelector('[role="alert"]') as HTMLElement;
    expect(alert.textContent).toContain('The requested RFQ resource could not be found.');
    expect(alert.textContent).not.toContain('Resource was not found.');
  });

  it('uses the save fallback for an unknown server code', () => {
    rfqApiSpy.createRfq.and.returnValue(
      throwError(
        () =>
          new HttpErrorResponse({
            status: 400,
            error: { code: 'unknown.code', message: 'Untrusted server detail' },
          }),
      ),
    );
    component.form.patchValue({
      lines: [{ workspace_product_id: 'prod-1', quantity: '10' }],
      supplierIds: ['sup-1'],
      neededByDate: new Date(2026, 9, 20),
    });
    component.onSave();
    fixture.detectChanges();

    const alert = fixture.nativeElement.querySelector('[role="alert"]') as HTMLElement;
    expect(alert.textContent).toContain('SAVE FALLBACK');
    expect(alert.textContent).not.toContain('Untrusted server detail');
  });
});
