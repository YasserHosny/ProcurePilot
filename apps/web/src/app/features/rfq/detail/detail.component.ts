import { Component, OnInit, DestroyRef, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject, forkJoin, of, catchError, tap, switchMap, finalize, take } from 'rxjs';
import { MatCardModule } from '@angular/material/card';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTableModule } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { RfqApi, RfqDetail, RfqRecipient } from '../rfq-api';
import { FormatService } from '../../../core/format/format.service';
import { ApiService } from '../../../core/api/api.service';
import { SessionService } from '../../../core/auth/session.service';
import { CatalogueConfirmDialogComponent } from '../../catalogue/confirm-dialog/confirm-dialog.component';
import { CompareComponent } from '../compare/compare.component';
import { isDateInPast } from '../history/history.component';

export type RecipientReplyStatus =
  | 'not_delivered'
  | 'replied'
  | 'no_reply'
  | 'overdue'
  | 'awaiting_reply';

export interface RecipientReplyState {
  status: RecipientReplyStatus;
  icon: string;
  label: string;
  isOverdue: boolean;
  count: number;
}

const TAB_MAP: Record<string, number> = {
  details: 0,
  items: 1,
  recipients: 2,
  responses: 3,
};

const TAB_NAMES = ['details', 'items', 'recipients', 'responses'] as const;

