import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { MatSnackBar } from '@angular/material/snack-bar';
import { By } from '@angular/platform-browser';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { ApiService } from '../../../core/api/api.service';
import type { Product } from '../../../core/api/models';
import { PosApiService, type PosProductMatch, type SyncedProductSignal, type TriggerSyncResponse } from '../pos-api';
import { SignalsReviewComponent } from './signals-review.component';

describe('SignalsReviewComponent (T027)', () => {
  let component: SignalsReviewComponent;
  let fixture: ComponentFixture<SignalsReviewComponent>;
  let posApiService: jasmine.SpyObj<PosApiService>;
  let apiService: jasmine.SpyObj<ApiService>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;

  const mockProduct: Product = {
    id: 'prod-001',
    tenant_name: 'Organic Espresso Roast',
    canonical_name: 'Organic Espresso Roast',
    brand: 'CoffeeCo',
    variant: '1kg Whole Bean',
    gtin: null,
    base_unit: 'kg',
    pack: {
      pack_count: 1,
      unit_size: '1.000000',
      base_quantity: '1.000000',
    },
    preferred_supplier_id: null,
    status: 'active',
    created_at: '2026-09-01T00:00:00Z',
  };

  const mockUnmatchedSignal: SyncedProductSignal = {
    id: 'sig-unmatched-1',
    external_item_name: 'Square Item - Unmatched Blend',
    matched: false,
    matched_workspace_product_id: null,
    stock_on_hand: '25.000',
    stock_synced_at: '2026-09-19T10:00:00Z',
    sales_velocity_per_day: '3.200',
    velocity_window_days: 30,
    velocity_window_days_observed: 30,
    velocity_computed_at: '2026-09-19T10:00:00Z',
  };

  const mockMatchedSignal: SyncedProductSignal = {
    id: 'sig-matched-1',
    external_item_name: 'Square Item - Organic Espresso',
    matched: true,
    matched_workspace_product_id: 'prod-001',
    stock_on_hand: '12.000',
    stock_synced_at: '2026-09-19T10:00:00Z',
    sales_velocity_per_day: '5.400',
    velocity_window_days: 30,
    velocity_window_days_observed: 30,
    velocity_computed_at: '2026-09-19T10:00:00Z',
  };

  beforeEach(async () => {
    posApiService = jasmine.createSpyObj<PosApiService>('PosApiService', [
      'listSignals',
      'triggerSync',
      'manuallyMatchSignal',
    ]);
    apiService = jasmine.createSpyObj<ApiService>('ApiService', ['products']);
    snackBarSpy = jasmine.createSpyObj<MatSnackBar>('MatSnackBar', ['open']);

    apiService.products.and.returnValue(
      of({ items: [mockProduct], next_cursor: null }),
    );

    posApiService.listSignals.and.callFake((params) => {
      if (params?.matchStatus === 'unmatched') {
        return of({ items: [mockUnmatchedSignal], next_cursor: null });
      }
      if (params?.matchStatus === 'matched') {
        return of({ items: [mockMatchedSignal], next_cursor: null });
      }
      return of({ items: [mockUnmatchedSignal, mockMatchedSignal], next_cursor: null });
    });

    posApiService.triggerSync.and.returnValue(
      of({ status: 'enqueued' } as TriggerSyncResponse),
    );

    const mockMatchResult: PosProductMatch = {
      id: 'match-001',
      synced_product_signal_id: mockUnmatchedSignal.id,
      workspace_product_id: mockProduct.id,
      match_method: 'manual',
      matched_at: '2026-09-19T12:00:00Z',
    };
    posApiService.manuallyMatchSignal.and.returnValue(of(mockMatchResult));

    await TestBed.configureTestingModule({
      imports: [SignalsReviewComponent, TranslateModule.forRoot()],
      providers: [
        provideNoopAnimations(),
        { provide: PosApiService, useValue: posApiService },
        { provide: ApiService, useValue: apiService },
      ],
    })
      // A plain top-level provider override is silently ignored for MatSnackBar on this
      // standalone component — must override at the component level instead (see
      // accounting/connection-settings.component.spec.ts's own identical workaround).
      .overrideComponent(SignalsReviewComponent, {
        set: { providers: [{ provide: MatSnackBar, useValue: snackBarSpy }] },
      })
      .compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(SignalsReviewComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should be created', () => {
    expect(component).toBeTruthy();
  });

  it('renders unmatched list', () => {
    const unmatchedSection = fixture.debugElement.query(By.css('[data-testid="unmatched-section"]'));
    expect(unmatchedSection).toBeTruthy();

    const unmatchedList = fixture.debugElement.query(By.css('[data-testid="unmatched-list"]'));
    expect(unmatchedList).toBeTruthy();

    const itemNameEl = fixture.debugElement.query(By.css('[data-testid="unmatched-item-name"]'));
    expect(itemNameEl.nativeElement.textContent).toContain('Square Item - Unmatched Blend');
  });

  it('renders matched list', () => {
    const matchedSection = fixture.debugElement.query(By.css('[data-testid="matched-section"]'));
    expect(matchedSection).toBeTruthy();

    const matchedList = fixture.debugElement.query(By.css('[data-testid="matched-list"]'));
    expect(matchedList).toBeTruthy();

    const itemNameEl = fixture.debugElement.query(By.css('[data-testid="matched-item-name"]'));
    expect(itemNameEl.nativeElement.textContent).toContain('Square Item - Organic Espresso');

    const productNameEl = fixture.debugElement.query(By.css('[data-testid="matched-product-name"]'));
    expect(productNameEl.nativeElement.textContent).toContain('Organic Espresso Roast (1kg Whole Bean)');
  });

  it('match action calls the API and refreshes the list', fakeAsync(() => {
    // Select product for the unmatched signal
    component.onProductSelect(mockUnmatchedSignal.id, mockProduct.id);
    fixture.detectChanges();

    const initialListSignalsCallCount = posApiService.listSignals.calls.count();

    // Trigger match
    component.matchSignal(mockUnmatchedSignal.id);
    tick();

    expect(posApiService.manuallyMatchSignal).toHaveBeenCalledWith(
      mockUnmatchedSignal.id,
      mockProduct.id,
    );

    // Verify list refreshed (listSignals called again)
    expect(posApiService.listSignals.calls.count()).toBeGreaterThan(initialListSignalsCallCount);
    expect(snackBarSpy.open).toHaveBeenCalled();
  }));

  it('sync button calls triggerSync()', fakeAsync(() => {
    const syncBtn = fixture.debugElement.query(By.css('[data-testid="sync-btn"]'));
    expect(syncBtn).toBeTruthy();

    syncBtn.nativeElement.click();
    tick();

    expect(posApiService.triggerSync).toHaveBeenCalled();
    expect(snackBarSpy.open).toHaveBeenCalled();
  }));
});
