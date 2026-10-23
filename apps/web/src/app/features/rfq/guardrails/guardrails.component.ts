import { Component, OnInit, inject, signal } from '@angular/core';

import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatIconModule } from '@angular/material/icon';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { ApiService } from '../../../core/api/api.service';
import type {
  Branch,
  ConfigOptions,
  CostCentre,
  ReferenceOption,
  Supplier,
} from '../../../core/api/models';
import { FormatService } from '../../../core/format/format.service';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import { I18nService } from '../../../core/i18n/i18n.service';
import { SessionService } from '../../../core/auth/session.service';
import {
  RfqApi,
  RfqGuardrail,
  RfqGuardrailPayload,
} from '../rfq-api';

@Component({
  selector: 'app-rfq-guardrails',
  standalone: true,
  imports: [
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatSlideToggleModule,
    MatProgressSpinnerModule,
    MatIconModule,
    TranslateModule,
    FormatMoneyPipe
],
  templateUrl: './guardrails.component.html',
  styleUrl: './guardrails.component.scss',
})
export class GuardrailsComponent implements OnInit {
  private readonly rfqApi = inject(RfqApi);
  private readonly api = inject(ApiService);
  private readonly translate = inject(TranslateService);
  private readonly i18n = inject(I18nService);
  private readonly session = inject(SessionService);
  private readonly format = inject(FormatService);

  readonly guardrails = signal<RfqGuardrail[]>([]);
  readonly suppliers = signal<readonly Supplier[]>([]);
  readonly branches = signal<readonly Branch[]>([]);
  /** Active cost centres on the selected default branch (finding 38b). */
  readonly costCentres = signal<readonly CostCentre[]>([]);
  readonly currencies = signal<readonly ReferenceOption[]>([]);
  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly editingId = signal<string | null>(null);

  maxOrderValue = '';
  currency = this.session.homeCurrency() ?? 'USD';
  minResponseCount = 1;
  maxPriceVariancePercent = '';
  supplierAllowlist: string[] = [];
  defaultBranchId = '';
  defaultCostCentreId: string | null = null;
  enabled = true;

  ngOnInit(): void {
    this.loadGuardrails();
    this.api.suppliers({ limit: 100 }).subscribe({ next: (response) => this.suppliers.set(response.items) });
    this.api.listBranches({ is_active: true, limit: 100 }).subscribe({ next: (response) => this.branches.set(response.items) });
    this.api.configOptions()
      .pipe(catchError(() => of<ConfigOptions>({ regions: [], currencies: [], tax_models: [] })))
      .subscribe((response) => this.currencies.set(response.currencies));
  }

  currencyLabel(option: ReferenceOption): string {
    const label = this.i18n.currentLocale() === 'ar' ? option.label_ar : option.label_en;
    return `${label || option.code} (${option.code})`;
  }

  /** A cost centre belongs to one branch, so changing the branch clears the choice. */
  onBranchChange(branchId: string): void {
    this.defaultBranchId = branchId;
    this.defaultCostCentreId = null;
    this.loadCostCentres(branchId);
  }

  private loadCostCentres(branchId: string): void {
    this.costCentres.set([]);
    if (!branchId) return;
    this.api.listCostCentres({ branch_id: branchId, is_archived: false, limit: 100 }).subscribe({
      next: (response) => this.costCentres.set(response.items),
    });
  }

  loadGuardrails(): void {
    this.loading.set(true);
    this.rfqApi.listGuardrails().subscribe({
      next: (items) => { this.guardrails.set(items); this.loading.set(false); },
      error: (error: unknown) => { this.loading.set(false); this.showError(error); },
    });
  }

  edit(guardrail: RfqGuardrail): void {
    this.editingId.set(guardrail.id);
    this.maxOrderValue = guardrail.max_order_value_amount;
    this.currency = guardrail.max_order_value_currency;
    this.minResponseCount = guardrail.min_response_count;
    this.maxPriceVariancePercent = String(Number(guardrail.max_price_variance_pct) * 100);
    this.supplierAllowlist = [...(guardrail.supplier_allowlist ?? [])];
    this.defaultBranchId = guardrail.default_branch_id;
    this.defaultCostCentreId = guardrail.default_cost_centre_id ?? null;
    this.loadCostCentres(guardrail.default_branch_id);
    this.enabled = guardrail.enabled;
    this.errorMessage.set(null);
  }

