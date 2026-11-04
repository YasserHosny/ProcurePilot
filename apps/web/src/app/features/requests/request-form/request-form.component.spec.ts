import { HttpErrorResponse } from '@angular/common/http';
import type { ComponentFixture } from '@angular/core/testing';
import { TestBed, fakeAsync, tick } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { MatSnackBar } from '@angular/material/snack-bar';
import { ActivatedRoute, Router, RouterLink, convertToParamMap, provideRouter } from '@angular/router';
import { By } from '@angular/platform-browser';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { BehaviorSubject, of, Subject, throwError } from 'rxjs';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import arCatalog from '../../../../../../../packages/i18n/ar.json';
import { ApiService } from '../../../core/api/api.service';
import type { BranchList, CostCentre, Member, Product, PurchaseRequest } from '../../../core/api/models';
import { OrganisationApiService } from '../../settings/organisation-api';
import { RequestsApiService } from '../requests-api';
import { OrdersApiService, type RequestAllocation } from '../../orders/orders-api';
import { RequestFormComponent, fetchAllPages } from './request-form.component';
import { provideAppDateAdapter } from '../../../core/i18n/date-adapter';

const mockRequest: PurchaseRequest = {
  id: 'r1',
  branch_id: 'b1',
  cost_centre_id: 'cc1',
  requested_by_membership_id: 'm1',
  required_by_date: '2026-09-15',
  status: 'draft',
  lines: [
    {
      quoted_prices_include_vat: false,
      quoted_vat_rate: null,
      quoted_net_unit_price: null,
      id: 'l1',
      workspace_product_id: 'wp1',
      quantity: '10.000000',
      estimated_unit_price: { amount: '25.5000', currency: 'GBP' },
      estimated_unit_price_source_landed_cost_id: 'lc1',
    },
  ],
  has_incomplete_estimate: false,
  created_at: '2026-08-23T00:00:00Z',
};

