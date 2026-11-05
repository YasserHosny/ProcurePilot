import { HttpErrorResponse } from '@angular/common/http';
import { Component, HostListener, OnInit, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormBuilder, FormGroup, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
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
  LandedCost,
  MatchCandidate,
  MatchCorrectionRequest,
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
import { ProductPickerComponent } from './product-picker.component';
import {
  CorrectMatchDialogComponent,
  FALLBACK_BASE_UNITS,
  type SelectableUnit,
} from './correct-match-dialog.component';
import { FormatPercentPipe } from '../../../core/format/percent.pipe';
import { FormatQuantityPipe } from '../../../core/format/quantity.pipe';
import { UnitLabelPipe } from '../../../core/format/unit-label';
import { formatSweptLinesMessage, appendSweptMessage, CorrectionKeyManager } from '../matching-api';

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
    MatDialogModule,
    MatTooltipModule,
    TranslatePipe,
    FormatPercentPipe,
    FormatQuantityPipe,
    UnitLabelPipe,
    FormatDatePipe,
    FormatMoneyPipe,
    MatchResolutionCandidatesComponent,
    ProductPickerComponent,
  ],
  templateUrl: './match-resolution.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
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
  private readonly dialog = inject(MatDialog);

  readonly isLoading = signal<boolean>(true);
  readonly isSubmitting = signal<boolean>(false);
  readonly routeId = signal<string>('');
  readonly quotationId = signal<string | null>(null);

  readonly task = signal<MatchTask | null>(null);
  readonly line = signal<QuotationLineSummary | null>(null);
  readonly candidates = signal<MatchCandidate[]>([]);
  readonly decision = signal<MatchDecision | null>(null);

  // Correction chain (P-154): loaded when the buyer opens it, so it is always current.
  readonly historyOpen = signal(false);
  readonly history = signal<readonly MatchDecision[] | null>(null);
  readonly historyFailed = signal(false);
  readonly landedCost = signal<LandedCost | null>(null);

  readonly baseUnits = signal<SelectableUnit[]>([]);
  readonly suppliers = signal<Supplier[]>([]);

  // Selected candidate and outcome
  readonly selectedCandidateId = signal<string | null>(null);
  readonly selectedOutcome = signal<MatchOutcome>('same_product');

  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);
  readonly purchaseRequestConflict = signal<{ id: string; shortId: string } | null>(null);
  readonly dependentLinesCount = signal<number>(0);
  readonly aliasConflictNotice = signal<boolean>(false);
  readonly isReloadable = signal<boolean>(false);
  private readonly correctionKeys = new CorrectionKeyManager();
  private currentLoadedLineId: string | null = null;
  private latestLoadTaskId = 0;
  private latestLandedCostRequestId = 0;
  private resolutionKey: string | null = null;

  isWriter(): boolean {
    return this.session.hasRole('owner', 'buyer');
  }

  readonly matchedRfqPosition = computed<number | null>(() => {
    const dec = this.decision();
    if (!dec || !dec.selected_match_candidate_id) return null;
    const cand = this.candidates().find((c) => c.id === dec.selected_match_candidate_id);
    if (cand?.reasons?.rfq?.matched && cand.reasons.rfq.position != null) {
      return cand.reasons.rfq.position;
    }
    return null;
  });

  backQueryParams = computed<Record<string, string>>(() => {
    const qp = this.route.snapshot.queryParamMap;
    const out: Record<string, string> = {};
    const keys = ['quotation_id', 'status', 'priority', 'reason', 'search', 'date_from', 'date_to', 'sort_by', 'sort_order'];
    for (const k of keys) {
      const v = qp.get(k);
      if (v) out[k] = v;
    }
    // Ensure quotation_id falls back to loaded task's quotation id
    if (!out['quotation_id']) {
      const qid = this.quotationId() || this.task()?.quotation_id;
      if (qid) out['quotation_id'] = qid;
    }
    return out;
  });

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

  readonly matchedProductName = computed<string>(() => {
    const taskProduct = this.task()?.matched_product;
    const decisionProduct = this.decision()?.matched_product;
    return (
      taskProduct?.tenant_name ||
      taskProduct?.canonical_name ||
      decisionProduct?.tenant_name ||
      decisionProduct?.canonical_name ||
      ''
    );
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
    this.loadReferenceData();
    if (this.route.paramMap) {
      this.route.paramMap.subscribe((params) => {
        const id = params.get('id');
        this.quotationId.set(this.route.snapshot?.queryParamMap?.get('quotation_id') ?? null);
        if (id && id !== this.routeId()) {
          this.routeId.set(id);
          this.loadTask(id);
        }
      });
    } else {
      const id = this.route.snapshot.paramMap.get('id');
      this.quotationId.set(this.route.snapshot.queryParamMap.get('quotation_id'));
      if (id) {
        this.routeId.set(id);
        this.loadTask(id);
      }
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
        this.baseUnits.set(FALLBACK_BASE_UNITS);
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
    const requestId = ++this.latestLoadTaskId;
    this.latestLandedCostRequestId++;
    if (this.currentLoadedLineId !== id) {
      this.correctionKeys.clear();
      this.currentLoadedLineId = id;
    }
    this.resolutionKey = null;
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);
    this.dependentLinesCount.set(0);
    this.aliasConflictNotice.set(false);

    this.api.getMatchTaskForLine(id).subscribe({
      next: (task) => {
        if (requestId !== this.latestLoadTaskId) return;
        this.quotationId.set(task.quotation.id);
        this.applyTask(task);
      },
      error: (err: unknown) => {
        if (requestId !== this.latestLoadTaskId) return;
        if (err instanceof HttpErrorResponse && err.status === 404 && this.api.getMatchTasks) {
          this.api.getMatchTasks({ status: 'all', limit: 100 }).subscribe({
            next: (res) => {
              if (requestId !== this.latestLoadTaskId) return;
              const matched = res.items.find((item) => item.id === id || item.quotation_line.id === id);
              if (matched && matched.quotation_line.id !== id) {
                this.loadTask(matched.quotation_line.id);
                return;
              }
              this.isLoading.set(false);
              this.handleError(err);
            },
            error: (fallbackErr: unknown) => {
              if (requestId !== this.latestLoadTaskId) return;
              this.isLoading.set(false);
              this.handleError(fallbackErr);
            },
          });
          return;
        }
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
      this.history.set(null);
      this.historyOpen.set(false);
      this.selectedOutcome.set(t.decision.outcome);
      if (t.decision.selected_match_candidate_id) {
        this.selectedCandidateId.set(t.decision.selected_match_candidate_id);
      }
      this.loadLandedCost(t.quotation_line.id);
    } else {
      this.decision.set(null);
      this.landedCost.set(null);
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
    const costRequestId = ++this.latestLandedCostRequestId;
    this.api.getLandedCost(lineId).subscribe({
      next: (cost) => {
        if (costRequestId !== this.latestLandedCostRequestId) return;
        this.landedCost.set(cost);
        this.isLoading.set(false);
      },
      error: () => {
        if (costRequestId !== this.latestLandedCostRequestId) return;
        this.isLoading.set(false);
      },
    });
  }

  toggleHistory(): void {
    if (this.historyOpen()) {
      this.historyOpen.set(false);
      return;
    }
    const lineId = this.line()?.id;
    if (!lineId) return;
    this.historyOpen.set(true);
    this.historyFailed.set(false);
    this.api.getDecisionHistory(lineId).subscribe({
      next: (res) => this.history.set(res.items),
      error: () => this.historyFailed.set(true),
    });
  }

  /** A catalogue product the buyer picked was recorded as a candidate: list it and select it. */
  onManualCandidate(candidate: MatchCandidate): void {
    if (!this.candidates().some((c) => c.id === candidate.id)) {
      this.candidates.update((list) => [...list, candidate]);
    }
    this.selectCandidate(candidate.id);
    this.selectedOutcome.set('same_product');
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
    if (this.dialog.openDialogs.length > 0) {
      return;
    }

    if (event.key === 'Enter') {
      if ((event.ctrlKey || event.metaKey) && !event.altKey) {
        if (this.isWriter() && !this.isSubmitting() && !this.decision()) {
          event.preventDefault();
          this.confirmResolution();
        }
      }
      return;
    }

    if (event.altKey || event.ctrlKey || event.metaKey) {
      return;
    }

    const targetEl =
      event.target instanceof Element
        ? event.target
        : (event.target as Node | null)?.parentElement ?? null;
    const tagName = targetEl?.tagName?.toLowerCase();
    const isTextInput =
      (tagName === 'input' &&
        (targetEl as HTMLInputElement).type !== 'radio' &&
        (targetEl as HTMLInputElement).type !== 'checkbox') ||
      tagName === 'textarea' ||
      tagName === 'select';

    const isInsideSelectOrList = Boolean(
      targetEl?.closest?.(
        '[role="combobox"], [role="listbox"], [role="option"], mat-select, mat-radio-group.outcomes-radio-group, .outcomes-radio-group'
      )
    );

    if (isTextInput || isInsideSelectOrList) {
      return;
    }

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
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      this.navigateCandidate(1);
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      this.navigateCandidate(-1);
      return;
    }
    if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
      event.preventDefault();
      const isRtl = document.documentElement.dir === 'rtl';
      const isNext = (event.key === 'ArrowRight' && !isRtl) || (event.key === 'ArrowLeft' && isRtl);
      this.navigateCandidate(isNext ? 1 : -1);
      return;
    }

    if (event.key === 'o' || event.key === 'O') {
      event.preventDefault();
      this.cycleOutcome();
      return;
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

    this.resolutionKey ??= crypto.randomUUID();
    const key = this.resolutionKey;

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

    this.api.resolveMatch(l.id, payload, key).subscribe({
      next: (decision) => {
        this.isSubmitting.set(false);
        this.resolutionKey = null;
        this.decision.set(decision);
        this.history.set(null);
        this.historyOpen.set(false);
        if (resolveNext) {
          this.navigateToNextTask(l.id, decision);
          return;
        }
        const baseMsg = this.translate.instant('matching.resolution.actions.saveSuccess');
        const swept = formatSweptLinesMessage(this.translate, decision.lines_matched_by_same_wording);
        const msg = swept ? appendSweptMessage(baseMsg, swept) : baseMsg;
        this.snackBar.open(
          msg,
          undefined,
          { duration: 3500 },
        );
        this.loadLandedCost(l.id);
        void this.router.navigate(['/matching'], { queryParams: this.backQueryParams() });
      },
      error: (err: unknown) => {
        this.isSubmitting.set(false);
        this.handleError(err);
      },
    });
  }

  private navigateToNextTask(resolvedLineId: string, decision?: MatchDecision): void {
    const excludeTaskId = this.task()?.id ?? resolvedLineId;
    const quotationId = this.quotationId() || this.task()?.quotation_id || undefined;
    if (this.api.getNextMatchTask) {
      this.api.getNextMatchTask(excludeTaskId, quotationId).subscribe({
        next: (res) => {
          if (res.next_quotation_line_id) {
            const baseMsg = this.translate.instant('matching.resolution.actions.saveSuccess');
            const swept = formatSweptLinesMessage(this.translate, decision?.lines_matched_by_same_wording);
            const msg = swept ? appendSweptMessage(baseMsg, swept) : baseMsg;
            this.snackBar.open(
              msg,
              undefined,
              { duration: 3500 },
            );
            void this.router.navigate(['/matching', res.next_quotation_line_id], {
              queryParams: this.backQueryParams(),
            });
            return;
          }
          const clearedKey = quotationId
            ? 'matching.queue.allLinesMatchedTitle'
            : 'matching.resolution.actions.queueCleared';
          const queueClearedMsg = this.translate.instant(clearedKey);
          const swept = formatSweptLinesMessage(this.translate, decision?.lines_matched_by_same_wording);
          const msg = swept ? appendSweptMessage(queueClearedMsg, swept) : queueClearedMsg;
          this.snackBar.open(
            msg,
            undefined,
            { duration: 3500 },
          );
          void this.router.navigate(['/matching'], { queryParams: this.backQueryParams() });
        },
        error: (err: unknown) => this.handleError(err),
      });
    }
  }

  formatScore(score: string | number | undefined | null): number {
    if (score === undefined || score === null) return 0;
    const num = typeof score === 'string' ? parseFloat(score) : score;
    return Math.round(num * 100);
  }

  formatVatRate(rate: string | number | null | undefined): string {
    if (rate == null || rate === '') return '';
    let str = String(rate).trim();
    if (!str) return '';
    if (str.endsWith('%')) {
      str = str.slice(0, -1).trim();
    }

    const isNegative = str.startsWith('-');
    const unsigned = isNegative ? str.slice(1) : str;
    const parts = unsigned.split('.');

    const whole = parts[0] || '0';
    let fraction = parts[1] || '';

    // Decimal-safe multiply by 100 by shifting decimal point 2 places to the right
    fraction = fraction.padEnd(2, '0');
    const shiftedWhole = (whole === '0' ? '' : whole) + fraction.slice(0, 2);
    const shiftedFraction = fraction.slice(2);

    let resultWhole = shiftedWhole.replace(/^0+/, '');
    if (resultWhole === '') {
      resultWhole = '0';
    }

    const resultFraction = shiftedFraction.replace(/0+$/, '');
    const sign = isNegative ? '-' : '';
    const result = resultFraction ? `${resultWhole}.${resultFraction}` : resultWhole;
    return `${sign}${result}%`;
  }

  isDiscountNonZero(discount?: { amount: string | number } | null): boolean {
    if (!discount || discount.amount == null) return false;
    const num = typeof discount.amount === 'number' ? discount.amount : parseFloat(discount.amount);
    return !isNaN(num) && num !== 0;
  }

  shouldShowSemanticSignal(candidate: MatchCandidate): boolean {
    return candidate.embedding_model !== 'stub-hash-v1';
  }

  localizedUnitLabel(unit: SelectableUnit): string {
    const label = this.translate.getCurrentLang() === 'ar' ? unit.label_ar : unit.label_en;
    return label || this.translate.instant(`matching.resolution.unitNames.${unit.code}`);
  }

  openCorrectMatchDialog(): void {
    const dec = this.decision();
    const l = this.line();
    if (!dec || !l || !this.isWriter()) return;

    const dialogRef = this.dialog.open(CorrectMatchDialogComponent, {
      width: '640px',
      data: {
        line: l,
        candidates: this.candidates(),
        expectedCurrentDecisionId: dec.id,
        currentCandidateId: dec.selected_match_candidate_id ?? null,
        // The unit list loads in parallel: until it arrives (or if it is empty) offer the built-in units.
        baseUnits: this.baseUnits().length > 0 ? this.baseUnits() : FALLBACK_BASE_UNITS,
        quotationSupplierId: this.task()?.quotation?.supplier_id ?? null,
      },
    });

    dialogRef.afterClosed().subscribe((result: MatchCorrectionRequest | null | undefined) => {
      if (result) {
        this.executeCorrection(l.id, result);
      }
    });
  }

  executeCorrection(lineId: string, payload: MatchCorrectionRequest): void {
    if (!this.isWriter()) return;

    const startLoadTaskId = this.latestLoadTaskId;
    const startLineId = this.currentLoadedLineId ?? this.line()?.id ?? lineId;

    this.isSubmitting.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);
    this.purchaseRequestConflict.set(null);
    this.dependentLinesCount.set(0);
    this.aliasConflictNotice.set(false);
    this.isReloadable.set(false);

    const key = this.correctionKeys.getKey(payload);

    const hasBuyerMoved = (): boolean => {
      const currentLineId = this.currentLoadedLineId ?? this.line()?.id ?? lineId;
      return this.latestLoadTaskId !== startLoadTaskId || currentLineId !== startLineId;
    };

    this.api.correctMatch(lineId, payload, key).subscribe({
      next: (res) => {
        this.isSubmitting.set(false);
        this.correctionKeys.recordSuccess();

        const baseMsg = this.translate.instant('matching.resolution.actions.correctSuccess');
        const swept = formatSweptLinesMessage(this.translate, res.lines_matched_by_same_wording);
        const msg = swept ? appendSweptMessage(baseMsg, swept) : baseMsg;
        this.snackBar.open(
          msg,
          undefined,
          { duration: 3500 },
        );

        if (hasBuyerMoved()) {
          return;
        }

        this.loadTask(lineId);
        this.decision.set(res.decision);
        this.history.set(null);
        this.historyOpen.set(false);

        if (res.lines_matched_through_old_wording && res.lines_matched_through_old_wording.length > 0) {
          this.dependentLinesCount.set(res.lines_matched_through_old_wording.length);
        }

        if (res.alias_conflict_product_id) {
          this.aliasConflictNotice.set(true);
        }
      },
      error: (err: unknown) => {
        this.isSubmitting.set(false);
        if (hasBuyerMoved()) {
          return;
        }
        this.handleCorrectionError(err);
      },
    });
  }

  private handleCorrectionError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorTraceId.set(apiError?.trace_id ?? null);

      if (err.status === 409) {
        const details = (apiError?.details as Record<string, unknown> | undefined);
        const reason = details?.['reason'];

        if (reason === 'line_on_purchase_request') {
          const prId = String(details?.['purchase_request_id'] ?? '');
          const shortId = prId ? prId.slice(0, 8) : '';
          this.purchaseRequestConflict.set({ id: prId, shortId });
          this.errorMessage.set(
            this.translate.instant('matching.resolution.errors.lineOnPurchaseRequest', { shortId }),
          );
          return;
        }

        if (reason === 'decision_changed') {
          this.isReloadable.set(true);
          this.errorMessage.set(
            this.translate.instant('matching.resolution.errors.decisionChanged'),
          );
          return;
        }
      }
    }
    this.handleError(err);
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
