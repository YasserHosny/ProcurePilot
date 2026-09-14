import { HttpErrorResponse } from '@angular/common/http';
import { Component, HostListener, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, FormGroup, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatRadioModule } from '@angular/material/radio';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { ApiService } from '../../../core/api/api.service';
import type {
  ApiError,
  BaseUnit,
  LandedCost,
  MatchCandidate,
  MatchDecision,
  MatchOutcome,
  MatchResolutionRequest,
  MatchTask,
  ProductCreate,
  QuotationLineSummary,
  Supplier,
} from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import { computeBaseQuantity } from '../../catalogue/normalisation';

import { MatchResolutionCandidatesComponent } from './match-resolution-candidates.component';

@Component({
  selector: 'app-match-resolution',
  standalone: true,
  imports: [
    FormsModule,
    ReactiveFormsModule,
    RouterLink,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatChipsModule,
    MatDividerModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatRadioModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatTooltipModule,
    TranslatePipe,
    FormatDatePipe,
    FormatMoneyPipe,
    MatchResolutionCandidatesComponent,
  ],
  templateUrl: './match-resolution.component.html',
  styleUrl: './match-resolution.component.scss',
})
export class MatchResolutionComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(true);
  readonly isSubmitting = signal<boolean>(false);
  readonly routeId = signal<string>('');
  readonly quotationId = signal<string | null>(null);

  readonly task = signal<MatchTask | null>(null);
  readonly line = signal<QuotationLineSummary | null>(null);
  readonly candidates = signal<MatchCandidate[]>([]);
  readonly decision = signal<MatchDecision | null>(null);
  readonly landedCost = signal<LandedCost | null>(null);

  readonly baseUnits = signal<BaseUnit[]>([]);
  readonly suppliers = signal<Supplier[]>([]);

  // Selected candidate and outcome
  readonly selectedCandidateId = signal<string | null>(null);
  readonly selectedOutcome = signal<MatchOutcome>('same_product');

  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);

  readonly isWriter = computed<boolean>(() => this.session.hasRole('owner', 'buyer'));

  // Product form for inline product creation
  readonly productForm: FormGroup = this.fb.group({
    tenant_name: ['', [Validators.required, Validators.maxLength(200)]],
    brand: [''],
    canonical_name: [''],
    variant: [''],
    gtin: ['', [Validators.pattern(/^(\d{8}|\d{12}|\d{13}|\d{14})?$/)]],
    base_unit: ['', [Validators.required]],
    pack_count: [1, [Validators.required, Validators.min(1)]],
    unit_size: ['', [Validators.required, Validators.pattern(/^\d+(\.\d+)?$/)]],
    preferred_supplier_id: [null],
  });

  readonly livePackCount = signal<number | null>(1);
  readonly liveUnitSize = signal<string>('');
  readonly liveBaseUnit = signal<string>('');

  readonly liveNormalisedQuantity = computed<string | null>(() => {
    const count = this.livePackCount();
    const size = this.liveUnitSize();
    return computeBaseQuantity(count, size);
  });

  readonly selectedCandidate = computed<MatchCandidate | null>(() => {
    const id = this.selectedCandidateId();
    if (!id) return null;
    return this.candidates().find((c) => c.id === id) ?? null;
  });

  readonly outcomeOptions: readonly { value: MatchOutcome; labelKey: string; descKey: string }[] = [
    {
      value: 'same_product',
      labelKey: 'matching.resolution.outcomes.same_product.label',
      descKey: 'matching.resolution.outcomes.same_product.description',
    },
    {
      value: 'different_pack',
      labelKey: 'matching.resolution.outcomes.different_pack.label',
      descKey: 'matching.resolution.outcomes.different_pack.description',
    },
    {
      value: 'different_variant',
      labelKey: 'matching.resolution.outcomes.different_variant.label',
      descKey: 'matching.resolution.outcomes.different_variant.description',
    },
    {
      value: 'compatible_alternative',
      labelKey: 'matching.resolution.outcomes.compatible_alternative.label',
      descKey: 'matching.resolution.outcomes.compatible_alternative.description',
    },
    {
      value: 'no_match_new_product',
      labelKey: 'matching.resolution.outcomes.no_match_new_product.label',
      descKey: 'matching.resolution.outcomes.no_match_new_product.description',
    },
  ];

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    this.quotationId.set(this.route.snapshot.queryParamMap.get('quotation_id'));
    if (id) {
      this.routeId.set(id);
      this.loadReferenceData();
      this.loadTask(id);
    }

    this.productForm.valueChanges.subscribe((vals) => {
      this.livePackCount.set(vals.pack_count ? Number(vals.pack_count) : null);
      this.liveUnitSize.set(vals.unit_size ? String(vals.unit_size) : '');
      this.liveBaseUnit.set(vals.base_unit ? String(vals.base_unit) : '');
    });
  }

  private loadReferenceData(): void {
    this.api.baseUnits().subscribe({
      next: (res) => this.baseUnits.set(res.items),
      error: () => {
        this.baseUnits.set([
          { code: 'litre', label_en: 'Litre (L)', label_ar: 'لتر (L)', dimension: 'volume' },
          { code: 'millilitre', label_en: 'Millilitre (ml)', label_ar: 'مليلتر (ml)', dimension: 'volume' },
          { code: 'kilogram', label_en: 'Kilogram (kg)', label_ar: 'كيلوغرام (kg)', dimension: 'mass' },
          { code: 'gram', label_en: 'Gram (g)', label_ar: 'غرام (g)', dimension: 'mass' },
          { code: 'each', label_en: 'Each (item)', label_ar: 'حبة / قطعة', dimension: 'count' },
        ]);
      },
    });

    this.api.suppliers({ status: 'all' }).subscribe({
      next: (res) => this.suppliers.set(res.items),
      error: () => {
        this.suppliers.set([]);
      },
    });
  }

  loadTask(id: string): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    this.api.getMatchTaskForLine(id).subscribe({
      next: (task) => {
        this.quotationId.set(task.quotation.id);
        this.applyTask(task);
      },
      error: (err: unknown) => {
        this.isLoading.set(false);
        this.handleError(err);
      },
    });
  }

  private applyTask(t: MatchTask): void {
    this.task.set(t);
    this.line.set(t.quotation_line);
    const sortedCandidates = [...t.candidates].sort((a, b) => a.rank - b.rank);
    this.candidates.set(sortedCandidates);

    if (t.decision) {
      this.decision.set(t.decision);
      this.selectedOutcome.set(t.decision.outcome);
      if (t.decision.selected_match_candidate_id) {
        this.selectedCandidateId.set(t.decision.selected_match_candidate_id);
      }
      this.loadLandedCost(t.quotation_line.id);
    } else {
      if (sortedCandidates.length > 0 && t.reason !== 'close_candidates') {
        this.selectedCandidateId.set(sortedCandidates[0].id);
        this.selectedOutcome.set('same_product');
      } else if (sortedCandidates.length > 0) {
        this.selectedCandidateId.set(null);
        this.selectedOutcome.set('same_product');
      } else {
        this.selectedOutcome.set('no_match_new_product');
      }

      if (t.quotation_line) {
        this.productForm.patchValue({
          tenant_name: t.quotation_line.original_text,
          unit_size: t.quotation_line.pack?.unit_size || '1.0',
          pack_count: t.quotation_line.pack?.pack_count || 1,
          preferred_supplier_id: t.quotation.supplier_id ?? null,
        });
      }
      this.isLoading.set(false);
    }
  }

  private loadLandedCost(lineId: string): void {
    this.api.getLandedCost(lineId).subscribe({
      next: (cost) => {
        this.landedCost.set(cost);
        this.isLoading.set(false);
      },
      error: () => {
        this.isLoading.set(false);
      },
    });
  }

  selectCandidate(candidateId: string): void {
    this.selectedCandidateId.set(candidateId);
    if (this.selectedOutcome() === 'no_match_new_product') {
      this.selectedOutcome.set('same_product');
    }
  }

  selectOutcome(outcome: MatchOutcome): void {
    this.selectedOutcome.set(outcome);
    if (outcome === 'no_match_new_product') {
      const currentLine = this.line();
      if (currentLine && !this.productForm.get('tenant_name')?.value) {
        this.productForm.patchValue({
          tenant_name: currentLine.original_text,
        });
      }
    }
  }

  // Keyboard navigation & confirmation
  @HostListener('window:keydown', ['$event'])
  handleKeyboardEvent(event: KeyboardEvent): void {
    // Ignore keyboard shortcuts if the user is typing in a text input or select
    const target = event.target as HTMLInputElement | null;
    const tagName = target?.tagName?.toLowerCase();
    const isTextInput =
      (tagName === 'input' && target?.type !== 'radio' && target?.type !== 'checkbox') ||
      tagName === 'textarea' ||
      tagName === 'select';

    // Allow Enter inside input if Ctrl or Meta is pressed
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey || !isTextInput)) {
      if (this.isWriter() && !this.isSubmitting() && !this.decision()) {
        event.preventDefault();
        this.confirmResolution();
        return;
      }
    }

    if (isTextInput) return;

    // Number keys 1-9: Select candidate by rank
    const digit = parseInt(event.key, 10);
    if (!isNaN(digit) && digit >= 1 && digit <= 9) {
      const cands = this.candidates();
      if (digit <= cands.length) {
        event.preventDefault();
        this.selectCandidate(cands[digit - 1].id);
      }
      return;
    }

    // Arrow keys: Navigate between candidates
    if (event.key === 'ArrowDown' || event.key === 'ArrowRight') {
      event.preventDefault();
      this.navigateCandidate(1);
    } else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') {
      event.preventDefault();
      this.navigateCandidate(-1);
    } else if (event.key === 'o' || event.key === 'O') {
      // Toggle outcome
      event.preventDefault();
      this.cycleOutcome();
    }
  }

  private navigateCandidate(offset: number): void {
    const cands = this.candidates();
    if (cands.length === 0) return;

    const currentId = this.selectedCandidateId();
    const currentIndex = currentId ? cands.findIndex((c) => c.id === currentId) : -1;
    let nextIndex = currentIndex + offset;

    if (nextIndex < 0) nextIndex = cands.length - 1;
    if (nextIndex >= cands.length) nextIndex = 0;

    this.selectCandidate(cands[nextIndex].id);
  }

  private cycleOutcome(): void {
    const outcomes: MatchOutcome[] = [
      'same_product',
      'different_pack',
      'different_variant',
      'compatible_alternative',
      'no_match_new_product',
    ];
    const currentIndex = outcomes.indexOf(this.selectedOutcome());
    const nextIndex = (currentIndex + 1) % outcomes.length;
    this.selectOutcome(outcomes[nextIndex]);
  }

  confirmResolution(resolveNext = false): void {
    const l = this.line();
    if (!l || !this.isWriter()) return;

    const outcome = this.selectedOutcome();

    // Validation checks
    if (outcome === 'no_match_new_product') {
      if (this.productForm.invalid) {
        this.productForm.markAllAsTouched();
        this.snackBar.open(
          this.translate.instant('matching.resolution.actions.formInvalid'),
          undefined,
          { duration: 3500 },
        );
        return;
      }
    } else {
      if (!this.selectedCandidateId()) {
        this.snackBar.open(
          this.translate.instant('matching.resolution.actions.candidateRequired'),
          undefined,
          { duration: 3500 },
        );
        return;
      }
    }

    this.isSubmitting.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    // CRITICAL: Ensure EVERY user selection is accurately serialized into the request payload!
    let payload: MatchResolutionRequest;

    if (outcome === 'no_match_new_product') {
      const fv = this.productForm.value;
      const productCreate: ProductCreate = {
        tenant_name: String(fv.tenant_name).trim(),
        brand: fv.brand ? String(fv.brand).trim() : null,
        canonical_name: fv.canonical_name ? String(fv.canonical_name).trim() : null,
        variant: fv.variant ? String(fv.variant).trim() : null,
        gtin: fv.gtin ? String(fv.gtin).trim() : null,
        base_unit: fv.base_unit,
        pack: {
          pack_count: Number(fv.pack_count),
          unit_size: String(fv.unit_size).trim(),
        },
        preferred_supplier_id: fv.preferred_supplier_id || null,
      };

      payload = {
        outcome: 'no_match_new_product',
        selected_match_candidate_id: null,
        create_product: productCreate,
      };
    } else {
      payload = {
        outcome,
        selected_match_candidate_id: this.selectedCandidateId(),
        create_product: null,
      };
    }

    this.api.resolveMatch(l.id, payload).subscribe({
      next: (decision) => {
        this.isSubmitting.set(false);
        this.decision.set(decision);
        this.snackBar.open(
          this.translate.instant('matching.resolution.actions.saveSuccess'),
          undefined,
          { duration: 3500 },
        );
        // Refresh landed cost for the resolved line
        this.loadLandedCost(l.id);
        if (resolveNext) {
          this.navigateToNextTask(l.id);
        }
      },
      error: (err: unknown) => {
        this.isSubmitting.set(false);
        this.handleError(err);
      },
    });
  }

  private navigateToNextTask(resolvedLineId: string): void {
    const quotationId = this.quotationId() ?? this.task()?.quotation.id;
    if (!quotationId) return;
    this.api
      .getMatchTasks({
        status: 'open',
        quotation_id: quotationId,
        limit: 100,
        sort_by: 'created_at',
        sort_order: 'asc',
      })
      .subscribe({
        next: (response) => {
          const next = response.items.find(
            (task) => task.quotation_line.id !== resolvedLineId,
          );
          if (next) {
            void this.router.navigate(['/matching', next.quotation_line.id], {
              queryParams: { quotation_id: quotationId },
            });
            return;
          }
          void this.router.navigate(['/matching'], {
            queryParams: { quotation_id: quotationId },
          });
        },
        error: (err: unknown) => this.handleError(err),
      });
  }

  formatScore(score: string | number | undefined | null): number {
    if (score === undefined || score === null) return 0;
    const num = typeof score === 'string' ? parseFloat(score) : score;
    return Math.round(num * 100);
  }

  shouldShowSemanticSignal(candidate: MatchCandidate): boolean {
    return candidate.embedding_model !== 'stub-hash-v1';
  }

  localizedUnitLabel(unit: BaseUnit): string {
    return this.translate.currentLang === 'ar' ? unit.label_ar : unit.label_en;
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorTraceId.set(apiError?.trace_id ?? null);

      if (err.status === 409) {
        this.errorMessage.set(
          apiError?.message ??
            this.translate.instant('matching.resolution.errors.aliasConflict'),
        );
        return;
      }

      this.errorMessage.set(
        apiError?.message ??
          err.message ??
          this.translate.instant('matching.resolution.errors.genericError'),
      );
      return;
    }
    this.errorMessage.set(this.translate.instant('matching.resolution.errors.genericError'));
  }
}
