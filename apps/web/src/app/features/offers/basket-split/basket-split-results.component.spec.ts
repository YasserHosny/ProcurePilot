import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import ar from '../../../../../../../packages/i18n/ar.json';
import en from '../../../../../../../packages/i18n/en.json';
import type { Product, Supplier } from '../../../core/api/models';
import type { BasketSplitJob } from '../offers-api';
import { BasketSplitResultsComponent } from './basket-split-results.component';
import { isUserFacingConstraint } from './constraint-text';

const money = (amount: string) => ({ amount, currency: 'EGP' });

const rice = {
  id: 'p-rice',
  tenant_name: 'Rice',
  base_unit: 'kilogram',
  pack: { pack_count: 1, unit_size: '25', base_quantity: '25' },
} as unknown as Product;
const loose = {
  id: 'p-loose',
  tenant_name: 'Loose',
  base_unit: 'kilogram',
  pack: { pack_count: 1, unit_size: '1', base_quantity: '1' },
} as unknown as Product;
const supplier = { id: 's1', name: 'Al Nour' } as unknown as Supplier;

const job = {
  id: 'j1',
  supplier_ids: ['s1'],
  items: [],
  status: 'completed',
  result_url: '/x',
  created_at: '2026-10-18T00:00:00Z',
  result: {
    feasible: true,
    allocation: [
      {
        supplier_id: 's1',
        total_landed_cost: money('100.0000'),
        lines: [
          {
            workspace_product_id: 'p-rice',
            quantity: '500',
            offer_id: 'o1',
            landed_cost: money('60.0000'),
          },
          {
            workspace_product_id: 'p-loose',
            quantity: '12',
            offer_id: 'o2',
            landed_cost: money('40.0000'),
          },
        ],
      },
    ],
    total_landed_cost: money('100.0000'),
    infeasible_items: [],
    computed_at: '2026-10-18T00:00:00Z',
  },
} as unknown as BasketSplitJob;

describe('BasketSplitResultsComponent — packs and constraint copy', () => {
  let fixture: ComponentFixture<BasketSplitResultsComponent>;
  let translate: TranslateService;

  function render(
    applied: unknown[],
    violated: unknown[] = [],
    currentJob: BasketSplitJob = job,
    products: Product[] = [rice, loose],
  ): HTMLElement {
    fixture.componentRef.setInput('currentJob', currentJob);
    fixture.componentRef.setInput('suppliers', [supplier]);
    fixture.componentRef.setInput('products', products);
    fixture.componentRef.setInput('solverConfidence', 'high');
    fixture.componentRef.setInput('validUntil', null);
    fixture.componentRef.setInput('appliedConstraints', applied);
    fixture.componentRef.setInput('violatedConstraints', violated);
    fixture.componentRef.setInput('riskNotes', []);
    fixture.componentRef.setInput('singleSupplierSavings', { type: 'neither_feasible' });
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [BasketSplitResultsComponent],
      providers: [provideTranslateService(), provideNoopAnimations()],
    });
    translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', en);
    translate.setTranslation('ar', ar);
    translate.use('en');
    fixture = TestBed.createComponent(BasketSplitResultsComponent);
  });

  it('shows allocated quantity in packs with the base total secondary (ADR-020)', () => {
    const el = render([]);
    const cells = el.querySelectorAll('.alloc-table tbody tr td:nth-child(2)');
    expect(cells[0].querySelector('.qty-primary')?.textContent?.trim()).toBe('20 × 25 kg');
    expect(cells[0].querySelector('.qty-secondary')?.textContent).toContain('500 kg');
    // loose goods (pack of 1) keep the plain base quantity
    expect(cells[1].querySelector('.qty-primary')?.textContent?.trim()).toBe('12 kg');
    expect(cells[1].querySelector('.qty-secondary')).toBeNull();
  });

  it('hides the solver tie-break and never renders solver free text', () => {
    const el = render([
      {
        kind: 'urgency',
        description: 'deterministic tie-break by supplier_id, then offer_id',
        source_ids: [],
      },
      { kind: 'supplier_exclusion', supplier_id: 's1', description: 'supplier excluded by requester' },
      { kind: 'delivery_fee', supplier_id: 's1', description: 'delivery fee applied below free-delivery threshold' },
    ]);
    const text = el.querySelector('.applied-constraints')?.textContent ?? '';
    expect(text).not.toContain('tie-break');
    expect(text).not.toContain('supplier excluded by requester');
    expect(text).toContain('Al Nour excluded as requested');
    expect(text).toContain('Delivery fee applied for Al Nour');
  });

  it('localises constraint sentences in Arabic', () => {
    translate.use('ar');
    const el = render([{ kind: 'supplier_exclusion', supplier_id: 's1', description: 'x' }]);
    const text = el.querySelector('.applied-constraints')?.textContent ?? '';
    expect(text).toContain('Al Nour');
    expect(text).toContain('تم استبعاد');
  });

  it('treats a pack smaller than one base unit as a pack, not loose goods', () => {
    const halfKg = {
      ...rice,
      pack: { pack_count: 1, unit_size: '0.5', base_quantity: '0.5' },
    } as unknown as Product;
    const el = render([], [], job, [halfKg, loose]);
    const primary = el.querySelector('.alloc-table tbody tr td:nth-child(2) .qty-primary');
    expect(primary?.textContent?.trim()).toBe('1,000 × 0.5 kg');
  });

  it("renders historical results with the pack captured at submission, not today's catalogue", () => {
    const snapshotJob = {
      ...job,
      pack_snapshot: { 'p-rice': { base_quantity: '10', base_unit: 'kilogram' } },
    } as unknown as BasketSplitJob;
    const el = render([], [], snapshotJob);
    const primary = el.querySelector('.alloc-table tbody tr td:nth-child(2) .qty-primary');
    expect(primary?.textContent?.trim()).toBe('50 × 10 kg');
  });

  it('words a violated constraint as a failure, not as the applied rule', () => {
    const el = render(
      [{ kind: 'minimum_order_value', supplier_id: 's1', description: 'x' }],
      [{ kind: 'minimum_order_value', supplier_id: 's1', description: 'x', reason: 'x' }],
    );
    expect(el.querySelector('.applied-constraints')?.textContent).toContain(
      'Minimum order value checked for Al Nour',
    );
    const violated = el.querySelector('.violated-constraints')?.textContent ?? '';
    expect(violated).toContain('Al Nour does not meet its minimum order value');
    expect(violated).not.toContain('checked');
  });

  it('has Arabic violation copy', () => {
    translate.use('ar');
    const el = render([], [{ kind: 'no_eligible_supplier', description: 'x', reason: 'x' }]);
    expect(el.querySelector('.violated-constraints')?.textContent).toContain('لا يوجد مورّد مؤهل');
  });

  it('flags only the tie-break as internal', () => {
    expect(isUserFacingConstraint({ kind: 'urgency', description: 'deterministic tie-break by x' })).toBeFalse();
    expect(isUserFacingConstraint({ kind: 'urgency', description: 'Requested basket urgency.' })).toBeTrue();
    expect(isUserFacingConstraint({ kind: 'delivery_fee', description: 'tie-break' })).toBeTrue();
  });
});