@Component({
  selector: 'app-rfq-detail',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    MatCardModule,
    MatTabsModule,
    MatTableModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatDialogModule,
    TranslatePipe,
    CompareComponent,
  ],
  templateUrl: './detail.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './detail.component.scss',
})
export class DetailComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly rfqApi = inject(RfqApi);
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);
  private readonly formatService = inject(FormatService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly loadTrigger$ = new Subject<string>();

  readonly rfqId = signal<string>('');
  readonly rfqDetail = signal<RfqDetail | null>(null);
  readonly responseCount = signal<number | null>(null);
  readonly loading = signal<boolean>(true);
  readonly isNotFound = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly selectedTabIndex = signal<number>(0);
  readonly currentMembershipId = signal<string | null>(null);
  readonly cancelling = signal(false);

  readonly retrying = signal<boolean>(false);

  readonly displayedItemColumns = ['product', 'quantity'];
  readonly displayedRecipientColumns = ['supplier', 'contactEmail', 'status', 'reply', 'sentAt'];

  constructor() {
    this.loadTrigger$.pipe(
      takeUntilDestroyed(this.destroyRef),
      tap((id) => {
        const idChanged = id !== this.rfqId();
        this.rfqId.set(id);
        this.loading.set(true);
        this.isNotFound.set(false);
        this.errorMessage.set(null);
        if (idChanged) {
          this.rfqDetail.set(null);
          this.responseCount.set(null);
        }
      }),
      switchMap((id) =>
        forkJoin({
          detail: this.rfqApi.getRfq(id).pipe(
            catchError((err: unknown) => of({ __error: true, err })),
          ),
          responses: this.rfqApi.listResponses(id).pipe(
            catchError((err: unknown) => of({ __error: true, err })),
          ),
        }),
      ),
    ).subscribe(({ detail, responses }) => {
      this.loading.set(false);
      if ('__error' in detail) {
        this.rfqDetail.set(null);
        this.responseCount.set(null);
        const err = detail.err;
        if (err instanceof HttpErrorResponse && err.status === 404) {
          this.isNotFound.set(true);
        } else {
          this.errorMessage.set(this.translate.instant('rfq.detail.loadError'));
        }
      } else {
        this.rfqDetail.set(detail);
      }

      if ('__error' in responses) {
        this.responseCount.set(null);
      } else {
        this.responseCount.set(responses.items.length);
      }
    });
  }

  ngOnInit(): void {
    this.api.members().subscribe(({ items }) => {
      const email = this.session.currentMember()?.email;
      this.currentMembershipId.set(items.find((m) => m.email === email)?.id ?? null);
    });

    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
      const id = params.get('id');
      if (id) {
        this.loadRfq(id);
      }
    });

    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((queryParams) => {
      const tabParam = queryParams.get('tab');
      if (tabParam && tabParam in TAB_MAP) {
        this.selectedTabIndex.set(TAB_MAP[tabParam]);
      }
    });
  }

  loadRfq(id: string): void {
    if (!id) return;
    this.loadTrigger$.next(id);
  }

  onTabChange(index: number): void {
    this.selectedTabIndex.set(index);
    const tabName = TAB_NAMES[index] ?? 'details';
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { tab: tabName },
      replaceUrl: true,
    });
  }

  responsesTabLabel(): string {
    const count = this.responseCount();
    if (count === null) {
      return this.translate.instant('rfq.detail.tabResponsesNoCount');
    }
    return this.translate.instant('rfq.detail.tabResponses', { count: this.formatService.formatNumber(count) });
  }

  responsesReceivedTitle(): string {
    const count = this.responseCount() ?? 0;
    const locale = this.translate.getCurrentLang() || this.translate.getFallbackLang() || 'en';
    const category = new Intl.PluralRules(locale).select(count);
    const key = `rfq.detail.responsesReceived.${category}`;
    const formatted = this.formatService.formatNumber(count);
    const translated = this.translate.instant(key, { count: formatted });
    if (translated && translated !== key) {
      return translated;
    }
    return this.translate.instant('rfq.detail.responsesReceivedTitle', { count: formatted });
  }

  convertedRequestIds(): string[] {
    return this.rfqDetail()?.converted_purchase_request_ids ?? [];
  }

  requestGroupId(): string | null {
    return this.rfqDetail()?.request_group_id ?? null;
  }

  convertedRequestsTitle(): string {
    const count = this.convertedRequestIds().length;
    const locale = this.translate.getCurrentLang() || this.translate.getFallbackLang() || 'en';
    const category = new Intl.PluralRules(locale).select(count);
    const key = `rfq.detail.convertedCount.${category}`;
    const formatted = this.formatService.formatNumber(count);
    return this.translate.instant(key, { count: formatted });
  }

  shortId(id: string): string {
    if (!id) return '';
    return id.length > 8 ? id.slice(0, 8) : id;
  }

  onCompareResponses(): void {
    this.onTabChange(TAB_MAP['responses']);
  }

  latestSentAt(): string | null {
    const detail = this.rfqDetail();
    if (!detail || !detail.recipients?.length) return null;
    const sentDates = detail.recipients
      .map((r) => r.sent_at)
      .filter((d): d is string => Boolean(d))
      .sort((a, b) => new Date(b).getTime() - new Date(a).getTime());
    return sentDates[0] ?? null;
  }

  breadcrumbText(): string {
    const detail = this.rfqDetail();
    if (!detail) return '';
    const sentAt = this.latestSentAt();
    if (sentAt) {
      const datePart = this.formatDate(sentAt);
      const timePart = this.formatTime(sentAt);
      return this.translate.instant('rfq.detail.breadcrumbRfqSent', { date: datePart, time: timePart });
    }
    return this.translate.instant('rfq.detail.breadcrumbRfqDraft');
  }

  formatQuantity(value: string | number): string {
    return this.formatService.formatExactQuantity(value);
  }

  formatDate(value: string | Date | number | null | undefined): string {
    return this.formatService.formatDate(value, { dateStyle: 'medium' });
  }

  formatTime(value: string | Date | number | null | undefined): string {
    return this.formatService.formatDate(value, { timeStyle: 'short' });
  }

  canCancel(): boolean {
    const rfq = this.rfqDetail()?.rfq;
    return Boolean(rfq && ['draft', 'sent', 'responded', 'expired'].includes(rfq.status) &&
      (this.session.hasRole('owner') || (this.session.hasRole('buyer') && this.isCreator())));
  }

  onCancelRfq(): void {
    const id = this.rfqId();
    if (!id || !this.canCancel() || this.cancelling()) return;
    this.cancelling.set(true);
    const dialogRef = this.dialog.open(CatalogueConfirmDialogComponent, {
      width: '440px',
      data: {
        titleKey: 'rfq.cancel.title',
        messageKey: 'rfq.cancel.message',
        confirmKey: 'rfq.cancel.confirm',
        cancelKey: 'rfq.cancel.keep',
        isDestructive: true,
      },
    });
    dialogRef.afterClosed().pipe(take(1), takeUntilDestroyed(this.destroyRef)).subscribe((confirmed: boolean | undefined) => {
      if (!confirmed) {
        this.cancelling.set(false);
        return;
      }
      this.rfqApi.cancelRfq(id).pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => { this.cancelling.set(false); }),
      ).subscribe({
        next: () => {
          this.showCancelMessage('rfq.cancel.success');
          this.loadRfq(id);
        },
        error: (err: unknown) => {
          let key = 'rfq.cancel.error';
          if (err instanceof HttpErrorResponse) {
            if (err.status === 403 && err.error?.details?.reason === 'not_creator') {
              key = 'rfq.cancel.notCreator';
            } else if (err.status === 409) {
              key = 'rfq.cancel.notCancellable';
              this.loadRfq(id);
            }
          }
          this.showCancelMessage(key);
        },
      });
    });
  }

  private showCancelMessage(key: string): void {
    this.snackBar.open(this.translate.instant(key), this.translate.instant('rfq.history.dismiss'), { duration: 5000 });
  }

  getStatusClass(status: string): string {
    switch (status) {
      case 'draft': return 'status-draft';
      case 'sent': return 'status-sent';
      case 'responded': return 'status-responded';
      case 'expired': return 'status-expired';
      case 'converted': return 'status-converted';
      case 'cancelled': return 'status-cancelled';
      default: return '';
    }
  }

  getRecipientReplyState(
    recipient: RfqRecipient,
    rfq: { status: string; needed_by_date?: string | null } | null = this.rfqDetail()?.rfq ?? null,
  ): RecipientReplyState {
    const responseCount = recipient.response_count ?? 0;
    const rfqStatus = rfq?.status;
    const neededByDate = rfq?.needed_by_date;

    if (recipient.status === 'draft' || recipient.status === 'failed') {
      return {
        status: 'not_delivered',
        icon: 'block',
        label: this.translate.instant('rfq.detail.replyStatus_notDelivered'),
        isOverdue: false,
        count: responseCount,
      };
    }

    if (recipient.status === 'sent' && responseCount > 0) {
      const formatted = this.formatService.formatNumber(responseCount);
      const label =
        responseCount > 1
          ? this.translate.instant('rfq.detail.replyStatus_repliedCount', { count: formatted })
          : this.translate.instant('rfq.detail.replyStatus_replied');
      return {
        status: 'replied',
        icon: 'check',
        label,
        isOverdue: false,
        count: responseCount,
      };
    }

    if (recipient.status === 'sent' && (rfqStatus === 'expired' || rfqStatus === 'converted' || rfqStatus === 'cancelled')) {
      return {
        status: 'no_reply',
        icon: 'close',
        label: this.translate.instant('rfq.detail.replyStatus_noReply'),
        isOverdue: false,
        count: responseCount,
      };
    }

    if (
      recipient.status === 'sent' &&
      (rfqStatus === 'sent' || rfqStatus === 'responded') &&
      isDateInPast(neededByDate)
    ) {
      const formattedDate = this.formatDate(neededByDate);
      return {
        status: 'overdue',
        icon: 'warning',
        label: this.translate.instant('rfq.detail.replyStatus_overdue', { date: formattedDate }),
        isOverdue: true,
        count: responseCount,
      };
    }

    return {
      status: 'awaiting_reply',
      icon: 'schedule',
      label: this.translate.instant('rfq.detail.replyStatus_awaiting'),
      isOverdue: false,
      count: responseCount,
    };
  }

  recipientSummaryCounts(detail: RfqDetail | null = this.rfqDetail()): {
    replied: number;
    delivered: number;
    overdue: number;
  } {
    if (!detail) {
      return { replied: 0, delivered: 0, overdue: 0 };
    }
    const recipients = detail.recipients ?? [];
    const delivered = recipients.filter((r) => r.status === 'sent');
    const replied = delivered.filter((r) => (r.response_count ?? 0) > 0);
    const overdue = delivered.filter((r) => this.getRecipientReplyState(r, detail.rfq).status === 'overdue');
    return {
      replied: replied.length,
      delivered: delivered.length,
      overdue: overdue.length,
    };
  }

  recipientSummaryText(detail: RfqDetail | null = this.rfqDetail()): string {
    if (!detail) return '';
    const counts = this.recipientSummaryCounts(detail);
    const locale = this.translate.getCurrentLang() || this.translate.getFallbackLang() || 'en';
    const rules = new Intl.PluralRules(locale);

    const repliedCategory = rules.select(counts.replied);
    const repliedKey = `rfq.detail.suppliersReplied.${repliedCategory}`;
    const repliedParams = {
      replied: this.formatService.formatNumber(counts.replied),
      total: this.formatService.formatNumber(counts.delivered),
    };
    let repliedPart = this.translate.instant(repliedKey, repliedParams);
    if (!repliedPart || repliedPart === repliedKey) {
      repliedPart = this.translate.instant('rfq.detail.suppliersRepliedTitle', repliedParams);
    }

    if (counts.overdue <= 0) {
      return repliedPart;
    }

    const overdueCategory = rules.select(counts.overdue);
    const overdueKey = `rfq.detail.suppliersOverdue.${overdueCategory}`;
    const overdueParams = {
      count: this.formatService.formatNumber(counts.overdue),
    };
    let overduePart = this.translate.instant(overdueKey, overdueParams);
    if (!overduePart || overduePart === overdueKey) {
      overduePart = this.translate.instant('rfq.detail.suppliersOverdueTitle', overdueParams);
    }

    return `${repliedPart} · ${overduePart}`;
  }

  isCreator(): boolean {
    return this.rfqDetail()?.rfq.created_by_membership_id === this.currentMembershipId();
  }

  unsentRecipients(): RfqRecipient[] {
    const recipients = this.rfqDetail()?.recipients ?? [];
    return recipients.filter((r) => r.status === 'draft' || r.status === 'failed');
  }

  showRetryNotice(): boolean {
    const status = this.rfqDetail()?.rfq.status;
    return (status === 'sent' || status === 'responded') && this.isCreator() && this.unsentRecipients().length > 0;
  }

  unsentRecipientsTitle(): string {
    const count = this.unsentRecipients().length;
    const locale = this.translate.getCurrentLang() || this.translate.getFallbackLang() || 'en';
    const category = new Intl.PluralRules(locale).select(count);
    const key = `rfq.detail.unsentRecipients.${category}`;
    const formatted = this.formatService.formatNumber(count);
    const translated = this.translate.instant(key, { count: formatted });
    if (translated && translated !== key) {
      return translated;
    }
    return this.translate.instant('rfq.detail.unsentRecipientsTitle', { count: formatted });
  }

  onRetryUnsent(): void {
    if (this.retrying() || !this.isCreator()) return;
    const detail = this.rfqDetail();
    const id = this.rfqId();
    if (!id || !detail) return;
    const unsent = this.unsentRecipients();
    if (unsent.length === 0) return;

    const dialogRef = this.dialog.open(CatalogueConfirmDialogComponent, {
      width: '440px',
      data: {
        titleKey: 'rfq.detail.confirmRetryTitle',
        messageKey: 'rfq.detail.confirmRetryMessage',
        messageParams: { count: unsent.length },
        count: unsent.length,
        confirmKey: 'rfq.detail.confirmRetryButton',
        cancelKey: 'rfq.detail.cancelRetryButton',
        isDestructive: false,
      },
    });

    dialogRef.afterClosed().subscribe((confirmed: boolean | undefined) => {
      if (confirmed) {
        if (this.retrying()) return;
        this.retrying.set(true);
        this.rfqApi.sendRfq(id).subscribe({
          next: (res) => {
            this.retrying.set(false);
            const total = res.recipients.length;
            const sent = res.recipients.filter((recipient) => recipient.status === 'sent').length;
            const key = sent === total && total > 0 ? 'rfq.history.sentSuccess' : sent > 0 ? 'rfq.create.sentPartial' : 'rfq.create.sentNone';
            const params = sent === total && total > 0 ? { count: sent } : { sent, total, failed: total - sent };
            this.snackBar.open(this.translate.instant(key, params), this.translate.instant('rfq.history.dismiss'), { duration: 5000 });
            this.loadRfq(id);
          },
          error: (err: unknown) => {
            this.retrying.set(false);
            let key = 'rfq.history.sendError';
            if (err instanceof HttpErrorResponse) {
              if (err.status === 403) {
                key = 'rfq.creatorOnly';
              } else if (err.status === 422) {
                const envelope = err.error as { details?: { reason?: string }; reason?: string } | null;
                const reason = envelope?.details?.reason ?? envelope?.reason;
                if (reason === 'needed_by_in_past') {
                  key = 'rfq.create.neededByPastError';
                } else if (reason === 'rfq_expired') {
                  key = 'rfq.detail.rfqExpiredError';
                } else if (reason === 'not_sendable') {
                  key = 'rfq.detail.notSendableError';
                }
              }
            }
            this.snackBar.open(
              this.translate.instant(key),
              this.translate.instant('rfq.history.dismiss'),
              { duration: 5000 },
            );
          },
        });
      }
    });
  }

  onEditDraft(): void {
    const id = this.rfqId();
    if (!id || !this.isCreator()) return;
    this.router.navigate(['/rfq', id, 'edit']);
  }

  onSendDraft(): void {
    if (!this.isCreator()) return;
    const detail = this.rfqDetail();
    const id = this.rfqId();
    if (!id) return;
    const recipientCount = detail?.recipients.length ?? 0;
    const formattedDate = this.formatService.formatDate(detail?.rfq.needed_by_date);

    const dialogRef = this.dialog.open(CatalogueConfirmDialogComponent, {
      width: '440px',
      data: {
        titleKey: 'rfq.history.confirmSendTitle',
        messageKey: 'rfq.history.confirmSendMessage',
        messageParams: { count: recipientCount, date: formattedDate },
        date: formattedDate,
        confirmKey: 'rfq.history.confirmSendButton',
        cancelKey: 'rfq.history.cancelSendButton',
        isDestructive: false,
      },
    });

    dialogRef.afterClosed().subscribe((confirmed: boolean | undefined) => {
      if (confirmed) {
        this.rfqApi.sendRfq(id).subscribe({
          next: (res) => {
            const total = res.recipients.length;
            const sent = res.recipients.filter((recipient) => recipient.status === 'sent').length;
            const key = sent === total && total > 0 ? 'rfq.history.sentSuccess' : sent > 0 ? 'rfq.create.sentPartial' : 'rfq.create.sentNone';
            const params = sent === total && total > 0 ? { count: sent } : { sent, total, failed: total - sent };
            this.snackBar.open(this.translate.instant(key, params), this.translate.instant('rfq.history.dismiss'), { duration: 5000 });
            this.loadRfq(id);
          },
          error: (err: unknown) => {
            let key = 'rfq.history.sendError';
            if (err instanceof HttpErrorResponse) {
              if (err.status === 403) {
                key = 'rfq.creatorOnly';
              } else if (err.status === 422) {
                const envelope = err.error as { details?: { reason?: string }; reason?: string } | null;
                const reason = envelope?.details?.reason ?? envelope?.reason;
                if (reason === 'needed_by_in_past') {
                  key = 'rfq.create.neededByPastError';
                } else if (reason === 'rfq_expired') {
                  key = 'rfq.detail.rfqExpiredError';
                } else if (reason === 'not_sendable') {
                  key = 'rfq.detail.notSendableError';
                }
              }
            }
            this.snackBar.open(
              this.translate.instant(key),
              this.translate.instant('rfq.history.dismiss'),
              { duration: 5000 },
            );
          },
        });
      }
    });
  }
}
