import { JsonPipe, PercentPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, HostListener, OnInit, computed, inject, signal } from '@angular/core';
import { DomSanitizer, type SafeResourceUrl } from '@angular/platform-browser';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatChipsModule } from '@angular/material/chips';
import { MatNativeDateModule } from '@angular/material/core';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatDialogModule } from '@angular/material/dialog';
import { MatDividerModule } from '@angular/material/divider';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { ApiService } from '../../../core/api/api.service';
import type {
  AuditTrailEntry,
  ApiError,
  FieldCorrection,
  FieldExtraction,
  Money,
  NewQuotationLine,
  QuotationDetail,
  Supplier,
} from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';

interface FlaggedField {
  readonly id: string;
  readonly entityType: 'quotation' | 'quotation_line';
  readonly entityId: string;
  readonly fieldName: string;
  readonly label: string;
  readonly confidence: number;
  readonly extraction: FieldExtraction;
}

interface ExpiryBadge {
  readonly kind: 'expired' | 'warning' | 'valid';
  readonly labelKey: 'quotations.review.expired' | 'quotations.review.expiresIn' | 'quotations.review.validFor';
  readonly count?: number;
}

interface EffectiveLineAmounts {
  readonly quantity: number;
  readonly unitPrice: number;
  readonly deliveryFee: number;
  readonly discount: number;
  readonly vatRate: number;
}

interface SupplierSuggestion {
  readonly id: string;
  readonly name: string;
  readonly confidencePct: number;
  readonly tier: 'high' | 'medium';
}

type QuotationTimestampFields = QuotationDetail & {
  readonly extracted_at?: string | null;
  readonly updated_at?: string | null;
};

