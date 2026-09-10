import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { HttpErrorResponse } from '@angular/common/http';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { ApiService } from '../../../core/api/api.service';
import type {
  LandedCost,
  MatchDecision,
  MatchTask,
  Role,
} from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { MatchResolutionComponent } from './match-resolution.component';

describe('MatchResolutionComponent (T039)', () => {
  let component: MatchResolutionComponent;
  let fixture: ComponentFixture<MatchResolutionComponent>;
  let apiService: jasmine.SpyObj<ApiService>;

  const mockTask: MatchTask = {
    id: 'task-resolve-1',
    quotation_id: 'q-99',
    quotation: {
      id: 'q-99',
      status: 'reviewed',
      source_filename: 'quotation.pdf',
      line_count: 1,
      open_match_task_count: 1,
      supplier_id: 'supplier-1',
      supplier_name: 'Fresh Farms Dairy',
    },
    quotation_line: {
      id: 'line-99',
      line_number: 1,
      original_text: 'Fresh Farm Whole Milk 2L',
      quantity: '10',
      pack: { pack_count: 1, unit_size: '2.0', unit: 'litre' },
      unit_price: { amount: '2.50', currency: 'GBP' },
      vat_rate: '0.20',
      delivery_fee: { amount: '5.00', currency: 'GBP' },
      discount: { amount: '1.00', currency: 'GBP' },
      quoted_line_total: { amount: '34.0000', currency: 'GBP' },
    },
    status: 'open',
    priority: 'normal',
    reason: 'low_confidence',
    candidates: [
      {
        id: 'cand-1',
        quotation_line_id: 'line-99',
        candidate_product: {
          id: 'prod-1',
          tenant_name: 'Farm Whole Milk 2L',
          canonical_name: 'Farm Whole Milk',
          brand: 'Farm Fresh',
          variant: 'Whole',
          gtin: '501234567890',
          base_unit: 'litre',
          status: 'active',
        },
        confidence: '0.8200',
        reasons: {
          alias_hit: false,
          gtin_match: false,
          supplier_code_match: false,
          lexical_similarity: '0.8800',
          semantic_similarity: '0.8000',
          feature_score: {
            brand_match: '1.0000',
            variant_match: '1.0000',
            pack_unit_match: '1.0000',
            pack_size_plausibility: '1.0000',
            price_plausibility: '0.9500',
          },
        },
        rank: 1,
        scoring_version: 'v1.0',
        created_at: '2026-08-21T01:00:00Z',
      },
      {
        id: 'cand-2',
        quotation_line_id: 'line-99',
        candidate_product: {
          id: 'prod-2',
          tenant_name: 'Farm Semi-Skimmed Milk 2L',
          canonical_name: 'Farm Semi-Skimmed Milk',
          brand: 'Farm Fresh',
          variant: 'Semi-Skimmed',
          gtin: '501234567891',
          base_unit: 'litre',
          status: 'active',
        },
        confidence: '0.7400',
        reasons: {
          alias_hit: false,
          gtin_match: false,
          supplier_code_match: false,
          lexical_similarity: '0.7800',
          semantic_similarity: '0.7000',
          feature_score: {
            brand_match: '1.0000',
            variant_match: '0.5000',
            pack_unit_match: '1.0000',
            pack_size_plausibility: '1.0000',
            price_plausibility: '0.9000',
          },
        },
        rank: 2,
        scoring_version: 'v1.0',
        created_at: '2026-08-21T01:00:00Z',
      },
    ],
    created_at: '2026-08-21T01:00:00Z',
  };

  const mockLandedCost: LandedCost = {
    id: 'lc-1',
    quotation_line_id: 'line-99',
    match_decision_id: 'dec-1',
    quantity: '10',
    normalised_base_quantity: '20.000000',
    base_unit: 'litre',
    unit_price: { amount: '2.50', currency: 'GBP' },
    vat_amount: { amount: '5.00', currency: 'GBP' },
    delivery_fee: { amount: '5.00', currency: 'GBP' },
    discount: { amount: '1.00', currency: 'GBP' },
    other_charges: { amount: '0.00', currency: 'GBP' },
    total: { amount: '34.00', currency: 'GBP' },
    raw_inputs: { unit_price: '2.50', quantity: '10', vat_rate: '0.20' },
    rule_version: 'landed-cost-v1',
    valid_from: '2026-08-21T00:00:00Z',
    recorded_at: '2026-08-21T01:00:00Z',
    created_at: '2026-08-21T01:00:00Z',
  };

  const mockDecision: MatchDecision = {
    id: 'dec-1',
    quotation_line_id: 'line-99',
    matched_product: {
      id: 'prod-1',
      tenant_name: 'Farm Whole Milk 2L',
      canonical_name: 'Farm Whole Milk',
      base_unit: 'litre',
      status: 'active',
    },
    selected_match_candidate_id: 'cand-1',
    outcome: 'same_product',
    is_automatic: false,
    decided_by: 'user-1',
    decided_at: '2026-08-21T02:00:00Z',
    confidence: '0.8200',
  };

  beforeEach(async () => {
    apiService = jasmine.createSpyObj('ApiService', [
      'getMatchTasks',
      'getMatchTaskForLine',
      'baseUnits',
      'suppliers',
      'resolveMatch',
      'getLandedCost',
    ]);
    apiService.getMatchTasks.and.returnValue(of({ items: [mockTask], next_cursor: null }));
    apiService.getMatchTaskForLine.and.returnValue(of(mockTask));
    apiService.baseUnits.and.returnValue(
      of({
        items: [{ code: 'litre', label_en: 'Litre (L)', label_ar: 'لتر', dimension: 'volume' }],
      }),
    );
    apiService.suppliers.and.returnValue(
      of({
        items: [
          {
            id: 'supplier-1',
            name: 'Fresh Farms Dairy',
            status: 'active',
            created_at: '2026-08-21T00:00:00Z',
          },
        ],
        next_cursor: null,
      }),
    );
    apiService.resolveMatch.and.returnValue(of(mockDecision));
    apiService.getLandedCost.and.returnValue(of(mockLandedCost));

    const mockSession = {
      hasRole: jasmine.createSpy('hasRole').and.returnValue(true),
      role: signal<Role | null>('buyer'),
      currentMember: signal(null),
      isAuthenticated: signal(true),
      tenant: signal(null),
      activeLocale: signal('en'),
    };

    await TestBed.configureTestingModule({
      imports: [MatchResolutionComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        { provide: ApiService, useValue: apiService },
        { provide: SessionService, useValue: mockSession },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              paramMap: {
                get: (k: string) => (k === 'id' ? 'line-99' : null),
              },
              queryParamMap: {
                get: (k: string) => (k === 'quotation_id' ? 'q-99' : null),
              },
            },
          },
        },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(MatchResolutionComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should load task and candidates on init and auto-select rank 1 candidate', () => {
    expect(apiService.getMatchTaskForLine).toHaveBeenCalledWith('line-99');
    expect(component.task()?.id).toBe('task-resolve-1');
    expect(component.candidates().length).toBe(2);
    expect(component.selectedCandidateId()).toBe('cand-1');
    expect(component.selectedOutcome()).toBe('same_product');
  });

  it('should require explicit candidate selection for close-candidate tasks', () => {
    apiService.getMatchTaskForLine.and.returnValue(
      of({
        ...mockTask,
        reason: 'close_candidates',
      }),
    );

    component.loadTask('line-99');

    expect(component.selectedCandidateId()).toBeNull();
    expect(component.selectedOutcome()).toBe('same_product');
  });

  it('should select a focused candidate card with Space without confirming', () => {
    apiService.getMatchTaskForLine.and.returnValue(
      of({
        ...mockTask,
        reason: 'close_candidates',
      }),
    );

    component.loadTask('line-99');
    fixture.detectChanges();
    apiService.resolveMatch.calls.reset();

    const candidateCards = fixture.nativeElement.querySelectorAll('.candidate-card');
    candidateCards[1].dispatchEvent(
      new KeyboardEvent('keydown', { key: ' ', bubbles: true }),
    );

    expect(component.selectedCandidateId()).toBe('cand-2');
    expect(apiService.resolveMatch).not.toHaveBeenCalled();
  });

  it('should show quoted exposure on the detail page', () => {
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Quoted exposure');
    expect(text).toContain('£34.00');
  });

  it('should prefill the quotation supplier when creating a new product', () => {
    expect(component.productForm.get('preferred_supplier_id')?.value).toBe('supplier-1');
  });

  it('should support candidate selection via number keys (FR-012)', () => {
    // Press '2' to select candidate rank 2
    const event = new KeyboardEvent('keydown', { key: '2' });
    window.dispatchEvent(event);

    expect(component.selectedCandidateId()).toBe('cand-2');
  });

  it('should navigate candidates using arrow keys (FR-012)', () => {
    expect(component.selectedCandidateId()).toBe('cand-1');

    // Arrow down moves to next candidate
    const downEvent = new KeyboardEvent('keydown', { key: 'ArrowDown' });
    window.dispatchEvent(downEvent);
    expect(component.selectedCandidateId()).toBe('cand-2');

    // Arrow up moves to previous candidate
    const upEvent = new KeyboardEvent('keydown', { key: 'ArrowUp' });
    window.dispatchEvent(upEvent);
    expect(component.selectedCandidateId()).toBe('cand-1');
  });

  it('should cycle outcomes using O key', () => {
    expect(component.selectedOutcome()).toBe('same_product');

    const oEvent = new KeyboardEvent('keydown', { key: 'o' });
    window.dispatchEvent(oEvent);
    expect(component.selectedOutcome()).toBe('different_pack');
  });

  it('should resolve match with candidate selection and outcome', () => {
    component.selectCandidate('cand-2');
    component.selectOutcome('different_variant');

    component.confirmResolution();

    expect(apiService.resolveMatch).toHaveBeenCalledWith('line-99', {
      outcome: 'different_variant',
      selected_match_candidate_id: 'cand-2',
      create_product: null,
    });
    expect(apiService.getLandedCost).toHaveBeenCalledWith('line-99');
    expect(component.decision()).toEqual(mockDecision);
  });

  it('should resolve match with inline product creation when no_match_new_product selected', () => {
    component.selectOutcome('no_match_new_product');
    component.productForm.patchValue({
      tenant_name: 'Farm Fresh Whole Milk 2L',
      brand: 'Farm Fresh',
      canonical_name: 'Farm Fresh Whole Milk',
      variant: 'Whole',
      gtin: '501234567890',
      base_unit: 'litre',
      pack_count: 6,
      unit_size: '2.0',
      preferred_supplier_id: null,
    });

    component.confirmResolution();

    expect(apiService.resolveMatch).toHaveBeenCalledWith('line-99', {
      outcome: 'no_match_new_product',
      selected_match_candidate_id: null,
      create_product: {
        tenant_name: 'Farm Fresh Whole Milk 2L',
        brand: 'Farm Fresh',
        canonical_name: 'Farm Fresh Whole Milk',
        variant: 'Whole',
        gtin: '501234567890',
        base_unit: 'litre',
        pack: {
          pack_count: 6,
          unit_size: '2.0',
        },
        preferred_supplier_id: null,
      },
    });
  });

  it('should handle 409 alias conflict error', () => {
    const errorResponse = new HttpErrorResponse({
      status: 409,
      error: {
        message: 'This supplier wording is already assigned to a different product.',
        trace_id: 'tr-conflict-1',
      },
    });
    apiService.resolveMatch.and.returnValue(throwError(() => errorResponse));

    component.confirmResolution();

    expect(component.isSubmitting()).toBeFalse();
    expect(component.errorMessage()).toContain('already assigned');
    expect(component.errorTraceId()).toBe('tr-conflict-1');
  });
});
