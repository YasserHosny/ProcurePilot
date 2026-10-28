import { ComponentFixture, TestBed } from '@angular/core/testing';
import { RfqCreateComponent } from './create.component';
import { RfqApi, Rfq, RfqDetail } from '../rfq-api';
import { ApiService } from '../../../core/api/api.service';
import { provideHttpClient, HttpErrorResponse, withXhr } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ActivatedRoute, Router, provideRouter } from '@angular/router';
import { MatSnackBar } from '@angular/material/snack-bar';
import { of, throwError } from 'rxjs';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
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
  let fromId: string | null;

  beforeEach(async () => {
    routeId = null;
    fromId = null;
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
      imports: [RfqCreateComponent],
      providers: [
        provideTranslateService(),
        provideHttpClient(withXhr()),
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
              queryParamMap: {
                get: (key: string) => (key === 'from' ? fromId : null),
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
            productRequired: 'Select a product from the catalogue.',
            sentSuccess: 'RFQ sent. Suppliers emailed: {{count}}',
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


  // Finding 40: typing 22/10/2026 used to give 02/10/2026 -- the first keystroke synced the
  // adapter's locale, and Material reformats the input on every locale change, wiping the "2".
  for (const [lang, typed] of [['en', '22/10/2026'], ['ar', '22/10/2026'], ['ar', '٢٢/١٠/٢٠٢٦']]) {
    it(`keeps a day-first date typed key by key (${lang}, ${typed})`, () => {
      // Open the form with the workspace already in this language, as on hosted.
      fixture.destroy();
      translate.use(lang);
      fixture = TestBed.createComponent(RfqCreateComponent);
      component = fixture.componentInstance;
      fixture.detectChanges();
      const input = fixture.nativeElement.querySelector(
        'input[formcontrolname="neededByDate"]',
      ) as HTMLInputElement;
      for (const key of typed) {
        input.value += key;
        input.dispatchEvent(new Event('input'));
        fixture.detectChanges();
      }
      input.dispatchEvent(new Event('blur'));
      fixture.detectChanges();

      const value = component.form.controls.neededByDate.value;
      expect([value?.getFullYear(), value?.getMonth(), value?.getDate()]).toEqual([2026, 9, 22]);
      expect(input.value).toBe('22/10/2026');
    });
  }

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
        recipients: [{ id: 'rec-1', status: 'sent' }, { id: 'rec-2', status: 'sent' }] as never[],
      }),
    );

    component.onSend();
    expect(rfqApiSpy.sendRfq).toHaveBeenCalledWith('rfq-1');
    expect(snackBarSpy.open).toHaveBeenCalledWith('RFQ sent. Suppliers emailed: 2', 'Close', {
      duration: 5000,
    });
    expect(router.navigate).toHaveBeenCalledWith(['/rfq/history']);
  });

  it('stays on the page and reports partial delivery', () => {
    component.rfqId.set('rfq-1');
    rfqApiSpy.sendRfq.and.returnValue(of({
      rfq: { id: 'rfq-1', status: 'sent' } as Rfq,
      recipients: [{ status: 'sent' }, { status: 'failed' }] as never[],
    }));
    component.onSend();
    expect(snackBarSpy.open).toHaveBeenCalledWith(jasmine.stringMatching('rfq.create.sentPartial|Sent to'), jasmine.any(String), jasmine.any(Object));
    expect(router.navigate).not.toHaveBeenCalled();
  });

  it('stays on the page and reports no delivery', () => {
    component.rfqId.set('rfq-1');
    rfqApiSpy.sendRfq.and.returnValue(of({
      rfq: { id: 'rfq-1', status: 'draft' } as Rfq,
      recipients: [{ status: 'failed' }] as never[],
    }));
    component.onSend();
    expect(snackBarSpy.open).toHaveBeenCalledWith(jasmine.stringMatching('rfq.create.sentNone|No suppliers'), jasmine.any(String), jasmine.any(Object));
    expect(router.navigate).not.toHaveBeenCalled();
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

  it('edit mode with line whose product id is not in products response clears display, marks line invalid, and renders error', async () => {
    routeId = 'rfq-edit-inactive';
    const editDetailWithInactive: RfqDetail = {
      rfq: {
        id: 'rfq-edit-inactive',
        tenant_id: 't-1',
        created_by_membership_id: 'm-1',
        status: 'draft',
        needed_by_date: '2026-11-15',
        tenant_terms: 'Some terms',
        idempotency_key: 'edit-key',
        created_at: '2026-10-01T00:00:00Z',
      },
      lines: [
        {
          id: 'l-edit-inactive',
          tenant_id: 't-1',
          rfq_id: 'rfq-edit-inactive',
          workspace_product_id: 'prod-inactive-uuid',
          quantity: '15',
          created_at: '2026-10-01T00:00:00Z',
        },
      ],
      recipients: [],
    };
    rfqApiSpy.getRfq.and.returnValue(of(editDetailWithInactive));

    const editFixture = TestBed.createComponent(RfqCreateComponent);
    const editComp = editFixture.componentInstance;
    editFixture.detectChanges();
    await editFixture.whenStable();
    editFixture.detectChanges();

    const lineControl = editComp.linesFormArray.at(0).get('workspace_product_id');
    expect(lineControl?.value).toBe('prod-inactive-uuid');
    expect(lineControl?.invalid).toBeTrue();
    expect(lineControl?.hasError('invalidProduct')).toBeTrue();
    expect(lineControl?.touched).toBeTrue();

    const productInput = editFixture.nativeElement.querySelector(
      'input[formcontrolname="workspace_product_id"]',
    ) as HTMLInputElement;
    expect(productInput.value).toBe('');

    const matError = editFixture.nativeElement.querySelector('mat-error');
    expect(matError).not.toBeNull();
    expect(matError?.textContent?.trim()).toBe('Select a product from the catalogue.');
  });

  it('paginates active products across multiple pages: validates page-2 product in edit mode, displays label, and filters by picker', async () => {
    routeId = 'rfq-edit-page-2';
    const page1Product: Product = {
      id: 'prod-p1',
      tenant_name: 'Product Page 1',
      variant: null,
    } as Product;
    const page2Product: Product = {
      id: 'prod-p2',
      tenant_name: 'Product Page 2',
      variant: 'Special Variant',
    } as Product;

    apiSpy.products.and.callFake((params?: { cursor?: string; limit?: number; status?: 'active' | 'archived' | 'all'; q?: string }) => {
      if (params?.cursor === 'c2') {
        return of({ items: [page2Product], next_cursor: null });
      }
      return of({ items: [page1Product], next_cursor: 'c2' });
    });
    apiSpy.products.calls.reset();

    const editDetailWithPage2: RfqDetail = {
      rfq: {
        id: 'rfq-edit-page-2',
        tenant_id: 't-1',
        created_by_membership_id: 'm-1',
        status: 'draft',
        needed_by_date: '2026-11-15',
        tenant_terms: 'Page 2 terms',
        idempotency_key: 'edit-key-p2',
        created_at: '2026-10-01T00:00:00Z',
      },
      lines: [
        {
          id: 'l-edit-page-2',
          tenant_id: 't-1',
          rfq_id: 'rfq-edit-page-2',
          workspace_product_id: 'prod-p2',
          quantity: '5',
          created_at: '2026-10-01T00:00:00Z',
        },
      ],
      recipients: [],
    };
    rfqApiSpy.getRfq.and.returnValue(of(editDetailWithPage2));

    const editFixture = TestBed.createComponent(RfqCreateComponent);
    const editComp = editFixture.componentInstance;
    editFixture.detectChanges();
    await editFixture.whenStable();
    editFixture.detectChanges();

    expect(apiSpy.products).toHaveBeenCalledTimes(2);
    expect(apiSpy.products.calls.argsFor(0)[0]).toEqual({ limit: 100, status: 'active' });
    expect(apiSpy.products.calls.argsFor(1)[0]).toEqual({ limit: 100, status: 'active', cursor: 'c2' });

    const lineControl = editComp.linesFormArray.at(0).get('workspace_product_id');
    expect(lineControl?.value).toBe('prod-p2');
    expect(lineControl?.valid).toBeTrue();
    expect(lineControl?.hasError('invalidProduct')).toBeFalse();

    const productInput = editFixture.nativeElement.querySelector(
      'input[formcontrolname="workspace_product_id"]',
    ) as HTMLInputElement;
    expect(productInput.value).toBe(editComp.productLabel(page2Product));
    expect(editComp.displayProduct('prod-p2')).toBe(editComp.productLabel(page2Product));

    const filterResults = editComp.getFilteredProducts('Page 2');
    expect(filterResults.some((p) => p.id === 'prod-p2')).toBeTrue();
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

  describe('Product autocomplete and Arabic normalisation (R5)', () => {
    beforeEach(() => {
      component.products.set([
        { id: 'p-rice', tenant_name: 'أرز بسمتي', variant: '5 كجم' } as Product,
        { id: 'p-sugar', tenant_name: 'سكر أبيض ناعم 10 كجم', variant: null } as Product,
        { id: 'p-milk', tenant_name: 'Fresh Milk', variant: 'Whole 2L' } as Product,
      ]);
      fixture.detectChanges();
    });

    it('filters products anywhere in tenant_name and variant with Arabic-aware normalisation', () => {
      // أرز بسمتي found by ارز
      const riceMatches = component.getFilteredProducts('ارز');
      expect(riceMatches.some((p) => p.id === 'p-rice')).toBeTrue();

      // سكر found inside سكر أبيض ناعم 10 كجم
      const sugarMatches = component.getFilteredProducts('سكر');
      expect(sugarMatches.some((p) => p.id === 'p-sugar')).toBeTrue();

      // variant match
      const milkMatches = component.getFilteredProducts('whole');
      expect(milkMatches.some((p) => p.id === 'p-milk')).toBeTrue();

      // empty / non-matching
      const emptyMatches = component.getFilteredProducts('منتج_غير_موجود');
      expect(emptyMatches.length).toBe(0);
    });

    it('formats product label via displayProduct', () => {
      expect(component.displayProduct('p-rice')).toBe('أرز بسمتي (5 كجم)');
      expect(component.displayProduct('p-sugar')).toBe('سكر أبيض ناعم 10 كجم');
      expect(component.displayProduct('unknown-uuid')).toBe('');
      expect(component.displayProduct('')).toBe('');
    });

    it('marks workspace_product_id control invalid (required) when typed text is not a picked product', () => {
      const line = component.linesFormArray.at(0);
      line.get('workspace_product_id')?.setValue('invalid-typed-text');
      line.get('workspace_product_id')?.updateValueAndValidity();
      expect(line.get('workspace_product_id')?.valid).toBeFalse();
      expect(line.get('workspace_product_id')?.hasError('required')).toBeTrue();

      // valid product id
      line.get('workspace_product_id')?.setValue('p-rice');
      line.get('workspace_product_id')?.updateValueAndValidity();
      expect(line.get('workspace_product_id')?.valid).toBeTrue();
    });
  });

  describe('Focus moves to Quantity after product picked (R1)', () => {
    it('moves focus to the quantity input when onProductSelected is called', () => {
      const inputs = component.quantityInputs();
      expect(inputs.length).toBeGreaterThan(0);
      const focusSpy = spyOn(inputs[0].nativeElement, 'focus').and.callThrough();

      component.onProductSelected(0);
      expect(focusSpy).toHaveBeenCalled();
    });
  });

  describe('Supplier email in options and trigger shows names only (R4)', () => {
    it('shows supplier email in picker option and only names in trigger', () => {
      component.suppliers.set([
        { id: 's-1', name: 'Al-Ahram Supplies', contact_email: 'sales@ahram.test' } as Supplier,
        { id: 's-2', name: 'Nile Traders', contact_email: 'nile@traders.test' } as Supplier,
      ]);
      component.form.controls.supplierIds.setValue(['s-1', 's-2']);
      fixture.detectChanges();

      expect(component.selectedSupplierNames()).toBe('Al-Ahram Supplies, Nile Traders');

      const compiled = fixture.nativeElement as HTMLElement;
      const select = compiled.querySelector('mat-select[formControlName="supplierIds"]');
      expect(select).toBeTruthy();
    });
  });

  describe('Arabic free text dir="auto" (R3)', () => {
    it('renders tenantTerms textarea and product input with dir="auto"', () => {
      const textarea = fixture.nativeElement.querySelector(
        'textarea[formControlName="tenantTerms"]',
      ) as HTMLTextAreaElement;
      expect(textarea).toBeTruthy();
      expect(textarea.getAttribute('dir')).toBe('auto');

      const productInput = fixture.nativeElement.querySelector(
        'input[formControlName="workspace_product_id"]',
      ) as HTMLInputElement;
      expect(productInput).toBeTruthy();
      expect(productInput.getAttribute('dir')).toBe('auto');
    });
  });

  describe('Duplicate RFQ (create side)', () => {
    const mockSourceDetail: RfqDetail = {
      rfq: {
        id: 'rfq-src-1',
        tenant_id: 't-1',
        created_by_membership_id: 'm-1',
        status: 'sent',
        needed_by_date: '2026-09-01',
        tenant_terms: 'Original duplicate terms',
        idempotency_key: 'src-key',
        created_at: '2026-09-01T00:00:00Z',
      },
      lines: [
        {
          id: 'l-1',
          tenant_id: 't-1',
          rfq_id: 'rfq-src-1',
          workspace_product_id: 'prod-1',
          quantity: '50.000000',
          created_at: '2026-09-01T00:00:00Z',
        },
      ],
      recipients: [
        {
          id: 'r-1',
          tenant_id: 't-1',
          rfq_id: 'rfq-src-1',
          supplier_id: 'sup-1',
          status: 'sent',
          outbound_message_id: null,
          sent_at: null,
          created_at: '2026-09-01T00:00:00Z',
        },
        {
          id: 'r-2',
          tenant_id: 't-1',
          rfq_id: 'rfq-src-1',
          supplier_id: 'sup-inactive',
          status: 'sent',
          outbound_message_id: null,
          sent_at: null,
          created_at: '2026-09-01T00:00:00Z',
        },
      ],
    };

    it('pre-fills new draft from earlier RFQ with lines, active suppliers, terms, and leaves neededByDate empty', () => {
      fromId = 'rfq-src-1';
      rfqApiSpy.getRfq.and.returnValue(of(mockSourceDetail));

      const dupFixture = TestBed.createComponent(RfqCreateComponent);
      const dupComp = dupFixture.componentInstance;
      dupFixture.detectChanges();

      expect(rfqApiSpy.getRfq).toHaveBeenCalledWith('rfq-src-1');
      expect(dupComp.isEditMode()).toBeFalse();
      expect(dupComp.rfqId()).toBeNull();
      expect(dupComp.isDuplicated()).toBeTrue();

      // Lines prefilled in order and trimmed
      expect(dupComp.form.getRawValue().lines).toEqual([
        { workspace_product_id: 'prod-1', quantity: '50' },
      ]);
      // Only active supplier with email (sup-1), sup-inactive filtered out
      expect(dupComp.form.controls.supplierIds.value).toEqual(['sup-1']);
      // Terms prefilled
      expect(dupComp.form.controls.tenantTerms.value).toBe('Original duplicate terms');
      // Needed by date left empty
      expect(dupComp.form.controls.neededByDate.value).toBeNull();

      // Notice rendered
      const notice = dupFixture.nativeElement.querySelector('.duplicate-notice');
      expect(notice).toBeTruthy();
    });

    it('saving a duplicated RFQ calls createRfq, not updateRfq', () => {
      fromId = 'rfq-src-1';
      rfqApiSpy.getRfq.and.returnValue(of(mockSourceDetail));
      rfqApiSpy.createRfq.and.returnValue(
        of({
          rfq: { id: 'rfq-new-dup', status: 'draft' } as Rfq,
          lines: [],
          recipients: [],
          rejected_recipients: [],
        }),
      );

      const dupFixture = TestBed.createComponent(RfqCreateComponent);
      const dupComp = dupFixture.componentInstance;
      dupFixture.detectChanges();

      dupComp.form.controls.neededByDate.setValue(new Date(2026, 11, 25));
      dupFixture.detectChanges();

      dupComp.onSave();

      expect(rfqApiSpy.createRfq).toHaveBeenCalled();
      expect(rfqApiSpy.updateRfq).not.toHaveBeenCalled();
      expect(dupComp.rfqId()).toBe('rfq-new-dup');
    });

    it('shows error card and keeps empty form when loading source RFQ fails in duplicate mode', () => {
      fromId = 'rfq-src-missing';
      rfqApiSpy.getRfq.and.returnValue(
        throwError(
          () =>
            new HttpErrorResponse({
              status: 404,
              error: { code: 'not_found', message: 'Not found' },
            }),
        ),
      );

      const dupFixture = TestBed.createComponent(RfqCreateComponent);
      const dupComp = dupFixture.componentInstance;
      dupFixture.detectChanges();

      expect(dupComp.errorMessage()).toBeTruthy();
      expect(dupComp.linesFormArray.length).toBe(1);
      expect(dupComp.form.controls.tenantTerms.value).toBe('');
      expect(dupFixture.nativeElement.querySelector('.form-card.loading-card')).toBeNull();
    });

    it('duplicate with source line whose product id is not in products response clears display, marks line invalid, and renders error', async () => {
      fromId = 'rfq-src-inactive-prod';
      const detailWithInactiveProd: RfqDetail = {
        rfq: {
          id: 'rfq-src-inactive-prod',
          tenant_id: 't-1',
          created_by_membership_id: 'm-1',
          status: 'sent',
          needed_by_date: '2026-09-01',
          tenant_terms: 'Original duplicate terms',
          idempotency_key: 'src-key-2',
          created_at: '2026-09-01T00:00:00Z',
        },
        lines: [
          {
            id: 'l-inactive',
            tenant_id: 't-1',
            rfq_id: 'rfq-src-inactive-prod',
            workspace_product_id: 'prod-inactive-uuid',
            quantity: '10',
            created_at: '2026-09-01T00:00:00Z',
          },
        ],
        recipients: [],
      };
      rfqApiSpy.getRfq.and.returnValue(of(detailWithInactiveProd));

      const dupFixture = TestBed.createComponent(RfqCreateComponent);
      const dupComp = dupFixture.componentInstance;
      dupFixture.detectChanges();
      await dupFixture.whenStable();
      dupFixture.detectChanges();

      const lineControl = dupComp.linesFormArray.at(0).get('workspace_product_id');
      expect(lineControl?.value).toBe('prod-inactive-uuid');
      expect(lineControl?.invalid).toBeTrue();
      expect(lineControl?.hasError('invalidProduct')).toBeTrue();
      expect(lineControl?.touched).toBeTrue();

      const productInput = dupFixture.nativeElement.querySelector(
        'input[formcontrolname="workspace_product_id"]',
      ) as HTMLInputElement;
      expect(productInput.value).toBe('');

      const matError = dupFixture.nativeElement.querySelector('mat-error');
      expect(matError).not.toBeNull();
      expect(matError?.textContent?.trim()).toBe('Select a product from the catalogue.');
    });
  });
});