@Component({
  selector: 'app-quotation-review',
  standalone: true,
  imports: [
    JsonPipe,
    PercentPipe,
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
    MatCheckboxModule,
    MatDatepickerModule,
    MatNativeDateModule,
    MatExpansionModule,
    MatTableModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatDialogModule,
    MatTooltipModule,
    TranslatePipe,
    FormatDatePipe,
    FormatMoneyPipe,
  ],
  templateUrl: './quotation-review.component.html',
  styleUrl: './quotation-review.component.scss',
})
export class QuotationReviewComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);
  private readonly sanitizer = inject(DomSanitizer);

  readonly isLoading = signal<boolean>(true);
  readonly isSaving = signal<boolean>(false);
  readonly isConfirming = signal<boolean>(false);
  readonly isRefusing = signal<boolean>(false);
  readonly isArchiving = signal<boolean>(false);
  readonly isRetryingExtraction = signal<boolean>(false);
  readonly isReplacingDocument = signal<boolean>(false);
  readonly isExporting = signal<boolean>(false);
  readonly mismatchAcknowledged = signal<boolean>(false);
  readonly confirmDialogVisible = signal<boolean>(false);
  readonly quotationId = signal<string>('');
  readonly quotation = signal<QuotationDetail | null>(null);
  readonly auditTrail = signal<AuditTrailEntry[]>([]);
  readonly isLoadingAudit = signal<boolean>(false);
  readonly suppliers = signal<Supplier[]>([]);
  readonly priorQuotations = signal<{ id: string; created_at: string; supplier_name: string | null }[]>([]);

  readonly selectedSupplierId = signal<string | null>(null);
  readonly reviewerNotes = signal<string>('');
  readonly isRequote = signal<boolean>(false);
  readonly selectedPreviousQuotationId = signal<string | null>(null);
  readonly isCreatingSupplierFromExtraction = signal<boolean>(false);

  // Field corrections map: field_extraction_id -> corrected value
  readonly pendingCorrections = signal<Map<string, unknown>>(new Map());

  // Line add/remove staging
  readonly pendingNewLines = signal<NewQuotationLine[]>([]);
  readonly pendingRemoveLineIds = signal<Set<string>>(new Set());
  readonly isAddingLine = signal<boolean>(false);
  readonly newLineText = signal<string>('');
  readonly newLineQuantity = signal<string>('');
  readonly newLinePriceAmount = signal<string>('');

  // Currently active/highlighted field extraction
  readonly activeExtraction = signal<FieldExtraction | null>(null);

  // PDF preview URL (signed)
  readonly documentPreviewUrl = signal<string | null>(null);
  readonly safePreviewUrl = computed<SafeResourceUrl | null>(() => {
    const url = this.documentPreviewUrl();
    return url ? this.sanitizer.bypassSecurityTrustResourceUrl(url) : null;
  });

  // Keyboard navigation through flagged items
  readonly currentFlaggedIndex = signal<number>(0);

  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);
  readonly confirmBlockedReason = signal<string | null>(null);

  readonly isWriter = computed<boolean>(() => this.session.hasRole('owner', 'buyer'));

  readonly supplierSuggestion = computed<SupplierSuggestion | null>(() => {
    const q = this.quotation();
    if (!q || q.supplier_id || !q.suggested_supplier_id) return null;
    const confidence = parseFloat(q.supplier_match_confidence ?? '0');
    const confidencePct = Number.isFinite(confidence) ? Math.round(confidence * 100) : 0;
    const fallbackName = this.suppliers().find((s) => s.id === q.suggested_supplier_id)?.name;
    const name = q.suggested_supplier_name || fallbackName;
    if (!name) return null;
    return {
      id: q.suggested_supplier_id,
      name,
      confidencePct,
      tier: confidence >= 0.6 ? 'high' : 'medium',
    };
  });

  readonly noSupplierMatchFlagged = computed<boolean>(() => {
    const q = this.quotation();
    return Boolean(!q?.supplier_id && q?.review_task?.reason === 'no_supplier_match');
  });

  readonly currencyOptions: readonly string[] = [
    'USD', 'EUR', 'GBP', 'AED', 'SAR', 'EGP', 'QAR', 'KWD', 'BHD',
    'OMR', 'JOD', 'CHF', 'JPY', 'CNY', 'INR', 'AUD', 'CAD',
  ];

  readonly displayedLineColumns: readonly string[] = [
    'line_number',
    'original_text',
    'quantity',
    'pack',
    'unit_price',
    'delivery_fee',
    'discount',
    'vat_rate',
    'line_total',
    'confidence',
    'actions',
  ];
  readonly dateTimeOptions: Intl.DateTimeFormatOptions = {
    dateStyle: 'medium',
    timeStyle: 'short',
  };

  truncateId(id: string): string {
    return id.slice(0, 8);
  }

  // List of all low confidence (<0.85) extractions needing attention
  readonly flaggedFields = computed<FlaggedField[]>(() => {
    const q = this.quotation();
    if (!q) return [];
    const flagged: FlaggedField[] = [];

    for (const fe of q.field_extractions) {
      const conf = parseFloat(fe.confidence);
      if (conf < 0.85 || !fe.extracted_value) {
        flagged.push({
          id: fe.id,
          entityType: fe.entity_type,
          entityId: fe.entity_id,
          fieldName: fe.field_name,
          label: `${fe.entity_type === 'quotation' ? 'Header' : 'Line'} - ${fe.field_name}`,
          confidence: conf,
          extraction: fe,
        });
      }
    }
    return flagged;
  });

  // Computed line total sum
  readonly computedLinesTotal = computed<{ amount: string; currency: string } | null>(() => {
    const q = this.quotation();
    if (!q) return null;
    const pendingNewLines = this.pendingNewLines();
    if (q.lines.length === 0 && pendingNewLines.length === 0) return null;

    let total = 0;
    const currency = q.currency || q.lines[0]?.unit_price?.currency || pendingNewLines[0]?.unit_price_currency || 'USD';

    for (const line of q.lines) {
      if (this.pendingRemoveLineIds().has(line.id)) continue;

      total += this.calculateLineTotal(this.effectiveLineAmounts(line));
    }

    for (const line of pendingNewLines) {
      const qty = this.parseNumericInput(line.quantity, 1);
      const price = this.parseNumericInput(line.unit_price_amount, 0);
      total += qty * price;
    }

    return {
      amount: total.toFixed(2),
      currency,
    };
  });

  // Whether there is an arithmetic mismatch (client-side authoritative)
  readonly hasArithmeticMismatch = computed<boolean>(() => {
    const q = this.quotation();
    if (!q) return false;

    const computedTotal = this.computedLinesTotal();
    if (!q.stated_total?.amount || !computedTotal) return false;

    const stated = parseFloat(q.stated_total.amount);
    const computed = parseFloat(computedTotal.amount);
    if (Math.abs(stated - computed) <= 0.01) return false;

    // If gap is explainable by document-level VAT, not a mismatch
    const hasLineVat = this.hasEffectiveLineVat();
    if (!hasLineVat && computed > 0 && stated > computed) {
      const inferredPct = Math.round(((stated - computed) / computed) * 100);
      if (inferredPct > 0 && inferredPct <= 30) {
        const recomputed = computed * (1 + inferredPct / 100);
        if (Math.abs(recomputed - stated) <= 0.01) return false;
      }
    }
    return true;
  });

  readonly isArithmeticReconciled = computed<boolean>(() => {
    const q = this.quotation();
    if (!q) return false;
    const computedTotal = this.computedLinesTotal();
    if (!q.stated_total?.amount || !computedTotal) return false;
    return !this.hasArithmeticMismatch();
  });

  readonly inferredVatPct = computed<number | null>(() => {
    const q = this.quotation();
    if (!q) return null;
    const computedTotal = this.computedLinesTotal();
    if (!q.stated_total?.amount || !computedTotal) return null;
    const stated = parseFloat(q.stated_total.amount);
    const computed = parseFloat(computedTotal.amount);
    if (Math.abs(stated - computed) <= 0.01) return null;
    const hasLineVat = this.hasEffectiveLineVat();
    if (!hasLineVat && computed > 0 && stated > computed) {
      const pct = Math.round(((stated - computed) / computed) * 100);
      if (pct > 0 && pct <= 30) {
        const recomputed = computed * (1 + pct / 100);
        if (Math.abs(recomputed - stated) <= 0.01) return pct;
      }
    }
    return null;
  });

  readonly arithmeticDifference = computed<string | null>(() => {
    const q = this.quotation();
    const computedTotal = this.computedLinesTotal();
    if (!q?.stated_total?.amount || !computedTotal) return null;

    const diff = parseFloat(computedTotal.amount) - parseFloat(q.stated_total.amount);
    return diff.toFixed(2);
  });

  readonly hasPendingReviewChanges = computed<boolean>(() => {
    const q = this.quotation();
    return (
      this.pendingCorrections().size > 0 ||
      this.reviewerNotes() !== (q?.reviewer_notes || '') ||
      this.pendingNewLines().length > 0 ||
      this.pendingRemoveLineIds().size > 0
    );
  });

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.quotationId.set(id);
      this.loadQuotation(id);
      this.loadSuppliers();
      this.loadPriorQuotations();
    }
  }

  loadQuotation(id: string): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    this.api.getQuotation(id).subscribe({
      next: (q) => {
        this.quotation.set(q);
        this.reviewerNotes.set(q.reviewer_notes || '');
        this.selectedSupplierId.set(q.supplier_id || null);
        if (q.previous_quotation_id) {
          this.isRequote.set(true);
          this.selectedPreviousQuotationId.set(q.previous_quotation_id);
        }

        // Set default active extraction if any flagged field exists
        const flagged = this.flaggedFields();
        if (flagged.length > 0) {
          this.activeExtraction.set(flagged[0].extraction);
        } else if (q.field_extractions.length > 0) {
          this.activeExtraction.set(q.field_extractions[0]);
        }

        this.isLoading.set(false);
        this.loadDocumentPreview(q.document.id);
        this.loadAuditTrail(q.id);
      },
      error: (err: unknown) => {
        this.isLoading.set(false);
        this.handleError(err);
      },
    });
  }

  private loadDocumentPreview(documentId: string): void {
    this.api.getDocumentDownloadUrl(documentId).subscribe({
      next: ({ download_url }) => {
        this.documentPreviewUrl.set(download_url);
      },
      error: () => {
        // Non-fatal — falls back to text simulation
      },
    });
  }

  loadSuppliers(): void {
    this.api.suppliers({ limit: 100 }).subscribe({
      next: (res) => {
        this.suppliers.set(res.items);
      },
      error: () => {
        // Non-fatal, suppliers dropdown will be empty
      },
    });
  }

  loadPriorQuotations(): void {
    this.api.getReviewTasks({ status: 'all', limit: 100 }).subscribe({
      next: (res) => {
        const currentId = this.quotationId();
        const seen = new Set<string>();
        const items: { id: string; created_at: string; supplier_name: string | null }[] = [];
        for (const task of res.items) {
          if (task.quotation_id !== currentId && !seen.has(task.quotation_id)) {
            seen.add(task.quotation_id);
            items.push({
              id: task.quotation_id,
              created_at: task.created_at,
              supplier_name: task.supplier_name ?? null,
            });
          }
        }
        this.priorQuotations.set(items);
      },
      error: () => {
        // Non-fatal
      },
    });
  }

  loadAuditTrail(quotationId = this.quotationId()): void {
    if (!quotationId) return;
    this.isLoadingAudit.set(true);

    this.api.getAuditTrail(quotationId).subscribe({
      next: (res) => {
        this.auditTrail.set(res.items);
        this.isLoadingAudit.set(false);
      },
      error: (err: unknown) => {
        this.isLoadingAudit.set(false);
        this.handleError(err);
      },
    });
  }

  auditActionLabel(action: string): string {
    const actionKeys: Record<string, string> = {
      'quotation.archived': 'quotations.audit.actions.archived',
      'quotation.restored': 'quotations.audit.actions.restored',
      'quotation.extraction_retried': 'quotations.audit.actions.extraction_retried',
      'quotation.exported': 'quotations.audit.actions.exported',
      'quotation.confirmed': 'quotations.audit.actions.confirmed',
      'quotation.refused': 'quotations.audit.actions.refused',
      'quotation.reviewed': 'quotations.audit.actions.reviewed',
    };
    return this.translate.instant(actionKeys[action] ?? 'quotations.audit.actions.unknown');
  }

  getFieldExtraction(entityType: 'quotation' | 'quotation_line', entityId: string, fieldName: string): FieldExtraction | undefined {
    const q = this.quotation();
    if (!q) return undefined;
    return q.field_extractions.find(
      (fe) => fe.entity_type === entityType && fe.entity_id === entityId && fe.field_name === fieldName,
    );
  }

  extractedSupplierName(): string | null {
    const q = this.quotation();
    if (!q) return null;
    const extracted = this.getFieldExtraction('quotation', q.id, 'supplier_name')?.extracted_value;
    if (typeof extracted === 'string' && extracted.trim()) {
      return extracted.trim();
    }
    return this.supplierSuggestion()?.name ?? null;
  }

  acceptSupplierSuggestion(): void {
    const suggestion = this.supplierSuggestion();
    if (!suggestion) return;
    this.selectedSupplierId.set(suggestion.id);
  }

  createSupplierFromExtraction(): void {
    const name = this.extractedSupplierName();
    if (!name) return;
    this.isCreatingSupplierFromExtraction.set(true);
    this.errorMessage.set(null);
    this.api.createSupplier({ name }).subscribe({
      next: (supplier) => {
        this.suppliers.update((items) => [...items, supplier]);
        this.selectedSupplierId.set(supplier.id);
        this.isCreatingSupplierFromExtraction.set(false);
        this.snackBar.open(
          this.translate.instant('quotations.review.supplierMatch.createSuccess'),
          undefined,
          { duration: 3000 },
        );
      },
      error: (err: unknown) => {
        this.isCreatingSupplierFromExtraction.set(false);
        this.handleError(err);
      },
    });
  }

  documentFileName(): string {
    const path = this.quotation()?.document.storage_path || '';
    const parts = path.split('/');
    return parts[parts.length - 1] || path;
  }

  extractedAt(q: QuotationDetail): string {
    const timestampFields = q as QuotationTimestampFields;
    return timestampFields.extracted_at ?? q.created_at;
  }

  lastModifiedAt(q: QuotationDetail): string | null {
    const timestampFields = q as QuotationTimestampFields;
    return timestampFields.updated_at ?? null;
  }

  fieldLabel(fieldName: string): string {
    const labels: Record<string, string> = {
      currency: 'Currency',
      issue_date: 'Issue Date',
      expiry_date: 'Expiry Date',
      stated_total: 'Stated Total',
      quantity: 'Quantity',
      unit_price: 'Unit Price',
      discount: 'Discount',
      delivery_fee: 'Delivery Fee',
      vat_rate: 'VAT Rate',
      original_text: 'Description',
      pack_details: 'Pack Details',
    };
    return labels[fieldName] || fieldName.replace(/_/g, ' ');
  }

  getEffectiveValue(entityType: 'quotation' | 'quotation_line', entityId: string, fieldName: string, defaultValue: unknown): unknown {
    const fe = this.getFieldExtraction(entityType, entityId, fieldName);
    if (!fe) return defaultValue;

    if (this.pendingCorrections().has(fe.id)) {
      return this.pendingCorrections().get(fe.id);
    }
    if (fe.corrected_value !== null && fe.corrected_value !== undefined) {
      return fe.corrected_value;
    }
    return fe.extracted_value ?? defaultValue;
  }

  expiryBadge(q: QuotationDetail): ExpiryBadge | null {
    const expiryValue = this.getEffectiveValue('quotation', q.id, 'expiry_date', q.expiry_date || '');
    if (!expiryValue || typeof expiryValue !== 'string') return null;

    const expiryDate = new Date(`${expiryValue}T00:00:00`);
    if (isNaN(expiryDate.getTime())) return null;

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const diffDays = Math.ceil((expiryDate.getTime() - today.getTime()) / 86_400_000);

    if (diffDays < 0) {
      return { kind: 'expired', labelKey: 'quotations.review.expired' };
    }
    if (diffDays <= 7) {
      return { kind: 'warning', labelKey: 'quotations.review.expiresIn', count: diffDays };
    }
    return { kind: 'valid', labelKey: 'quotations.review.validFor', count: diffDays };
  }

  isFieldCorrected(entityType: 'quotation' | 'quotation_line', entityId: string, fieldName: string): boolean {
    const fe = this.getFieldExtraction(entityType, entityId, fieldName);
    if (!fe) return false;
    return this.pendingCorrections().has(fe.id) || fe.corrected_value !== null && fe.corrected_value !== undefined;
  }

  getFieldConfidence(entityType: 'quotation' | 'quotation_line', entityId: string, fieldName: string): number {
    const fe = this.getFieldExtraction(entityType, entityId, fieldName);
    if (!fe) return 1.0;
    return parseFloat(fe.confidence);
  }

  normalizeMoneyInput(value: string): string {
    const normalised = value.replace(/[^0-9.-]/g, '');
    return normalised || '0';
  }

  selectField(entityType: 'quotation' | 'quotation_line', entityId: string, fieldName: string): void {
    const fe = this.getFieldExtraction(entityType, entityId, fieldName);
    if (fe) {
      this.activeExtraction.set(fe);
    }
  }

  updateCorrection(feId: string, newValue: unknown): void {
    const current = new Map(this.pendingCorrections());
    current.set(feId, newValue);
    this.pendingCorrections.set(current);
  }

  confirmFieldAsIs(entityType: 'quotation' | 'quotation_line', entityId: string, fieldName: string): void {
    const fe = this.getFieldExtraction(entityType, entityId, fieldName);
    if (!fe) return;
    const current = this.pendingCorrections().has(fe.id)
      ? this.pendingCorrections().get(fe.id)
      : fe.extracted_value;
    this.updateCorrection(fe.id, current);
  }

  // FR-014: Keyboard Navigation through flagged fields
  @HostListener('window:keydown', ['$event'])
  handleKeyboardEvent(event: KeyboardEvent): void {
    if (event.altKey && (event.key === 'n' || event.key === 'N')) {
      event.preventDefault();
      this.nextFlaggedField();
    } else if (event.altKey && (event.key === 'p' || event.key === 'P')) {
      event.preventDefault();
      this.prevFlaggedField();
    }
  }

  nextFlaggedField(): void {
    const flagged = this.flaggedFields();
    if (flagged.length === 0) return;

    const nextIdx = (this.currentFlaggedIndex() + 1) % flagged.length;
    this.currentFlaggedIndex.set(nextIdx);
    const target = flagged[nextIdx];
    this.activeExtraction.set(target.extraction);
    this.scrollToField(target.id);
  }

  prevFlaggedField(): void {
    const flagged = this.flaggedFields();
    if (flagged.length === 0) return;

    const prevIdx = (this.currentFlaggedIndex() - 1 + flagged.length) % flagged.length;
    this.currentFlaggedIndex.set(prevIdx);
    const target = flagged[prevIdx];
    this.activeExtraction.set(target.extraction);
    this.scrollToField(target.id);
  }

  private scrollToField(extractionId: string): void {
    setTimeout(() => {
      const el = document.getElementById(`field-${extractionId}`);
      if (!el) return;
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.focus();
      const ff = el.querySelector('mat-form-field') as HTMLElement | null;
      const target = ff ?? el;
      target.classList.add('flagged-highlight');
      setTimeout(() => target.classList.remove('flagged-highlight'), 2000);
    }, 300);
  }

  downloadDocument(): void {
    const documentId = this.quotation()?.document.id;
    if (!documentId) return;

    const downloadWindow = window.open('about:blank', '_blank');
    if (downloadWindow) {
      downloadWindow.opener = null;
    }

    this.api.getDocumentDownloadUrl(documentId).subscribe({
      next: ({ download_url }) => {
        if (downloadWindow) {
          downloadWindow.location.href = download_url;
        } else {
          window.location.href = download_url;
        }
      },
      error: (err: unknown) => {
        downloadWindow?.close();
        this.handleError(err);
      },
    });
  }

  onNotesChange(value: string): void {
    this.reviewerNotes.set(value);
  }

  saveCorrections(): void {
    const q = this.quotation();
    if (!q) return;

    this.isSaving.set(true);
    this.errorMessage.set(null);
    this.confirmBlockedReason.set(null);

    const corrections: FieldCorrection[] = [];
    for (const [field_extraction_id, corrected_value] of this.pendingCorrections().entries()) {
      corrections.push({ field_extraction_id, corrected_value });
    }

    this.api
      .patchQuotation(q.id, {
        supplier_id: this.selectedSupplierId(),
        reviewer_notes: this.reviewerNotes() || null,
        corrections,
        add_lines: this.pendingNewLines(),
        remove_line_ids: Array.from(this.pendingRemoveLineIds()),
      })
      .subscribe({
        next: (updated) => {
          this.quotation.set(updated);
          this.pendingCorrections.set(new Map());
          this.pendingNewLines.set([]);
          this.pendingRemoveLineIds.set(new Set());
          this.isSaving.set(false);
          this.snackBar.open(
            this.translate.instant('quotations.review.actions.saveSuccess'),
            undefined,
            { duration: 3000 },
          );
        },
        error: (err: unknown) => {
          this.isSaving.set(false);
          this.handleError(err);
        },
      });
  }

  requestConfirm(): void {
    if (!this.selectedSupplierId()) {
      this.confirmBlockedReason.set(
        this.translate.instant('quotations.review.actions.confirmBlockedMissingSupplier'),
      );
      return;
    }
    this.confirmDialogVisible.set(true);
  }

  cancelConfirm(): void {
    this.confirmDialogVisible.set(false);
  }

  confirmQuotation(): void {
    const q = this.quotation();
    if (!q) return;

    this.confirmDialogVisible.set(false);
    this.isConfirming.set(true);
    this.errorMessage.set(null);
    this.confirmBlockedReason.set(null);

    const supplierNeedsSaving = q.supplier_id !== this.selectedSupplierId();
    const notesNeedSaving = this.reviewerNotes() !== (q.reviewer_notes || '');
    if (this.pendingCorrections().size > 0 || supplierNeedsSaving || notesNeedSaving) {
      const corrections: FieldCorrection[] = [];
      for (const [field_extraction_id, corrected_value] of this.pendingCorrections().entries()) {
        corrections.push({ field_extraction_id, corrected_value });
      }

      this.api
        .patchQuotation(q.id, {
          supplier_id: this.selectedSupplierId(),
          reviewer_notes: this.reviewerNotes() || null,
          corrections,
        })
        .subscribe({
          next: () => {
            this.pendingCorrections.set(new Map());
            this.executeConfirm(q.id);
          },
          error: (err: unknown) => {
            this.isConfirming.set(false);
            this.handleError(err);
          },
        });
    } else {
      this.executeConfirm(q.id);
    }
  }

  refuseQuotation(): void {
    const q = this.quotation();
    if (!q) return;

    this.isRefusing.set(true);
    this.errorMessage.set(null);

    this.api.refuseQuotation(q.id).subscribe({
      next: () => {
        this.isRefusing.set(false);
        this.loadQuotation(q.id);
        this.snackBar.open(
          this.translate.instant('quotations.review.actions.refuseSuccess'),
          undefined,
          { duration: 4000 },
        );
      },
      error: (err: unknown) => {
        this.isRefusing.set(false);
        this.handleError(err);
      },
    });
  }

  archiveQuotation(): void {
    const q = this.quotation();
    if (!q) return;
    if (!window.confirm(this.translate.instant('quotations.review.archiveConfirm'))) {
      return;
    }

    this.isArchiving.set(true);
    this.errorMessage.set(null);

    this.api.archiveQuotation(q.id).subscribe({
      next: () => {
        this.isArchiving.set(false);
        this.snackBar.open(this.translate.instant('quotations.review.archived'), undefined, {
          duration: 3000,
        });
        this.router.navigate(['/quotations']);
      },
      error: (err: unknown) => {
        this.isArchiving.set(false);
        this.handleError(err);
      },
    });
  }

  retryExtraction(): void {
    const q = this.quotation();
    if (!q) return;
    if (!window.confirm(this.translate.instant('quotations.review.retryConfirm'))) {
      return;
    }

    this.isRetryingExtraction.set(true);
    this.errorMessage.set(null);

    this.api.retryExtraction(q.id).subscribe({
      next: (updated) => {
        this.isRetryingExtraction.set(false);
        this.loadQuotation(updated.id);
      },
      error: (err: unknown) => {
        this.isRetryingExtraction.set(false);
        this.handleError(err);
      },
    });
  }

  onReplaceDocumentSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;

    const q = this.quotation();
    if (!q) return;

    const mimeType = file.type as import('../../../core/api/models').PresignMimeType;
    if (!mimeType) {
      this.errorMessage.set(this.translate.instant('quotations.review.replaceDocument.unsupportedType'));
      return;
    }

    this.isReplacingDocument.set(true);
    this.errorMessage.set(null);

    this.api.presignDocument({ filename: file.name, mime_type: mimeType, size_bytes: file.size }).subscribe({
      next: (presign) => {
        this.api.uploadFileToStorage(presign.upload_url, file, presign.upload_fields).subscribe({
          next: () => {
            this.api.replaceDocument(q.id, presign.document_id).subscribe({
              next: () => {
                this.isReplacingDocument.set(false);
                this.loadQuotation(q.id);
                this.snackBar.open(
                  this.translate.instant('quotations.review.replaceDocument.success'),
                  undefined,
                  { duration: 3000 },
                );
              },
              error: (err: unknown) => {
                this.isReplacingDocument.set(false);
                this.handleError(err);
              },
            });
          },
          error: (err: unknown) => {
            this.isReplacingDocument.set(false);
            this.handleError(err);
          },
        });
      },
      error: (err: unknown) => {
        this.isReplacingDocument.set(false);
        this.handleError(err);
      },
    });
  }

  exportQuotation(): void {
    const q = this.quotation();
    if (!q) return;

    this.isExporting.set(true);
    this.errorMessage.set(null);

    this.api.exportQuotation(q.id).subscribe({
      next: (blob) => {
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `quotation-${q.id}.csv`;
        link.click();
        window.URL.revokeObjectURL(url);
        this.isExporting.set(false);
      },
      error: (err: unknown) => {
        this.isExporting.set(false);
        this.handleError(err);
      },
    });
  }

  canRetryExtraction(q: QuotationDetail): boolean {
    return q.status === 'extracted' || q.status === 'in_review' || q.status === 'refused';
  }

  computeLineTotal(line: QuotationDetail['lines'][number]): string | null {
    const amounts = this.effectiveLineAmounts(line);
    if (amounts.unitPrice === 0 && !line.unit_price?.amount) return null;
    return this.calculateLineTotal(amounts).toFixed(2);
  }

  private hasEffectiveLineVat(): boolean {
    const q = this.quotation();
    if (!q) return false;
    return q.lines.some((line) => {
      if (this.pendingRemoveLineIds().has(line.id)) return false;
      return this.effectiveLineAmounts(line).vatRate > 0;
    });
  }

  private effectiveLineAmounts(line: QuotationDetail['lines'][number]): EffectiveLineAmounts {
    return {
      quantity: this.effectiveNumericLineValue(line, 'quantity', line.quantity, 1),
      unitPrice: this.effectiveNumericLineValue(line, ['unit_price_amount', 'unit_price'], line.unit_price, 0),
      deliveryFee: this.effectiveNumericLineValue(line, ['delivery_fee_amount', 'delivery_fee'], line.delivery_fee, 0),
      discount: this.effectiveNumericLineValue(line, ['discount_amount', 'discount'], line.discount, 0),
      vatRate: this.effectiveNumericLineValue(line, 'vat_rate', line.vat_rate, 0),
    };
  }

  private effectiveNumericLineValue(
    line: QuotationDetail['lines'][number],
    fieldNames: string | readonly string[],
    defaultValue: unknown,
    fallback: number,
  ): number {
    const names = typeof fieldNames === 'string' ? [fieldNames] : fieldNames;
    for (const fieldName of names) {
      const extraction = this.getFieldExtraction('quotation_line', line.id, fieldName);
      if (extraction && this.pendingCorrections().has(extraction.id)) {
        return this.parseNumericInput(this.pendingCorrections().get(extraction.id), fallback);
      }
    }
    return this.parseNumericInput(defaultValue, fallback);
  }

  private parseNumericInput(value: unknown, fallback: number): number {
    const rawValue = this.moneyAmount(value);
    const parsed = typeof rawValue === 'number' ? rawValue : parseFloat(String(rawValue ?? ''));
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  private moneyAmount(value: unknown): string | number | null {
    if (this.isMoney(value)) return value.amount;
    return typeof value === 'string' || typeof value === 'number' ? value : null;
  }

  private isMoney(value: unknown): value is Money {
    return (
      typeof value === 'object' &&
      value !== null &&
      'amount' in value &&
      typeof value.amount === 'string'
    );
  }

  private calculateLineTotal(amounts: EffectiveLineAmounts): number {
    const lineNet = amounts.quantity * amounts.unitPrice + amounts.deliveryFee - amounts.discount;
    return lineNet * (1 + amounts.vatRate);
  }

  revertToAiValue(feId: string): void {
    const current = new Map(this.pendingCorrections());
    current.delete(feId);
    this.pendingCorrections.set(current);
  }

  toDate(value: unknown): Date | null {
    if (!value || typeof value !== 'string') return null;
    const d = new Date(value);
    return isNaN(d.getTime()) ? null : d;
  }

  toIsoDate(date: Date | null): string {
    if (!date) return '';
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  private executeConfirm(quotationId: string): void {
    const previousQuotationId = this.isRequote() ? this.selectedPreviousQuotationId() : null;

    this.api
      .confirmQuotation(quotationId, {
        previous_quotation_id: previousQuotationId,
        acknowledge_mismatch: this.mismatchAcknowledged() || undefined,
      })
      .subscribe({
        next: (confirmed) => {
          this.isConfirming.set(false);
          this.loadQuotation(confirmed.id);
          this.snackBar.open(
            this.translate.instant('quotations.review.actions.confirmSuccess'),
            undefined,
            { duration: 4000 },
          );
          // A confirmed quotation is the only trusted source matching may read (FR-016). This
          // is the one place in the product that ever calls the matches endpoint, which is what
          // actually runs the matching pipeline and populates the match resolution queue —
          // without this call a confirmed quotation's lines would never reach it.
          this.api.getQuotationMatches(confirmed.id).subscribe({ error: () => undefined });
        },
        error: (err: unknown) => {
          this.isConfirming.set(false);
          if (err instanceof HttpErrorResponse && err.status === 409) {
            const apiError = err.error as ApiError | undefined;
            this.confirmBlockedReason.set(
              apiError?.message ??
                this.translate.instant('quotations.review.actions.confirmBlockedTitle'),
            );
          } else {
            this.handleError(err);
          }
        },
      });
  }

  showAddLineForm(): void {
    this.isAddingLine.set(true);
    this.newLineText.set('');
    this.newLineQuantity.set('');
    this.newLinePriceAmount.set('');
  }

  cancelAddLine(): void {
    this.isAddingLine.set(false);
  }

  addNewLine(): void {
    const text = this.newLineText().trim();
    if (!text) return;
    const q = this.quotation();
    const currency = q?.currency || 'USD';
    const newLine: NewQuotationLine = {
      original_text: text,
      quantity: this.newLineQuantity() || null,
      unit_price_amount: this.newLinePriceAmount() || null,
      unit_price_currency: this.newLinePriceAmount() ? currency : null,
    };
    this.pendingNewLines.update(lines => [...lines, newLine]);
    this.isAddingLine.set(false);
  }

  markLineForRemoval(lineId: string): void {
    this.pendingRemoveLineIds.update(ids => {
      const next = new Set(ids);
      next.add(lineId);
      return next;
    });
  }

  unmarkLineForRemoval(lineId: string): void {
    this.pendingRemoveLineIds.update(ids => {
      const next = new Set(ids);
      next.delete(lineId);
      return next;
    });
  }

  createRequote(): void {
    const id = this.quotationId();
    this.router.navigate(['/quotations/upload'], {
      queryParams: { requote_from: id },
    });
  }

  formatConfidence(score: string | number): number {
    const num = typeof score === 'string' ? parseFloat(score) : score;
    return Math.round(num * 100);
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorTraceId.set(apiError?.trace_id ?? null);
      this.errorMessage.set(
        apiError?.message ??
          err.message ??
          this.translate.instant('quotations.review.actions.genericError'),
      );
      return;
    }
    this.errorMessage.set(this.translate.instant('quotations.review.actions.genericError'));
  }
}