describe('RequestFormComponent — create mode (T017)', () => {
  let component: RequestFormComponent;
  let fixture: ComponentFixture<RequestFormComponent>;
  let requestsApi: jasmine.SpyObj<RequestsApiService>;
  let ordersApi: jasmine.SpyObj<OrdersApiService>;
  let organisationApi: jasmine.SpyObj<OrganisationApiService>;
  let api: jasmine.SpyObj<ApiService>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;
  let routerSpy: jasmine.SpyObj<Router>;
  let dialogSpy: jasmine.SpyObj<MatDialog>;
  let routeParams: BehaviorSubject<ReturnType<typeof convertToParamMap>>;

  beforeEach(async () => {
    routeParams = new BehaviorSubject(convertToParamMap({}));
    requestsApi = jasmine.createSpyObj('RequestsApiService', [
      'createRequest',
      'updateRequest',
      'submitRequest',
      'submitGroup',
      'withdrawRequest',
      'withdrawGroup',
      'getRequest',
    ]);
    ordersApi = jasmine.createSpyObj('OrdersApiService', ['getAllocations']);
    ordersApi.getAllocations.and.returnValue(
      of({
        source_request_id: 'r1',
        lines: [
          {
            source_request_line_id: 'l1',
            requested_quantity: '10.000000',
            allocated_quantity: '0',
            remaining_quantity: '10.000000',
          },
        ],
        orders: [],
      }),
    );
    organisationApi = jasmine.createSpyObj('OrganisationApiService', [
      'listBranches',
      'listCostCentres',
    ]);
    api = jasmine.createSpyObj('ApiService', ['members', 'products']);
    snackBarSpy = jasmine.createSpyObj('MatSnackBar', ['open']);
    routerSpy = jasmine.createSpyObj('Router', ['navigate']);
    dialogSpy = jasmine.createSpyObj('MatDialog', ['open']);
    dialogSpy.open.and.returnValue({ afterClosed: () => of(true) } as ReturnType<MatDialog['open']>);

    organisationApi.listBranches.and.returnValue(of({ items: [], next_cursor: null }));
    organisationApi.listCostCentres.and.returnValue(of({ items: [], next_cursor: null }));
    api.members.and.returnValue(of({ items: [], next_cursor: null }));
    api.products.and.returnValue(of({ items: [], next_cursor: null }));

    await TestBed.configureTestingModule({
      imports: [RequestFormComponent],
      providers: [
        provideTranslateService(),
        provideRouter([]),
        { provide: RequestsApiService, useValue: requestsApi },
        { provide: OrdersApiService, useValue: ordersApi },
        { provide: OrganisationApiService, useValue: organisationApi },
        { provide: ApiService, useValue: api },
        {
          provide: ActivatedRoute,
          useValue: { paramMap: routeParams, queryParamMap: of(convertToParamMap({})) },
        },
      ],
    })
      .overrideComponent(RequestFormComponent, {
        set: {
          providers: [
            provideAppDateAdapter(),
            { provide: MatSnackBar, useValue: snackBarSpy },
            { provide: Router, useValue: routerSpy },
            { provide: MatDialog, useValue: dialogSpy },
          ],
        },
      })
      .compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(RequestFormComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  describe('PPS-167 self approval marker', () => {
    for (const locale of ['en', 'ar']) {
      for (const status of ['pending', 'approved', 'rejected'] as const) {
        for (const flag of [true, false, undefined]) {
          it(`renders the marker for ${locale}, ${status}, self_approval=${flag}`, () => {
            const translate = TestBed.inject(TranslateService);
            translate.setTranslation('ar', arCatalog);
            translate.use(locale);
            const step = {
              id: 'step-own', assigned_membership_id: 'm1',
              source: 'owner_fallback' as const, status,
              ...(flag === undefined ? {} : { self_approval: flag }),
            };
            requestsApi.getRequest.and.returnValue(of({
              ...mockRequest, status: 'submitted', approval_step: step,
            }));
            routeParams.next(convertToParamMap({ id: 'r1' }));
            fixture.detectChanges();
            const marker = (fixture.nativeElement as HTMLElement).querySelector('.self-approval');
            if (flag !== true) {
              expect(marker).toBeNull();
              return;
            }
            expect(marker).not.toBeNull();
            expect(marker?.querySelector('mat-icon')?.getAttribute('aria-hidden')).toBe('true');
            if (status === 'pending') {
              expect(marker?.textContent).toContain(locale === 'ar'
                ? 'مُسند إلى مقدّم الطلب'
                : 'Assigned to the requester');
              expect(marker?.textContent).not.toContain(locale === 'ar' ? 'المالك الوحيد' : 'the only owner');
              expect(marker?.textContent).not.toContain('Decided by the person');
            } else {
              const approvedLabel = locale === 'ar' ? 'اعتماد ذاتي' : 'Self-approved';
              const rejectedLabel = locale === 'ar' ? 'رفض ذاتي' : 'Self-rejected';
              expect(marker?.textContent).toContain(status === 'approved' ? approvedLabel : rejectedLabel);
              expect(marker?.textContent).not.toContain(status === 'approved' ? rejectedLabel : approvedLabel);
              expect(marker?.textContent).toContain(locale === 'ar'
                ? 'اتخذ القرار الشخص الذي قدّم الطلب'
                : 'Decided by the person who submitted it');
              expect(marker?.textContent).not.toContain('Assigned to the requester');
            }
          });
        }
      }
    }
  });

  describe('PPS-193 pack hints and Save and submit', () => {
    const product: Product = {
      id: 'wp1', tenant_name: 'Flour', canonical_name: 'Flour', base_unit: 'kg',
      pack: { pack_count: 2, unit_size: '3.000000', base_quantity: '10.000000' },
      status: 'active', created_at: '',
    };

    const matchingDraft: PurchaseRequest = {
      ...mockRequest, cost_centre_id: null, required_by_date: '2099-01-01',
      lines: [{ ...mockRequest.lines[0], quantity: '25.000000', note: '' }],
    };

    function fillForm(): void {
      component.form.patchValue({ branch_id: 'b1', required_by_date: '2099-01-01' });
      component.lines.at(0).patchValue({ workspace_product_id: 'wp1', quantity: '25' });
    }

    function hint(): string | null {
      fixture.detectChanges();
      return fixture.nativeElement.querySelector('.line-quantity mat-hint')?.textContent ?? null;
    }

    it('shows pack size/unit on selection and updates on product changes with fallback pack arithmetic', () => {
      component.products.set([product, {
        ...product, id: 'wp2', base_unit: 'l', pack: { pack_count: 3, unit_size: '2.500000' },
      }]);
      expect(hint()).toBeNull();
      component.lines.at(0).controls.workspace_product_id.setValue('wp1');
      expect(hint()).toContain('1 pack = 10 kg');
      component.lines.at(0).controls.workspace_product_id.setValue('wp2');
      expect(hint()).toContain('1 pack = 7.5 l');
    });

    it('updates the trimmed total for valid quantities and omits it for empty, zero and invalid quantities', () => {
      component.products.set([product]);
      fillForm();
      expect(hint()).toContain('Total 250 kg');
      component.lines.at(0).controls.quantity.setValue('1.25');
      expect(hint()).toContain('Total 12.5 kg');
      for (const quantity of ['', '0', 'invalid', '-1', '1.1234567']) {
        component.lines.at(0).controls.quantity.setValue(quantity);
        expect(hint()).not.toContain('Total');
      }
    });

    it('omits the hint for a product without pack data', () => {
      component.products.set([{ ...product, pack: undefined } as unknown as Product]);
      fillForm();
      expect(hint()).toBeNull();
    });

    it('shows the translated packs suffix only on editable quantity inputs', () => {
      fixture.detectChanges();
      expect(fixture.nativeElement.querySelector('.line-quantity [matSuffix]')?.textContent).toContain('packs');
      component.form.disable();
      fixture.detectChanges();
      expect(fixture.nativeElement.querySelector('.line-quantity [matSuffix]')).toBeNull();
    });

    it('preserves the hint and raw total for localized read-only quantities', () => {
      component.products.set([product]);
      requestsApi.getRequest.and.returnValue(of({
        ...mockRequest, status: 'submitted', lines: [{ ...mockRequest.lines[0], quantity: '1250.000000' }],
      }));
      routeParams.next(convertToParamMap({ id: 'r1' }));
      expect(component.form.disabled).toBeTrue();
      expect(hint()).toContain('1 pack = 10 kg');
      expect(hint()).toContain('Total 12,500 kg');
      expect(fixture.nativeElement.querySelector('.save-and-submit-btn')).toBeNull();
    });

    it('uses the saved pack snapshot for a read-only request after the catalogue pack changes', () => {
      component.products.set([product]);
      requestsApi.getRequest.and.returnValue(of({
        ...mockRequest, status: 'submitted',
        lines: [{ ...mockRequest.lines[0], quantity: '3', pack_base_quantity: '2.500000', base_unit: 'kg' }],
      }));
      routeParams.next(convertToParamMap({ id: 'r1' }));
      expect(hint()).toContain('1 pack = 2.5 kg');
      expect(hint()).toContain('Total 7.5 kg');
      // The saved unit and pack remain available even without a catalogue product.
      component.products.set([]);
      expect(hint()).toContain('1 pack = 2.5 kg');
    });

    it('uses the current catalogue pack for an editable draft with a saved snapshot', () => {
      component.products.set([product]);
      requestsApi.getRequest.and.returnValue(of({
        ...mockRequest, lines: [{ ...mockRequest.lines[0], pack_base_quantity: '2.500000' }],
      }));
      routeParams.next(convertToParamMap({ id: 'r1' }));
      expect(component.form.enabled).toBeTrue();
      expect(hint()).toContain('1 pack = 10 kg');
      expect(hint()).toContain('Total 100 kg');
    });

    for (const size of ['0.001', '0.125']) {
      it(`preserves exact pack size ${size} in the hint`, () => {
        component.products.set([{ ...product, pack: { ...product.pack, base_quantity: size } }]);
        fillForm();
        expect(hint()).toContain(`1 pack = ${size} kg`);
      });
    }

    it('formats three packs of 0.1 as 0.3 without floating point noise', () => {
      component.products.set([{ ...product, pack: { ...product.pack, base_quantity: '0.1' } }]);
      fillForm();
      component.lines.at(0).controls.quantity.setValue('3');
      expect(hint()).toContain('Total 0.3 kg');
      expect(hint()).not.toContain('0.30000000000000004');
    });

    it('renders Arabic pack copy, totals and the suffix', () => {
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('ar', arCatalog);
      translate.use('ar');
      component.products.set([product]);
      fillForm();
      const text = hint();
      expect(text).toContain('عبوة واحدة = ١٠ kg');
      expect(text).toContain('الإجمالي ٢٥٠ kg');
      expect(fixture.nativeElement.querySelector('.line-quantity [matSuffix]')?.textContent).toContain('عبوات');
    });

    it('marks an invalid form touched, shows and focuses the banner without calling either API', fakeAsync(() => {
      component.saveAndSubmit();
      fixture.detectChanges();
      tick();
      expect(component.form.controls.branch_id.touched).toBeTrue();
      expect(component.errorMessage()).toBeTruthy();
      expect(document.activeElement).toBe(fixture.nativeElement.querySelector('.error-banner'));
      expect(requestsApi.createRequest).not.toHaveBeenCalled();
      expect(requestsApi.submitRequest).not.toHaveBeenCalled();
    }));

    it('creates then submits with distinct stable keys, shows success and navigates without reloading', () => {
      fillForm();
      const created = new Subject<PurchaseRequest>();
      const submitted = new Subject<PurchaseRequest>();
      requestsApi.createRequest.and.returnValue(created);
      requestsApi.submitRequest.and.returnValue(submitted);
      const uuid = spyOn(crypto, 'randomUUID').and.returnValues(
        '11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222',
      );
      component.saveAndSubmit();
      expect(requestsApi.createRequest).toHaveBeenCalledOnceWith({
        branch_id: 'b1', cost_centre_id: null, required_by_date: '2099-01-01',
        lines: [{ workspace_product_id: 'wp1', quantity: '25', note: null }],
      }, '11111111-1111-4111-8111-111111111111');
      expect(requestsApi.submitRequest).not.toHaveBeenCalled();
      created.next(matchingDraft);
      created.complete();
      expect(requestsApi.submitRequest).toHaveBeenCalledOnceWith('r1', '22222222-2222-4222-8222-222222222222');
      submitted.next({ ...mockRequest, status: 'submitted' });
      submitted.complete();
      expect(uuid).toHaveBeenCalledTimes(2);
      expect(snackBarSpy.open).toHaveBeenCalledWith(enCatalog.requests.submitSuccess, undefined, { duration: 3500 });
      expect(routerSpy.navigate).toHaveBeenCalledWith(['/requests', 'r1']);
      const line = component.lines.at(0);
      routeParams.next(convertToParamMap({ id: 'r1' }));
      expect(requestsApi.getRequest).not.toHaveBeenCalled();
      expect(component.lines.at(0)).toBe(line);
      expect(component.existingRequest()?.status).toBe('submitted');
      expect(component.form.disabled).toBeTrue();
      expect(component.isSaving()).toBeFalse();
      expect(component.isSubmitting()).toBeFalse();
    });

    it('keeps create failures on the form with inline errors and reuses the create key on retry', () => {
      fillForm();
      requestsApi.createRequest.and.returnValue(throwError(() => new HttpErrorResponse({
        status: 422, error: { details: [{ field: 'lines[0].quantity', reason: 'quantity_not_positive' }] },
      })));
      component.saveAndSubmit();
      const key = requestsApi.createRequest.calls.mostRecent().args[1];
      expect(key).toBeTruthy();
      expect(component.lines.at(0).controls.quantity.errors?.['server']).toBe('requests.errors.quantity_not_positive');
      expect(requestsApi.submitRequest).not.toHaveBeenCalled();
      expect(routerSpy.navigate).not.toHaveBeenCalled();
      expect(component.existingRequest()).toBeNull();
      expect(component.isSaving()).toBeFalse();
      component.lines.at(0).controls.quantity.setValue('25');
      component.saveAndSubmit();
      expect(requestsApi.createRequest.calls.mostRecent().args[1]).toBe(key);
    });

    it('preserves the draft after submit failure, navigates without reloading and retries without another create', () => {
      fillForm();
      requestsApi.createRequest.and.returnValue(of(matchingDraft));
      requestsApi.submitRequest.and.returnValue(throwError(() => new Error('submit failed')));
      component.saveAndSubmit();
      const key = requestsApi.submitRequest.calls.mostRecent().args[1];
      expect(component.existingRequest()).toEqual(matchingDraft);
      expect(routerSpy.navigate).toHaveBeenCalledWith(['/requests', 'r1']);
      expect(snackBarSpy.open).toHaveBeenCalledWith(enCatalog.requests.form.draftSavedSubmitFailed, undefined, { duration: 3500 });
      const line = component.lines.at(0);
      routeParams.next(convertToParamMap({ id: 'r1' }));
      expect(requestsApi.getRequest).not.toHaveBeenCalled();
      expect(component.lines.at(0)).toBe(line);
      requestsApi.submitRequest.and.returnValue(of({ ...mockRequest, status: 'submitted' }));
      component.saveAndSubmit();
      expect(requestsApi.createRequest).toHaveBeenCalledTimes(1);
      expect(requestsApi.submitRequest.calls.mostRecent().args[1]).toBe(key);
    });

    it('updates an older replay with the edited payload before submitting on retry', () => {
      fillForm();
      requestsApi.createRequest.and.returnValue(throwError(() => new Error('response lost')));
      component.saveAndSubmit();
      const key = requestsApi.createRequest.calls.mostRecent().args[1];
      component.lines.at(0).controls.quantity.setValue('3');
      requestsApi.createRequest.and.returnValue(of(matchingDraft));
      const updated = new Subject<PurchaseRequest>();
      const currentDraft = { ...matchingDraft, lines: [{ ...matchingDraft.lines[0], quantity: '3.000000' }] };
      requestsApi.updateRequest.and.returnValue(updated);
      requestsApi.submitRequest.and.returnValue(throwError(() => new Error('submit failed')));
      component.saveAndSubmit();
      expect(requestsApi.createRequest.calls.mostRecent().args[1]).toBe(key);
      expect(requestsApi.updateRequest).toHaveBeenCalledOnceWith('r1', {
        branch_id: 'b1', cost_centre_id: null, required_by_date: '2099-01-01',
        lines: [{ workspace_product_id: 'wp1', quantity: '3', note: null }],
      });
      expect(requestsApi.submitRequest).not.toHaveBeenCalled();
      updated.next(currentDraft);
      updated.complete();
      expect(requestsApi.submitRequest).toHaveBeenCalledTimes(1);
      expect(requestsApi.updateRequest).toHaveBeenCalledBefore(requestsApi.submitRequest);
      expect(component.existingRequest()).toEqual(currentDraft);
    });

    it('submits a matching replay without updating normalized decimal, date and empty fields', () => {
      fillForm();
      component.form.controls.required_by_date.setValue(new Date(2099, 0, 1));
      requestsApi.createRequest.and.returnValue(of(matchingDraft));
      requestsApi.submitRequest.and.returnValue(of({ ...matchingDraft, status: 'submitted' }));
      component.saveAndSubmit();
      expect(requestsApi.updateRequest).not.toHaveBeenCalled();
      expect(requestsApi.submitRequest).toHaveBeenCalledTimes(1);
    });

    it('keeps the saved draft and navigates with the draft-saved snackbar when replay update fails', () => {
      fillForm();
      component.lines.at(0).controls.quantity.setValue('3');
      requestsApi.createRequest.and.returnValue(of(matchingDraft));
      requestsApi.updateRequest.and.returnValue(throwError(() => new Error('update failed')));
      component.saveAndSubmit();
      expect(requestsApi.updateRequest).toHaveBeenCalledTimes(1);
      expect(requestsApi.submitRequest).not.toHaveBeenCalled();
      expect(component.existingRequest()).toEqual(matchingDraft);
      expect(snackBarSpy.open).toHaveBeenCalledWith(
        enCatalog.requests.form.draftSavedSubmitFailed, undefined, { duration: 3500 },
      );
      expect(routerSpy.navigate).toHaveBeenCalledWith(['/requests', 'r1']);
      expect(component.isSaving()).toBeFalse();
      expect(component.isSubmitting()).toBeFalse();
    });

    for (const [field, replay] of Object.entries({
      branch: { ...matchingDraft, branch_id: 'b2' },
      costCentre: { ...matchingDraft, cost_centre_id: 'cc1' },
      date: { ...matchingDraft, required_by_date: '2099-01-02' },
      lineCount: { ...matchingDraft, lines: [...matchingDraft.lines, matchingDraft.lines[0]] },
      product: { ...matchingDraft, lines: [{ ...matchingDraft.lines[0], workspace_product_id: 'wp2' }] },
      note: { ...matchingDraft, lines: [{ ...matchingDraft.lines[0], note: 'old note' }] },
    })) {
      it(`updates a replay when its ${field} differs from the form`, () => {
        fillForm();
        requestsApi.createRequest.and.returnValue(of(replay));
        requestsApi.updateRequest.and.returnValue(of(matchingDraft));
        requestsApi.submitRequest.and.returnValue(of({ ...matchingDraft, status: 'submitted' }));
        component.saveAndSubmit();
        expect(requestsApi.updateRequest).toHaveBeenCalledTimes(1);
        expect(requestsApi.updateRequest).toHaveBeenCalledBefore(requestsApi.submitRequest);
      });
    }

    it('disables both save buttons during create and submit and ignores repeated clicks', () => {
      fillForm();
      const created = new Subject<PurchaseRequest>();
      const submitted = new Subject<PurchaseRequest>();
      requestsApi.createRequest.and.returnValue(created);
      requestsApi.submitRequest.and.returnValue(submitted);
      component.saveAndSubmit();
      const expectDisabled = (): void => {
        fixture.detectChanges();
        expect(fixture.nativeElement.querySelector('button[type="submit"]').disabled).toBeTrue();
        expect(fixture.nativeElement.querySelector('.save-and-submit-btn').disabled).toBeTrue();
      };
      expectDisabled();
      component.saveAndSubmit();
      component.saveDraft();
      expect(requestsApi.createRequest).toHaveBeenCalledTimes(1);
      created.next(matchingDraft);
      created.complete();
      expectDisabled();
      submitted.next({ ...mockRequest, status: 'submitted' });
      submitted.complete();
      expect(component.isSaving()).toBeFalse();
      expect(component.isSubmitting()).toBeFalse();
    });

    it('disables Save and submit while Save Draft is in flight', () => {
      fillForm();
      const created = new Subject<PurchaseRequest>();
      requestsApi.createRequest.and.returnValue(created);
      component.saveDraft();
      fixture.detectChanges();
      expect(fixture.nativeElement.querySelector('button[type="submit"]').disabled).toBeTrue();
      expect(fixture.nativeElement.querySelector('.save-and-submit-btn').disabled).toBeTrue();
      component.saveAndSubmit();
      expect(requestsApi.createRequest).toHaveBeenCalledTimes(1);
      created.next(matchingDraft);
      created.complete();
    });

    it('hides Save and submit on an existing draft', () => {
      requestsApi.getRequest.and.returnValue(of(mockRequest));
      routeParams.next(convertToParamMap({ id: 'r1' }));
      fixture.detectChanges();
      expect(fixture.nativeElement.querySelector('.save-and-submit-btn')).toBeNull();
      expect(fixture.nativeElement.querySelector('.submit-request-btn')).not.toBeNull();
    });
  });

  it('filters cost centres to the selected branch and keeps tenant-wide centres', () => {
    component.allCostCentres.set([
      { id: 'global', name: 'Global', code: 'G', branch_id: null, is_orphaned: false, is_archived: false, created_at: '' },
      { id: 'b1cc', name: 'Branch 1', code: '1', branch_id: 'b1', is_orphaned: false, is_archived: false, created_at: '' },
      { id: 'b2cc', name: 'Branch 2', code: '2', branch_id: 'b2', is_orphaned: false, is_archived: false, created_at: '' },
    ]);
    component.form.controls.branch_id.setValue('b1');
    expect(component.costCentres().map((centre) => centre.id)).toEqual(['global', 'b1cc']);
    component.form.controls.cost_centre_id.setValue('b1cc');
    component.form.controls.branch_id.setValue('b2');
    expect(component.costCentres().map((centre) => centre.id)).toEqual(['global', 'b2cc']);
    expect(component.form.controls.cost_centre_id.value).toBe('');
  });

  it('should start with one empty line in create mode', () => {
    expect(component.isEditMode()).toBeFalse();
    expect(component.lines.length).toBe(1);
  });

  it('should keep the form gated until branch options finish loading', () => {
    const delayedBranches$ = new Subject<BranchList>();
    organisationApi.listBranches.and.returnValue(delayedBranches$);

    const delayedFixture = TestBed.createComponent(RequestFormComponent);
    const delayedComponent = delayedFixture.componentInstance;
    delayedFixture.detectChanges();

    expect(delayedComponent.isLoading()).toBeTrue();
    expect(delayedFixture.nativeElement.querySelector('.loading-state')).not.toBeNull();
    expect(delayedFixture.nativeElement.querySelector('mat-select')).toBeNull();

    delayedBranches$.next({
      items: [{ id: 'b1', name: 'Main branch', is_active: true, created_at: '2026-01-01T00:00:00Z' }],
      next_cursor: null,
    });
    delayedBranches$.complete();
    delayedFixture.detectChanges();

    expect(delayedComponent.isLoading()).toBeFalse();
    expect(delayedFixture.nativeElement.querySelector('mat-select')).not.toBeNull();
  });

  it('should add and remove lines', () => {
    component.addLine();
    expect(component.lines.length).toBe(2);

    component.removeLine(0);
    expect(component.lines.length).toBe(1);
  });

  it('should save a draft and navigate to the detail', () => {
    requestsApi.createRequest.and.returnValue(of(mockRequest));

    component.form.controls.branch_id.setValue('b1');
    component.form.controls.required_by_date.setValue('2026-09-15');
    component.lines.at(0).controls.workspace_product_id.setValue('wp1');
    component.lines.at(0).controls.quantity.setValue('10');

    component.saveDraft();

    expect(requestsApi.createRequest).toHaveBeenCalledTimes(1);
    expect(component.isSaving()).toBeFalse();
    expect(routerSpy.navigate).toHaveBeenCalledWith(['/requests', 'r1']);
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      'Purchase request saved as a draft.',
      undefined,
      { duration: 3500 },
    );
  });

  it('should not save when form is invalid', () => {
    component.saveDraft();
    expect(requestsApi.createRequest).not.toHaveBeenCalled();
  });

  it('should not save when lines are empty', () => {
    component.removeLine(0);
    component.form.controls.branch_id.setValue('b1');
    component.form.controls.required_by_date.setValue('2026-09-15');

    component.saveDraft();
    expect(requestsApi.createRequest).not.toHaveBeenCalled();
  });

  it('should display an error on API failure', () => {
    const error422 = new HttpErrorResponse({
      status: 422,
      error: { code: 'unprocessable', message: 'Zero lines', trace_id: 'tr_422' },
    });
    requestsApi.createRequest.and.returnValue(throwError(() => error422));

    component.form.controls.branch_id.setValue('b1');
    component.form.controls.required_by_date.setValue('2026-09-15');
    component.lines.at(0).controls.workspace_product_id.setValue('wp1');
    component.lines.at(0).controls.quantity.setValue('5');

    component.saveDraft();

    expect(component.errorMessage()).toBe('Unable to save the purchase request. Please try again.');
    expect(component.isSaving()).toBeFalse();
  });

  it('should cancel and navigate back', () => {
    component.cancel();
    expect(routerSpy.navigate).toHaveBeenCalledWith(['/requests']);
  });
});

describe('RequestFormComponent — edit mode (T017)', () => {
  let component: RequestFormComponent;
  let fixture: ComponentFixture<RequestFormComponent>;
  let requestsApi: jasmine.SpyObj<RequestsApiService>;
  let ordersApi: jasmine.SpyObj<OrdersApiService>;
  let organisationApi: jasmine.SpyObj<OrganisationApiService>;
  let api: jasmine.SpyObj<ApiService>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;
  let routerSpy: jasmine.SpyObj<Router>;
  let dialogSpy: jasmine.SpyObj<MatDialog>;

  beforeEach(async () => {
    requestsApi = jasmine.createSpyObj('RequestsApiService', [
      'createRequest',
      'updateRequest',
      'submitRequest',
      'submitGroup',
      'withdrawRequest',
      'withdrawGroup',
      'getRequest',
    ]);
    ordersApi = jasmine.createSpyObj('OrdersApiService', ['getAllocations']);
    ordersApi.getAllocations.and.returnValue(
      of({
        source_request_id: 'r1',
        lines: [
          {
            source_request_line_id: 'l1',
            requested_quantity: '10.000000',
            allocated_quantity: '0',
            remaining_quantity: '10.000000',
          },
        ],
        orders: [],
      }),
    );
    organisationApi = jasmine.createSpyObj('OrganisationApiService', [
      'listBranches',
      'listCostCentres',
    ]);
    api = jasmine.createSpyObj('ApiService', ['members', 'products']);
    snackBarSpy = jasmine.createSpyObj('MatSnackBar', ['open']);
    routerSpy = jasmine.createSpyObj('Router', ['navigate']);
    dialogSpy = jasmine.createSpyObj('MatDialog', ['open']);
    dialogSpy.open.and.returnValue({ afterClosed: () => of(true) } as ReturnType<MatDialog['open']>);

    organisationApi.listBranches.and.returnValue(of({ items: [], next_cursor: null }));
    organisationApi.listCostCentres.and.returnValue(of({ items: [], next_cursor: null }));
    api.members.and.returnValue(of({ items: [], next_cursor: null }));
    api.products.and.returnValue(
      of({
        items: [
          {
            id: 'wp1',
            tenant_name: 'Nitrile Gloves',
            canonical_name: 'Gloves',
            base_unit: 'each',
            pack: { pack_count: 1, unit_size: '1.000000' },
            status: 'active',
            created_at: '2026-01-01T00:00:00Z',
          },
        ],
        next_cursor: null,
      }),
    );
    requestsApi.getRequest.and.returnValue(of(mockRequest));
    requestsApi.updateRequest.and.returnValue(of(mockRequest));

    await TestBed.configureTestingModule({
      imports: [RequestFormComponent],
      providers: [
        provideTranslateService(),
        provideRouter([]),
        { provide: RequestsApiService, useValue: requestsApi },
        { provide: OrdersApiService, useValue: ordersApi },
        { provide: OrganisationApiService, useValue: organisationApi },
        { provide: ApiService, useValue: api },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: { get: () => 'r1' } } },
        },
      ],
    })
      .overrideComponent(RequestFormComponent, {
        set: {
          providers: [
            provideAppDateAdapter(),
            { provide: MatSnackBar, useValue: snackBarSpy },
            { provide: Router, useValue: routerSpy },
            { provide: MatDialog, useValue: dialogSpy },
          ],
        },
      })
      .compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(RequestFormComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('preserves all decimal digits when prefilling an editable quantity', () => {
    requestsApi.getRequest.and.returnValue(of({ ...mockRequest, lines: [
      { ...mockRequest.lines[0], quantity: '999999999999.999999' },
    ] }));
    const editFixture = TestBed.createComponent(RequestFormComponent);
    editFixture.detectChanges();
    expect(editFixture.componentInstance.lines.at(0).controls.quantity.value)
      .toBe('999999999999.999999');
  });

  it('should load the existing request and pre-fill the form', () => {
    expect(requestsApi.getRequest).toHaveBeenCalledWith('r1');
    expect(component.isEditMode()).toBeTrue();
    expect(component.form.controls.branch_id.value).toBe('b1');
    expect(component.form.controls.cost_centre_id.value).toBe('cc1');
    expect(component.form.controls.required_by_date.value).toEqual(new Date(2026, 8, 15));
    expect(component.lines.length).toBe(1);
    expect(component.lines.at(0).controls.workspace_product_id.value).toBe('wp1');
    expect(component.products()[0]?.tenant_name).toBe('Nitrile Gloves');
    expect(api.products).toHaveBeenCalledWith({ status: 'all', limit: 100 });
  });

  it('should wait for branches before rendering an edit form with a patched branch', () => {
    const delayedBranches$ = new Subject<BranchList>();
    organisationApi.listBranches.and.returnValue(delayedBranches$);
    requestsApi.getRequest.and.returnValue(of(mockRequest));

    const delayedFixture = TestBed.createComponent(RequestFormComponent);
    const delayedComponent = delayedFixture.componentInstance;
    delayedFixture.detectChanges();

    expect(delayedComponent.isLoading()).toBeTrue();
    expect(delayedFixture.nativeElement.querySelector('mat-select')).toBeNull();

    delayedBranches$.next({
      items: [{ id: 'b1', name: 'Main branch', is_active: true, created_at: '2026-01-01T00:00:00Z' }],
      next_cursor: null,
    });
    delayedBranches$.complete();
    delayedFixture.detectChanges();

    expect(delayedComponent.isLoading()).toBeFalse();
    expect(delayedComponent.form.controls.branch_id.value).toBe('b1');
    expect(delayedFixture.nativeElement.querySelector('mat-select')).not.toBeNull();
  });

  it('should update an existing draft via updateRequest', () => {
    const updated = { ...mockRequest, required_by_date: '2026-10-01' };
    requestsApi.updateRequest.and.returnValue(of(updated));

    component.form.controls.required_by_date.setValue('2026-10-01');
    component.saveDraft();

    expect(requestsApi.updateRequest).toHaveBeenCalledWith('r1', jasmine.objectContaining({
      branch_id: 'b1',
      required_by_date: '2026-10-01',
    }));
    expect(requestsApi.createRequest).not.toHaveBeenCalled();
  });

  it('accepts a typed day-first date, displays day-first format, and emits ISO date in payload', () => {
    fixture.detectChanges();
    const input = fixture.nativeElement.querySelector(
      'input[formcontrolname="required_by_date"]'
    ) as HTMLInputElement;
    expect(input).toBeTruthy();

    input.value = '';
    for (const char of '22/10/2026') {
      input.value += char;
      input.dispatchEvent(new Event('input'));
      fixture.detectChanges();
    }
    input.dispatchEvent(new Event('blur'));
    fixture.detectChanges();

    const val = component.form.controls.required_by_date.value;
    expect(val instanceof Date).toBeTrue();
    if (val instanceof Date) {
      expect([val.getFullYear(), val.getMonth(), val.getDate()]).toEqual([2026, 9, 22]);
    }
    expect(input.value).toBe('22/10/2026');

    component.saveDraft();
    expect(requestsApi.updateRequest).toHaveBeenCalledWith('r1', jasmine.objectContaining({
      required_by_date: '2026-10-22',
    }));
  });

  it('should submit the request and navigate to the list', () => {
    requestsApi.submitRequest.and.returnValue(
      of({ ...mockRequest, status: 'submitted' } as PurchaseRequest),
    );

    component.submitRequest();

    expect(requestsApi.updateRequest).toHaveBeenCalledTimes(1);
    expect(requestsApi.submitRequest).toHaveBeenCalledWith('r1');
    expect(routerSpy.navigate).toHaveBeenCalledWith(['/requests']);
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      'Purchase request submitted for approval.',
      undefined,
      { duration: 3500 },
    );
  });

  it('should save dirty valid form before submitting, in order', () => {
    const callOrder: string[] = [];
    requestsApi.updateRequest.and.callFake((id, body) => {
      callOrder.push('save');
      return of({ ...mockRequest, id, cost_centre_id: body.cost_centre_id });
    });
    requestsApi.submitRequest.and.callFake(() => {
      callOrder.push('submit');
      return of({ ...mockRequest, status: 'submitted' } as PurchaseRequest);
    });

    component.form.controls.cost_centre_id.setValue('cc-new');
    component.form.markAsDirty();

    component.submitRequest();

    expect(callOrder).toEqual(['save', 'submit']);
    expect(requestsApi.updateRequest).toHaveBeenCalledWith(
      'r1',
      jasmine.objectContaining({ cost_centre_id: 'cc-new' }),
    );
    expect(requestsApi.submitRequest).toHaveBeenCalledWith('r1');
  });

  it('should call neither save nor submit when form is dirty and invalid', () => {
    requestsApi.updateRequest.calls.reset();
    requestsApi.submitRequest.calls.reset();

    component.form.controls.branch_id.setValue('');
    component.form.controls.branch_id.markAsDirty();
    component.form.markAsDirty();

    component.submitRequest();
    fixture.detectChanges();

    expect(requestsApi.updateRequest).not.toHaveBeenCalled();
    expect(requestsApi.submitRequest).not.toHaveBeenCalled();
    expect(component.form.controls.branch_id.touched).toBeTrue();
  });

  it('should not call submit when save fails before submit', () => {
    const error500 = new HttpErrorResponse({
      status: 500,
      error: { code: 'internal', message: 'Failed to save draft', trace_id: 'tr_save_err' },
    });
    requestsApi.updateRequest.and.returnValue(throwError(() => error500));
    requestsApi.submitRequest.calls.reset();

    component.form.controls.cost_centre_id.setValue('cc-fail');
    component.form.markAsDirty();

    component.submitRequest();

    expect(requestsApi.updateRequest).toHaveBeenCalledTimes(1);
    expect(requestsApi.submitRequest).not.toHaveBeenCalled();
    expect(component.errorMessage()).toBe('Unable to save the purchase request. Please try again.');
    expect(component.isSubmitting()).toBeFalse();
  });

  it('should display the estimate for a line with price history', () => {
    expect(component.formatEstimate(mockRequest.lines[0])).toBe('GBP 25.50 / pack');
  });

  it('should display a fallback for a line without price history', () => {
    const noEstimateLine = {
      quoted_prices_include_vat: false, quoted_vat_rate: null, quoted_net_unit_price: null,
      id: 'l2', workspace_product_id: 'wp2', quantity: '5.000000',
    };
    expect(component.formatEstimate(noEstimateLine)).toBe(
      'No price history available for this product.',
    );
  });

  it('should disable the form and show read-only title + status chip when viewing a non-draft request', async () => {
    const compiledDraft = fixture.nativeElement as HTMLElement;
    expect(compiledDraft.querySelector('.form-title')?.textContent?.trim()).toBe(
      'Edit Purchase Request',
    );
    expect(compiledDraft.querySelector('[data-testid="request-status-chip"]')).toBeNull();

    requestsApi.getRequest.and.returnValue(
      of({ ...mockRequest, status: 'submitted' } as PurchaseRequest),
    );

    const submittedRoute = TestBed.createComponent(RequestFormComponent);
    submittedRoute.detectChanges();

    expect(submittedRoute.componentInstance.form.disabled).toBeTrue();
    const compiledSubmitted = submittedRoute.nativeElement as HTMLElement;
    expect(compiledSubmitted.querySelector('.form-title')?.textContent?.trim()).toBe(
      'Purchase Request',
    );
    const chip = compiledSubmitted.querySelector('[data-testid="request-status-chip"]');
    expect(chip).toBeTruthy();
    expect(chip?.textContent?.trim()).toBe('Submitted');

    const qtyInput = compiledSubmitted.querySelector<HTMLInputElement>('.line-quantity input');
    expect(qtyInput?.value).toBe('10');
  });

  it('shows Create purchase order for an approved step on an ordered request', () => {
    const compiledDraft = fixture.nativeElement as HTMLElement;
    expect(compiledDraft.querySelector('[data-testid="request-create-order-btn"]')).toBeNull();

    requestsApi.getRequest.and.returnValue(
      of({ ...mockRequest, status: 'ordered', approval_step: {
        id: 'step1', assigned_membership_id: 'm1', source: 'owner_fallback', status: 'approved',
        decided_by_membership_id: 'm1', decided_at: '2026-10-01T00:00:00Z',
      } } as PurchaseRequest),
    );

    const approvedFixture = TestBed.createComponent(RequestFormComponent);
    approvedFixture.detectChanges();

    const compiledApproved = approvedFixture.nativeElement as HTMLElement;
    const createOrderBtn = compiledApproved.querySelector<HTMLButtonElement>(
      '[data-testid="request-create-order-btn"]',
    );
    expect(createOrderBtn).toBeTruthy();
    expect(createOrderBtn?.textContent).toContain('Create purchase order');
    expect(compiledApproved.querySelector('.form-title')?.textContent?.trim()).toBe('Purchase Request');
    expect(compiledApproved.querySelector('[data-testid="request-status-chip"]')?.textContent?.trim()).toBe('Ordered');

    createOrderBtn?.click();
    expect(routerSpy.navigate).toHaveBeenCalledWith(['/orders/new'], {
      queryParams: { source_request_id: 'r1' },
    });
  });

  it('hides Create purchase order while approval is pending', () => {
    requestsApi.getRequest.and.returnValue(of({ ...mockRequest, status: 'submitted', approval_step: {
      id: 'step1', assigned_membership_id: 'm1', source: 'owner_fallback', status: 'pending',
      decided_by_membership_id: null, decided_at: null,
    } } as PurchaseRequest));
    const pendingFixture = TestBed.createComponent(RequestFormComponent);
    pendingFixture.detectChanges();
    expect(pendingFixture.nativeElement.querySelector('[data-testid="request-create-order-btn"]')).toBeNull();
  });

  it('does not show the auto-prepared banner on a manually created request', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('[data-testid="auto-prepared-banner"]')).toBeNull();
  });

  it('tells the owner a guardrail drafted the request from the winning quote', () => {
    requestsApi.getRequest.and.returnValue(
      of({
        ...mockRequest,
        auto_prepared: {
          guardrail_id: 'g1',
          rfq_id: 'rfq1',
          supplier_id: 's1',
          supplier_name: 'Nile Bakery',
          created_at: '2026-10-18T09:00:00Z',
        },
      }),
    );
    const autoFixture = TestBed.createComponent(RequestFormComponent);
    autoFixture.detectChanges();

    const banner = (autoFixture.nativeElement as HTMLElement).querySelector(
      '[data-testid="auto-prepared-banner"]',
    );
    expect(banner).toBeTruthy();
    expect(banner?.textContent).toContain('Prepared automatically by a guardrail');
    expect(banner?.textContent).toContain("from Nile Bakery's quote. Review it and submit it");
  });

  it('should not display budget status block when budget_status is absent', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.budget-warning-banner')).toBeNull();
    expect(compiled.querySelector('.budget-status-row')).toBeNull();
  });

  it('should display informational warning with remaining budget when budget_status.exceeds is true without disabling submit', () => {
    const exceedingRequest: PurchaseRequest = {
      ...mockRequest,
      budget_status: {
        status: 'over',
        remaining_amount: { amount: '75.0000', currency: 'GBP' },
        exceeds: true,
        reason_code: 'budget_exceeded',
      },
    };
    requestsApi.getRequest.and.returnValue(of(exceedingRequest));

    const hostFixture = TestBed.createComponent(RequestFormComponent);
    hostFixture.detectChanges();

    const compiled = hostFixture.nativeElement as HTMLElement;
    const warningBanner = compiled.querySelector('.budget-warning-banner');
    expect(warningBanner).toBeTruthy();
    expect(warningBanner?.textContent).toContain(
      'This request would exceed the remaining budget for its scope.',
    );
    expect(warningBanner?.textContent).toContain('Remaining budget');
    expect(warningBanner?.textContent).toContain('GBP 75');

    const submitBtn = compiled.querySelector<HTMLButtonElement>('.submit-request-btn');
    expect(submitBtn).toBeTruthy();
    expect(submitBtn?.disabled).toBeFalse();
  });

  it('should display quiet remaining budget status when budget_status exists and exceeds is false', () => {
    const withinBudgetRequest: PurchaseRequest = {
      ...mockRequest,
      budget_status: {
        status: 'within',
        remaining_amount: { amount: '500.0000', currency: 'GBP' },
        exceeds: false,
        reason_code: null,
      },
    };
    requestsApi.getRequest.and.returnValue(of(withinBudgetRequest));

    const hostFixture = TestBed.createComponent(RequestFormComponent);
    hostFixture.detectChanges();

    const compiled = hostFixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.budget-warning-banner')).toBeNull();

    const budgetRow = compiled.querySelector('.budget-status-row');
    expect(budgetRow).toBeTruthy();
    expect(budgetRow?.textContent).toContain('Remaining budget');
    expect(budgetRow?.textContent).toContain('GBP 500');

    const submitBtn = compiled.querySelector<HTMLButtonElement>('.submit-request-btn');
    expect(submitBtn).toBeTruthy();
    expect(submitBtn?.disabled).toBeFalse();
  });

  it('does not render a budget row or warning when there is no budget', () => {
    requestsApi.getRequest.and.returnValue(of({
      ...mockRequest,
      budget_status: {
        status: 'no_budget',
        remaining_amount: null,
        exceeds: false,
        reason_code: 'no_budget',
      },
    } as PurchaseRequest));

    const hostFixture = TestBed.createComponent(RequestFormComponent);
    hostFixture.detectChanges();

    const compiled = hostFixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.budget-warning-banner')).toBeNull();
    expect(compiled.querySelector('.budget-status-row')).toBeNull();
  });

  it('should not render an approval section when the request has no approval_step', () => {
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('.approval-step')).toBeNull();
  });

  it('should render a pending approval_step with assigned approver email and no comment/decided-at', () => {
    const approverMember = { id: 'm-approver', email: 'approver@example.com' } as Member;
    api.members.and.returnValue(of({ items: [approverMember], next_cursor: null }));

    const pendingRequest: PurchaseRequest = {
      ...mockRequest,
      status: 'submitted',
      approval_step: {
        id: 'as1',
        assigned_membership_id: 'm-approver',
        source: 'threshold_match',
        status: 'pending',
      },
    };
    requestsApi.getRequest.and.returnValue(of(pendingRequest));

    const hostFixture = TestBed.createComponent(RequestFormComponent);
    hostFixture.detectChanges();

    const compiled = hostFixture.nativeElement as HTMLElement;
    const section = compiled.querySelector('.approval-step');
    expect(section).toBeTruthy();
    expect(section?.textContent).toContain('Approval');
    expect(section?.textContent).toContain('Pending approval');
    expect(section?.textContent).toContain('Assigned to');
    expect(section?.textContent).toContain('approver@example.com');
    expect(section?.textContent).not.toContain('Decision comment');
    expect(section?.textContent).not.toContain('Decided on');

    const chip = section?.querySelector('.status-chip');
    expect(chip?.getAttribute('data-status')).toBe('pending');
    expect(chip?.textContent).toContain('Pending');
  });

  it('should render an approved approval_step with comment and decided-at', () => {
    const approverMember = { id: 'm-approver', email: 'approver@example.com' } as Member;
    api.members.and.returnValue(of({ items: [approverMember], next_cursor: null }));

    const approvedRequest: PurchaseRequest = {
      ...mockRequest,
      status: 'approved',
      approval_step: {
        id: 'as2',
        assigned_membership_id: 'm-approver',
        source: 'threshold_match',
        status: 'approved',
        comment: 'Budget confirmed.',
        decided_by_membership_id: 'm-approver',
        decided_at: '2026-09-10T12:00:00Z',
      },
    };
    requestsApi.getRequest.and.returnValue(of(approvedRequest));

    const hostFixture = TestBed.createComponent(RequestFormComponent);
    hostFixture.detectChanges();

    const compiled = hostFixture.nativeElement as HTMLElement;
    const section = compiled.querySelector('.approval-step');
    expect(section).toBeTruthy();
    expect(section?.textContent).toContain('Decision comment');
    expect(section?.textContent).toContain('Budget confirmed.');
    expect(section?.textContent).toContain('Decided on');
    expect(section?.textContent).toContain('Sep 10, 2026');

    const chip = section?.querySelector('.status-chip');
    expect(chip?.getAttribute('data-status')).toBe('approved');
    expect(chip?.textContent).toContain('Approved');
  });

  it('should fall back to the raw membership id when the approver is not in the members list', () => {
    api.members.and.returnValue(of({ items: [], next_cursor: null }));

    const pendingRequest: PurchaseRequest = {
      ...mockRequest,
      status: 'submitted',
      approval_step: {
        id: 'as3',
        assigned_membership_id: 'unknown-approver-id',
        source: 'owner_fallback',
        status: 'pending',
      },
    };
    requestsApi.getRequest.and.returnValue(of(pendingRequest));

    const hostFixture = TestBed.createComponent(RequestFormComponent);
    hostFixture.detectChanges();

    const compiled = hostFixture.nativeElement as HTMLElement;
    const section = compiled.querySelector('.approval-step');
    expect(section?.textContent).toContain('unknown-approver-id');
  });

  it('renders a source line linking to RFQ and quote and naming the supplier with dir="auto"', () => {
    const sourcedRequest: PurchaseRequest = {
      ...mockRequest,
      source: {
        rfq_id: 'rfq-123',
        rfq_response_id: 'resp-456',
        quotation_id: 'quote-789',
        supplier_id: 'sup-1',
        supplier_name: 'الوفرة للمواد الغذائية',
      },
    };
    requestsApi.getRequest.and.returnValue(of(sourcedRequest));

    const hostFixture = TestBed.createComponent(RequestFormComponent);
    hostFixture.detectChanges();

    const compiled = hostFixture.nativeElement as HTMLElement;
    const sourceLine = compiled.querySelector('[data-testid="request-source-line"]');
    expect(sourceLine).toBeTruthy();
    expect(sourceLine?.textContent).toContain('الوفرة للمواد الغذائية');

    const supplierSpan = sourceLine?.querySelector('.source-supplier');
    expect(supplierSpan?.getAttribute('dir')).toBe('auto');

    const linkDirectives = hostFixture.debugElement.queryAll(By.directive(RouterLink));
    expect(linkDirectives.length).toBe(2);
    const getLinkInput = (dir: typeof linkDirectives[0]) =>
      (dir.injector.get(RouterLink) as unknown as Record<string, () => unknown>)['routerLinkInput']();
    expect(getLinkInput(linkDirectives[0])).toEqual(['/rfq', 'rfq-123']);
    expect(getLinkInput(linkDirectives[1])).toEqual(['/quotations', 'quote-789', 'review']);
  });

  describe('Spec 024 User Story 3 (T030) — Grouped request', () => {
    const groupedRequest: PurchaseRequest = {
      ...mockRequest,
      status: 'draft',
      request_group: {
        id: 'grp-001',
        rfq_id: 'rfq-split-001',
        position: 1,
        size: 2,
        combined_total: { amount: '4063.00', currency: 'SAR' },
        best_single_total: { amount: '4137.00', currency: 'SAR' },
        saving: { amount: '74.00', currency: 'SAR' },
        sibling_request_ids: ['r2'],
      },
    };

    it('shows 1 of 2 and links to sibling request', () => {
      requestsApi.getRequest.and.returnValue(of(groupedRequest));
      const hostFixture = TestBed.createComponent(RequestFormComponent);
      hostFixture.detectChanges();

      const compiled = hostFixture.nativeElement as HTMLElement;
      expect(compiled.textContent).toContain('1 of 2');
      expect(compiled.textContent).toContain('Part of a split');
      expect(compiled.textContent).toContain('4,063');

      const siblingLinks = compiled.querySelectorAll('a.sibling-link');
      expect(siblingLinks.length).toBe(1);
    });

    it('a grouped draft renders read-only with no Save and explains why', () => {
      requestsApi.getRequest.and.returnValue(of(groupedRequest));
      const hostFixture = TestBed.createComponent(RequestFormComponent);
      hostFixture.detectChanges();

      const comp = hostFixture.componentInstance;
      const compiled = hostFixture.nativeElement as HTMLElement;

      expect(comp.isReadOnly()).toBeTrue();
      expect(comp.form.disabled).toBeTrue();
      expect(compiled.querySelector('button[type="submit"]')).toBeNull();
      expect(compiled.textContent).toContain(
        'Part of a split: these requests are submitted and approved together',
      );
      expect(compiled.querySelector('.submit-request-btn')).toBeTruthy();
    });

    it('Submit calls submitGroup once directly and never updateRequest', () => {
      requestsApi.getRequest.and.returnValue(of(groupedRequest));
      requestsApi.submitGroup.and.returnValue(of([groupedRequest]));

      const hostFixture = TestBed.createComponent(RequestFormComponent);
      hostFixture.detectChanges();

      const compiled = hostFixture.nativeElement as HTMLElement;
      const submitBtn = compiled.querySelector('.submit-request-btn') as HTMLButtonElement;
      expect(submitBtn).toBeTruthy();
      expect(submitBtn.textContent).toContain('Submits both requests of this split');

      submitBtn.click();
      hostFixture.detectChanges();

      expect(requestsApi.submitGroup).toHaveBeenCalledTimes(1);
      expect(requestsApi.submitGroup.calls.mostRecent().args[0]).toBe('grp-001');
      expect(requestsApi.submitGroup.calls.mostRecent().args[1]).toEqual(jasmine.any(String));
      expect(requestsApi.updateRequest).not.toHaveBeenCalled();
      expect(requestsApi.submitRequest).not.toHaveBeenCalled();
    });

    it('a retry after an error reuses the same key', () => {
      requestsApi.getRequest.and.returnValue(of(groupedRequest));
      requestsApi.submitGroup.and.returnValue(throwError(() => new Error('Network error')));

      const hostFixture = TestBed.createComponent(RequestFormComponent);
      hostFixture.detectChanges();

      const compiled = hostFixture.nativeElement as HTMLElement;
      const submitBtn = compiled.querySelector('.submit-request-btn') as HTMLButtonElement;

      // First click -> error
      submitBtn.click();
      hostFixture.detectChanges();

      expect(requestsApi.submitGroup).toHaveBeenCalledTimes(1);
      const firstKey = requestsApi.submitGroup.calls.mostRecent().args[1];
      expect(firstKey).toBeTruthy();

      // Retry click -> reuses key
      requestsApi.submitGroup.and.returnValue(of([groupedRequest]));
      submitBtn.click();
      hostFixture.detectChanges();

      expect(requestsApi.submitGroup).toHaveBeenCalledTimes(2);
      const retryKey = requestsApi.submitGroup.calls.mostRecent().args[1];
      expect(retryKey).toBe(firstKey);
    });

    it('withdraw retry after an error reuses the same key', () => {
      const submittedGrouped = { ...groupedRequest, status: 'submitted' as const };
      requestsApi.getRequest.and.returnValue(of(submittedGrouped));
      requestsApi.withdrawGroup.and.returnValue(throwError(() => new Error('Server error')));

      const hostFixture = TestBed.createComponent(RequestFormComponent);
      hostFixture.detectChanges();

      const compiled = hostFixture.nativeElement as HTMLElement;
      const withdrawBtn = compiled.querySelector('.withdraw-request-btn') as HTMLButtonElement;
      expect(withdrawBtn).toBeTruthy();

      // First click -> error
      withdrawBtn.click();
      hostFixture.detectChanges();

      expect(requestsApi.withdrawGroup).toHaveBeenCalledTimes(1);
      const firstKey = requestsApi.withdrawGroup.calls.mostRecent().args[1];
      expect(firstKey).toBeTruthy();

      // Retry click -> reuses key
      requestsApi.withdrawGroup.and.returnValue(of([submittedGrouped]));
      withdrawBtn.click();
      hostFixture.detectChanges();

      expect(requestsApi.withdrawGroup).toHaveBeenCalledTimes(2);
      const retryKey = requestsApi.withdrawGroup.calls.mostRecent().args[1];
      expect(retryKey).toBe(firstKey);
    });

    it('opens confirm dialog on withdraw click and does not withdraw if cancelled (PPS-188)', () => {
      requestsApi.withdrawRequest.calls.reset();
      dialogSpy.open.calls.reset();
      dialogSpy.open.and.returnValue({ afterClosed: () => of(false) } as ReturnType<MatDialog['open']>);
      requestsApi.getRequest.and.returnValue(of({ ...mockRequest, status: 'submitted' }));

      const hostFixture = TestBed.createComponent(RequestFormComponent);
      hostFixture.detectChanges();

      const withdrawBtn = hostFixture.nativeElement.querySelector('.withdraw-request-btn') as HTMLButtonElement;
      expect(withdrawBtn).toBeTruthy();
      withdrawBtn.click();
      hostFixture.detectChanges();

      expect(dialogSpy.open).toHaveBeenCalled();
      expect(requestsApi.withdrawRequest).not.toHaveBeenCalled();
    });

    it('withdraws request only after confirmation in dialog (PPS-188)', () => {
      requestsApi.withdrawRequest.calls.reset();
      dialogSpy.open.calls.reset();
      dialogSpy.open.and.returnValue({ afterClosed: () => of(true) } as ReturnType<MatDialog['open']>);
      requestsApi.getRequest.and.returnValue(of({ ...mockRequest, status: 'submitted' }));
      requestsApi.withdrawRequest.and.returnValue(of({ ...mockRequest, status: 'withdrawn' }));

      const hostFixture = TestBed.createComponent(RequestFormComponent);
      hostFixture.detectChanges();

      const withdrawBtn = hostFixture.nativeElement.querySelector('.withdraw-request-btn') as HTMLButtonElement;
      expect(withdrawBtn).toBeTruthy();
      withdrawBtn.click();
      hostFixture.detectChanges();

      expect(dialogSpy.open).toHaveBeenCalled();
      const dialogData = dialogSpy.open.calls.mostRecent().args[1]?.data as {
        titleKey?: string;
        messageKey?: string;
        confirmKey?: string;
        isDestructive?: boolean;
      };
      expect(dialogData?.titleKey).toBe('requests.withdrawConfirmTitle');
      expect(dialogData?.messageKey).toBe('requests.withdrawConfirmMessage');
      expect(dialogData?.confirmKey).toBe('requests.actions.withdraw');
      expect(dialogData?.isDestructive).toBeTrue();
      expect(requestsApi.withdrawRequest).toHaveBeenCalledWith('r1', jasmine.any(String));
    });

    it('withdraws group with split confirmation dialog when request is part of a split (PPS-188)', () => {
      requestsApi.withdrawGroup.calls.reset();
      dialogSpy.open.calls.reset();
      const submittedGrouped = { ...groupedRequest, status: 'submitted' as const };
      requestsApi.getRequest.and.returnValue(of(submittedGrouped));
      requestsApi.withdrawGroup.and.returnValue(of([submittedGrouped]));
      dialogSpy.open.and.returnValue({ afterClosed: () => of(true) } as ReturnType<MatDialog['open']>);

      const hostFixture = TestBed.createComponent(RequestFormComponent);
      hostFixture.detectChanges();

      const withdrawBtn = hostFixture.nativeElement.querySelector('.withdraw-request-btn') as HTMLButtonElement;
      expect(withdrawBtn).toBeTruthy();
      withdrawBtn.click();
      hostFixture.detectChanges();

      expect(dialogSpy.open).toHaveBeenCalled();
      const dialogData = dialogSpy.open.calls.mostRecent().args[1]?.data as {
        titleKey?: string;
        messageKey?: string;
        confirmKey?: string;
        confirmParams?: Record<string, unknown>;
        messageParams?: Record<string, unknown>;
        isDestructive?: boolean;
      };
      expect(dialogData?.titleKey).toBe('requests.split.withdrawConfirmTitle');
      expect(dialogData?.messageKey).toBe('requests.split.withdrawConfirmMessageBoth');
      expect(dialogData?.confirmKey).toBe('requests.split.withdrawBoth');
      expect(dialogData?.isDestructive).toBeTrue();
      expect(requestsApi.withdrawGroup).toHaveBeenCalledWith('grp-001', jasmine.any(String));
    });

    it('uses split wording with count for size 3 split in confirm dialog (PPS-188)', () => {
      dialogSpy.open.calls.reset();
      const threeWay = {
        ...groupedRequest,
        status: 'submitted' as const,
        request_group: { ...groupedRequest.request_group!, size: 3 },
      };
      requestsApi.getRequest.and.returnValue(of(threeWay));
      requestsApi.withdrawGroup.and.returnValue(of([threeWay]));
      dialogSpy.open.and.returnValue({ afterClosed: () => of(true) } as ReturnType<MatDialog['open']>);

      const hostFixture = TestBed.createComponent(RequestFormComponent);
      hostFixture.detectChanges();

      const withdrawBtn = hostFixture.nativeElement.querySelector('.withdraw-request-btn') as HTMLButtonElement;
      expect(withdrawBtn).toBeTruthy();
      withdrawBtn.click();
      hostFixture.detectChanges();

      expect(dialogSpy.open).toHaveBeenCalled();
      const dialogData = dialogSpy.open.calls.mostRecent().args[1]?.data as {
        titleKey?: string;
        messageKey?: string;
        confirmKey?: string;
        confirmParams?: Record<string, unknown>;
        messageParams?: Record<string, unknown>;
      };
      expect(dialogData?.titleKey).toBe('requests.split.withdrawConfirmTitle');
      expect(dialogData?.messageKey).toBe('requests.split.withdrawConfirmMessageAll');
      expect(dialogData?.confirmKey).toBe('requests.split.withdrawAll');
      expect(dialogData?.messageParams).toEqual({ count: 3 });
      expect(dialogData?.confirmParams).toEqual({ count: 3 });
    });

    it('part_of_split shows the message pointing to the group action', () => {
      requestsApi.getRequest.and.returnValue(of(mockRequest));
      requestsApi.updateRequest.and.returnValue(of(mockRequest));
      const errorResp = new HttpErrorResponse({
        error: { code: 'conflict', message: 'Conflict', details: { reason: 'part_of_split' } },
        status: 409,
        statusText: 'Conflict',
      });
      requestsApi.submitRequest.and.returnValue(throwError(() => errorResp));

      const hostFixture = TestBed.createComponent(RequestFormComponent);
      hostFixture.detectChanges();

      const compiled = hostFixture.nativeElement as HTMLElement;
      const submitBtn = compiled.querySelector('.submit-request-btn') as HTMLButtonElement;
      submitBtn.click();
      hostFixture.detectChanges();

      expect(hostFixture.componentInstance.errorMessage()).toBeTruthy();
      expect(compiled.querySelector('.error-banner')?.textContent?.toLowerCase()).toContain('split');
    });
  });

  describe('PPS-119: offer Create purchase order only while something is left', () => {
    const baseApprovedRequest: PurchaseRequest = {
      ...mockRequest,
      status: 'approved',
      approval_step: {
        id: 'step1',
        assigned_membership_id: 'm1',
        source: 'owner_fallback',
        status: 'approved',
        decided_by_membership_id: 'm1',
        decided_at: '2026-10-01T00:00:00Z',
      },
    };

    it('approved request with (none ordered) → button, no PO row', () => {
      requestsApi.getRequest.and.returnValue(of(baseApprovedRequest));
      ordersApi.getAllocations.and.returnValue(
        of({
          source_request_id: 'r1',
          lines: [
            {
              source_request_line_id: 'l1',
              requested_quantity: '10',
              allocated_quantity: '0',
              remaining_quantity: '10',
            },
          ],
          orders: [],
        }),
      );

      const f = TestBed.createComponent(RequestFormComponent);
      f.detectChanges();

      const btn = f.nativeElement.querySelector('[data-testid="request-create-order-btn"]');
      expect(btn).toBeTruthy();

      const poRow = f.nativeElement.querySelector('[data-testid="request-purchase-orders-row"]');
      expect(poRow).toBeNull();
    });

    it('(partly ordered) → button and PO-000005 link', () => {
      requestsApi.getRequest.and.returnValue(of({ ...baseApprovedRequest, status: 'ordered' }));
      ordersApi.getAllocations.and.returnValue(
        of({
          source_request_id: 'r1',
          lines: [
            {
              source_request_line_id: 'l1',
              requested_quantity: '10',
              allocated_quantity: '4',
              remaining_quantity: '6',
            },
          ],
          orders: [
            {
              id: 'po-5',
              order_number: 'PO-000005',
              status: 'draft',
            },
          ],
        }),
      );

      const f = TestBed.createComponent(RequestFormComponent);
      f.detectChanges();

      const btn = f.nativeElement.querySelector('[data-testid="request-create-order-btn"]');
      expect(btn).toBeTruthy();

      const poRow = f.nativeElement.querySelector('[data-testid="request-purchase-orders-row"]');
      expect(poRow).toBeTruthy();

      const link = Array.from((f.nativeElement as HTMLElement).querySelectorAll('a')).find((a) =>
        a.textContent?.includes('PO-000005'),
      );
      expect(link).toBeTruthy();
    });

    it('(fully ordered) → no button, link, ordered text', () => {
      requestsApi.getRequest.and.returnValue(of({ ...baseApprovedRequest, status: 'ordered' }));
      ordersApi.getAllocations.and.returnValue(
        of({
          source_request_id: 'r1',
          lines: [
            {
              source_request_line_id: 'l1',
              requested_quantity: '10',
              allocated_quantity: '10',
              remaining_quantity: '0',
            },
          ],
          orders: [
            {
              id: 'po-5',
              order_number: 'PO-000005',
              status: 'draft',
            },
          ],
        }),
      );

      const f = TestBed.createComponent(RequestFormComponent);
      f.detectChanges();

      const btn = f.nativeElement.querySelector('[data-testid="request-create-order-btn"]');
      expect(btn).toBeNull();

      const poRow = f.nativeElement.querySelector('[data-testid="request-purchase-orders-row"]');
      expect(poRow).toBeTruthy();

      const link = Array.from((f.nativeElement as HTMLElement).querySelectorAll('a')).find((a) =>
        a.textContent?.includes('PO-000005'),
      );
      expect(link).toBeTruthy();

      const orderedText = f.nativeElement.querySelector('[data-testid="request-fully-ordered-text"]');
      expect(orderedText).toBeTruthy();
      expect(orderedText?.textContent).toContain('Everything on this request has been ordered.');
    });

    it('(allocation call fails) → button', () => {
      requestsApi.getRequest.and.returnValue(of(baseApprovedRequest));
      ordersApi.getAllocations.and.returnValue(throwError(() => new Error('Failed to load allocations')));

      const f = TestBed.createComponent(RequestFormComponent);
      f.detectChanges();

      const btn = f.nativeElement.querySelector('[data-testid="request-create-order-btn"]');
      expect(btn).toBeTruthy();
    });

    it('(status withdrawn with an approved step) → no button', () => {
      requestsApi.getRequest.and.returnValue(
        of({
          ...baseApprovedRequest,
          status: 'withdrawn',
        }),
      );

      const f = TestBed.createComponent(RequestFormComponent);
      f.detectChanges();

      const btn = f.nativeElement.querySelector('[data-testid="request-create-order-btn"]');
      expect(btn).toBeNull();
      expect(ordersApi.getAllocations).not.toHaveBeenCalled();
    });
  });

  describe('PPS-189 (1): Split sibling navigation via paramMap', () => {
    it('navigating from request A to B via paramMap reloads B and resets keys/state (A\'s Submit key must not be reused for B)', async () => {
      const requestA: PurchaseRequest = {
        ...mockRequest,
        id: 'req-A',
        branch_id: 'b1',
        request_group: {
          id: 'grp-A',
          rfq_id: 'rfq-1',
          position: 1,
          size: 2,
          combined_total: { amount: '200.00', currency: 'SAR' },
          sibling_request_ids: ['req-B'],
        },
      };

      const requestB: PurchaseRequest = {
        ...mockRequest,
        id: 'req-B',
        branch_id: 'b2',
        request_group: {
          id: 'grp-B',
          rfq_id: 'rfq-1',
          position: 2,
          size: 2,
          combined_total: { amount: '200.00', currency: 'SAR' },
          sibling_request_ids: ['req-A'],
        },
      };

      const paramMap$ = new BehaviorSubject(convertToParamMap({ id: 'req-A' }));
      const requestsApiSpy = jasmine.createSpyObj('RequestsApiService', [
        'createRequest',
        'updateRequest',
        'submitRequest',
        'submitGroup',
        'withdrawRequest',
        'withdrawGroup',
        'getRequest',
      ]);
      const ordersApiSpy = jasmine.createSpyObj('OrdersApiService', ['getAllocations']);
      ordersApiSpy.getAllocations.and.returnValue(of(null));
      const orgApiSpy = jasmine.createSpyObj('OrganisationApiService', ['listBranches', 'listCostCentres']);
      orgApiSpy.listBranches.and.returnValue(of({ items: [], next_cursor: null }));
      orgApiSpy.listCostCentres.and.returnValue(of({ items: [], next_cursor: null }));
      const apiSpy = jasmine.createSpyObj('ApiService', ['members', 'products']);
      apiSpy.members.and.returnValue(of({ items: [], next_cursor: null }));
      apiSpy.products.and.returnValue(of({ items: [], next_cursor: null }));
      const routerSpyLocal = jasmine.createSpyObj('Router', ['navigate']);
      const snackBarSpyLocal = jasmine.createSpyObj('MatSnackBar', ['open']);

      requestsApiSpy.getRequest.and.callFake((id: string) => {
        if (id === 'req-A') return of(requestA);
        if (id === 'req-B') return of(requestB);
        return throwError(() => new Error('Not found'));
      });
      requestsApiSpy.submitGroup.and.returnValue(throwError(() => new Error('Submission error')));

      await TestBed.resetTestingModule();
      await TestBed.configureTestingModule({
        imports: [RequestFormComponent],
        providers: [
          provideTranslateService(),
          provideRouter([]),
          { provide: RequestsApiService, useValue: requestsApiSpy },
          { provide: OrdersApiService, useValue: ordersApiSpy },
          { provide: OrganisationApiService, useValue: orgApiSpy },
          { provide: ApiService, useValue: apiSpy },
          {
            provide: ActivatedRoute,
            useValue: {
              paramMap: paramMap$.asObservable(),
              snapshot: { paramMap: convertToParamMap({ id: 'req-A' }) },
            },
          },
        ],
      })
        .overrideComponent(RequestFormComponent, {
          set: {
            providers: [
              provideAppDateAdapter(),
              { provide: MatSnackBar, useValue: snackBarSpyLocal },
              { provide: Router, useValue: routerSpyLocal },
              { provide: MatDialog, useValue: jasmine.createSpyObj('MatDialog', ['open']) },
            ],
          },
        })
        .compileComponents();

      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog);
      translate.use('en');

      const testFixture = TestBed.createComponent(RequestFormComponent);
      const testComp = testFixture.componentInstance;
      testFixture.detectChanges();

      expect(testComp.existingRequest()?.id).toBe('req-A');

      // Attempt submit on request A which fails and leaves submitIdempotencyKey & errorMessage
      testComp.submitRequest();
      testFixture.detectChanges();

      expect(requestsApiSpy.submitGroup).toHaveBeenCalledWith('grp-A', jasmine.any(String));
      const keyA = requestsApiSpy.submitGroup.calls.mostRecent().args[1];
      expect(keyA).toBeTruthy();
      expect(testComp.errorMessage()).toBeTruthy();

      // Set allocation state to verify it gets cleared
      testComp.allocations.set({ source_request_id: 'req-A', orders: [], lines: [] });

      // Navigate to sibling request B via paramMap
      requestsApiSpy.submitGroup.calls.reset();
      requestsApiSpy.submitGroup.and.returnValue(of({}));
      paramMap$.next(convertToParamMap({ id: 'req-B' }));
      testFixture.detectChanges();

      // State and keys must be reset, and request B loaded
      expect(requestsApiSpy.getRequest).toHaveBeenCalledWith('req-B');
      expect(testComp.existingRequest()?.id).toBe('req-B');
      expect(testComp.errorMessage()).toBeNull();
      expect(testComp.allocations()).toBeNull();

      // Submitting request B must use a fresh idempotency key, not request A's key
      testComp.submitRequest();
      testFixture.detectChanges();

      expect(requestsApiSpy.submitGroup).toHaveBeenCalledWith('grp-B', jasmine.any(String));
      const keyB = requestsApiSpy.submitGroup.calls.mostRecent().args[1];
      expect(keyB).toBeTruthy();
      expect(keyB).not.toBe(keyA);
    });
  });

  describe('Review Finding A (#426): Stale allocation response on sibling navigation', () => {
    it('two requests, A allocation response delayed until after navigating to B -> B allocations stay B and late A response never changes B canCreateOrder or isFullyOrdered', async () => {
      const requestA: PurchaseRequest = {
        ...mockRequest,
        id: 'req-A',
        status: 'approved',
        approval_step: {
          id: 'as-a',
          assigned_membership_id: 'm-approver',
          source: 'threshold_match',
          status: 'approved',
          comment: null,
          decided_by_membership_id: 'm-approver',
          decided_at: '2026-09-10T12:00:00Z',
        },
        lines: [
          {
            ...mockRequest.lines[0],
            id: 'l1',
            quantity: '5.000000',
          },
        ],
      };

      const requestB: PurchaseRequest = {
        ...mockRequest,
        id: 'req-B',
        status: 'approved',
        approval_step: {
          id: 'as-b',
          assigned_membership_id: 'm-approver',
          source: 'threshold_match',
          status: 'approved',
          comment: null,
          decided_by_membership_id: 'm-approver',
          decided_at: '2026-09-10T12:00:00Z',
        },
        lines: [
          {
            ...mockRequest.lines[0],
            id: 'l2',
            quantity: '10.000000',
          },
        ],
      };

      const allocationsA: RequestAllocation = {
        source_request_id: 'req-A',
        lines: [
          {
            source_request_line_id: 'l1',
            requested_quantity: '5.000000',
            allocated_quantity: '5.000000',
            remaining_quantity: '0',
          },
        ],
        orders: [
          {
            id: 'po-1',
            order_number: 'PO-001',
            status: 'confirmed',
          },
        ],
      };

      const allocationsB: RequestAllocation = {
        source_request_id: 'req-B',
        lines: [
          {
            source_request_line_id: 'l2',
            requested_quantity: '10.000000',
            allocated_quantity: '0',
            remaining_quantity: '10.000000',
          },
        ],
        orders: [],
      };

      const paramMap$ = new BehaviorSubject(convertToParamMap({ id: 'req-A' }));
      const requestsApiSpy = jasmine.createSpyObj('RequestsApiService', [
        'createRequest',
        'updateRequest',
        'submitRequest',
        'submitGroup',
        'withdrawRequest',
        'withdrawGroup',
        'getRequest',
      ]);
      const ordersApiSpy = jasmine.createSpyObj('OrdersApiService', ['getAllocations']);
      const allocationsASubject = new Subject<RequestAllocation>();
      ordersApiSpy.getAllocations.and.callFake((id: string) => {
        if (id === 'req-A') return allocationsASubject.asObservable();
        if (id === 'req-B') return of(allocationsB);
        return throwError(() => new Error('Unknown id'));
      });

      const orgApiSpy = jasmine.createSpyObj('OrganisationApiService', ['listBranches', 'listCostCentres']);
      orgApiSpy.listBranches.and.returnValue(of({ items: [], next_cursor: null }));
      orgApiSpy.listCostCentres.and.returnValue(of({ items: [], next_cursor: null }));
      const apiSpy = jasmine.createSpyObj('ApiService', ['members', 'products']);
      apiSpy.members.and.returnValue(of({ items: [], next_cursor: null }));
      apiSpy.products.and.returnValue(of({ items: [], next_cursor: null }));

      requestsApiSpy.getRequest.and.callFake((id: string) => {
        if (id === 'req-A') return of(requestA);
        if (id === 'req-B') return of(requestB);
        return throwError(() => new Error('Not found'));
      });

      await TestBed.resetTestingModule();
      await TestBed.configureTestingModule({
        imports: [RequestFormComponent],
        providers: [
          provideTranslateService(),
          provideRouter([]),
          { provide: RequestsApiService, useValue: requestsApiSpy },
          { provide: OrdersApiService, useValue: ordersApiSpy },
          { provide: OrganisationApiService, useValue: orgApiSpy },
          { provide: ApiService, useValue: apiSpy },
          {
            provide: ActivatedRoute,
            useValue: {
              paramMap: paramMap$.asObservable(),
              snapshot: { paramMap: convertToParamMap({ id: 'req-A' }) },
            },
          },
        ],
      })
        .overrideComponent(RequestFormComponent, {
          set: {
            providers: [
              provideAppDateAdapter(),
              { provide: MatSnackBar, useValue: jasmine.createSpyObj('MatSnackBar', ['open']) },
              { provide: Router, useValue: jasmine.createSpyObj('Router', ['navigate']) },
              { provide: MatDialog, useValue: jasmine.createSpyObj('MatDialog', ['open']) },
            ],
          },
        })
        .compileComponents();

      const testFixture = TestBed.createComponent(RequestFormComponent);
      const testComp = testFixture.componentInstance;
      testFixture.detectChanges();

      expect(testComp.existingRequest()?.id).toBe('req-A');
      expect(testComp.isAllocationsLoading()).toBeTrue();

      // Navigate to sibling request B before A's allocations arrive
      paramMap$.next(convertToParamMap({ id: 'req-B' }));
      testFixture.detectChanges();

      expect(testComp.existingRequest()?.id).toBe('req-B');
      expect(testComp.allocations()).toEqual(allocationsB);
      expect(testComp.canCreateOrder()).toBeTrue();
      expect(testComp.isFullyOrdered()).toBeFalse();

      // Now late allocations for A arrive
      allocationsASubject.next(allocationsA);
      testFixture.detectChanges();

      // B's allocations and computed properties must remain intact
      expect(testComp.allocations()).toEqual(allocationsB);
      expect(testComp.canCreateOrder()).toBeTrue();
      expect(testComp.isFullyOrdered()).toBeFalse();
    });
  });

  describe('Review Finding B (#426): fetchAllPages per-subscription state', () => {
    it('subscribe, cancel after page one, subscribe again -> result has no duplicates and fetches every page', (done) => {
      const page2$ = new Subject<{ items: readonly string[]; next_cursor: string | null }>();
      const fetchPage = jasmine.createSpy('fetchPage').and.callFake((cursor?: string) => {
        if (!cursor) {
          return of({ items: ['a', 'b'], next_cursor: 'cursor-1' });
        }
        return page2$.asObservable();
      });

      const obs$ = fetchAllPages(fetchPage, 50);

      // First subscription: receives page 1, then cancels before page 2
      const sub1 = obs$.subscribe();
      expect(fetchPage).toHaveBeenCalledWith();
      expect(fetchPage).toHaveBeenCalledWith('cursor-1');
      sub1.unsubscribe();

      // Second subscription to the SAME observable
      fetchPage.calls.reset();
      obs$.subscribe((items) => {
        expect(items).toEqual(['a', 'b', 'c']);
        done();
      });

      expect(fetchPage).toHaveBeenCalledWith();
      expect(fetchPage).toHaveBeenCalledWith('cursor-1');

      // Now complete page 2 for the second subscription
      page2$.next({ items: ['c'], next_cursor: null });
      page2$.complete();
    });
  });

  describe('Review Finding C (#429): Clearing server errors on value changes', () => {
    it('set a duplicate-product server error on line 2, change line 1 product, expect line 2 control to be valid and Save/Submit to proceed', () => {
      component.form.controls.branch_id.setValue('b1');
      component.form.controls.required_by_date.setValue('2026-09-15');
      // Line 1
      component.lines.at(0).controls.workspace_product_id.setValue('wp1');
      component.lines.at(0).controls.quantity.setValue('10');
      // Line 2
      component.addLine();
      component.lines.at(1).controls.workspace_product_id.setValue('wp1');
      component.lines.at(1).controls.quantity.setValue('5');
      fixture.detectChanges();

      const error422 = new HttpErrorResponse({
        status: 422,
        error: {
          code: 'unprocessable',
          message: 'Duplicate product',
          details: { field: 'lines[1].workspace_product_id', reason: 'duplicate_product' },
        },
      });
      requestsApi.createRequest.and.returnValue(throwError(() => error422));
      requestsApi.updateRequest.and.returnValue(throwError(() => error422));


      component.saveDraft();
      fixture.detectChanges();

      expect(component.lines.at(1).controls.workspace_product_id.errors?.['server']).toBe(
        'requests.errors.duplicate_product',
      );
      expect(component.form.invalid).toBeTrue();

      // Change line 1 product
      requestsApi.createRequest.calls.reset();
      requestsApi.updateRequest.calls.reset();
      requestsApi.createRequest.and.returnValue(of({ ...mockRequest, id: 'req-saved', lines: [] }));
      requestsApi.updateRequest.and.returnValue(of({ ...mockRequest, id: 'req-saved', lines: [] }));

      component.lines.at(0).controls.workspace_product_id.setValue('wp2');
      fixture.detectChanges();

      expect(component.lines.at(1).controls.workspace_product_id.errors?.['server']).toBeUndefined();
      expect(component.lines.at(1).controls.workspace_product_id.valid).toBeTrue();
      expect(component.form.valid).toBeTrue();

      component.saveDraft();
      expect(requestsApi.updateRequest).toHaveBeenCalled();
    });

    it('set a duplicate-product server error on line 2, remove line 1, expect remaining control to be valid and Save/Submit to proceed', () => {
      component.form.controls.branch_id.setValue('b1');
      component.form.controls.required_by_date.setValue('2026-09-15');
      // Line 1
      component.lines.at(0).controls.workspace_product_id.setValue('wp1');
      component.lines.at(0).controls.quantity.setValue('10');
      // Line 2
      component.addLine();
      component.lines.at(1).controls.workspace_product_id.setValue('wp1');
      component.lines.at(1).controls.quantity.setValue('5');
      fixture.detectChanges();

      const error422 = new HttpErrorResponse({
        status: 422,
        error: {
          code: 'unprocessable',
          message: 'Duplicate product',
          details: { field: 'lines[1].workspace_product_id', reason: 'duplicate_product' },
        },
      });
      requestsApi.createRequest.and.returnValue(throwError(() => error422));
      requestsApi.updateRequest.and.returnValue(throwError(() => error422));


      component.saveDraft();
      fixture.detectChanges();

      expect(component.lines.at(1).controls.workspace_product_id.errors?.['server']).toBe(
        'requests.errors.duplicate_product',
      );
      expect(component.form.invalid).toBeTrue();

      // Remove line 1
      requestsApi.createRequest.calls.reset();
      requestsApi.updateRequest.calls.reset();
      requestsApi.createRequest.and.returnValue(of({ ...mockRequest, id: 'req-saved', lines: [] }));
      requestsApi.updateRequest.and.returnValue(of({ ...mockRequest, id: 'req-saved', lines: [] }));

      component.removeLine(0);
      fixture.detectChanges();

      // Former line 2 is now line 0
      expect(component.lines.at(0).controls.workspace_product_id.errors?.['server']).toBeUndefined();
      expect(component.lines.at(0).controls.workspace_product_id.valid).toBeTrue();
      expect(component.form.valid).toBeTrue();

      component.saveDraft();
      expect(requestsApi.updateRequest).toHaveBeenCalled();
    });
  });

  describe('Review Finding D (#429): Array-shaped validation details and 6-decimal limit', () => {
    it('rejects more than 6 decimal places client-side with quantityPattern error (1.1234567 rejected, 1.123456 accepted)', () => {
      component.lines.at(0).controls.quantity.setValue('1.1234567');
      expect(component.lines.at(0).controls.quantity.hasError('pattern')).toBeTrue();
      expect(component.lines.at(0).controls.quantity.valid).toBeFalse();

      component.lines.at(0).controls.quantity.setValue('1.123456');
      expect(component.lines.at(0).controls.quantity.hasError('pattern')).toBeFalse();
      expect(component.lines.at(0).controls.quantity.valid).toBeTrue();
    });

    it('a 422 with array-shaped details for lines[0].quantity marks line 1 quantity control, shows the inline message and the generic banner; object-shaped details still work', () => {
      component.form.controls.branch_id.setValue('b1');
      component.form.controls.required_by_date.setValue('2026-09-15');
      component.lines.at(0).controls.workspace_product_id.setValue('wp1');
      component.lines.at(0).controls.quantity.setValue('1.5');
      fixture.detectChanges();

      const arrayError422 = new HttpErrorResponse({
        status: 422,
        error: {
          code: 'unprocessable',
          message: 'Validation error',
          details: [
            {
              loc: ['body', 'lines', 0, 'quantity'],
              msg: 'String should match pattern',
              type: 'string_pattern_mismatch',
              field: 'lines[0].quantity',
            },
          ],
        },
      });
      requestsApi.createRequest.and.returnValue(throwError(() => arrayError422));
      requestsApi.updateRequest.and.returnValue(throwError(() => arrayError422));

      component.saveDraft();
      fixture.detectChanges();

      // Control has server error mapped to requests.errors.too_many_decimals
      expect(component.lines.at(0).controls.quantity.errors?.['server']).toBe(
        'requests.errors.too_many_decimals',
      );
      // Inline message rendered in template
      const qtyField = fixture.nativeElement.querySelector(
        'mat-form-field.line-quantity',
      );
      expect(qtyField?.querySelector('mat-error')?.textContent?.trim()).toBe(
        'Quantity can have at most 6 decimals.',
      );
      // Banner displays the generic error
      expect(component.errorMessage()).toBe('Unable to save the purchase request. Please try again.');
    });

    it('object-shaped details still work with field-level server error and translated banner', () => {
      component.form.controls.branch_id.setValue('b1');
      component.form.controls.required_by_date.setValue('2026-09-15');
      component.lines.at(0).controls.workspace_product_id.setValue('wp1');
      component.lines.at(0).controls.quantity.setValue('1.5');
      fixture.detectChanges();

      const objectError422 = new HttpErrorResponse({
        status: 422,
        error: {
          code: 'unprocessable',
          message: 'Date in past',
          details: { field: 'required_by_date', reason: 'required_by_in_the_past' },
        },
      });
      requestsApi.createRequest.and.returnValue(throwError(() => objectError422));
      requestsApi.updateRequest.and.returnValue(throwError(() => objectError422));

      component.saveDraft();
      fixture.detectChanges();

      expect(component.form.controls.required_by_date.errors?.['server']).toBe(
        'requests.errors.required_by_in_the_past',
      );
      expect(component.errorMessage()).toBe('The required-by date cannot be in the past.');
    });
  });

  describe('PPS-189 (2): Stale estimate label', () => {
    it('stale label shows when quantity changed and not when pristine', async () => {
      const draftRequest: PurchaseRequest = {
        ...mockRequest,
        id: 'req-draft-1',
        estimated_total: { amount: '255.00', currency: 'GBP' },
        lines: [
          {
            ...mockRequest.lines[0],
            id: 'line-1',
            quantity: '10.000000',
            estimated_unit_price: { amount: '25.50', currency: 'GBP' },
          },
        ],
      };

      const requestsApiSpy = jasmine.createSpyObj('RequestsApiService', [
        'getRequest',
        'createRequest',
        'updateRequest',
        'submitRequest',
        'submitGroup',
        'withdrawRequest',
        'withdrawGroup',
      ]);
      requestsApiSpy.getRequest.and.returnValue(of(draftRequest));
      const ordersApiSpy = jasmine.createSpyObj('OrdersApiService', ['getAllocations']);
      ordersApiSpy.getAllocations.and.returnValue(of(null));
      const orgApiSpy = jasmine.createSpyObj('OrganisationApiService', ['listBranches', 'listCostCentres']);
      orgApiSpy.listBranches.and.returnValue(of({ items: [], next_cursor: null }));
      orgApiSpy.listCostCentres.and.returnValue(of({ items: [], next_cursor: null }));
      const apiSpy = jasmine.createSpyObj('ApiService', ['members', 'products']);
      apiSpy.members.and.returnValue(of({ items: [], next_cursor: null }));
      apiSpy.products.and.returnValue(of({ items: [], next_cursor: null }));

      await TestBed.resetTestingModule();
      await TestBed.configureTestingModule({
        imports: [RequestFormComponent],
        providers: [
          provideTranslateService(),
          provideRouter([]),
          { provide: RequestsApiService, useValue: requestsApiSpy },
          { provide: OrdersApiService, useValue: ordersApiSpy },
          { provide: OrganisationApiService, useValue: orgApiSpy },
          { provide: ApiService, useValue: apiSpy },
          {
            provide: ActivatedRoute,
            useValue: {
              paramMap: of(convertToParamMap({ id: 'req-draft-1' })),
              snapshot: { paramMap: convertToParamMap({ id: 'req-draft-1' }) },
            },
          },
        ],
      })
        .overrideComponent(RequestFormComponent, {
          set: {
            providers: [
              provideAppDateAdapter(),
              { provide: MatSnackBar, useValue: jasmine.createSpyObj('MatSnackBar', ['open']) },
              { provide: Router, useValue: jasmine.createSpyObj('Router', ['navigate']) },
              { provide: MatDialog, useValue: jasmine.createSpyObj('MatDialog', ['open']) },
            ],
          },
        })
        .compileComponents();

      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog);
      translate.use('en');

      const fixture = TestBed.createComponent(RequestFormComponent);
      const component = fixture.componentInstance;
      fixture.detectChanges();

      const totalLabelEl = fixture.nativeElement.querySelector('.total-label') as HTMLElement;
      expect(totalLabelEl).toBeTruthy();
      // Pristine state: shows regular Estimated Total
      expect(totalLabelEl.textContent?.trim()).toBe('Estimated Total');

      // Change quantity: form becomes dirty and quantity differs from saved line
      const qtyControl = component.lines.at(0).controls.quantity;
      qtyControl.setValue('20');
      qtyControl.markAsDirty();
      component.form.markAsDirty();
      fixture.detectChanges();

      // Dirty + changed quantity: shows stale estimate label
      expect(totalLabelEl.textContent?.trim()).toBe('Saved estimate — save to refresh');
    });
  });

  describe('PPS-189 (3): Line estimates tracking', () => {
    async function createFixtureWithRequest(req: PurchaseRequest) {
      const requestsApiSpy = jasmine.createSpyObj('RequestsApiService', [
        'getRequest',
        'createRequest',
        'updateRequest',
        'submitRequest',
        'submitGroup',
        'withdrawRequest',
        'withdrawGroup',
      ]);
      requestsApiSpy.getRequest.and.returnValue(of(req));
      const ordersApiSpy = jasmine.createSpyObj('OrdersApiService', ['getAllocations']);
      ordersApiSpy.getAllocations.and.returnValue(of(null));
      const orgApiSpy = jasmine.createSpyObj('OrganisationApiService', ['listBranches', 'listCostCentres']);
      orgApiSpy.listBranches.and.returnValue(of({ items: [], next_cursor: null }));
      orgApiSpy.listCostCentres.and.returnValue(of({ items: [], next_cursor: null }));
      const apiSpy = jasmine.createSpyObj('ApiService', ['members', 'products']);
      apiSpy.members.and.returnValue(of({ items: [], next_cursor: null }));
      apiSpy.products.and.returnValue(of({ items: [], next_cursor: null }));

      await TestBed.resetTestingModule();
      await TestBed.configureTestingModule({
        imports: [RequestFormComponent],
        providers: [
          provideTranslateService(),
          provideRouter([]),
          { provide: RequestsApiService, useValue: requestsApiSpy },
          { provide: OrdersApiService, useValue: ordersApiSpy },
          { provide: OrganisationApiService, useValue: orgApiSpy },
          { provide: ApiService, useValue: apiSpy },
          {
            provide: ActivatedRoute,
            useValue: {
              paramMap: of(convertToParamMap({ id: req.id })),
              snapshot: { paramMap: convertToParamMap({ id: req.id }) },
            },
          },
        ],
      })
        .overrideComponent(RequestFormComponent, {
          set: {
            providers: [
              provideAppDateAdapter(),
              { provide: MatSnackBar, useValue: jasmine.createSpyObj('MatSnackBar', ['open']) },
              { provide: Router, useValue: jasmine.createSpyObj('Router', ['navigate']) },
              { provide: MatDialog, useValue: jasmine.createSpyObj('MatDialog', ['open']) },
            ],
          },
        })
        .compileComponents();

      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog);
      translate.use('en');

      const fixture = TestBed.createComponent(RequestFormComponent);
      const component = fixture.componentInstance;
      fixture.detectChanges();
      return { fixture, component };
    }

    it('removing line 1 of 3 keeps each remaining line\'s own price and a new line shows none', async () => {
      const threeLineRequest: PurchaseRequest = {
        ...mockRequest,
        id: 'req-3-lines',
        lines: [
          {
            ...mockRequest.lines[0],
            id: 'line-1',
            workspace_product_id: 'prod-1',
            quantity: '1.000000',
            estimated_unit_price: { amount: '10.00', currency: 'GBP' },
          },
          {
            ...mockRequest.lines[0],
            id: 'line-2',
            workspace_product_id: 'prod-2',
            quantity: '2.000000',
            estimated_unit_price: { amount: '20.00', currency: 'GBP' },
          },
          {
            ...mockRequest.lines[0],
            id: 'line-3',
            workspace_product_id: 'prod-3',
            quantity: '3.000000',
            estimated_unit_price: { amount: '30.00', currency: 'GBP' },
          },
        ],
      };

      const { fixture, component } = await createFixtureWithRequest(threeLineRequest);

      // Remove line 0 (first of 3 lines)
      component.removeLine(0);
      fixture.detectChanges();

      // Add a new line
      component.addLine();
      fixture.detectChanges();

      const lineRows = fixture.nativeElement.querySelectorAll('.line-row') as NodeListOf<HTMLElement>;
      expect(lineRows.length).toBe(3);

      // Remaining line-2 (now at index 0) must show its own price (20), not line-1's (10)
      const line0Estimate = lineRows[0].querySelector('.line-estimate');
      expect(line0Estimate?.textContent).toContain('20');
      expect(line0Estimate?.textContent).not.toContain('10');

      // Remaining line-3 (now at index 1) must show its own price (30), not line-2's (20)
      const line1Estimate = lineRows[1].querySelector('.line-estimate');
      expect(line1Estimate?.textContent).toContain('30');
      expect(line1Estimate?.textContent).not.toContain('10');

      // New line (at index 2) must show NO estimate
      const line2Estimate = lineRows[2].querySelector('.line-estimate');
      expect(line2Estimate).toBeNull();
    });

    it('saved draft line whose product is changed in the form shows NO per-line estimate in the DOM (and getLineEstimate returns null), while the other unchanged lines keep theirs', async () => {
      const twoLineRequest: PurchaseRequest = {
        ...mockRequest,
        id: 'req-2-lines-changed-product',
        lines: [
          {
            ...mockRequest.lines[0],
            id: 'line-1',
            workspace_product_id: 'prod-1',
            quantity: '1.000000',
            estimated_unit_price: { amount: '10.00', currency: 'GBP' },
          },
          {
            ...mockRequest.lines[0],
            id: 'line-2',
            workspace_product_id: 'prod-2',
            quantity: '2.000000',
            estimated_unit_price: { amount: '20.00', currency: 'GBP' },
          },
        ],
      };

      const { fixture, component } = await createFixtureWithRequest(twoLineRequest);

      let lineRows = fixture.nativeElement.querySelectorAll('.line-row') as NodeListOf<HTMLElement>;
      expect(lineRows.length).toBe(2);
      expect(component.getLineEstimate(component.lines.at(0))).toContain('10');
      expect(component.getLineEstimate(component.lines.at(1))).toContain('20');
      expect(lineRows[0].querySelector('.line-estimate')?.textContent).toContain('10');
      expect(lineRows[1].querySelector('.line-estimate')?.textContent).toContain('20');

      // Change product on line 0
      component.lines.at(0).controls.workspace_product_id.setValue('prod-changed');
      component.lines.at(0).controls.workspace_product_id.markAsDirty();
      component.form.markAsDirty();
      fixture.detectChanges();

      lineRows = fixture.nativeElement.querySelectorAll('.line-row') as NodeListOf<HTMLElement>;

      // Changed line shows NO estimate in DOM and getLineEstimate returns null
      expect(component.getLineEstimate(component.lines.at(0))).toBeNull();
      expect(lineRows[0].querySelector('.line-estimate')).toBeNull();

      // Other unchanged line keeps its estimate in DOM and getLineEstimate
      expect(component.getLineEstimate(component.lines.at(1))).toContain('20');
      const line1Estimate = lineRows[1].querySelector('.line-estimate');
      expect(line1Estimate).not.toBeNull();
      expect(line1Estimate?.textContent).toContain('20');
    });

    it('changing the product back to the saved one shows the estimate again', async () => {
      const singleLineRequest: PurchaseRequest = {
        ...mockRequest,
        id: 'req-1-line-toggle-product',
        lines: [
          {
            ...mockRequest.lines[0],
            id: 'line-1',
            workspace_product_id: 'prod-1',
            quantity: '1.000000',
            estimated_unit_price: { amount: '10.00', currency: 'GBP' },
          },
        ],
      };

      const { fixture, component } = await createFixtureWithRequest(singleLineRequest);

      expect(component.getLineEstimate(component.lines.at(0))).toContain('10');
      expect(fixture.nativeElement.querySelector('.line-estimate')?.textContent).toContain('10');

      // Change product to a different product
      component.lines.at(0).controls.workspace_product_id.setValue('prod-different');
      component.lines.at(0).controls.workspace_product_id.markAsDirty();
      component.form.markAsDirty();
      fixture.detectChanges();

      // Estimate must be hidden while product is changed
      expect(component.getLineEstimate(component.lines.at(0))).toBeNull();
      expect(fixture.nativeElement.querySelector('.line-estimate')).toBeNull();

      // Change product back to the saved product
      component.lines.at(0).controls.workspace_product_id.setValue('prod-1');
      fixture.detectChanges();

      // Estimate is restored in DOM and getLineEstimate
      expect(component.getLineEstimate(component.lines.at(0))).toContain('10');
      const restoredEstimate = fixture.nativeElement.querySelector('.line-estimate');
      expect(restoredEstimate).not.toBeNull();
      expect(restoredEstimate?.textContent).toContain('10');
    });
  });

  describe('PPS-189 (4): Line estimate per-pack label', () => {
    it('the «/ pack» format', () => {
      const lineWithEstimate = {
        ...mockRequest.lines[0],
        estimated_unit_price: { amount: '87.00', currency: 'SAR' },
      };
      // In English
      expect(component.formatEstimate(lineWithEstimate)).toBe('SAR 87 / pack');

      // In Arabic
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('ar', {
        requests: {
          form: {
            perPack: '{{price}} / العبوة',
            noEstimateAvailable: 'لا توجد بيانات أسعار سابقة لهذا المنتج.',
          },
        },
      }, true);
      translate.use('ar');
      expect(component.formatEstimate(lineWithEstimate)).toBe('٨٧ ر.س / العبوة');
      translate.use('en');
    });
  });

  describe('PPS-189 (5): Pagination lookup', () => {
    it('two-page products/branches/cost-centres fully loaded', async () => {
      const prodPage1: Product = {
        id: 'prod-1',
        tenant_name: 'Product 1',
        canonical_name: 'Product 1',
        base_unit: 'each',
        pack: { pack_count: 1, unit_size: '1' },
        status: 'active',
        created_at: '2026-01-01T00:00:00Z',
      };
      const prodPage2: Product = {
        id: 'prod-2',
        tenant_name: 'Product 2',
        canonical_name: 'Product 2',
        base_unit: 'each',
        pack: { pack_count: 1, unit_size: '1' },
        status: 'active',
        created_at: '2026-01-01T00:00:00Z',
      };

      const brPage1 = {
        id: 'br-1',
        name: 'Branch 1',
        is_active: true,
        created_at: '2026-01-01T00:00:00Z',
      };
      const brPage2 = {
        id: 'br-2',
        name: 'Branch 2',
        is_active: true,
        created_at: '2026-01-01T00:00:00Z',
      };

      const ccPage1 = {
        id: 'cc-1',
        name: 'Cost Centre 1',
        code: 'CC1',
        branch_id: null,
        is_orphaned: false,
        is_archived: false,
        created_at: '2026-01-01T00:00:00Z',
      };
      const ccPage2 = {
        id: 'cc-2',
        name: 'Cost Centre 2',
        code: 'CC2',
        branch_id: null,
        is_orphaned: false,
        is_archived: false,
        created_at: '2026-01-01T00:00:00Z',
      };

      const requestsApiSpy = jasmine.createSpyObj('RequestsApiService', [
        'getRequest',
        'createRequest',
        'updateRequest',
        'submitRequest',
        'submitGroup',
        'withdrawRequest',
        'withdrawGroup',
      ]);
      const ordersApiSpy = jasmine.createSpyObj('OrdersApiService', ['getAllocations']);
      const orgApiSpy = jasmine.createSpyObj('OrganisationApiService', ['listBranches', 'listCostCentres']);
      const apiSpy = jasmine.createSpyObj('ApiService', ['members', 'products']);
      apiSpy.members.and.returnValue(of({ items: [], next_cursor: null }));

      apiSpy.products.and.callFake((params?: { cursor?: string }) => {
        if (!params?.cursor) {
          return of({ items: [prodPage1], next_cursor: 'cur-prod-2' });
        }
        if (params.cursor === 'cur-prod-2') {
          return of({ items: [prodPage2], next_cursor: null });
        }
        return of({ items: [], next_cursor: null });
      });

      orgApiSpy.listBranches.and.callFake((params?: { cursor?: string }) => {
        if (!params?.cursor) {
          return of({ items: [brPage1], next_cursor: 'cur-br-2' });
        }
        if (params.cursor === 'cur-br-2') {
          return of({ items: [brPage2], next_cursor: null });
        }
        return of({ items: [], next_cursor: null });
      });

      orgApiSpy.listCostCentres.and.callFake((params?: { cursor?: string }) => {
        if (!params?.cursor) {
          return of({ items: [ccPage1], next_cursor: 'cur-cc-2' });
        }
        if (params.cursor === 'cur-cc-2') {
          return of({ items: [ccPage2], next_cursor: null });
        }
        return of({ items: [], next_cursor: null });
      });

      await TestBed.resetTestingModule();
      await TestBed.configureTestingModule({
        imports: [RequestFormComponent],
        providers: [
          provideTranslateService(),
          provideRouter([]),
          { provide: RequestsApiService, useValue: requestsApiSpy },
          { provide: OrdersApiService, useValue: ordersApiSpy },
          { provide: OrganisationApiService, useValue: orgApiSpy },
          { provide: ApiService, useValue: apiSpy },
          {
            provide: ActivatedRoute,
            useValue: {
              paramMap: of(convertToParamMap({})),
              snapshot: { paramMap: convertToParamMap({}) },
            },
          },
        ],
      })
        .overrideComponent(RequestFormComponent, {
          set: {
            providers: [
              provideAppDateAdapter(),
              { provide: MatSnackBar, useValue: jasmine.createSpyObj('MatSnackBar', ['open']) },
              { provide: Router, useValue: jasmine.createSpyObj('Router', ['navigate']) },
              { provide: MatDialog, useValue: jasmine.createSpyObj('MatDialog', ['open']) },
            ],
          },
        })
        .compileComponents();

      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('en', enCatalog);
      translate.use('en');

      const fixture = TestBed.createComponent(RequestFormComponent);
      const component = fixture.componentInstance;
      fixture.detectChanges();

      expect(component.products().map((p) => p.id)).toEqual(['prod-1', 'prod-2']);
      expect(component.branches().map((b) => b.id)).toEqual(['br-1', 'br-2']);
      expect(component.allCostCentres().map((cc) => cc.id)).toEqual(['cc-1', 'cc-2']);
    });
  });

  describe('PPS-191 Point 1: Inline field errors', () => {
    it('shows inline mat-error for branch when touched and empty', () => {
      const branchField = fixture.nativeElement.querySelector('mat-form-field:has(mat-select[formcontrolname="branch_id"])');
      expect(branchField?.querySelector('mat-error')).toBeNull();

      component.form.controls.branch_id.setValue('');
      component.form.controls.branch_id.markAsTouched();
      fixture.detectChanges();

      const error = branchField?.querySelector('mat-error');
      expect(error).toBeTruthy();
      expect(error?.textContent?.trim()).toBe('Branch is required.');
    });

    it('shows inline mat-error for required-by date when touched and empty', () => {
      const dateField = fixture.nativeElement.querySelector('mat-form-field:has(input[formcontrolname="required_by_date"])');
      expect(dateField?.querySelector('mat-error')).toBeNull();

      component.form.controls.required_by_date.setValue(null);
      component.form.controls.required_by_date.markAsTouched();
      fixture.detectChanges();

      const error = dateField?.querySelector('mat-error');
      expect(error).toBeTruthy();
      expect(error?.textContent?.trim()).toBe('Required-by date is required.');
    });

    it('shows inline mat-error for product on line when touched and empty', () => {
      const productField = fixture.nativeElement.querySelector('.line-product');
      expect(productField?.querySelector('mat-error')).toBeNull();

      component.lines.at(0).controls.workspace_product_id.setValue('');
      component.lines.at(0).controls.workspace_product_id.markAsTouched();
      fixture.detectChanges();

      const error = productField?.querySelector('mat-error');
      expect(error).toBeTruthy();
      expect(error?.textContent?.trim()).toBe('Select a product.');
    });

    it('shows inline mat-error for quantity on line when empty or invalid pattern', () => {
      const quantityField = fixture.nativeElement.querySelector('.line-quantity');
      expect(quantityField?.querySelector('mat-error')).toBeNull();

      // Empty quantity -> required error
      component.lines.at(0).controls.quantity.setValue('');
      component.lines.at(0).controls.quantity.markAsTouched();
      fixture.detectChanges();

      let error = quantityField?.querySelector('mat-error');
      expect(error).toBeTruthy();
      expect(error?.textContent?.trim()).toBe('Quantity must be greater than zero.');

      // Zero or non-positive quantity -> pattern error
      component.lines.at(0).controls.quantity.setValue('0');
      component.lines.at(0).controls.quantity.markAsTouched();
      fixture.detectChanges();

      error = quantityField?.querySelector('mat-error');
      expect(error).toBeTruthy();
      expect(error?.textContent?.trim()).toBe('Quantity must be a number greater than zero.');
    });
  });

  describe('PPS-191 Point 2: Error banner focus and scroll', () => {
    it('sets tabindex=-1 on error banner, scrolls it into view, and moves focus to it on failed submit', async () => {
      const scrollSpy = spyOn(HTMLElement.prototype, 'scrollIntoView').and.callThrough();
      const focusSpy = spyOn(HTMLElement.prototype, 'focus').and.callThrough();

      component.form.controls.branch_id.setValue('');
      component.submitRequest();
      fixture.detectChanges();

      await new Promise((resolve) => setTimeout(resolve, 50));
      fixture.detectChanges();

      const banner = fixture.nativeElement.querySelector('.error-banner') as HTMLElement;
      expect(banner).toBeTruthy();
      expect(banner.getAttribute('tabindex')).toBe('-1');
      expect(scrollSpy).toHaveBeenCalled();
      expect(focusSpy).toHaveBeenCalled();
    });
  });

  describe('PPS-191 Point 3: Save draft enabled when invalid', () => {
    it('keeps Save Draft button enabled when form is invalid, and clicking it displays inline errors and banner', () => {
      component.form.controls.branch_id.setValue('');
      fixture.detectChanges();

      const saveBtn = fixture.nativeElement.querySelector('button[type="submit"]') as HTMLButtonElement;
      expect(saveBtn).toBeTruthy();
      expect(saveBtn.disabled).toBeFalse();

      saveBtn.click();
      fixture.detectChanges();

      expect(requestsApi.createRequest).not.toHaveBeenCalled();
      expect(requestsApi.updateRequest).not.toHaveBeenCalled();
      expect(component.form.controls.branch_id.touched).toBeTrue();
      expect(component.errorMessage()).toBe('Branch is required.');
    });
  });

  describe('PPS-191 Point 4: Server field errors', () => {
    it('maps 422 server field errors to inline control errors and error banner for known reasons', () => {
      component.form.controls.branch_id.setValue('b1');
      component.form.controls.required_by_date.setValue('2026-09-15');
      component.lines.at(0).controls.workspace_product_id.setValue('wp1');
      component.lines.at(0).controls.quantity.setValue('10');

      const error422 = new HttpErrorResponse({
        status: 422,
        error: {
          code: 'unprocessable',
          message: 'Raw date in past message',
          details: { field: 'required_by_date', reason: 'required_by_in_the_past' },
        },
      });
      requestsApi.createRequest.and.returnValue(throwError(() => error422));
      requestsApi.updateRequest.and.returnValue(throwError(() => error422));


      component.saveDraft();
      fixture.detectChanges();

      expect(component.form.controls.required_by_date.errors?.['server']).toBe(
        'requests.errors.required_by_in_the_past',
      );
      const dateField = fixture.nativeElement.querySelector(
        'mat-form-field:has(input[formcontrolname="required_by_date"])',
      );
      expect(dateField?.querySelector('mat-error')?.textContent?.trim()).toBe(
        'The required-by date cannot be in the past.',
      );
      expect(component.errorMessage()).toBe('The required-by date cannot be in the past.');
    });

    it('falls back to requests.genericError on unknown error reason and never displays raw English apiError.message', () => {
      component.form.controls.branch_id.setValue('b1');
      component.form.controls.required_by_date.setValue('2026-09-15');
      component.lines.at(0).controls.workspace_product_id.setValue('wp1');
      component.lines.at(0).controls.quantity.setValue('10');

      const error422 = new HttpErrorResponse({
        status: 422,
        error: {
          code: 'unprocessable',
          message: 'Raw database constraint failure',
          details: { reason: 'unknown_weird_reason' },
        },
      });
      requestsApi.createRequest.and.returnValue(throwError(() => error422));
      requestsApi.updateRequest.and.returnValue(throwError(() => error422));


      component.saveDraft();
      fixture.detectChanges();

      expect(component.errorMessage()).toBe('Unable to save the purchase request. Please try again.');
      expect(component.errorMessage()).not.toContain('Raw database constraint failure');
    });
  });

  describe('PPS-191 Point 5: Repeated labels', () => {
    it('wraps each line row in role="group" with Line {position} aria-label and gives remove button position and product name', () => {
      // In edit mode beforeEach, line 0 has product wp1 (Nitrile Gloves)
      fixture.detectChanges();

      const lineRows = fixture.nativeElement.querySelectorAll('.line-row') as NodeListOf<HTMLElement>;
      expect(lineRows.length).toBe(1);

      const row0 = lineRows[0];
      expect(row0.getAttribute('role')).toBe('group');
      expect(row0.getAttribute('aria-label')).toBe('Line 1');

      const removeBtn = row0.querySelector('.remove-line-btn') as HTMLButtonElement;
      expect(removeBtn).toBeTruthy();
      expect(removeBtn.getAttribute('aria-label')).toBe('Remove line 1: Nitrile Gloves');
    });
  });

  describe('PPS-191 Point 6: Arabic ordered status label', () => {
    it('translates ordered status in Arabic to تم إصدار أمر الشراء', () => {
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('ar', arCatalog, true);
      translate.use('ar');

      component.existingRequest.set({ ...mockRequest, status: 'ordered' });
      fixture.detectChanges();

      const chip = fixture.nativeElement.querySelector('[data-testid="request-status-chip"]') as HTMLElement;
      expect(chip).toBeTruthy();
      expect(chip.textContent?.trim()).toBe('تم إصدار أمر الشراء');

      translate.use('en');
    });
  });

  describe('PPS-191 Point 7: Date format hint', () => {
    it('displays date format hint for required-by date field in en and ar', () => {
      const dateField = fixture.nativeElement.querySelector(
        'mat-form-field:has(input[formcontrolname="required_by_date"])',
      ) as HTMLElement;
      expect(dateField).toBeTruthy();

      const hint = dateField.querySelector('mat-hint');
      expect(hint).toBeTruthy();
      expect(hint?.textContent?.trim()).toBe('Format: DD/MM/YYYY');

      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('ar', arCatalog, true);
      translate.use('ar');
      fixture.detectChanges();

      const arHint = dateField.querySelector('mat-hint');
      expect(arHint?.textContent?.trim()).toBe('التنسيق: DD/MM/YYYY');

      translate.use('en');
    });
  });
});

