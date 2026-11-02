import { ComponentFixture, TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { ActivatedRoute, provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { HttpErrorResponse } from '@angular/common/http';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import arCatalog from '../../../../../../../packages/i18n/ar.json';
import { ApiService } from '../../../core/api/api.service';
import type {
  LandedCost,
  MatchCorrectionRequest,
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
  let mockSession: {
    hasRole: jasmine.Spy;
    role: ReturnType<typeof signal<Role | null>>;
    currentMember: ReturnType<typeof signal<unknown>>;
    isAuthenticated: ReturnType<typeof signal<boolean>>;
    tenant: ReturnType<typeof signal<unknown>>;
    activeLocale: ReturnType<typeof signal<string>>;
  };

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
      'getNextMatchTask',
      'baseUnits',
      'suppliers',
      'resolveMatch',
      'correctMatch',
      'getLandedCost',
    ]);
    apiService.getMatchTasks.and.returnValue(of({ items: [mockTask], next_cursor: null }));
    apiService.getMatchTaskForLine.and.returnValue(of(mockTask));
    apiService.getNextMatchTask.and.returnValue(of({ next_task_id: null, next_quotation_line_id: null }));
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

    mockSession = {
      hasRole: jasmine.createSpy('hasRole').and.returnValue(true),
      role: signal<Role | null>('buyer'),
      currentMember: signal(null),
      isAuthenticated: signal(true),
      tenant: signal(null),
      activeLocale: signal('en'),
    };

    await TestBed.configureTestingModule({
      imports: [MatchResolutionComponent],
      providers: [
        provideTranslateService(),
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

  it('should select a focused candidate radio without confirming', () => {
    apiService.getMatchTaskForLine.and.returnValue(
      of({
        ...mockTask,
        reason: 'close_candidates',
      }),
    );

    component.loadTask('line-99');
    fixture.detectChanges();
    apiService.resolveMatch.calls.reset();

    const radioInputs = fixture.nativeElement.querySelectorAll('.cand-radio-input');
    radioInputs[1].checked = true;
    radioInputs[1].dispatchEvent(new Event('change', { bubbles: true }));

    expect(component.selectedCandidateId()).toBe('cand-2');
    expect(apiService.resolveMatch).not.toHaveBeenCalled();
  });

  it('should expose candidate choices as native radio controls', () => {
    fixture.detectChanges();

    const radioGroup = fixture.nativeElement.querySelector('.candidates-grid');
    const candidateCards = fixture.nativeElement.querySelectorAll('.candidate-card');
    const radioInputs = fixture.nativeElement.querySelectorAll('.cand-radio-input');

    expect(radioGroup.getAttribute('role')).toBe('radiogroup');
    expect(radioGroup.getAttribute('aria-label')).toBe('Match Candidates Selection');
    expect(candidateCards.length).toBe(2);
    expect(radioInputs.length).toBe(2);
    expect(candidateCards[0].getAttribute('role')).toBeNull();
    expect(radioInputs[0].getAttribute('type')).toBe('radio');
    expect(radioInputs[0].getAttribute('name')).toBe('candidate_selection');
    expect(radioInputs[0].getAttribute('aria-label')).toBe(
      'Select candidate #1: Farm Whole Milk 2L',
    );
  });

  it('should show quoted exposure on the detail page', () => {
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Quoted exposure');
    expect(text).toContain('GBP 34');
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

  it('navigates to the next open task on Resolve and Next when next_task_id is returned', () => {
    const router = (component as unknown as { router: { navigate: (...args: unknown[]) => Promise<boolean> } }).router;
    const navSpy = spyOn(router, 'navigate').and.returnValue(Promise.resolve(true));
    apiService.getNextMatchTask.and.returnValue(of({ next_task_id: 'task-resolve-2', next_quotation_line_id: 'line-next' }));

    component.confirmResolution(true);

    expect(apiService.resolveMatch).toHaveBeenCalled();
    expect(apiService.getNextMatchTask).toHaveBeenCalledWith('task-resolve-1');
    expect(navSpy).toHaveBeenCalledWith(['/matching', 'line-next']);
  });

  it('navigates to /matching and shows queue cleared toast on Resolve and Next when no tasks remain', () => {
    const router = (component as unknown as { router: { navigate: (...args: unknown[]) => Promise<boolean> } }).router;
    const navSpy = spyOn(router, 'navigate').and.returnValue(Promise.resolve(true));
    const snackBar = (component as unknown as { snackBar: { open: (...args: unknown[]) => unknown } }).snackBar;
    const snackSpy = spyOn(snackBar, 'open');
    apiService.getNextMatchTask.and.returnValue(of({ next_task_id: null, next_quotation_line_id: null }));

    component.confirmResolution(true);

    expect(apiService.getNextMatchTask).toHaveBeenCalledWith('task-resolve-1');
    expect(snackSpy).toHaveBeenCalledWith(
      enCatalog.matching.resolution.actions.queueCleared,
      undefined,
      { duration: 3500 },
    );
    expect(navSpy).toHaveBeenCalledWith(['/matching']);
  });

  it('displays task.matched_product name in the Matched Product box on a resolved task page', () => {
    apiService.getMatchTaskForLine.and.returnValue(
      of({
        ...mockTask,
        status: 'resolved',
        matched_product: {
          id: 'prod-resolved-1',
          tenant_name: '',
          canonical_name: 'Canonical Whole Milk 2L',
          base_unit: 'litre',
          status: 'active',
        },
        decision: {
          ...mockDecision,
          matched_product: {
            id: 'prod-resolved-1',
            tenant_name: '',
            canonical_name: 'Canonical Whole Milk 2L',
            base_unit: 'litre',
            status: 'active',
          },
        },
      }),
    );

    component.loadTask('line-99');
    fixture.detectChanges();

    const banner = fixture.nativeElement.querySelector('.decision-banner') as HTMLElement | null;
    expect(banner).toBeTruthy();
    expect(banner?.textContent).toContain('Canonical Whole Milk 2L');
  });

  it('returns to the queue for the same quotation after Confirm Match Decision', () => {
    const router = (component as unknown as { router: { navigate: (...args: unknown[]) => Promise<boolean> } }).router;
    const navSpy = spyOn(router, 'navigate').and.returnValue(Promise.resolve(true));
    component.quotationId.set('q-99');

    component.confirmResolution(false);

    expect(apiService.resolveMatch).toHaveBeenCalled();
    expect(navSpy).toHaveBeenCalledWith(['/matching'], {
      queryParams: jasmine.objectContaining({ quotation_id: 'q-99' }),
    });
  });

  it('places the rule version chip and pinned to rule version notice inside a collapsed details disclosure', () => {
    component.landedCost.set(mockLandedCost);
    fixture.detectChanges();

    const details = fixture.nativeElement.querySelector('details.landed-cost-details') as HTMLDetailsElement | null;
    expect(details).toBeTruthy();
    expect(details?.open).toBeFalse();

    const summary = details?.querySelector('summary');
    expect(summary?.textContent?.trim()).toBe(enCatalog.matching.resolution.landedCost.details);

    const badge = details?.querySelector('.rule-version-badge');
    expect(badge?.textContent?.trim()).toBe(mockLandedCost.rule_version);

    const replayNotice = details?.querySelector('.replay-notice');
    expect(replayNotice).toBeTruthy();
  });

  it('formats line quantity using shared quantity formatter (e.g. 8.0 -> 8)', () => {
    component.line.set({
      ...mockTask.quotation_line,
      quantity: '8.0',
    });
    fixture.detectChanges();

    const metricValues = fixture.nativeElement.querySelectorAll('.metric-item .metric-value');
    const quantityText = metricValues[0]?.textContent?.trim();
    expect(quantityText).toBe('8');
  });

  describe('RFQ-aware matching (spec 023 US1)', () => {
    it('shows "Your RFQ line {n}" when candidate has rfq_line_id and pack_check is not conflict', () => {
      apiService.getMatchTaskForLine.and.returnValue(
        of({
          ...mockTask,
          candidates: [
            {
              ...mockTask.candidates[0],
              confidence: '0.6400',
              reasons: {
                ...mockTask.candidates[0].reasons,
                rfq: {
                  rfq_id: 'rfq-1',
                  rfq_line_id: 'rfq-line-1',
                  position: 2,
                  wording_score: '0.6400',
                  pack_check: 'equal',
                  quoted_pack_base_quantity: '10.000000',
                  rfq_pack_base_quantity: '10.000000',
                  fitting_rfq_line_ids: ['rfq-line-1'],
                  not_in_rfq: false,
                  matched: false,
                },
              },
            },
          ],
        }),
      );

      component.loadTask('line-99');
      fixture.detectChanges();

      const text = fixture.nativeElement.textContent as string;
      expect(text).toContain('Your RFQ line 2');
    });

    it('shows warning "Pack differs from your RFQ ({asked} asked, {quoted} quoted)" when pack_check is conflict', () => {
      apiService.getMatchTaskForLine.and.returnValue(
        of({
          ...mockTask,
          candidates: [
            {
              ...mockTask.candidates[0],
              candidate_product: {
                ...mockTask.candidates[0].candidate_product,
                base_unit: 'kilogram',
              },
              reasons: {
                ...mockTask.candidates[0].reasons,
                rfq: {
                  rfq_id: 'rfq-1',
                  rfq_line_id: 'rfq-line-1',
                  position: 1,
                  pack_check: 'conflict',
                  quoted_pack_base_quantity: '5.000000',
                  rfq_pack_base_quantity: '10.000000',
                  fitting_rfq_line_ids: ['rfq-line-1'],
                  not_in_rfq: false,
                  matched: false,
                },
              },
            },
          ],
        }),
      );

      component.loadTask('line-99');
      fixture.detectChanges();

      const text = fixture.nativeElement.textContent as string;
      expect(text).toContain('Pack differs from your RFQ (10 kg asked, 5 kg quoted)');
    });

    it('shows differing units in pack conflict warning when rfq_pack_unit and quoted_pack_unit are present', () => {
      apiService.getMatchTaskForLine.and.returnValue(
        of({
          ...mockTask,
          candidates: [
            {
              ...mockTask.candidates[0],
              candidate_product: {
                ...mockTask.candidates[0].candidate_product,
                base_unit: 'piece',
              },
              reasons: {
                ...mockTask.candidates[0].reasons,
                rfq: {
                  rfq_id: 'rfq-1',
                  rfq_line_id: 'rfq-line-1',
                  position: 1,
                  pack_check: 'conflict',
                  rfq_pack_base_quantity: '16.000000',
                  rfq_pack_unit: 'kilogram',
                  quoted_pack_base_quantity: '18.000000',
                  quoted_pack_unit: 'litre',
                  fitting_rfq_line_ids: ['rfq-line-1'],
                  not_in_rfq: false,
                  matched: false,
                },
              },
            },
          ],
        }),
      );

      component.loadTask('line-99');
      fixture.detectChanges();

      const text = fixture.nativeElement.textContent as string;
      expect(text).toContain('Pack differs from your RFQ (16 kg asked, 18 L quoted)');
    });

    it('shows neutral chip "Not in your RFQ" when candidate has not_in_rfq', () => {
      apiService.getMatchTaskForLine.and.returnValue(
        of({
          ...mockTask,
          candidates: [
            {
              ...mockTask.candidates[0],
              reasons: {
                ...mockTask.candidates[0].reasons,
                rfq: {
                  rfq_id: 'rfq-1',
                  not_in_rfq: true,
                  fitting_rfq_line_ids: [],
                },
              },
            },
          ],
        }),
      );

      component.loadTask('line-99');
      fixture.detectChanges();

      const text = fixture.nativeElement.textContent as string;
      expect(text).toContain('Not in your RFQ');
    });

    it('shows hint "Could be more than one of your RFQ lines" when multiple fitting_rfq_line_ids', () => {
      apiService.getMatchTaskForLine.and.returnValue(
        of({
          ...mockTask,
          candidates: [
            {
              ...mockTask.candidates[0],
              reasons: {
                ...mockTask.candidates[0].reasons,
                rfq: {
                  rfq_id: 'rfq-1',
                  rfq_line_id: 'rfq-line-1',
                  position: 1,
                  pack_check: 'equal',
                  fitting_rfq_line_ids: ['rfq-line-1', 'rfq-line-2'],
                },
              },
            },
          ],
        }),
      );

      component.loadTask('line-99');
      fixture.detectChanges();

      const text = fixture.nativeElement.textContent as string;
      expect(text).toContain('Could be more than one of your RFQ lines');
    });

    it('does not style RFQ candidates with low confidence red class even if score is below 70%', () => {
      apiService.getMatchTaskForLine.and.returnValue(
        of({
          ...mockTask,
          candidates: [
            {
              ...mockTask.candidates[0],
              confidence: '0.2800',
              reasons: {
                ...mockTask.candidates[0].reasons,
                rfq: {
                  rfq_id: 'rfq-1',
                  rfq_line_id: 'rfq-line-1',
                  position: 2,
                  pack_check: 'equal',
                  fitting_rfq_line_ids: ['rfq-line-1'],
                },
              },
            },
          ],
        }),
      );

      component.loadTask('line-99');
      fixture.detectChanges();

      const badge = fixture.nativeElement.querySelector('.cand-confidence-badge') as HTMLElement;
      expect(badge).toBeTruthy();
      expect(badge.classList.contains('low')).toBeFalse();
    });

    it('shows "From your RFQ line {n}" in the decision banner when decision candidate has reasons.rfq.matched', () => {
      apiService.getMatchTaskForLine.and.returnValue(
        of({
          ...mockTask,
          status: 'resolved',
          decision: {
            ...mockDecision,
            selected_match_candidate_id: 'cand-1',
          },
          candidates: [
            {
              ...mockTask.candidates[0],
              reasons: {
                ...mockTask.candidates[0].reasons,
                rfq: {
                  rfq_id: 'rfq-1',
                  rfq_line_id: 'rfq-line-1',
                  position: 3,
                  pack_check: 'equal',
                  matched: true,
                  fitting_rfq_line_ids: ['rfq-line-1'],
                },
              },
            },
          ],
        }),
      );

      component.loadTask('line-99');
      fixture.detectChanges();

      const banner = fixture.nativeElement.querySelector('.decision-banner') as HTMLElement;
      expect(banner).toBeTruthy();
      expect(banner.textContent).toContain('From your RFQ line 3');
    });

    it('does not show RFQ tag in decision banner when corrected away from RFQ candidate to another candidate', () => {
      apiService.getMatchTaskForLine.and.returnValue(
        of({
          ...mockTask,
          status: 'resolved',
          decision: {
            ...mockDecision,
            selected_match_candidate_id: 'cand-2',
          },
          candidates: [
            {
              ...mockTask.candidates[0],
              id: 'cand-1',
              reasons: {
                ...mockTask.candidates[0].reasons,
                rfq: {
                  rfq_id: 'rfq-1',
                  rfq_line_id: 'rfq-line-1',
                  position: 3,
                  pack_check: 'equal',
                  matched: true,
                  fitting_rfq_line_ids: ['rfq-line-1'],
                },
              },
            },
            {
              ...mockTask.candidates[0],
              id: 'cand-2',
              reasons: {
                ...mockTask.candidates[0].reasons,
                rfq: null,
              },
            },
          ],
        }),
      );

      component.loadTask('line-99');
      fixture.detectChanges();

      const tag = fixture.nativeElement.querySelector('.rfq-matched-tag');
      expect(tag).toBeNull();
      const banner = fixture.nativeElement.querySelector('.decision-banner') as HTMLElement;
      expect(banner?.textContent).not.toContain('From your RFQ line');
    });

    it('does not show RFQ tag in decision banner when corrected to new product (selected_match_candidate_id is null)', () => {
      apiService.getMatchTaskForLine.and.returnValue(
        of({
          ...mockTask,
          status: 'resolved',
          decision: {
            ...mockDecision,
            selected_match_candidate_id: null,
          },
          candidates: [
            {
              ...mockTask.candidates[0],
              id: 'cand-1',
              reasons: {
                ...mockTask.candidates[0].reasons,
                rfq: {
                  rfq_id: 'rfq-1',
                  rfq_line_id: 'rfq-line-1',
                  position: 3,
                  pack_check: 'equal',
                  matched: true,
                  fitting_rfq_line_ids: ['rfq-line-1'],
                },
              },
            },
          ],
        }),
      );

      component.loadTask('line-99');
      fixture.detectChanges();

      const tag = fixture.nativeElement.querySelector('.rfq-matched-tag');
      expect(tag).toBeNull();
      const banner = fixture.nativeElement.querySelector('.decision-banner') as HTMLElement;
      expect(banner?.textContent).not.toContain('From your RFQ line');
    });

    it('shows "Correct match" button for buyer/owner on decided line, and hides it for non-writer', () => {
      apiService.getMatchTaskForLine.and.returnValue(
        of({
          ...mockTask,
          status: 'resolved',
          decision: mockDecision,
        }),
      );

      component.loadTask('line-99');
      fixture.detectChanges();

      let correctBtn = fixture.nativeElement.querySelector('.correct-match-btn') as HTMLButtonElement | null;
      expect(correctBtn).toBeTruthy();
      expect(correctBtn?.textContent).toContain('Correct match');

      // Non-writer role (e.g. viewer)
      mockSession.hasRole.and.returnValue(false);
      fixture.detectChanges();

      correctBtn = fixture.nativeElement.querySelector('.correct-match-btn') as HTMLButtonElement | null;
      expect(correctBtn).toBeNull();
    });

    it('submits correction with expected_current_decision_id, selected candidate, learn_alias, and idempotency key', () => {
      apiService.getMatchTaskForLine.and.returnValue(
        of({
          ...mockTask,
          status: 'resolved',
          decision: mockDecision,
        }),
      );
      apiService.correctMatch.and.returnValue(
        of({
          decision: { ...mockDecision, id: 'dec-corrected-1' },
          superseded_decision_id: mockDecision.id,
          lines_matched_through_old_wording: [],
        }),
      );

      component.loadTask('line-99');
      fixture.detectChanges();

      const request: MatchCorrectionRequest = {
        expected_current_decision_id: mockDecision.id,
        outcome: 'same_product',
        selected_match_candidate_id: 'cand-2',
        learn_alias: true,
      };

      component.executeCorrection('line-99', request);

      expect(apiService.correctMatch).toHaveBeenCalledWith(
        'line-99',
        request,
        jasmine.stringMatching(/^[0-9a-f-]{36}$/),
      );
      expect(component.decision()?.id).toBe('dec-corrected-1');
    });

    it('handles success with dependent lines and alias conflict', () => {
      apiService.getMatchTaskForLine.and.returnValue(
        of({
          ...mockTask,
          status: 'resolved',
          decision: mockDecision,
        }),
      );
      apiService.correctMatch.and.returnValue(
        of({
          decision: { ...mockDecision, id: 'dec-corrected-2' },
          superseded_decision_id: mockDecision.id,
          lines_matched_through_old_wording: ['dep-line-1', 'dep-line-2'],
          alias_conflict_product_id: 'prod-conflict-1',
        }),
      );

      component.loadTask('line-99');
      fixture.detectChanges();

      component.executeCorrection('line-99', {
        expected_current_decision_id: mockDecision.id,
        outcome: 'same_product',
        selected_match_candidate_id: 'cand-2',
        learn_alias: true,
      });
      fixture.detectChanges();

      const text = fixture.nativeElement.textContent as string;
      expect(text).toContain('2 other lines were matched through the old wording — review them');
      expect(text).toContain('The wording already points to another product; it was not changed');

      const queueLink = fixture.nativeElement.querySelector('.dependent-lines-banner a') as HTMLAnchorElement | null;
      expect(queueLink).toBeTruthy();
    });

    it('handles 409 line_on_purchase_request with short id and link to /requests/{id}', () => {
      const errorResponse = new HttpErrorResponse({
        status: 409,
        error: {
          code: 'conflict',
          message: 'Line is on a live purchase request',
          details: {
            reason: 'line_on_purchase_request',
            purchase_request_id: 'abcdef01-2345-6789-abcd-ef0123456789',
          },
        },
      });
      apiService.getMatchTaskForLine.and.returnValue(
        of({
          ...mockTask,
          status: 'resolved',
          decision: mockDecision,
        }),
      );
      apiService.correctMatch.and.returnValue(throwError(() => errorResponse));

      component.loadTask('line-99');
      fixture.detectChanges();

      component.executeCorrection('line-99', {
        expected_current_decision_id: mockDecision.id,
        outcome: 'same_product',
        selected_match_candidate_id: 'cand-2',
        learn_alias: true,
      });
      fixture.detectChanges();

      const text = fixture.nativeElement.textContent as string;
      expect(text).toContain('This match prices request abcdef01 — withdraw it first');

      const reqLink = fixture.nativeElement.querySelector('a[href*="/requests/abcdef01-2345-6789-abcd-ef0123456789"]') as HTMLAnchorElement | null;
      expect(reqLink).toBeTruthy();
    });

    it('handles 409 decision_changed with reload prompt', () => {
      const errorResponse = new HttpErrorResponse({
        status: 409,
        error: {
          code: 'conflict',
          message: 'Decision changed',
          details: {
            reason: 'decision_changed',
          },
        },
      });
      apiService.getMatchTaskForLine.and.returnValue(
        of({
          ...mockTask,
          status: 'resolved',
          decision: mockDecision,
        }),
      );
      apiService.correctMatch.and.returnValue(throwError(() => errorResponse));

      component.loadTask('line-99');
      fixture.detectChanges();

      component.executeCorrection('line-99', {
        expected_current_decision_id: mockDecision.id,
        outcome: 'same_product',
        selected_match_candidate_id: 'cand-2',
        learn_alias: true,
      });
      fixture.detectChanges();

      const text = fixture.nativeElement.textContent as string;
      expect(text).toContain('Someone changed this match — reload');
    });
  });

  describe('alias sweep feedback notices (US3 / T026)', () => {
    let snackSpy: jasmine.Spy;

    beforeEach(() => {
      const snackBar = (component as unknown as { snackBar: { open: jasmine.Spy } }).snackBar;
      snackSpy = spyOn(snackBar, 'open');
    });

    it('resolution with 3 swept lines adds "Also matched 3 more lines with the same wording"', () => {
      apiService.resolveMatch.and.returnValue(
        of({
          ...mockDecision,
          lines_matched_by_same_wording: ['swept-1', 'swept-2', 'swept-3'],
        }),
      );

      component.confirmResolution();

      expect(snackSpy).toHaveBeenCalledWith(
        jasmine.stringMatching(/Also matched 3 more lines/),
        undefined,
        { duration: 3500 },
      );
    });

    it('resolution with 1 swept line uses singular "Also matched 1 more line"', () => {
      apiService.resolveMatch.and.returnValue(
        of({
          ...mockDecision,
          lines_matched_by_same_wording: ['swept-1'],
        }),
      );

      component.confirmResolution();

      expect(snackSpy).toHaveBeenCalledWith(
        jasmine.stringMatching(/Also matched 1 more line/),
        undefined,
        { duration: 3500 },
      );
    });

    it('resolution with null/empty swept lines leaves snackbar text unchanged from today', () => {
      apiService.resolveMatch.and.returnValue(
        of({
          ...mockDecision,
          lines_matched_by_same_wording: null,
        }),
      );

      component.confirmResolution();

      expect(snackSpy).toHaveBeenCalledWith(
        enCatalog.matching.resolution.actions.saveSuccess,
        undefined,
        { duration: 3500 },
      );
    });

    it('resolve-and-next with 2 swept lines and no next task includes both queue-cleared and swept message', () => {
      const router = (component as unknown as { router: { navigate: (...args: unknown[]) => Promise<boolean> } }).router;
      spyOn(router, 'navigate').and.returnValue(Promise.resolve(true));
      apiService.resolveMatch.and.returnValue(
        of({
          ...mockDecision,
          lines_matched_by_same_wording: ['swept-1', 'swept-2'],
        }),
      );
      apiService.getNextMatchTask.and.returnValue(of({ next_task_id: null, next_quotation_line_id: null }));

      component.confirmResolution(true);

      expect(apiService.getNextMatchTask).toHaveBeenCalledWith('task-resolve-1');
      expect(snackSpy).toHaveBeenCalledWith(
        jasmine.stringMatching(/All match tasks resolved — queue cleared.*Also matched 2 more lines/),
        undefined,
        { duration: 3500 },
      );
    });

    it('correction with 3 swept lines adds "Also matched 3 more lines with the same wording"', () => {
      apiService.getMatchTaskForLine.and.returnValue(
        of({
          ...mockTask,
          status: 'resolved',
          decision: mockDecision,
        }),
      );
      apiService.correctMatch.and.returnValue(
        of({
          decision: { ...mockDecision, id: 'dec-corrected-3' },
          superseded_decision_id: mockDecision.id,
          lines_matched_through_old_wording: [],
          lines_matched_by_same_wording: ['swept-1', 'swept-2', 'swept-3'],
        }),
      );

      component.executeCorrection('line-99', {
        expected_current_decision_id: mockDecision.id,
        outcome: 'same_product',
        selected_match_candidate_id: 'cand-2',
        learn_alias: true,
      });

      expect(snackSpy).toHaveBeenCalledWith(
        jasmine.stringMatching(/Also matched 3 more lines/),
        undefined,
        { duration: 3500 },
      );
    });

    it('correction with 1 swept line uses singular "Also matched 1 more line"', () => {
      apiService.getMatchTaskForLine.and.returnValue(
        of({
          ...mockTask,
          status: 'resolved',
          decision: mockDecision,
        }),
      );
      apiService.correctMatch.and.returnValue(
        of({
          decision: { ...mockDecision, id: 'dec-corrected-1' },
          superseded_decision_id: mockDecision.id,
          lines_matched_through_old_wording: [],
          lines_matched_by_same_wording: ['swept-1'],
        }),
      );

      component.executeCorrection('line-99', {
        expected_current_decision_id: mockDecision.id,
        outcome: 'same_product',
        selected_match_candidate_id: 'cand-2',
        learn_alias: true,
      });

      expect(snackSpy).toHaveBeenCalledWith(
        jasmine.stringMatching(/Also matched 1 more line/),
        undefined,
        { duration: 3500 },
      );
    });

    it('correction with null/empty swept lines leaves snackbar text unchanged from today', () => {
      apiService.getMatchTaskForLine.and.returnValue(
        of({
          ...mockTask,
          status: 'resolved',
          decision: mockDecision,
        }),
      );
      apiService.correctMatch.and.returnValue(
        of({
          decision: { ...mockDecision, id: 'dec-corrected-0' },
          superseded_decision_id: mockDecision.id,
          lines_matched_through_old_wording: [],
          lines_matched_by_same_wording: [],
        }),
      );

      component.executeCorrection('line-99', {
        expected_current_decision_id: mockDecision.id,
        outcome: 'same_product',
        selected_match_candidate_id: 'cand-2',
        learn_alias: true,
      });

      expect(snackSpy).toHaveBeenCalledWith(
        enCatalog.matching.resolution.actions.correctSuccess,
        undefined,
        { duration: 3500 },
      );
    });

    it('supports Arabic plural forms for swept lines feedback', () => {
      const translate = TestBed.inject(TranslateService);
      translate.setTranslation('ar', arCatalog);
      translate.use('ar');

      // 1 swept line (singular / one)
      apiService.resolveMatch.and.returnValue(
        of({
          ...mockDecision,
          lines_matched_by_same_wording: ['swept-1'],
        }),
      );
      component.confirmResolution();
      expect(snackSpy).toHaveBeenCalledWith(
        jasmine.stringMatching(/تمت أيضًا مطابقة بند إضافي واحد بنفس الصياغة/),
        undefined,
        { duration: 3500 },
      );

      // 3 swept lines (few)
      snackSpy.calls.reset();
      apiService.resolveMatch.and.returnValue(
        of({
          ...mockDecision,
          lines_matched_by_same_wording: ['swept-1', 'swept-2', 'swept-3'],
        }),
      );
      component.confirmResolution();
      expect(snackSpy).toHaveBeenCalledWith(
        jasmine.stringMatching(/تمت أيضًا مطابقة 3 بنود إضافية بنفس الصياغة/),
        undefined,
        { duration: 3500 },
      );
    });
  });
});
