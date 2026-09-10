import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
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
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import type {
  ApiError,
  ApprovalDecisionInput,
  PurchaseRequest,
  PurchaseRequestLine,
} from '../../../core/api/models';
import { RequestsApiService } from '../../requests/requests-api';
import { ApprovalsApiService } from '../approvals-api';

const I18N = 'approvals';

export interface ApprovalDecisionDialogData {
  readonly action: 'approve' | 'reject';
  readonly requestId: string;
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
        (data.action === 'approve'
          ? 'approvals.decisionDialog.approveTitle'
          : 'approvals.decisionDialog.rejectTitle'
        ) | translate
      }}
    </h2>
    <mat-dialog-content>
      <mat-form-field appearance="outline" class="decision-comment-field">
        <mat-label>{{ 'approvals.decisionDialog.commentLabel' | translate }}</mat-label>
        <textarea
          matInput
          [(ngModel)]="comment"
          [placeholder]="'approvals.decisionDialog.commentPlaceholder' | translate"
          rows="3"
          (keydown.ctrl.enter)="onConfirm()"
          (keydown.meta.enter)="onConfirm()"
        ></textarea>
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
      >
        {{ 'approvals.decisionDialog.confirmButton' | translate }}
      </button>
    </mat-dialog-actions>
  `,
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
    MatCardModule,
    MatTableModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatDialogModule,
    MatTooltipModule,
    TranslatePipe,
  ],
  templateUrl: './approval-queue.component.html',
  styleUrl: './approval-queue.component.scss',
})
export class ApprovalQueueComponent implements OnInit {
  private readonly approvalsApi = inject(ApprovalsApiService);
  private readonly requestsApi = inject(RequestsApiService);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(true);
  readonly pendingRequests = signal<PurchaseRequest[]>([]);
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

  ngOnInit(): void {
    this.loadPendingApprovals();
  }

  loadPendingApprovals(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    this.approvalsApi.listPendingApprovals({ limit: 50 }).subscribe({
      next: (res) => {
        this.pendingRequests.set([...res.items]);
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
    const dialogRef = this.dialog.open<
      ApprovalDecisionDialogComponent,
      ApprovalDecisionDialogData,
      ApprovalDecisionDialogResult
    >(ApprovalDecisionDialogComponent, {
      width: '480px',
      data: { action, requestId: request.id },
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
        const msgKey =
          action === 'approve'
            ? `${I18N}.approveSuccess`
            : `${I18N}.rejectSuccess`;
        this.snackBar.open(this.translate.instant(msgKey), undefined, { duration: 3500 });
      },
      error: (err: unknown) => {
        this.processingRequestId.set(null);
        this.handleError(err);
      },
    });
  }

  formatMoney(request: PurchaseRequest): string {
    if (!request.estimated_total) {
      return this.translate.instant(`${I18N}.notAvailable`);
    }
    return `${request.estimated_total.currency} ${request.estimated_total.amount}`;
  }

  formatLinePrice(line: PurchaseRequestLine): string {
    if (!line.estimated_unit_price) {
      return this.translate.instant(`${I18N}.notAvailable`);
    }
    return `${line.estimated_unit_price.currency} ${line.estimated_unit_price.amount}`;
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorTraceId.set(apiError?.trace_id ?? null);
      this.errorMessage.set(
        apiError?.message ?? err.message ?? this.translate.instant(`${I18N}.genericError`),
      );
      return;
    }
    this.errorMessage.set(this.translate.instant(`${I18N}.genericError`));
  }
}
