import { NgTemplateOutlet } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import {
  MAT_DIALOG_DATA,
  MatDialog,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Router } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { ApiService } from '../../../core/api/api.service';
import { SessionService } from '../../../core/auth/session.service';
import type {
  ApiError,
  ApprovalDecisionInput,
  Branch,
  BranchList,
  BudgetStatusValue,
  CostCentre,
  CostCentreList,
  Product,
  PurchaseRequest,
  PurchaseRequestLine,
  RequestGroupSummary,
} from '../../../core/api/models';

export interface SingleQueueItem {
  readonly kind: 'single';
  readonly id: string;
  readonly request: PurchaseRequest;
  readonly linesCount: number;
}

export interface GroupQueueItem {
  readonly kind: 'group';
  readonly id: string;
  readonly groupId: string;
  readonly group: RequestGroupSummary;
  readonly requests: PurchaseRequest[];
  readonly linesCount: number;
}

export type QueueItem = SingleQueueItem | GroupQueueItem;
import { FormatService } from '../../../core/format/format.service';
import { parseIsoDateLocal } from '../../../core/format/iso-date';
import { FormatQuantityPipe } from '../../../core/format/quantity.pipe';
import { RequestsApiService } from '../../requests/requests-api';
import { OrganisationApiService } from '../../settings/organisation-api';
import { ApprovalsApiService } from '../approvals-api';

const I18N = 'approvals';

export interface ApprovalDecisionDialogData {
  readonly action: 'approve' | 'reject';
  readonly requestId: string;
  readonly amount?: string;
  readonly branchName?: string;
}

export interface ApprovalDecisionDialogResult {
  readonly confirmed: boolean;
  readonly comment?: string;
}

@Component({
  selector: 'app-approval-decision-dialog',
  standalone: true,
  imports: [
    MatDialogModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    FormsModule,
    TranslatePipe,
  ],
  template: `
    <h2 mat-dialog-title>
      {{
        (data.action === 'approve' && data.amount && data.branchName
          ? ('approvals.decisionDialog.approveTitle' | translate: { amount: data.amount, branchName: data.branchName })
          : data.action === 'approve' && data.branchName
            ? ('approvals.decisionDialog.approveTitleBranchOnly' | translate: { branchName: data.branchName })
            : data.action === 'approve'
              ? ('approvals.decisionDialog.approveTitleDefault' | translate)
              : ('approvals.decisionDialog.rejectTitle' | translate)
        )
      }}
    </h2>
    <mat-dialog-content>
      <mat-form-field appearance="outline" class="decision-comment-field">
        <mat-label>
          {{
            (data.action === 'reject'
              ? 'approvals.decisionDialog.reasonLabel'
              : 'approvals.decisionDialog.commentLabel'
            ) | translate
          }}
        </mat-label>
        <textarea
          matInput
          [(ngModel)]="comment"
          [placeholder]="
            (data.action === 'reject'
              ? 'approvals.decisionDialog.reasonPlaceholder'
              : 'approvals.decisionDialog.commentPlaceholder'
            ) | translate
          "
          rows="3"
          (keydown.ctrl.enter)="onConfirm()"
          (keydown.meta.enter)="onConfirm()"
        ></textarea>
        @if (data.action === 'reject' && !comment.trim()) {
          <mat-hint class="reason-required-hint">
            {{ 'approvals.decisionDialog.reasonRequired' | translate }}
          </mat-hint>
        }
      </mat-form-field>
    </mat-dialog-content>
    <mat-dialog-actions align="end" class="dialog-actions">
      <button mat-button type="button" (click)="onCancel()" class="cancel-btn">
        {{ 'approvals.decisionDialog.cancelButton' | translate }}
      </button>
      <button
        mat-flat-button
        [color]="data.action === 'approve' ? 'primary' : 'warn'"
        type="button"
        (click)="onConfirm()"
        class="confirm-btn"
        [disabled]="data.action === 'reject' && !comment.trim()"
      >
        {{ 'approvals.decisionDialog.confirmButton' | translate }}
      </button>
    </mat-dialog-actions>
  `,
  changeDetection: ChangeDetectionStrategy.Eager,
  styles: [
    `
      .decision-comment-field {
        inline-size: 100%;
        margin-block-start: 0.5rem;
      }
      .dialog-actions {
        display: flex;
        gap: 0.5rem;
        padding-block-end: 0.5rem;
      }
    `,
  ],
})
export class ApprovalDecisionDialogComponent {
  private readonly dialogRef = inject(
    MatDialogRef<ApprovalDecisionDialogComponent, ApprovalDecisionDialogResult>,
  );
  readonly data: ApprovalDecisionDialogData = inject(MAT_DIALOG_DATA);
  comment = '';

