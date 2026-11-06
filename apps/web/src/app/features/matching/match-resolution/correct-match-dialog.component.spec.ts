import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { ApiService } from '../../../core/api/api.service';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import arCatalog from '../../../../../../../packages/i18n/ar.json';
import enCatalog from '../../../../../../../packages/i18n/en.json';
import type { MatchCandidate, QuotationLineSummary } from '../../../core/api/models';
import { CorrectMatchDialogComponent, type CorrectMatchDialogData } from './correct-match-dialog.component';

describe('CorrectMatchDialogComponent', () => {
  let component: CorrectMatchDialogComponent;
  let fixture: ComponentFixture<CorrectMatchDialogComponent>;
  let mockDialogRef: jasmine.SpyObj<MatDialogRef<CorrectMatchDialogComponent>>;

  const mockLine: QuotationLineSummary = {
    id: 'line-1',
    line_number: 1,
    original_text: 'Organic Milk 2L',
    quantity: '5',
    unit_price: { amount: '2.5000', currency: 'GBP' },
  };

  const mockCandidates: MatchCandidate[] = [
    {
      id: 'cand-1',
      quotation_line_id: 'line-1',
      candidate_product: {
        id: 'prod-1',
        tenant_name: 'Organic Whole Milk 2L',
        canonical_name: 'Organic Whole Milk',
        base_unit: 'litre',
        status: 'active',
      },
      confidence: '0.8500',
      reasons: {
        alias_hit: false,
        gtin_match: false,
        supplier_code_match: false,
        lexical_similarity: '0.9000',
        semantic_similarity: '0.8000',
        rfq: {
          rfq_id: 'rfq-1',
          rfq_line_id: 'rfq-line-1',
          position: 1,
          pack_check: 'equal',
          fitting_rfq_line_ids: ['rfq-line-1'],
        },
      },
      rank: 1,
      scoring_version: 'v1.0',
      created_at: '2026-08-20T00:00:00Z',
    },
    {
      id: 'cand-2',
      quotation_line_id: 'line-1',
      candidate_product: {
        id: 'prod-2',
        tenant_name: 'Conventional Milk 2L',
        canonical_name: 'Conventional Milk',
        base_unit: 'litre',
        status: 'active',
      },
      confidence: '0.5000',
      reasons: {
        alias_hit: false,
        gtin_match: false,
        supplier_code_match: false,
        lexical_similarity: '0.6000',
        semantic_similarity: '0.4000',
        rfq: {
          rfq_id: 'rfq-1',
          not_in_rfq: true,
          fitting_rfq_line_ids: [],
        },
      },
      rank: 2,
      scoring_version: 'v1.0',
      created_at: '2026-08-20T00:00:00Z',
    },
    {
      id: 'cand-3',
      quotation_line_id: 'line-1',
      candidate_product: {
        id: 'prod-3',
        tenant_name: 'Milk 1L Pack',
        canonical_name: 'Milk',
        base_unit: 'litre',
        status: 'active',
      },
      confidence: '0.6000',
      reasons: {
        alias_hit: false,
        gtin_match: false,
        supplier_code_match: false,
        lexical_similarity: '0.6000',
        semantic_similarity: '0.6000',
        rfq: {
          rfq_id: 'rfq-1',
          rfq_line_id: 'rfq-line-3',
          position: 3,
          pack_check: 'conflict',
          rfq_pack_base_quantity: '2.000000',
          quoted_pack_base_quantity: '1.000000',
          fitting_rfq_line_ids: ['rfq-line-3', 'rfq-line-4'],
        },
      },
      rank: 3,
      scoring_version: 'v1.0',
      created_at: '2026-08-20T00:00:00Z',
    },
    {
      id: 'cand-4',
      quotation_line_id: 'line-1',
      candidate_product: {
        id: 'prod-4',
        tenant_name: 'Bulk Cheese 16kg',
        canonical_name: 'Bulk Cheese',
        base_unit: 'piece',
        status: 'active',
      },
      confidence: '0.5500',
      reasons: {
        alias_hit: false,
        gtin_match: false,
        supplier_code_match: false,
        lexical_similarity: '0.5000',
        semantic_similarity: '0.5000',
        rfq: {
          rfq_id: 'rfq-1',
          rfq_line_id: 'rfq-line-4',
          position: 4,
          pack_check: 'conflict',
          rfq_pack_base_quantity: '16.000000',
          rfq_pack_unit: 'kilogram',
          quoted_pack_base_quantity: '18.000000',
          quoted_pack_unit: 'litre',
          fitting_rfq_line_ids: ['rfq-line-4'],
        },
      },
      rank: 4,
      scoring_version: 'v1.0',
      created_at: '2026-08-20T00:00:00Z',
    },
  ];

  const mockDialogData: CorrectMatchDialogData = {
    line: mockLine,
    candidates: mockCandidates,
    expectedCurrentDecisionId: 'dec-1',
    currentCandidateId: 'cand-1',
    baseUnits: [{ code: 'litre', label_en: 'Litre', label_ar: 'لتر', dimension: 'volume' }],
  };

  beforeEach(async () => {
    mockDialogRef = jasmine.createSpyObj('MatDialogRef', ['close']);

    await TestBed.configureTestingModule({
      imports: [CorrectMatchDialogComponent],
      providers: [
        provideTranslateService(),
        { provide: MatDialogRef, useValue: mockDialogRef },
        { provide: ApiService, useValue: jasmine.createSpyObj('ApiService', ['products', 'addManualCandidate']) },
        { provide: MAT_DIALOG_DATA, useValue: mockDialogData },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(CorrectMatchDialogComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  const manualCandidate: MatchCandidate = {
    id: 'cand-manual',
    quotation_line_id: 'line-1',
    candidate_product: {
      id: 'prod-manual',
      tenant_name: 'Picked From Catalogue 5L',
      canonical_name: 'Picked From Catalogue',
      base_unit: 'litre',
      status: 'active',
    },
    confidence: '0.0000',
    reasons: { alias_hit: false, gtin_match: false, supplier_code_match: false, manual: true },
    rank: 1,
    scoring_version: 'manual-v1',
    created_at: '2026-08-20T00:00:00Z',
  };

  it('offers the catalogue picker and lists the product it records, selected (P-151)', () => {
    expect(fixture.nativeElement.querySelector('app-product-picker')).not.toBeNull();
    component.onManualCandidate(manualCandidate);
    fixture.detectChanges();
    expect(component.selectedCandidateId()).toBe('cand-manual');
    expect(component.selectedOutcome()).toBe('same_product');
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Picked From Catalogue 5L');
    expect(text).toContain('Picked by you');
    expect(text).not.toContain('Picked by you 0%');
    expect(text).not.toMatch(/Picked From Catalogue 5L\s*0%/);
    // Picking the same product again does not add a second row.
    component.onManualCandidate(manualCandidate);
    expect(component.allCandidates().filter((c) => c.id === 'cand-manual').length).toBe(1);
  });

  it('shows the line number with Arabic-Indic digits in Arabic (P-159)', () => {
    expect(fixture.nativeElement.querySelector('.line-badge').textContent).toContain('#1');
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('ar', arCatalog);
    translate.use('ar');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.line-badge').textContent).toContain('#١');
  });

  it('renders line text and candidates list with RFQ badges', () => {
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Organic Milk 2L');
    expect(text).toContain('Organic Whole Milk 2L');
    expect(text).toContain('Conventional Milk 2L');

    // RFQ label 1: position 1
    expect(text).toContain('Your RFQ line 1');
    // RFQ label 2: not in RFQ
    expect(text).toContain('Not in your RFQ');
    // RFQ label 3: pack conflict
    expect(text).toContain('Pack differs from your RFQ (2 L asked, 1 L quoted)');
    expect(text).toContain('Pack differs from your RFQ (16 kg asked, 18 L quoted)');
    // RFQ label 4: multiple fitting lines
    expect(text).toContain('Could be more than one of your RFQ lines');
  });

  it('gives the candidate radio group an accessible name from its heading (P-159)', () => {
    const group = fixture.nativeElement.querySelector('[role="radiogroup"]') as HTMLElement;
    const id = group.getAttribute('aria-labelledby');
    expect(id).withContext('aria-labelledby').toBeTruthy();
    expect(document.getElementById(id!)?.textContent?.trim()).toBeTruthy();
  });

  describe('new-product and unchanged guards (P-151, PPS-195)', () => {
    const save = (): HTMLButtonElement =>
      fixture.nativeElement.querySelector('.confirm-correction-btn') as HTMLButtonElement;

    it('leaves Base Unit blank so the buyer chooses it, instead of defaulting to the first unit', () => {
      expect(component.productForm.get('base_unit')?.value).toBe('');
    });

    it('disables Save while the choice is the current match, and enables it once another is picked', () => {
      expect(save().disabled).toBeTrue();

      component.selectCandidate('cand-2');
      fixture.detectChanges();

      expect(save().disabled).toBeFalse();
    });

    it('disables Save for a new product until it is valid, and says what is missing straight away', () => {
      component.selectOutcome('no_match_new_product');
      fixture.detectChanges();
      expect(save().disabled).toBeTrue();
      // Save cannot be clicked to reveal errors, so they show as soon as the form appears.
      expect(fixture.nativeElement.textContent).toContain(enCatalog.matching.resolution.newProduct.baseUnitRequired);

      component.productForm.patchValue({ base_unit: 'litre' });
      fixture.detectChanges();
      expect(save().disabled).withContext('unit size still missing').toBeTrue();
      expect(fixture.nativeElement.textContent).toContain(enCatalog.matching.resolution.newProduct.unitSizeRequired);

      component.productForm.patchValue({ unit_size: '10' });
      fixture.detectChanges();
      expect(save().disabled).toBeFalse();
    });

    it('leaves Unit Size blank when the line carries no pack, so a pack size is never invented', () => {
      expect(mockLine.pack).toBeUndefined();
      expect(component.productForm.get('unit_size')?.value).toBe('');
    });

    it('explains a product name that is too long, even though it was prefilled and untouched', () => {
      component.selectOutcome('no_match_new_product');
      component.productForm.patchValue({ tenant_name: 'x'.repeat(201) });
      fixture.detectChanges();

      expect(fixture.nativeElement.textContent).toContain(enCatalog.matching.resolution.newProduct.tenantNameMaxLength);
    });
  });

  it('submits correction with selected candidate, expected_current_decision_id, and learn_alias', () => {
    component.selectCandidate('cand-2');
    fixture.detectChanges();

    component.onConfirm();

    expect(mockDialogRef.close).toHaveBeenCalledWith({
      expected_current_decision_id: 'dec-1',
      outcome: 'same_product',
      selected_match_candidate_id: 'cand-2',
      new_product: null,
      learn_alias: true,
    });
  });

  it('allows unchecking learn_alias', () => {
    component.learnAlias.set(false);
    fixture.detectChanges();

    component.onConfirm();

    expect(mockDialogRef.close).toHaveBeenCalledWith({
      expected_current_decision_id: 'dec-1',
      outcome: 'same_product',
      selected_match_candidate_id: 'cand-1',
      new_product: null,
      learn_alias: false,
    });
  });

  it('submits correction with new product when no_match_new_product is selected', () => {
    component.selectOutcome('no_match_new_product');
    fixture.detectChanges();

    component.productForm.patchValue({
      tenant_name: 'Custom Product Name',
      base_unit: 'litre',
      pack_count: 2,
      unit_size: '1.5',
    });

    component.onConfirm();

    expect(mockDialogRef.close).toHaveBeenCalledWith({
      expected_current_decision_id: 'dec-1',
      outcome: 'no_match_new_product',
      selected_match_candidate_id: null,
      new_product: jasmine.objectContaining({
        tenant_name: 'Custom Product Name',
        base_unit: 'litre',
        pack: {
          pack_count: 2,
          unit_size: '1.5',
        },
      }),
      learn_alias: true,
    });
  });

  it('cancels dialog without submitting', () => {
    component.onCancel();
    expect(mockDialogRef.close).toHaveBeenCalledWith(null);
  });
});
