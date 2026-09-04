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
  ApiError,
  FieldCorrection,
  FieldExtraction,
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
  readonly mismatchAcknowledged = signal<boolean>(false);
  readonly confirmDialogVisible = signal<boolean>(false);
  readonly quotationId = signal<string>('');
  readonly quotation = signal<QuotationDetail | null>(null);
  readonly suppliers = signal<Supplier[]>([]);
  readonly priorQuotations = signal<{ id: string; created_at: string; supplier_id: string | null }[]>([]);

  readonly selectedSupplierId = signal<string | null>(null);
  readonly isRequote = signal<boolean>(false);
  readonly selectedPreviousQuotationId = signal<string | null>(null);

  // Field corrections map: field_extraction_id -> corrected value
  readonly pendingCorrections = signal<Map<string, unknown>>(new Map());

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
    if (!q || !q.lines || q.lines.length === 0) return null;

    let total = 0;
    const currency = q.currency || q.lines[0]?.unit_price?.currency || 'USD';

    for (const line of q.lines) {
      if (line.unit_price?.amount) {
        const qty = parseFloat(line.quantity || '1');
        const price = parseFloat(line.unit_price.amount);
        const delivery = parseFloat(line.delivery_fee?.amount || '0');
        const discount = parseFloat(line.discount?.amount || '0');
        const vatRate = parseFloat(line.vat_rate || '0');
        const lineNet = qty * price + delivery - discount;
        total += lineNet * (1 + vatRate);
      }
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
    const hasLineVat = q.lines?.some(
      (l) => l.vat_rate != null && parseFloat(l.vat_rate) > 0,
    );
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
    const hasLineVat = q.lines?.some(
      (l) => l.vat_rate != null && parseFloat(l.vat_rate) > 0,
    );
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

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (id) {
      this.quotationId.set(id);
      this.loadQuotation(id);
      this.loadSuppliers();
    }
  }

  loadQuotation(id: string): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    this.api.getQuotation(id).subscribe({
      next: (q) => {
        this.quotation.set(q);
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

  getFieldExtraction(entityType: 'quotation' | 'quotation_line', entityId: string, fieldName: string): FieldExtraction | undefined {
    const q = this.quotation();
    if (!q) return undefined;
    return q.field_extractions.find(
      (fe) => fe.entity_type === entityType && fe.entity_id === entityId && fe.field_name === fieldName,
    );
  }

  documentFileName(): string {
    const path = this.quotation()?.document.storage_path || '';
    const parts = path.split('/');
    return parts[parts.length - 1] || path;
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
        corrections,
      })
      .subscribe({
        next: (updated) => {
          this.quotation.set(updated);
          this.pendingCorrections.set(new Map());
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
    if (this.pendingCorrections().size > 0 || supplierNeedsSaving) {
      const corrections: FieldCorrection[] = [];
      for (const [field_extraction_id, corrected_value] of this.pendingCorrections().entries()) {
        corrections.push({ field_extraction_id, corrected_value });
      }

      this.api
        .patchQuotation(q.id, {
          supplier_id: this.selectedSupplierId(),
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

  computeLineTotal(line: QuotationDetail['lines'][number]): string | null {
    if (!line.unit_price?.amount) return null;
    const qty = parseFloat(line.quantity || '1');
    const price = parseFloat(line.unit_price.amount);
    const delivery = parseFloat(line.delivery_fee?.amount || '0');
    const discount = parseFloat(line.discount?.amount || '0');
    const vatRate = parseFloat(line.vat_rate || '0');
    const lineNet = qty * price + delivery - discount;
    return (lineNet * (1 + vatRate)).toFixed(2);
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