  onConfirm(): void {
    if (this.data.action === 'reject' && !this.comment.trim()) {
      return;
    }
    this.dialogRef.close({
      confirmed: true,
      comment: this.comment.trim() || undefined,
    });
  }

  onCancel(): void {
    this.dialogRef.close({ confirmed: false });
  }
}

@Component({
  selector: 'app-approval-queue',
  standalone: true,
  imports: [
    NgTemplateOutlet,
    MatCardModule,
    MatTableModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatDialogModule,
    MatTooltipModule,
    TranslatePipe,
    FormatQuantityPipe,
  ],
  templateUrl: './approval-queue.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './approval-queue.component.scss',
})
export class ApprovalQueueComponent implements OnInit {
  private readonly approvalsApi = inject(ApprovalsApiService);
  private readonly requestsApi = inject(RequestsApiService);
  private readonly organisationApi = inject(OrganisationApiService);
  private readonly api = inject(ApiService);
  private readonly formatService = inject(FormatService);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);

  readonly isLoading = signal<boolean>(true);
  readonly pendingRequests = signal<PurchaseRequest[]>([]);
  readonly branches = signal<Branch[]>([]);
  readonly costCentres = signal<CostCentre[]>([]);
  readonly products = signal<Product[]>([]);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);
  readonly expandedRequestIds = signal<ReadonlySet<string>>(new Set<string>());
  readonly processingRequestId = signal<string | null>(null);

  readonly displayedColumns: readonly string[] = [
    'requiredByDate',
    'requester',
    'branch',
    'costCentre',
    'estimatedTotal',
    'budgetStatus',
    'lines',
    'actions',
  ];

  readonly branchNameById = computed<Map<string, string>>(() => {
    const byId = new Map<string, string>();
    for (const branch of this.branches()) {
      byId.set(branch.id, branch.name);
    }
    return byId;
  });

  readonly costCentreNameById = computed<Map<string, string>>(() => {
    const byId = new Map<string, string>();
    for (const cc of this.costCentres()) {
      byId.set(cc.id, cc.name);
    }
    return byId;
  });

  readonly productNameById = computed<Map<string, string>>(() => {
    const byId = new Map<string, string>();
    for (const product of this.products()) {
      byId.set(product.id, product.tenant_name);
    }
    return byId;
  });

  readonly queueItems = computed<QueueItem[]>(() => {
    const reqs = this.pendingRequests();
    const groupsMap = new Map<string, PurchaseRequest[]>();
    const seenGroupIds = new Set<string>();
    const items: QueueItem[] = [];

    for (const req of reqs) {
      if (req.request_group) {
        const gid = req.request_group.id;
        if (!groupsMap.has(gid)) {
          groupsMap.set(gid, []);
        }
        groupsMap.get(gid)!.push(req);
      }
    }

    for (const req of reqs) {
      if (req.request_group) {
        const gid = req.request_group.id;
        if (!seenGroupIds.has(gid)) {
          seenGroupIds.add(gid);
          const requests = groupsMap.get(gid)!;
          const linesCount = requests.reduce((sum, r) => sum + r.lines.length, 0);
          items.push({
            kind: 'group',
            id: gid,
            groupId: gid,
            group: req.request_group,
            requests,
            linesCount,
          });
        }
      } else {
        items.push({
          kind: 'single',
          id: req.id,
          request: req,
          linesCount: req.lines.length,
        });
      }
    }
    return items;
  });

  private readonly idempotencyKeys = new Map<string, string>();

  private getIdempotencyKey(action: string, targetId: string): string {
    const keyId = `${action}:${targetId}`;
    let key = this.idempotencyKeys.get(keyId);
    if (!key) {
      key = crypto.randomUUID();
      this.idempotencyKeys.set(keyId, key);
    }
    return key;
  }

  private clearIdempotencyKey(action: string, targetId: string): void {
    this.idempotencyKeys.delete(`${action}:${targetId}`);
  }

  ngOnInit(): void {
    this.loadPendingApprovals();
  }

  loadPendingApprovals(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    forkJoin({
      approvals: this.approvalsApi.listPendingApprovals({ limit: 50 }),
      branches: this.loadBranches(),
      costCentres: this.loadCostCentres(),
      products: this.loadProducts(),
    }).subscribe({
      next: ({ approvals, branches, costCentres, products }) => {
        this.pendingRequests.set([...approvals.items]);
        this.branches.set([...branches.items]);
        this.costCentres.set([...costCentres.items]);
        this.products.set([...products.items]);
        this.isLoading.set(false);
      },
      error: (err: unknown) => {
        this.isLoading.set(false);
        this.handleError(err);
      },
    });
  }

  toggleExpand(requestId: string): void {
    const next = new Set(this.expandedRequestIds());
    if (next.has(requestId)) {
      next.delete(requestId);
    } else {
      next.add(requestId);
    }
    this.expandedRequestIds.set(next);
  }

  isExpanded(requestId: string): boolean {
    return this.expandedRequestIds().has(requestId);
  }

  isProcessing(requestId: string): boolean {
    return this.processingRequestId() === requestId;
  }

  openDecisionDialog(request: PurchaseRequest, action: 'approve' | 'reject'): void {
    const branchName = this.branchNameById().get(request.branch_id);
    const amount = request.estimated_total
      ? this.formatService.formatCurrencyAmount(request.estimated_total)
      : undefined;

    const dialogRef = this.dialog.open<
      ApprovalDecisionDialogComponent,
      ApprovalDecisionDialogData,
      ApprovalDecisionDialogResult
    >(ApprovalDecisionDialogComponent, {
      width: '480px',
      data: {
        action,
        requestId: request.id,
        amount,
        branchName,
      },
    });

    dialogRef.afterClosed().subscribe((result?: ApprovalDecisionDialogResult) => {
      if (!result?.confirmed) {
        return;
      }
      this.submitDecision(request.id, action, result.comment);
    });
  }

  submitDecision(requestId: string, action: 'approve' | 'reject', comment?: string): void {
    this.processingRequestId.set(requestId);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    const body: ApprovalDecisionInput = {
      comment: comment?.trim() || undefined,
    };

    const action$ =
      action === 'approve'
        ? this.requestsApi.approveRequest(requestId, body)
        : this.requestsApi.rejectRequest(requestId, body);

    action$.subscribe({
      next: () => {
        this.processingRequestId.set(null);
        this.loadPendingApprovals();
        if (action === 'approve') {
          const msg = this.translate.instant(`${I18N}.approveSuccess`);
          if (this.session.hasRole('owner', 'buyer')) {
            const actionLabel = this.translate.instant(`${I18N}.createOrderAction`);
            const snackRef = this.snackBar.open(msg, actionLabel, { duration: 6000 });
            snackRef.onAction().subscribe(() => {
              this.router.navigate(['/orders/new'], {
                queryParams: { source_request_id: requestId },
              });
            });
          } else {
            this.snackBar.open(msg, undefined, { duration: 3500 });
          }
        } else {
          this.snackBar.open(this.translate.instant(`${I18N}.rejectSuccess`), undefined, {
            duration: 3500,
          });
        }
      },
      error: (err: unknown) => {
        this.processingRequestId.set(null);
        this.handleError(err);
      },
    });
  }

  openGroupDecisionDialog(item: GroupQueueItem, action: 'approve' | 'reject'): void {
    const branchName = this.branchNameById().get(item.requests[0]?.branch_id);
    const amount = this.formatService.formatCurrencyAmount(item.group.combined_total);

    const dialogRef = this.dialog.open<
      ApprovalDecisionDialogComponent,
      ApprovalDecisionDialogData,
      ApprovalDecisionDialogResult
    >(ApprovalDecisionDialogComponent, {
      width: '480px',
      data: {
        action,
        requestId: item.groupId,
        amount,
        branchName,
      },
    });

    dialogRef.afterClosed().subscribe((result?: ApprovalDecisionDialogResult) => {
      if (!result?.confirmed) {
        return;
      }
      this.submitGroupDecision(item.groupId, action, result.comment);
    });
  }

  submitGroupDecision(groupId: string, action: 'approve' | 'reject', comment?: string): void {
    this.processingRequestId.set(groupId);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    const idempotencyKey = this.getIdempotencyKey(action, groupId);
    const body: ApprovalDecisionInput = {
      comment: comment?.trim() || undefined,
    };

    const action$ =
      action === 'approve'
        ? this.approvalsApi.approveGroup(groupId, body, idempotencyKey)
        : this.approvalsApi.rejectGroup(groupId, body, idempotencyKey);

    action$.subscribe({
      next: () => {
        this.clearIdempotencyKey(action, groupId);
        this.processingRequestId.set(null);
        this.loadPendingApprovals();
        if (action === 'approve') {
          const msg = this.translate.instant(`${I18N}.approveSuccess`);
          this.snackBar.open(msg, undefined, { duration: 3500 });
        } else {
          this.snackBar.open(this.translate.instant(`${I18N}.rejectSuccess`), undefined, {
            duration: 3500,
          });
        }
      },
      error: (err: unknown) => {
        this.processingRequestId.set(null);
        this.handleError(err);
      },
    });
  }

  isGroupRow(item: QueueItem): item is GroupQueueItem {
    return item.kind === 'group';
  }

  getSplitGroupText(item: GroupQueueItem): string {
    const rfqShort = item.group.rfq_id ? item.group.rfq_id.slice(0, 8) : '';
    const requestsStr = this.requestCountLabel(item.group.size);
    const totalStr = this.formatService.formatCurrencyAmount(item.group.combined_total);

    if (item.group.saving) {
      const savingStr = this.formatService.formatCurrencyAmount(item.group.saving);
      return this.translate.instant('approvals.splitGroup.summary', {
        short: rfqShort,
        requests: requestsStr,
        total: totalStr,
        saving: savingStr,
      });
    }

    return this.translate.instant('approvals.splitGroup.summaryNoSaving', {
      short: rfqShort,
      requests: requestsStr,
      total: totalStr,
    });
  }

  requestCountLabel(count: number): string {
    const locale = this.translate.getCurrentLang() || this.translate.getFallbackLang() || 'en';
    const category = new Intl.PluralRules(locale).select(count);
    return this.translate.instant(`approvals.requestCount.${category}`, {
      count: this.formatService.formatNumber(count),
    });
  }

  getRequesterDisplay(request: PurchaseRequest): string {
    const name = request.requester_name?.trim();
    if (name) {
      return name;
    }
    const email = request.requester_email?.trim();
    if (email) {
      return email;
    }
    if (request.requested_by_membership_id) {
      return request.requested_by_membership_id.slice(0, 8);
    }
    return this.translate.instant(`${I18N}.notAvailable`);
  }

  getCostCentreDisplay(request: PurchaseRequest): string {
    if (request.cost_centre_id) {
      return this.costCentreNameById().get(request.cost_centre_id) ?? request.cost_centre_id;
    }
    if (request.branch_id) {
      return this.translate.instant(`${I18N}.costCentreNone`);
    }
    return this.translate.instant(`${I18N}.notAvailable`);
  }

  getBudgetStatusValue(request: PurchaseRequest): BudgetStatusValue | null {
    const bs = request.budget_status;
    if (!bs) {
      return null;
    }
    if (bs.status) {
      return bs.status;
    }
    if (bs.exceeds) {
      return 'over';
    }
    if (!bs.remaining_amount) {
      return 'no_budget';
    }
    return 'within';
  }

  getBudgetStatusLabel(request: PurchaseRequest): string {
    const status = this.getBudgetStatusValue(request);
    if (!status) {
      return this.translate.instant(`${I18N}.notAvailable`);
    }
    return this.translate.instant(`${I18N}.budgetStatus.${status}`);
  }

  getBudgetReasonText(request: PurchaseRequest): string | null {
    const reasonCode = request.budget_status?.reason_code;
    if (!reasonCode) {
      return null;
    }
    const key = `${I18N}.budgetStatus.reasons.${reasonCode}`;
    const translated = this.translate.instant(key);
    return translated !== key ? translated : reasonCode;
  }

  formatBudgetRemaining(request: PurchaseRequest): string {
    return this.formatService.formatCurrencyAmount(request.budget_status?.remaining_amount);
  }

  formatRequiredBy(value: string | null | undefined): string {
    return this.formatService.formatDate(parseIsoDateLocal(value));
  }

  lineCountLabel(count: number): string {
    const locale = this.translate.getCurrentLang() || this.translate.getFallbackLang() || 'en';
    const category = new Intl.PluralRules(locale).select(count);
    return this.translate.instant(`approvals.lineCount.${category}`, {
      count: this.formatService.formatNumber(count),
    });
  }

  formatNumber(value: number | string | null | undefined): string {
    return this.formatService.formatNumber(value);
  }

  formatMoney(request: PurchaseRequest): string {
    if (!request.estimated_total) {
      return this.translate.instant(`${I18N}.notAvailable`);
    }
    return this.formatService.formatCurrencyAmount(request.estimated_total);
  }

  formatLinePrice(line: PurchaseRequestLine): string {
    if (!line.estimated_unit_price) {
      return this.translate.instant(`${I18N}.notAvailable`);
    }
    return this.formatService.formatCurrencyAmount(line.estimated_unit_price);
  }

  getBranchName(branchId: string): string {
    return this.branchNameById().get(branchId) ?? branchId;
  }

  getProductName(productId: string): string {
    return this.productNameById().get(productId) ?? productId;
  }

  private loadBranches() {
    return this.organisationApi.listBranches({ limit: 100 }).pipe(
      catchError(() =>
        of<BranchList>({
          items: [],
          next_cursor: null,
        }),
      ),
    );
  }

  private loadCostCentres() {
    const listFn = this.organisationApi.listCostCentres;
    if (typeof listFn !== 'function') {
      return of<CostCentreList>({ items: [], next_cursor: null });
    }
    return (listFn.call(this.organisationApi, { limit: 100 }) ?? of<CostCentreList>({ items: [], next_cursor: null })).pipe(
      catchError(() =>
        of<CostCentreList>({
          items: [],
          next_cursor: null,
        }),
      ),
    );
  }

  private loadProducts() {
    return this.api.products({ status: 'all', limit: 100 }).pipe(
      catchError(() =>
        of<{ items: Product[]; next_cursor: string | null }>({
          items: [],
          next_cursor: null,
        }),
      ),
    );
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      const details = apiError?.details as { reason?: string } | undefined;
      if (err.status === 409 && details?.reason === 'part_of_split') {
        this.errorMessage.set(this.translate.instant(`${I18N}.partOfSplitError`));
        return;
      }
      this.errorTraceId.set(apiError?.trace_id ?? null);
      this.errorMessage.set(
        apiError?.message ?? err.message ?? this.translate.instant(`${I18N}.genericError`),
      );
      return;
    }
    this.errorMessage.set(this.translate.instant(`${I18N}.genericError`));
  }
}