// PPS-190: specs written before the implementation; Karma red/green is owned by the orchestrator.
describe('RequestFormComponent — PPS-190 draft actions', () => {
  let fixture: ComponentFixture<RequestFormComponent>;
  let component: RequestFormComponent;
  let requestsApi: jasmine.SpyObj<RequestsApiService>;
  let router: jasmine.SpyObj<Router>;
  let dialog: jasmine.SpyObj<MatDialog>;
  let snackBar: jasmine.SpyObj<MatSnackBar>;
  let params: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  let query: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  let confirmation: Subject<boolean>;
  let centres: Subject<{ items: CostCentre[]; next_cursor: null }>;

  beforeEach(async () => {
    params = new BehaviorSubject(convertToParamMap({ id: 'r1' }));
    query = new BehaviorSubject(convertToParamMap({}));
    confirmation = new Subject<boolean>();
    centres = new Subject();
    requestsApi = jasmine.createSpyObj('RequestsApiService', [
      'getRequest', 'withdrawRequest', 'withdrawGroup', 'createRequest', 'updateRequest',
    ]);
    requestsApi.getRequest.and.returnValue(of(mockRequest));
    requestsApi.withdrawRequest.and.returnValue(of({ ...mockRequest, status: 'withdrawn' }));
    router = jasmine.createSpyObj('Router', ['navigate']);
    dialog = jasmine.createSpyObj('MatDialog', ['open']);
    snackBar = jasmine.createSpyObj('MatSnackBar', ['open']);
    dialog.open.and.returnValue({ afterClosed: () => confirmation.asObservable() } as ReturnType<MatDialog['open']>);
    await TestBed.configureTestingModule({
      imports: [RequestFormComponent],
      providers: [
        provideTranslateService(), provideRouter([]),
        { provide: RequestsApiService, useValue: requestsApi },
        { provide: OrdersApiService, useValue: jasmine.createSpyObj('OrdersApiService', ['getAllocations']) },
        { provide: OrganisationApiService, useValue: {
          listBranches: () => of({ items: [], next_cursor: null }),
          listCostCentres: () => centres,
        } },
        { provide: ApiService, useValue: {
          products: () => of({ items: [], next_cursor: null }),
          members: () => of({ items: [], next_cursor: null }),
        } },
        { provide: ActivatedRoute, useValue: { paramMap: params, queryParamMap: query } },
      ],
    }).overrideComponent(RequestFormComponent, { set: { providers: [
      provideAppDateAdapter(),
      { provide: Router, useValue: router },
      { provide: MatDialog, useValue: dialog },
      { provide: MatSnackBar, useValue: snackBar },
    ] } }).compileComponents();
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.setTranslation('ar', arCatalog);
    translate.use('en');
    fixture = TestBed.createComponent(RequestFormComponent);
    component = fixture.componentInstance;
  });

  function start(duplicateFrom?: string): void {
    if (duplicateFrom) {
      params.next(convertToParamMap({}));
      query.next(convertToParamMap({ duplicate_from: duplicateFrom }));
    }
    fixture.detectChanges();
    centres.next({ items: [
      { id: 'cc1', branch_id: 'b1', name: 'Centre', code: 'CC', is_archived: false, is_orphaned: false, created_at: '' },
      { id: 'cc2', branch_id: 'b2', name: 'Other', code: 'CC2', is_archived: false, is_orphaned: false, created_at: '' },
    ], next_cursor: null });
    centres.complete();
    fixture.detectChanges();
  }

  function button(selector: string): HTMLButtonElement | null {
    return fixture.nativeElement.querySelector(selector);
  }

  it('shows Discard only for a non-split draft', () => {
    start();
    expect(button('.discard-draft-btn')?.textContent).toContain('Discard draft');
    for (const req of [
      { ...mockRequest, request_group: { id: 'g', rfq_id: 'rfq', position: 1, size: 2, sibling_request_ids: [], combined_total: { amount: '1', currency: 'GBP' } } },
      ...(['submitted', 'withdrawn', 'rejected', 'approved', 'ordered'] as const).map(status => ({ ...mockRequest, status })),
    ]) {
      component.existingRequest.set(req);
      fixture.detectChanges();
      expect(button('.discard-draft-btn')).toBeNull();
    }
  });

  it('opens the destructive discard confirmation and cancellation does nothing', () => {
    start();
    button('.discard-draft-btn')!.click();
    expect(dialog.open).toHaveBeenCalledWith(jasmine.any(Function), jasmine.objectContaining({ data: {
      titleKey: 'requests.discard.title', messageKey: 'requests.discard.message',
      confirmKey: 'requests.discard.confirm', isDestructive: true,
    } }));
    confirmation.next(false);
    expect(requestsApi.withdrawRequest).not.toHaveBeenCalled();
    expect(snackBar.open).not.toHaveBeenCalled();
    expect(router.navigate).not.toHaveBeenCalled();
  });

  it('confirms discard with a stable idempotency key, then shows success and navigates', () => {
    start();
    requestsApi.withdrawRequest.and.returnValue(throwError(() => new HttpErrorResponse({ status: 500 })));
    button('.discard-draft-btn')!.click();
    confirmation.next(true);
    const key = requestsApi.withdrawRequest.calls.mostRecent().args[1];
    expect(key).toEqual(jasmine.any(String));
    expect(component.errorMessage()).toBe(enCatalog.requests.genericError);
    expect(router.navigate).not.toHaveBeenCalled();
    requestsApi.withdrawRequest.and.returnValue(of({ ...mockRequest, status: 'withdrawn' }));
    confirmation.next(true);
    expect(requestsApi.withdrawRequest).toHaveBeenCalledWith('r1', key);
    expect(requestsApi.withdrawGroup).not.toHaveBeenCalled();
    expect(snackBar.open).toHaveBeenCalledWith('Draft discarded.', undefined, { duration: 3500 });
    expect(router.navigate).toHaveBeenCalledWith(['/requests']);
  });

  it('shows Duplicate only for withdrawn and rejected and navigates with duplicate_from', () => {
    start();
    for (const status of ['draft', 'submitted', 'approved', 'ordered', 'withdrawn', 'rejected'] as const) {
      component.existingRequest.set({ ...mockRequest, status });
      fixture.detectChanges();
      const duplicate = button('.duplicate-request-btn');
      if (status === 'withdrawn' || status === 'rejected') {
        expect(duplicate?.textContent).toContain('Duplicate as new draft');
        duplicate!.click();
        expect(router.navigate).toHaveBeenCalledWith(['/requests/new'], { queryParams: { duplicate_from: 'r1' } });
      } else {
        expect(duplicate).toBeNull();
      }
    }
  });

  it('prefills only branch, valid cost centre and editable lines with notes and no date or metadata', () => {
    requestsApi.getRequest.and.returnValue(of({ ...mockRequest, status: 'rejected',
      source_rfq_response_id: 'response',
      source: { rfq_id: 'rfq', rfq_response_id: 'response', quotation_id: 'quote', supplier_id: 'supplier' },
      request_group: { id: 'g', rfq_id: 'rfq', position: 1, size: 2, sibling_request_ids: ['sibling'], combined_total: { amount: '50', currency: 'GBP' } },
      approval_step: { id: 'approval', assigned_membership_id: 'm1', source: 'owner_fallback', status: 'rejected' },
      estimated_total: { amount: '50', currency: 'GBP' },
      lines: [
      { ...mockRequest.lines[0], quantity: '999999999999.999900', note: 'Keep this note' },
    ] }));
    start('r1');
    expect(component.isEditMode()).toBeFalse();
    expect(component.existingRequest()).toBeNull();
    expect(component.form.enabled).toBeTrue();
    expect(component.form.getRawValue()).toEqual({ branch_id: 'b1', cost_centre_id: 'cc1', required_by_date: null,
      lines: [{ workspace_product_id: 'wp1', quantity: '999999999999.9999', note: 'Keep this note' }] });
    expect(component.getLineEstimate(component.lines.at(0))).toBeNull();
    expect(fixture.nativeElement.querySelector('.request-source-line, .split-info-line, .approval-step, .total-row')).toBeNull();
    const banner = fixture.nativeElement.querySelector('.duplicate-banner');
    expect(banner?.getAttribute('role')).toBe('status');
    expect(banner?.textContent).toContain('Copied from a Rejected request. Choose a new required-by date and review the lines.');
    component.saveDraft();
    expect(requestsApi.createRequest).not.toHaveBeenCalled();
    expect(component.form.controls.required_by_date.hasError('required')).toBeTrue();
  });

  it('drops cost centres missing from the loaded branch options', () => {
    requestsApi.getRequest.and.returnValue(of({ ...mockRequest, cost_centre_id: 'cc2' }));
    start('r1');
    expect(component.form.controls.cost_centre_id.value).toBe('');
    requestsApi.getRequest.and.returnValue(of({ ...mockRequest, cost_centre_id: 'deleted' }));
    query.next(convertToParamMap({ duplicate_from: 'r2' }));
    expect(component.form.controls.cost_centre_id.value).toBe('');
  });

  for (const status of [404, 500]) {
    it(`falls back to an empty create form and generic error on duplicate source ${status}`, () => {
      requestsApi.getRequest.and.returnValue(throwError(() => new HttpErrorResponse({ status })));
      start('missing');
      expect(component.existingRequest()).toBeNull();
      expect(component.form.getRawValue()).toEqual({ branch_id: '', cost_centre_id: '', required_by_date: null,
        lines: [{ workspace_product_id: '', quantity: '', note: '' }] });
      expect(component.errorMessage()).toBe(enCatalog.requests.genericError);
      expect(fixture.nativeElement.querySelector('.duplicate-banner')).toBeNull();
    });
  }

  it('reloads from detail to duplicate, then a second source, then plain new', () => {
    start();
    requestsApi.getRequest.and.returnValue(of({ ...mockRequest, status: 'withdrawn' }));
    params.next(convertToParamMap({}));
    query.next(convertToParamMap({ duplicate_from: 'r1' }));
    expect(component.form.controls.branch_id.value).toBe('b1');
    requestsApi.getRequest.and.returnValue(of({ ...mockRequest, branch_id: 'b2', status: 'rejected' }));
    query.next(convertToParamMap({ duplicate_from: 'r2' }));
    fixture.detectChanges();
    expect(requestsApi.getRequest).toHaveBeenCalledWith('r2');
    expect(component.form.controls.branch_id.value).toBe('b2');
    expect(fixture.nativeElement.querySelector('.duplicate-banner')?.textContent).toContain('Rejected');
    query.next(convertToParamMap({}));
    fixture.detectChanges();
    expect(component.form.controls.branch_id.value).toBe('');
    expect(component.lines.length).toBe(1);
    expect(component.lines.at(0).controls.workspace_product_id.value).toBe('');
    expect(fixture.nativeElement.querySelector('.duplicate-banner')).toBeNull();
  });

  it('saves a duplicate as a new draft and preserves it when the saved-id route emits', () => {
    start('r1');
    component.form.controls.required_by_date.setValue(new Date(2099, 0, 1));
    requestsApi.createRequest.and.returnValue(of({ ...mockRequest, id: 'new-draft' }));
    requestsApi.getRequest.calls.reset();
    component.saveDraft();
    expect(requestsApi.createRequest).toHaveBeenCalledOnceWith({
      branch_id: 'b1', cost_centre_id: 'cc1', required_by_date: '2099-01-01',
      lines: [{ workspace_product_id: 'wp1', quantity: '10', note: null }],
    });
    expect(requestsApi.updateRequest).not.toHaveBeenCalled();
    expect(router.navigate).toHaveBeenCalledWith(['/requests', 'new-draft']);
    params.next(convertToParamMap({ id: 'new-draft' }));
    query.next(convertToParamMap({}));
    fixture.detectChanges();
    expect(requestsApi.getRequest).not.toHaveBeenCalled();
    expect(component.existingRequest()?.id).toBe('new-draft');
    expect(component.lines.length).toBe(1);
    expect(fixture.nativeElement.querySelector('.duplicate-banner')).toBeNull();
  });

  it('keeps plain new empty with one line and ignores duplicate_from in edit mode', () => {
    params.next(convertToParamMap({}));
    start();
    expect(component.lines.length).toBe(1);
    expect(component.form.controls.branch_id.value).toBe('');
    expect(requestsApi.getRequest).not.toHaveBeenCalled();
    query.next(convertToParamMap({ duplicate_from: 'other' }));
    requestsApi.getRequest.calls.reset();
    params.next(convertToParamMap({ id: 'r1' }));
    expect(requestsApi.getRequest).toHaveBeenCalledOnceWith('r1');
    expect(component.existingRequest()?.id).toBe('r1');
  });
});
