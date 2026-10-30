import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import type { MatchCandidate } from '../../../core/api/models';
import { MatchResolutionCandidatesComponent } from './match-resolution-candidates.component';

describe('MatchResolutionCandidatesComponent', () => {
  let component: MatchResolutionCandidatesComponent;
  let fixture: ComponentFixture<MatchResolutionCandidatesComponent>;

  const baseCandidate: MatchCandidate = {
    id: 'cand-1',
    quotation_line_id: 'line-1',
    candidate_product: {
      id: 'prod-1',
      tenant_name: 'Test Milk 2L',
      canonical_name: 'Test Milk',
      base_unit: 'litre',
      status: 'active',
    },
    confidence: '0.6500',
    reasons: {
      alias_hit: false,
      gtin_match: false,
      supplier_code_match: false,
      lexical_similarity: '0.7000',
      semantic_similarity: '0.6000',
    },
    rank: 1,
    scoring_version: 'v1.0',
    created_at: '2026-08-20T00:00:00Z',
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MatchResolutionCandidatesComponent],
      providers: [provideTranslateService()],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(MatchResolutionCandidatesComponent);
    component = fixture.componentInstance;
  });

  it('displays "Your RFQ line {n}" when candidate has rfq_line_id and pack_check is not conflict', () => {
    component.candidates = [
      {
        ...baseCandidate,
        reasons: {
          ...baseCandidate.reasons,
          rfq: {
            rfq_id: 'rfq-1',
            rfq_line_id: 'rfq-line-1',
            position: 4,
            pack_check: 'equal',
            fitting_rfq_line_ids: ['rfq-line-1'],
          },
        },
      },
    ];
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Your RFQ line 4');
  });

  it('displays warning "Pack differs from your RFQ ({asked} asked, {quoted} quoted)" when pack_check is conflict', () => {
    component.candidates = [
      {
        ...baseCandidate,
        reasons: {
          ...baseCandidate.reasons,
          rfq: {
            rfq_id: 'rfq-1',
            rfq_line_id: 'rfq-line-1',
            position: 1,
            pack_check: 'conflict',
            rfq_pack_base_quantity: '4.000000',
            quoted_pack_base_quantity: '2.000000',
            fitting_rfq_line_ids: ['rfq-line-1'],
          },
        },
      },
    ];
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Pack differs from your RFQ (4 L asked, 2 L quoted)');
  });

  it('displays neutral chip "Not in your RFQ" when candidate has not_in_rfq: true', () => {
    component.candidates = [
      {
        ...baseCandidate,
        reasons: {
          ...baseCandidate.reasons,
          rfq: {
            rfq_id: 'rfq-1',
            not_in_rfq: true,
            fitting_rfq_line_ids: [],
          },
        },
      },
    ];
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Not in your RFQ');
  });

  it('displays hint "Could be more than one of your RFQ lines" when multiple fitting_rfq_line_ids', () => {
    component.candidates = [
      {
        ...baseCandidate,
        reasons: {
          ...baseCandidate.reasons,
          rfq: {
            rfq_id: 'rfq-1',
            rfq_line_id: 'rfq-line-1',
            position: 1,
            fitting_rfq_line_ids: ['rfq-line-1', 'rfq-line-2'],
          },
        },
      },
    ];
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Could be more than one of your RFQ lines');
  });

  it('does not style RFQ candidates with .low class even if confidence is under 70%', () => {
    component.candidates = [
      {
        ...baseCandidate,
        confidence: '0.4500',
        reasons: {
          ...baseCandidate.reasons,
          rfq: {
            rfq_id: 'rfq-1',
            rfq_line_id: 'rfq-line-1',
            position: 1,
            pack_check: 'equal',
            fitting_rfq_line_ids: ['rfq-line-1'],
          },
        },
      },
    ];
    fixture.detectChanges();

    const badge = fixture.nativeElement.querySelector('.cand-confidence-badge') as HTMLElement;
    expect(badge).toBeTruthy();
    expect(badge.classList.contains('low')).toBeFalse();
    expect(badge.classList.contains('rfq-info')).toBeTrue();
  });

  it('renders only the signals present in measured map (measured subset only)', () => {
    component.candidates = [
      {
        ...baseCandidate,
        reasons: {
          ...baseCandidate.reasons,
          measured: {
            lexical_similarity: '0.8200',
            variant_match: '1.0000',
            pack_unit_match: '1.0000',
          },
        },
      },
    ];
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Name 82 % similar');
    expect(text).toContain('Variant Match');
    expect(text).toContain('Pack matches');
    expect(text).not.toContain('Brand Match');
    expect(text).not.toContain('Pack Size Plausibility');
    expect(text).not.toContain('Price Plausibility');
    expect(text).not.toContain('Semantic Similarity');
  });

  it('shows lexical only and no feature bars for legacy candidate without measured', () => {
    component.candidates = [
      {
        ...baseCandidate,
        embedding_model: 'stub-hash-v1',
        reasons: {
          alias_hit: false,
          gtin_match: false,
          supplier_code_match: false,
          lexical_similarity: '0.7000',
          semantic_similarity: '0.6000',
          feature_score: {
            brand_match: '0.5000',
            variant_match: '0.5000',
            pack_unit_match: '0.5000',
            pack_size_plausibility: '0.5000',
            price_plausibility: '0.5000',
          },
        },
      },
    ];
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Name 70 % similar');
    expect(text).not.toContain('Semantic Similarity');
    expect(text).not.toContain('Brand Match');
    expect(text).not.toContain('Variant Match');
    expect(text).not.toContain('Pack Unit Match');
    expect(text).not.toContain('Pack Size Plausibility');
    expect(text).not.toContain('Price Plausibility');
    expect(text).not.toContain('50%');
  });

  it('shows the deterministic hit line and no measured signals for deterministic hits', () => {
    component.candidates = [
      {
        ...baseCandidate,
        reasons: {
          alias_hit: true,
          gtin_match: false,
          supplier_code_match: false,
          measured: {},
        },
      },
    ];
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Same wording as confirmed before');
    expect(text).not.toContain('similar');
    expect(text).not.toContain('Brand Match');

    component.candidates = [
      {
        ...baseCandidate,
        reasons: {
          alias_hit: false,
          gtin_match: true,
          supplier_code_match: false,
          measured: {},
        },
      },
    ];
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Barcode matches');

    component.candidates = [
      {
        ...baseCandidate,
        reasons: {
          alias_hit: false,
          gtin_match: false,
          supplier_code_match: true,
          measured: {},
        },
      },
    ];
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Supplier code matches');
  });

  it('shows RFQ lead line above measured signals and does not style as low confidence red', () => {
    component.candidates = [
      {
        ...baseCandidate,
        confidence: '0.3400',
        reasons: {
          alias_hit: false,
          gtin_match: false,
          supplier_code_match: false,
          rfq: {
            rfq_id: 'rfq-1',
            rfq_line_id: 'rfq-line-2',
            position: 2,
            pack_check: 'equal',
            fitting_rfq_line_ids: ['rfq-line-2'],
          },
          measured: {
            lexical_similarity: '0.3400',
            pack_unit_match: '1.0000',
          },
        },
      },
    ];
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Your RFQ line 2');
    expect(text).toContain('Name 34 % similar');
    expect(text).toContain('Pack matches');

    const badge = fixture.nativeElement.querySelector('.cand-confidence-badge') as HTMLElement;
    expect(badge.classList.contains('low')).toBeFalse();
    expect(badge.classList.contains('rfq-info')).toBeTrue();
  });

  it('never displays "Not available" text anywhere in the component', () => {
    component.candidates = [
      {
        ...baseCandidate,
        embedding_model: 'stub-hash-v1',
        reasons: {
          alias_hit: false,
          gtin_match: false,
          supplier_code_match: false,
          lexical_similarity: '0.7000',
          semantic_similarity: '0.6000',
        },
      },
      {
        ...baseCandidate,
        id: 'cand-2',
        reasons: {
          alias_hit: false,
          gtin_match: false,
          supplier_code_match: false,
          measured: {
            lexical_similarity: '0.8000',
          },
        },
      },
    ];
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).not.toContain('Not available');
  });
});
