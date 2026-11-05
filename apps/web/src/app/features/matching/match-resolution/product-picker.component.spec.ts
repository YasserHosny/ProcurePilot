import { ComponentFixture, TestBed, fakeAsync, flush, tick } from '@angular/core/testing';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { ApiService } from '../../../core/api/api.service';
import type { MatchCandidate, Product } from '../../../core/api/models';
import { ProductPickerComponent } from './product-picker.component';

const product = (id: string, name: string): Product => ({
  id,
  tenant_name: name,
  canonical_name: name,
  base_unit: 'litre',
  pack: { pack_count: 1, unit_size: '5' },
  status: 'active',
  created_at: '2026-08-20T00:00:00Z',
});

const candidate: MatchCandidate = {
  id: 'cand-manual',
  quotation_line_id: 'line-1',
  candidate_product: {
    id: 'p1',
    tenant_name: 'Sunflower oil 5L',
    canonical_name: 'Sunflower oil',
    base_unit: 'litre',
    status: 'active',
  },
  confidence: '0.0000',
  reasons: { alias_hit: false, gtin_match: false, supplier_code_match: false, manual: true },
  rank: 1,
  scoring_version: 'manual-v1',
  created_at: '2026-08-20T00:00:00Z',
};

describe('ProductPickerComponent', () => {
  let fixture: ComponentFixture<ProductPickerComponent>;
  let api: jasmine.SpyObj<ApiService>;
  let picked: MatchCandidate[];

  beforeEach(async () => {
    api = jasmine.createSpyObj<ApiService>('ApiService', ['products', 'addManualCandidate']);
    api.products.and.returnValue(
      of({ items: [product('p1', 'Sunflower oil 5L'), product('p2', 'Olive oil 1L')], next_cursor: null }),
    );
    api.addManualCandidate.and.returnValue(of(candidate));
    await TestBed.configureTestingModule({
      imports: [ProductPickerComponent],
      providers: [provideTranslateService(), { provide: ApiService, useValue: api }],
    }).compileComponents();
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');
    fixture = TestBed.createComponent(ProductPickerComponent);
    fixture.componentRef.setInput('lineId', 'line-1');
    picked = [];
    fixture.componentInstance.picked.subscribe((c) => picked.push(c));
    fixture.detectChanges();
  });

  const type = (value: string): void => {
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
    input.value = value;
    input.dispatchEvent(new Event('input'));
  };

  it('does not search for fewer than two characters', fakeAsync(() => {
    type('s');
    tick(400);
    expect(api.products).not.toHaveBeenCalled();
    flush();
  }));

  it('searches active products once, after the typing pauses', fakeAsync(() => {
    type('su');
    type('sun');
    tick(400);
    fixture.detectChanges();
    expect(api.products).toHaveBeenCalledOnceWith({ q: 'sun', limit: 8, status: 'active' });
    const rows = fixture.nativeElement.querySelectorAll('[data-testid="picker-result"]');
    expect(rows.length).toBe(2);
    expect(rows[0].textContent).toContain('Sunflower oil 5L');
  }));

  it('says so when nothing matches', fakeAsync(() => {
    api.products.and.returnValue(of({ items: [], next_cursor: null }));
    type('zzz');
    tick(400);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[data-testid="picker-empty"]')).not.toBeNull();
  }));

  it('records the chosen product as a candidate and emits it', fakeAsync(() => {
    type('sun');
    tick(400);
    fixture.detectChanges();
    (fixture.nativeElement.querySelector('[data-testid="picker-result"]') as HTMLElement).click();
    fixture.detectChanges();
    expect(api.addManualCandidate).toHaveBeenCalledOnceWith('line-1', 'p1');
    expect(picked).toEqual([candidate]);
    expect(fixture.nativeElement.querySelectorAll('[data-testid="picker-result"]').length).toBe(0);
  }));

  it('shows an error and keeps the results when recording fails', fakeAsync(() => {
    api.addManualCandidate.and.returnValue(throwError(() => new Error('boom')));
    type('sun');
    tick(400);
    fixture.detectChanges();
    (fixture.nativeElement.querySelector('[data-testid="picker-result"]') as HTMLElement).click();
    fixture.detectChanges();
    expect(picked).toEqual([]);
    expect(fixture.nativeElement.querySelector('[role="alert"]')).not.toBeNull();
    expect(fixture.nativeElement.querySelectorAll('[data-testid="picker-result"]').length).toBe(2);
  }));

  it('shows an error when the search fails', fakeAsync(() => {
    api.products.and.returnValue(throwError(() => new Error('boom')));
    type('sun');
    tick(400);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role="alert"]')).not.toBeNull();
  }));
});
