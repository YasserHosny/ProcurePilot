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
});
