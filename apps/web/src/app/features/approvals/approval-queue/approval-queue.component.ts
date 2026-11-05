import { NgTemplateOutlet } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  DestroyRef,
  ElementRef,
  Injector,
  OnInit,
  afterNextRender,
  computed,
  inject,
  signal,
  viewChild,
  ChangeDetectionStrategy,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
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
import { MatSelect, MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import type { ParamMap } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { EMPTY, Observable, defer, forkJoin, of } from 'rxjs';
import { catchError, expand, map, reduce } from 'rxjs/operators';

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
  PendingApprovalSort,
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
const DEFAULT_SORT: PendingApprovalSort = 'submitted_desc';
interface BranchLookupResult {
  readonly list: BranchList;
  readonly succeeded: boolean;
}

const PENDING_APPROVAL_SORTS: readonly PendingApprovalSort[] = [
  'submitted_desc',
  'submitted_asc',
  'required_by_asc',
  'total_desc',
  'total_asc',
];

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
    RouterLink,
    MatCardModule,
    MatTableModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatDialogModule,
    MatTooltipModule,
    MatSelectModule,
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
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  private readonly injector = inject(Injector);
  private readonly host = inject(ElementRef<HTMLElement>);
  private readonly sortSelect = viewChild<MatSelect>('sortSelect');

  readonly isLoading = signal<boolean>(true);
  readonly pendingRequests = signal<PurchaseRequest[]>([]);
  readonly nextCursor = signal<string | null>(null);
  readonly isLoadingMore = signal<boolean>(false);
  readonly groupSiblings = signal<Map<string, PurchaseRequest[]>>(new Map());
  readonly groupStatus = signal<Map<string, 'loading' | 'complete' | 'failed'>>(new Map());
  readonly branches = signal<Branch[]>([]);
  readonly costCentres = signal<CostCentre[]>([]);
  readonly products = signal<Product[]>([]);
  readonly errorMessage = signal<string | null>(null);
  readonly pageLoadFailed = signal<boolean>(false);
  readonly errorTraceId = signal<string | null>(null);
  readonly expandedRequestIds = signal<ReadonlySet<string>>(new Set<string>());
  readonly processingRequestId = signal<string | null>(null);
  readonly sortOption = signal<PendingApprovalSort>(DEFAULT_SORT);
  readonly branchFilter = signal<string>('');
  readonly totalCount = signal<number | null>(null);
  readonly sortOptions = PENDING_APPROVAL_SORTS;
  readonly hasActiveFilters = computed(
    () => this.sortOption() !== DEFAULT_SORT || this.branchFilter() !== '',
  );

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

  readonly branchFilterName = computed(() => {
    const branchId = this.branchFilter();
    return branchId ? (this.branchNameById().get(branchId) ?? branchId) : '';
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

    const siblingsMap = this.groupSiblings();

    for (const req of reqs) {
      if (req.request_group) {
        const gid = req.request_group.id;
        if (!seenGroupIds.has(gid)) {
          seenGroupIds.add(gid);
          const pageRequests = groupsMap.get(gid)!;
          const fetchedSiblings = siblingsMap.get(gid) ?? [];

          const reqMap = new Map<string, PurchaseRequest>();
          for (const r of pageRequests) {
            reqMap.set(r.id, r);
          }
          for (const r of fetchedSiblings) {
            if (!reqMap.has(r.id)) {
              reqMap.set(r.id, r);
            }
          }
          const requests = Array.from(reqMap.values());
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
  private loadGeneration = 0;
  private branchesLoaded = false;
  private initialized = false;
  private urlNeedsCleanup = false;

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
    this.route.queryParamMap
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((params) => this.applyUrlState(params));
  }

  private applyUrlState(params: ParamMap): void {
    const rawSort = params.get('sort');
    const sort = this.isPendingApprovalSort(rawSort) ? rawSort : DEFAULT_SORT;
    const rawBranch = params.get('branch') ?? '';
    const branch = this.normalizeBranch(rawBranch);
    const invalidSort = !!rawSort && !this.isPendingApprovalSort(rawSort);
    const invalidBranch = !!rawBranch && !this.isUuid(rawBranch);
    const unknownBranch =
      !!rawBranch && !invalidBranch && this.branchesLoaded && branch === '';
    this.urlNeedsCleanup = invalidSort || invalidBranch || unknownBranch;

    const changed = this.sortOption() !== sort || this.branchFilter() !== branch;
    this.sortOption.set(sort);
    this.branchFilter.set(branch);

    if (!this.initialized) {
      this.initialized = true;
      this.loadPendingApprovals();
      return;
    }

    if (!changed) {
      if (this.urlNeedsCleanup && this.branchesLoaded) {
        this.writeUrl();
      }
      return;
    }

    this.resetAndReload();
    if (this.urlNeedsCleanup && this.branchesLoaded) {
      this.writeUrl();
    }
  }

  private isPendingApprovalSort(value: string | null): value is PendingApprovalSort {
    return value !== null && PENDING_APPROVAL_SORTS.includes(value as PendingApprovalSort);
  }

  private isUuid(value: string): boolean {
    return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
  }

  private normalizeBranch(raw: string): string {
    if (!raw || !this.isUuid(raw)) {
      return '';
    }
    if (!this.branchesLoaded) {
      return raw;
    }
    return this.branchNameById().has(raw) ? raw : '';
  }

  private resetAndReload(): void {
    this.pendingRequests.set([]);
    this.totalCount.set(null);
    this.expandedRequestIds.set(new Set());
    this.loadPendingApprovals();
  }

  private listParams(cursor?: string): {
    sort?: PendingApprovalSort;
    branch_id?: string;
    cursor?: string;
    limit: number;
  } {
    return {
      ...(this.sortOption() !== DEFAULT_SORT ? { sort: this.sortOption() } : {}),
      ...(this.branchFilter() ? { branch_id: this.branchFilter() } : {}),
      ...(cursor ? { cursor } : {}),
      limit: 50,
    };
  }

  private writeUrl(): void {
    void this.router.navigate([], {
      queryParams: {
        sort: this.sortOption() === DEFAULT_SORT ? null : this.sortOption(),
        branch: this.branchFilter() || null,
      },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  onSortChange(sort: PendingApprovalSort): void {
    if (!this.isPendingApprovalSort(sort) || this.sortOption() === sort) {
      return;
    }
    this.sortOption.set(sort);
    this.urlNeedsCleanup = false;
    this.writeUrl();
    this.resetAndReload();
  }

  onBranchChange(branchId: string): void {
    const branch = branchId ?? '';
    if (this.branchFilter() === branch) {
      return;
    }
    this.branchFilter.set(branch);
    this.urlNeedsCleanup = false;
    this.writeUrl();
    this.resetAndReload();
  }

  removeSortFilter(): void {
    this.onSortChange(DEFAULT_SORT);
    this.focusAfterChipRemoval();
  }

  removeBranchFilter(): void {
    this.onBranchChange('');
    this.focusAfterChipRemoval();
  }

  private focusAfterChipRemoval(): void {
    afterNextRender(
      () => {
        const host = this.host.nativeElement as HTMLElement;
        const buttons = host.querySelectorAll<HTMLButtonElement>('.chip-remove');
        if (buttons.length > 0) {
          buttons[0].focus();
          return;
        }
        this.sortSelect()?.focus();
      },
      { injector: this.injector },
    );
  }

  clearFilters(): void {
    const changed = this.hasActiveFilters();
    this.sortOption.set(DEFAULT_SORT);
    this.branchFilter.set('');
    this.urlNeedsCleanup = false;
    this.writeUrl();
    if (changed) {
      this.resetAndReload();
    }
    this.sortSelect()?.focus();
  }

  sortOptionLabel(sort: PendingApprovalSort): string {
    return this.translate.instant(`${I18N}.sort.options.${sort}`);
  }

  totalCountLabel(): string {
    const total = this.totalCount();
    if (total === null) {
      return '';
    }
    const locale = this.translate.getCurrentLang() || this.translate.getFallbackLang() || 'en';
    const category = new Intl.PluralRules(locale).select(total);
    return this.translate.instant(`approvals.total.${category}`, {
      count: this.formatService.formatNumber(total, { numberingSystem: 'latn' }),
    });
  }

  announcementText(): string {
    if (this.isLoading() || this.totalCount() === null) {
      return '';
    }
    return this.translate.instant(`${I18N}.announce.sorted`, {
      sort: this.sortOptionLabel(this.sortOption()),
      count: this.totalCountLabel(),
    });
  }

  loadPendingApprovals(): void {
    // When reloading (e.g. after a decision), reload from the first page and reset cursor.
    // Why: Reloading from cursor=null fetches fresh page 1 from the server. If accumulated
    // extra pages were kept, items could be duplicated or stale across pages, and the server
    // cursor would be out-of-sync with the spliced client list.
    const generation = ++this.loadGeneration;
    this.isLoading.set(true);
    this.isLoadingMore.set(false);
    this.errorMessage.set(null);
    this.pageLoadFailed.set(false);
    this.errorTraceId.set(null);
    this.totalCount.set(null);
    this.nextCursor.set(null);
    this.groupSiblings.set(new Map());
    this.groupStatus.set(new Map());

    forkJoin({
      approvals: this.approvalsApi.listPendingApprovals(this.listParams()),
      branches: this.loadBranches(),
      costCentres: this.loadCostCentres(),
      products: this.loadProducts(),
    }).subscribe({
      next: ({ approvals, branches, costCentres, products }) => {
        if (generation !== this.loadGeneration) {
          return;
        }
        this.pendingRequests.set([...approvals.items]);
        this.nextCursor.set(approvals.next_cursor ?? null);
        this.totalCount.set(approvals.total ?? null);
        if (branches.succeeded) {
          this.branches.set([...branches.list.items]);
          this.branchesLoaded = true;
        }
        this.costCentres.set([...costCentres.items]);
        this.products.set([...products.items]);
        this.isLoading.set(false);
        if (this.branchesLoaded && this.dropUnknownBranch(generation)) {
          return;
        }
        this.cleanupUrlAfterLookups();
        this.checkAndFetchMissingGroupSiblings(generation);
      },
      error: (err: unknown) => {
        if (generation !== this.loadGeneration) {
          return;
        }
        this.isLoading.set(false);
        this.totalCount.set(null);
        this.pageLoadFailed.set(true);
        this.handleError(err, 'approvals.pagination.pageLoadError');
      },
    });
  }

  retryLoad(): void {
    this.loadPendingApprovals();
  }

  private dropUnknownBranch(generation: number): boolean {
    const branch = this.branchFilter();
    if (!branch || this.branchNameById().has(branch)) {
      return false;
    }
    this.branchFilter.set('');
    this.urlNeedsCleanup = false;
    this.writeUrl();
    if (generation === this.loadGeneration) {
      this.resetAndReload();
    }
    return true;
  }

  private cleanupUrlAfterLookups(): void {
    if (!this.urlNeedsCleanup) {
      return;
    }
    this.urlNeedsCleanup = false;
    this.writeUrl();
  }

  loadMore(): void {
    const cursor = this.nextCursor();
    if (!cursor || this.isLoadingMore()) {
      return;
    }
    const generation = this.loadGeneration;
    this.isLoadingMore.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    this.approvalsApi.listPendingApprovals(this.listParams(cursor)).subscribe({
      next: (res) => {
        if (generation !== this.loadGeneration) {
          return;
        }
        const current = this.pendingRequests();
        const seenIds = new Set(current.map((r) => r.id));
        const additions = res.items.filter((r) => !seenIds.has(r.id));
        this.pendingRequests.set([...current, ...additions]);
        this.nextCursor.set(res.next_cursor ?? null);
        this.totalCount.set(res.total ?? this.totalCount());
        this.isLoadingMore.set(false);
        this.checkAndFetchMissingGroupSiblings(generation);
      },
      error: (err: unknown) => {
        if (generation !== this.loadGeneration) {
          return;
        }
        this.isLoadingMore.set(false);
        // Keep rows already loaded, show error banner and keep nextCursor so Load more can retry.
        this.handleError(err, 'approvals.pagination.loadError');
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
    if (!this.isGroupComplete(item)) {
      return;
    }
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
    const targetItem = this.queueItems().find((i) => i.id === groupId);
    if (targetItem && this.isGroupRow(targetItem) && !this.isGroupComplete(targetItem)) {
      return;
    }
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

  isOwnRequest(item: QueueItem): boolean {
    const membershipId = this.session.currentMember()?.membership_id;
    if (!membershipId) return false;
    const isOwn = (request: PurchaseRequest): boolean =>
      request.approval_step?.self_approval === true &&
      request.requested_by_membership_id === membershipId;
    return item.kind === 'group'
      ? item.requests.some(isOwn)
      : isOwn(item.request);
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

  getRequesterInfo(request?: PurchaseRequest | null): { text: string; tooltip: string | null } {
    if (!request) {
      return { text: this.translate.instant(`${I18N}.notAvailable`), tooltip: null };
    }
    const name = request.requester_name?.trim();
    if (name) {
      return { text: name, tooltip: null };
    }
    const email = request.requester_email?.trim();
    if (email) {
      const atIdx = email.indexOf('@');
      const localPart = atIdx !== -1 ? email.slice(0, atIdx) : email;
      return { text: localPart, tooltip: email };
    }
    if (request.requested_by_membership_id) {
      return { text: request.requested_by_membership_id.slice(0, 8), tooltip: null };
    }
    return { text: this.translate.instant(`${I18N}.notAvailable`), tooltip: null };
  }

  getRequesterDisplay(request: PurchaseRequest): string {
    return this.getRequesterInfo(request).text;
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

  private loadBranches(): Observable<BranchLookupResult> {
    return defer(() => {
      const HARD_CAP = 50;
      let pageCount = 0;

      return this.organisationApi.listBranches({ limit: 100 }).pipe(
        expand((res) => {
          pageCount++;
          if (res.next_cursor && pageCount < HARD_CAP) {
            return this.organisationApi.listBranches({ limit: 100, cursor: res.next_cursor });
          }
          return EMPTY;
        }),
        reduce(
          (acc: BranchList, res: BranchList) => ({
            items: [...acc.items, ...res.items],
            next_cursor: res.next_cursor,
          }),
          { items: [], next_cursor: null } as BranchList,
        ),
        map((list): BranchLookupResult => ({ list, succeeded: list.next_cursor === null })),
        catchError(() =>
          of<BranchLookupResult>({
            list: { items: [], next_cursor: null },
            succeeded: false,
          }),
        ),
      );
    });
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

  isGroupLoading(groupId: string): boolean {
    return this.groupStatus().get(groupId) === 'loading';
  }

  isGroupFailed(groupId: string): boolean {
    return this.groupStatus().get(groupId) === 'failed';
  }

  isGroupComplete(item: GroupQueueItem): boolean {
    const pageReqs = this.pendingRequests().filter(
      (r) => r.request_group?.id === item.groupId,
    );
    if (pageReqs.length >= item.group.size) {
      return true;
    }
    return (
      this.groupStatus().get(item.groupId) === 'complete' &&
      item.requests.length === item.group.size &&
      item.requests.every((r) => r.request_group?.id === item.groupId)
    );
  }

  isDecisionDisabled(row: QueueItem): boolean {
    if (this.isProcessing(row.id)) {
      return true;
    }
    if (this.isGroupRow(row) && !this.isGroupComplete(row)) {
      return true;
    }
    return false;
  }

  private checkAndFetchMissingGroupSiblings(generation = this.loadGeneration): void {
    const reqs = this.pendingRequests();
    const groups = new Map<string, { summary: RequestGroupSummary; requests: PurchaseRequest[] }>();

    for (const req of reqs) {
      if (req.request_group) {
        const gid = req.request_group.id;
        if (!groups.has(gid)) {
          groups.set(gid, { summary: req.request_group, requests: [] });
        }
        groups.get(gid)!.requests.push(req);
      }
    }

    const completeGroupIds: string[] = [];

    for (const [gid, { summary, requests }] of groups.entries()) {
      if (requests.length >= summary.size) {
        const allMatchGroupId = requests.every((r) => r.request_group?.id === summary.id);
        const uniqueIds = new Set(requests.map((r) => r.id));
        const verified =
          allMatchGroupId &&
          uniqueIds.size === summary.size &&
          requests.length === summary.size;
        if (verified && this.groupStatus().get(gid) !== 'complete') {
          completeGroupIds.push(gid);
        }
        continue;
      }
      const currentStatus = this.groupStatus().get(gid);
      if (currentStatus === 'loading' || currentStatus === 'complete') {
        continue;
      }
      this.fetchGroupSiblings(summary, requests, generation);
    }

    if (completeGroupIds.length > 0) {
      this.groupStatus.update((current) => {
        const next = new Map(current);
        for (const gid of completeGroupIds) {
          next.set(gid, 'complete');
        }
        return next;
      });
    }
  }

  fetchGroupSiblings(
    summary: RequestGroupSummary,
    knownRequests: PurchaseRequest[],
    generation = this.loadGeneration,
  ): void {
    const knownIds = new Set(knownRequests.map((r) => r.id));
    const siblingIds = summary.sibling_request_ids ?? [];
    const missingIds = siblingIds.filter((id) => !knownIds.has(id));

    if (missingIds.length === 0 && knownRequests.length >= summary.size) {
      if (generation !== this.loadGeneration) {
        return;
      }
      const allMatchGroupId = knownRequests.every((r) => r.request_group?.id === summary.id);
      const uniqueIds = new Set(knownRequests.map((r) => r.id));
      const verified =
        allMatchGroupId &&
        uniqueIds.size === summary.size &&
        knownRequests.length === summary.size;

      const nextStatus = new Map(this.groupStatus());
      nextStatus.set(summary.id, verified ? 'complete' : 'failed');
      this.groupStatus.set(nextStatus);
      return;
    }

    if (missingIds.length === 0 || knownRequests.length + missingIds.length < summary.size) {
      if (generation !== this.loadGeneration) {
        return;
      }
      const nextStatus = new Map(this.groupStatus());
      nextStatus.set(summary.id, 'failed');
      this.groupStatus.set(nextStatus);
      return;
    }

    const nextLoading = new Map(this.groupStatus());
    nextLoading.set(summary.id, 'loading');
    this.groupStatus.set(nextLoading);

    forkJoin(missingIds.map((id) => this.requestsApi.getRequest(id))).subscribe({
      next: (fetchedSiblings) => {
        if (generation !== this.loadGeneration) {
          return;
        }
        const allRequests = [...knownRequests, ...fetchedSiblings];
        const allMatchGroupId = allRequests.every((r) => r.request_group?.id === summary.id);
        const uniqueIds = new Set(allRequests.map((r) => r.id));
        const verified =
          allMatchGroupId &&
          uniqueIds.size === summary.size &&
          allRequests.length === summary.size;

        if (!verified) {
          const nextStatus = new Map(this.groupStatus());
          nextStatus.set(summary.id, 'failed');
          this.groupStatus.set(nextStatus);
          return;
        }

        const sibMap = new Map(this.groupSiblings());
        sibMap.set(summary.id, fetchedSiblings);
        this.groupSiblings.set(sibMap);

        const nextStatus = new Map(this.groupStatus());
        nextStatus.set(summary.id, 'complete');
        this.groupStatus.set(nextStatus);
      },
      error: () => {
        if (generation !== this.loadGeneration) {
          return;
        }
        const nextStatus = new Map(this.groupStatus());
        nextStatus.set(summary.id, 'failed');
        this.groupStatus.set(nextStatus);
      },
    });
  }

  retryLoadGroup(item: GroupQueueItem): void {
    const knownRequests = this.pendingRequests().filter(
      (r) => r.request_group?.id === item.groupId,
    );
    this.fetchGroupSiblings(item.group, knownRequests, this.loadGeneration);
  }

  showingRequestsLabel(count: number): string {
    const locale = this.translate.getCurrentLang() || this.translate.getFallbackLang() || 'en';
    const category = new Intl.PluralRules(locale).select(count);
    return this.translate.instant(`approvals.pagination.showing.${category}`, {
      count: this.formatService.formatNumber(count),
    });
  }

  paginationStatusText(): string {
    const count = this.pendingRequests().length;
    const total = this.totalCount();
    if (total !== null && total > count) {
      return this.translate.instant('approvals.pagination.showingOf', {
        loaded: this.formatService.formatNumber(count, { numberingSystem: 'latn' }),
        total: this.formatService.formatNumber(total, { numberingSystem: 'latn' }),
      });
    }
    const locale = this.translate.getCurrentLang() || this.translate.getFallbackLang() || 'en';
    const category = new Intl.PluralRules(locale).select(count);
    const key = this.nextCursor()
      ? `approvals.pagination.showingMore.${category}`
      : `approvals.pagination.showing.${category}`;
    return this.translate.instant(key, {
      count: this.formatService.formatNumber(count, { numberingSystem: 'latn' }),
    });
  }

  private handleError(err: unknown, defaultMessageKey = `${I18N}.genericError`): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      const details = apiError?.details as { reason?: string } | undefined;
      if (err.status === 403 && details?.reason === 'self_decision_not_allowed') {
        this.loadPendingApprovals();
        this.errorMessage.set(this.translate.instant('approvals.selfDecisionNotAllowed'));
        return;
      }
      if (err.status === 409 && details?.reason === 'part_of_split') {
        this.errorMessage.set(this.translate.instant(`${I18N}.partOfSplitError`));
        return;
      }
      this.errorTraceId.set(apiError?.trace_id ?? null);

      const isListError =
        defaultMessageKey === 'approvals.pagination.loadError' ||
        defaultMessageKey === 'approvals.pagination.pageLoadError';
      if (isListError) {
        const raw = err.error as unknown;
        const isEnvelope =
          typeof raw === 'object' &&
          raw !== null &&
          typeof (raw as Record<string, unknown>)['code'] === 'string' &&
          typeof (raw as Record<string, unknown>)['message'] === 'string';
        this.errorMessage.set(
          isEnvelope && apiError?.message
            ? apiError.message
            : this.translate.instant(defaultMessageKey),
        );
        return;
      }

      this.errorMessage.set(
        apiError?.message ?? err.message ?? this.translate.instant(defaultMessageKey),
      );
      return;
    }
    this.errorMessage.set(this.translate.instant(defaultMessageKey));
  }
}
