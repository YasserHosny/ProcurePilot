import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

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
    // RFQ label 4: multiple fitting lines
    expect(text).toContain('Could be more than one of your RFQ lines');
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