  cancelEdit(): void { this.editingId.set(null); this.resetForm(); }

  toggle(guardrail: RfqGuardrail): void {
    this.rfqApi.updateGuardrail(guardrail.id, { enabled: !guardrail.enabled }).subscribe({
      next: (updated) => this.guardrails.update((items) => items.map((item) => item.id === updated.id ? updated : item)),
      error: (error: unknown) => this.showError(error),
    });
  }

  variancePercent(guardrail: RfqGuardrail): number {
    return Number(guardrail.max_price_variance_pct) * 100;
  }

  summaryParams(guardrail: RfqGuardrail): Record<string, string> {
    return {
      min: this.format.formatNumber(guardrail.min_response_count),
      variance: this.format.formatNumber(this.variancePercent(guardrail)),
    };
  }

  save(): void {
    this.errorMessage.set(null);
    const maxValue = Number(this.maxOrderValue);
    const variance = Number(this.maxPriceVariancePercent);
    if (!Number.isFinite(maxValue) || maxValue <= 0) {
      this.errorMessage.set(this.translate.instant('rfq.guardrails.validation.maxOrderValue'));
      return;
    }
    if (!Number.isInteger(this.minResponseCount) || this.minResponseCount < 1) {
      this.errorMessage.set(this.translate.instant('rfq.guardrails.validation.minResponses'));
      return;
    }
    if (!Number.isFinite(variance) || variance < 0 || variance > 100) {
      this.errorMessage.set(this.translate.instant('rfq.guardrails.validation.priceVariance'));
      return;
    }
    if (!this.defaultBranchId) {
      this.errorMessage.set(this.translate.instant('rfq.guardrails.validation.branch'));
      return;
    }

    const payload: RfqGuardrailPayload = {
      max_order_value_amount: this.maxOrderValue,
      max_order_value_currency: this.currency,
      supplier_allowlist: this.supplierAllowlist,
      min_response_count: this.minResponseCount,
      max_price_variance_pct: String(variance / 100),
      default_branch_id: this.defaultBranchId,
      default_cost_centre_id: this.defaultCostCentreId,
      enabled: this.enabled,
    };
    this.saving.set(true);
    const request = this.editingId()
      ? this.rfqApi.updateGuardrail(this.editingId() as string, payload)
      : this.rfqApi.createGuardrail(payload);
    request.subscribe({
      next: (guardrail) => {
        this.guardrails.update((items) => this.editingId() ? items.map((item) => item.id === guardrail.id ? guardrail : item) : [guardrail, ...items]);
        this.saving.set(false);
        this.cancelEdit();
      },
      error: (error: unknown) => { this.saving.set(false); this.showError(error); },
    });
  }

  private resetForm(): void {
    this.maxOrderValue = '';
    this.currency = this.session.homeCurrency() ?? 'USD';
    this.minResponseCount = 1;
    this.maxPriceVariancePercent = '';
    this.supplierAllowlist = [];
    this.defaultBranchId = '';
    this.defaultCostCentreId = null;
    this.costCentres.set([]);
    this.enabled = true;
  }

  private showError(error: unknown): void {
    if (error instanceof HttpErrorResponse) {
      const body = error.error as {
        code?: string;
        details?: Record<string, unknown>;
      } | undefined;
      if (body?.details?.['max_order_value_amount']) {
        this.errorMessage.set(this.translate.instant('rfq.guardrails.validation.maxOrderValue'));
        return;
      }
      if (body?.details?.['default_cost_centre_id'] || body?.details?.['resource'] === 'cost_centre') {
        this.errorMessage.set(this.translate.instant('rfq.guardrails.validation.costCentre'));
        return;
      }
      if (body?.details?.['max_price_variance_pct']) {
        this.errorMessage.set(this.translate.instant('rfq.guardrails.validation.priceVariance'));
        return;
      }
    }
    this.errorMessage.set(this.translate.instant('rfq.guardrails.errors.save'));
  }
}
