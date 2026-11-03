import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import arCatalog from '../../../../../../../packages/i18n/ar.json';
import enCatalog from '../../../../../../../packages/i18n/en.json';
import { CompareTableComponent } from './compare-table.component';

describe('CompareTableComponent (P-159, PPS-203)', () => {
  let fixture: ComponentFixture<CompareTableComponent>;
  let translate: TranslateService;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CompareTableComponent],
      providers: [provideTranslateService(), provideRouter([])],
    }).compileComponents();
    translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.setTranslation('ar', arCatalog);
    fixture = TestBed.createComponent(CompareTableComponent);
    fixture.componentRef.setInput('offers', []);
    fixture.componentRef.setInput('displayedColumns', ['supplier']);
    fixture.componentRef.setInput('requestedQuantity', '1');
    fixture.componentRef.setInput('baseUnit', 'unit');
  });

  const tableLabel = (): string | null =>
    (fixture.nativeElement as HTMLElement).querySelector('table')!.getAttribute('aria-label');

  it('names the table from the i18n catalogue in English', () => {
    translate.use('en');
    fixture.detectChanges();
    expect(tableLabel()).toBe(enCatalog.compare.table.ariaLabel);
  });

  it('names the table in Arabic instead of a hardcoded English label', () => {
    translate.use('ar');
    fixture.detectChanges();
    expect(tableLabel()).toBe(arCatalog.compare.table.ariaLabel);
    expect(tableLabel()).not.toBe('Supplier Offers Comparison');
  });

  it('prints the unit next to each unit price so per-pack and per-base-unit prices cannot be confused', () => {
    translate.use('en');
    fixture.componentRef.setInput('displayedColumns', ['unitPrice']);
    fixture.componentRef.setInput('baseUnit', 'kilogram');
    fixture.componentRef.setInput('offers', [
      {
        id: 'o1',
        supplier_name: 'Supplier',
        supplier_id: 's1',
        normalised_unit_price: { amount: '8.5000', currency: 'SAR' },
        projected_unit_price: { amount: '8.5000', currency: 'SAR' },
        landed_cost: { amount: '850.0000', currency: 'SAR' },
        projected_landed_cost: { amount: '850.0000', currency: 'SAR' },
        base_unit: 'kilogram',
        is_expired: false,
      },
    ]);
    fixture.detectChanges();

    const cell = (fixture.nativeElement as HTMLElement).querySelector('td.mat-column-unitPrice')?.textContent ?? '';
    expect(cell).toContain('8.5');
    expect(cell).toContain(enCatalog.units.kilogram);
  });
});

