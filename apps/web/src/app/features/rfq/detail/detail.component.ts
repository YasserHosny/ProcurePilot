import { Component, OnInit, DestroyRef, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject, forkJoin, of, catchError, tap, switchMap, finalize, take, from, concatMap, map, toArray } from 'rxjs';
import { MatCardModule } from '@angular/material/card';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTableModule } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { formatRfqReference, RfqActionKeys, RfqApi, RfqDetail, RfqRecipient, RfqReminderPreview } from '../rfq-api';
import { FormatService } from '../../../core/format/format.service';
import { ApiService } from '../../../core/api/api.service';
import { SessionService } from '../../../core/auth/session.service';
import { CatalogueConfirmDialogComponent, ConfirmDialogData } from '../../catalogue/confirm-dialog/confirm-dialog.component';
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
  readonly formatRfqReference = formatRfqReference;
  private readonly actionKeys = new RfqActionKeys();
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
  readonly remindingAll = signal<boolean>(false);

  readonly displayedItemColumns = ['product', 'quantity'];
  readonly displayedRecipientColumns = ['supplier', 'contactEmail', 'status', 'reply', 'sentAt', 'reminders'];

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

  /**
   * The viewer's own membership id comes from the session. The members list is owner-only (a buyer
   * gets 403), so it is only a fallback for a session without the id.
   */
  private resolveMembershipId(): void {
    const sessionMembershipId = this.session.currentMember()?.membership_id;
    if (sessionMembershipId) {
      this.currentMembershipId.set(sessionMembershipId);
      return;
    }
    this.api.members().subscribe({
      next: ({ items }) => {
        const email = this.session.currentMember()?.email;
        this.currentMembershipId.set(items.find((m) => m.email === email)?.id ?? null);
      },
      error: () => this.currentMembershipId.set(null),
    });
  }

  ngOnInit(): void {
    this.resolveMembershipId();

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
    if (detail.rfq.status === 'cancelled') {
      return this.translate.instant('rfq.detail.breadcrumbRfqCancelled');
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

  /** Any owner or buyer can start a new RFQ from this one, whatever its status. */
  canDuplicate(): boolean {
    return this.session.hasRole('owner', 'buyer');
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
      this.rfqApi.cancelRfq(id, this.actionKeys.get(`cancel:${id}`)).pipe(
        takeUntilDestroyed(this.destroyRef),
        finalize(() => { this.cancelling.set(false); }),
      ).subscribe({
        next: () => {
          this.actionKeys.clear(`cancel:${id}`);
          this.showCancelMessage('rfq.cancel.success');
          this.loadRfq(id);
        },
        error: (err: unknown) => {
          this.actionKeys.onError(`cancel:${id}`, err);
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

  canSend(): boolean {
    return this.isCreator() || this.session.hasRole('owner');
  }

  canRemindRecipient(recipient: RfqRecipient): boolean {
    return this.canSend() && recipient.can_remind === true;
  }

  hasRemindableRecipients(): boolean {
    return this.canSend() && (this.rfqDetail()?.recipients ?? []).some((r) => r.can_remind === true);
  }

  reminderBlockedText(recipient: RfqRecipient): string | null {
    const reason = recipient.remind_blocked_reason;
    if (reason !== 'too_early' && reason !== 'cooldown' && reason !== 'limit_reached') {
      return null;
    }
    return this.translate.instant(this.reminderBlockedKeyFor(reason));
  }

  reminderHistoryText(recipient: RfqRecipient): string {
    const count = recipient.reminder_count ?? 0;
    const sent = this.translate.instant('rfq.detail.remindersSent', {
      count: this.formatService.formatNumber(count),
    });
    if (!recipient.last_reminder_at) {
      return sent;
    }
    return `${sent} · ${this.translate.instant('rfq.detail.lastReminderAt')} ` +
      `${this.formatDate(recipient.last_reminder_at)} · ${this.formatTime(recipient.last_reminder_at)}`;
  }

  onRemindRecipient(recipient: RfqRecipient): void {
    const id = this.rfqId();
    if (!id || !this.canRemindRecipient(recipient)) return;

    this.rfqApi.previewReminder(id, recipient.id).pipe(
      take(1),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe({
      next: (preview) => this.openReminderPreview(id, recipient, preview),
      error: () => this.showReminderMessage('rfq.detail.reminderPreviewError'),
    });
  }

  private openReminderPreview(id: string, recipient: RfqRecipient, preview: RfqReminderPreview): void {
    const blockedKey = this.reminderBlockedKeyFor(preview.blocked_reason);
    const data: ConfirmDialogData = {
      titleKey: 'rfq.detail.reminderPreviewTitle',
      messageKey: 'rfq.detail.reminderPreviewMessage',
      previewSubject: preview.subject,
      previewBody: preview.body_text,
      previewLocale: preview.locale,
      showConfirm: preview.allowed,
      confirmKey: 'rfq.detail.reminderSend',
      cancelKey: 'rfq.detail.reminderCancel',
      warningKey: preview.allowed ? undefined : (blockedKey ?? 'rfq.detail.reminderBlockedNotPermitted'),
      isDestructive: false,
    };

    const dialogRef = this.dialog.open(CatalogueConfirmDialogComponent, { width: '560px', data });
    dialogRef.afterClosed().pipe(take(1), takeUntilDestroyed(this.destroyRef)).subscribe((confirmed: boolean | undefined) => {
      if (!confirmed || !preview.allowed) return;
      this.sendReminder(id, recipient);
    });
  }

  private sendReminder(id: string, recipient: RfqRecipient): void {
    const action = `remind:${id}:${recipient.id}`;
    this.rfqApi.sendReminder(id, recipient.id, this.actionKeys.get(action)).pipe(
      take(1),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe({
      next: (updated) => {
        this.actionKeys.clear(action);
        this.applyRecipientUpdate(updated);
        this.showReminderMessage('rfq.detail.reminderSent');
      },
      error: (err: unknown) => {
        this.actionKeys.onError(action, err);
        this.showReminderMessage(this.reminderErrorKey(err));
      },
    });
  }

  private applyRecipientUpdate(updated: RfqRecipient): void {
    const detail = this.rfqDetail();
    if (!detail) return;
    this.rfqDetail.set({
      ...detail,
      recipients: detail.recipients.map((recipient) => (
        recipient.id === updated.id ? { ...recipient, ...updated } : recipient
      )),
    });
  }

  onRemindAll(): void {
    if (this.remindingAll() || !this.canSend()) return;
    const id = this.rfqId();
    const recipients = (this.rfqDetail()?.recipients ?? []).filter((r) => r.can_remind === true);
    if (!id || recipients.length === 0) return;

    const names = recipients.map((recipient) => (
      recipient.supplier_name || this.translate.instant('rfq.detail.unknownSupplier')
    ));
    const dialogRef = this.dialog.open(CatalogueConfirmDialogComponent, {
      width: '520px',
      data: {
        titleKey: 'rfq.detail.remindAllConfirmTitle',
        messageKey: 'rfq.detail.remindAllConfirmMessage',
        messageParams: { count: recipients.length },
        count: recipients.length,
        listItems: names,
        confirmKey: 'rfq.detail.remindAllConfirmButton',
        cancelKey: 'rfq.detail.reminderCancel',
        isDestructive: false,
      } satisfies ConfirmDialogData,
    });

    dialogRef.afterClosed().pipe(take(1), takeUntilDestroyed(this.destroyRef)).subscribe((confirmed: boolean | undefined) => {
      if (!confirmed) return;
      this.remindingAll.set(true);

      const sendOne = (recipient: RfqRecipient) => {
        const action = `remind:${id}:${recipient.id}`;
        return this.rfqApi.sendReminder(id, recipient.id, this.actionKeys.get(action)).pipe(
          tap(() => this.actionKeys.clear(action)),
          map(() => true),
          catchError((error: unknown) => {
            this.actionKeys.onError(action, error);
            return of(false);
          }),
        );
      };

      from(recipients).pipe(
        concatMap(sendOne),
        toArray(),
        finalize(() => this.remindingAll.set(false)),
        takeUntilDestroyed(this.destroyRef),
      ).subscribe((results) => {
        const sent = results.filter((ok) => ok).length;
        const failed = results.length - sent;
        this.showReminderMessage('rfq.detail.remindAllResult', { sent, failed });
        this.loadRfq(id);
      });
    });
  }

  neededInDays(): number | null {
    const detail = this.rfqDetail();
    if (!detail) return null;
    const { status, needed_by_date } = detail.rfq;
    if (status !== 'sent' && status !== 'responded') return null;
    const days = this.calendarDaysUntil(needed_by_date);
    if (days === null || days < 0 || days > 2) return null;
    const recipients = detail.recipients ?? [];
    if (!recipients.some((recipient) => (recipient.response_count ?? 0) === 0)) return null;
    return days;
  }

  neededHintText(): string {
    const days = this.neededInDays();
    if (days === null) return '';
    const locale = this.translate.getCurrentLang() || this.translate.getFallbackLang() || 'en';
    const category = new Intl.PluralRules(locale).select(days);
    const params = { count: this.formatService.formatNumber(days) };
    const key = `rfq.detail.neededInDays.${category}`;
    const translated = this.translate.instant(key, params);
    if (translated && translated !== key) {
      return translated;
    }
    return this.translate.instant('rfq.detail.neededInDaysTitle', params);
  }

  private calendarDaysUntil(value: string | null | undefined): number | null {
    if (!value) return null;
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    const target = match
      ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
      : new Date(value);
    if (Number.isNaN(target.getTime())) return null;
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    return Math.round((target.getTime() - today.getTime()) / 86_400_000);
  }

  private reminderBlockedKeyFor(reason: string | null | undefined): string {
    switch (reason) {
      case 'rfq_not_open': return 'rfq.detail.reminderBlockedRfqNotOpen';
      case 'not_delivered': return 'rfq.detail.reminderBlockedNotDelivered';
      case 'replied': return 'rfq.detail.reminderBlockedReplied';
      case 'too_early': return 'rfq.detail.reminderBlockedTooEarly';
      case 'cooldown': return 'rfq.detail.reminderBlockedCooldown';
      case 'limit_reached': return 'rfq.detail.reminderBlockedLimitReached';
      case 'not_permitted': return 'rfq.detail.reminderBlockedNotPermitted';
      default: return 'rfq.detail.reminderSendError';
    }
  }

  private reminderErrorKey(error: unknown): string {
    if (error instanceof HttpErrorResponse) {
      if (error.status === 503) {
        return 'rfq.detail.reminderDeliveryFailed';
      }
      if (error.status === 422) {
        const envelope = error.error as { details?: { reason?: string }; reason?: string } | null;
        const reason = envelope?.details?.reason ?? envelope?.reason;
        return this.reminderBlockedKeyFor(reason);
      }
      if (error.status === 403) {
        return 'rfq.detail.reminderBlockedNotPermitted';
      }
    }
    return 'rfq.detail.reminderSendError';
  }

  private showReminderMessage(key: string, params?: Record<string, unknown>): void {
    this.snackBar.open(
      this.translate.instant(key, params),
      this.translate.instant('rfq.history.dismiss'),
      { duration: 5000 },
    );
  }

  sendAttemptsText(recipient: RfqRecipient): string {
    const count = recipient.send_attempts ?? 0;
    const locale = this.translate.getCurrentLang() || this.translate.getFallbackLang() || 'en';
    const category = new Intl.PluralRules(locale).select(count);
    return this.translate.instant(`rfq.detail.sendAttempts.${category}`, {
      count: this.formatService.formatNumber(count),
    });
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
    return (status === 'sent' || status === 'responded') && this.canSend() && this.unsentRecipients().length > 0;
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
    if (this.retrying() || !this.canSend()) return;
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
        this.rfqApi.sendRfq(id, this.actionKeys.get(`send:${id}`)).subscribe({
          next: (res) => {
            this.actionKeys.clear(`send:${id}`);
            this.retrying.set(false);
            const total = res.recipients.length;
            const sent = res.recipients.filter((recipient) => recipient.status === 'sent').length;
            const key = sent === total && total > 0 ? 'rfq.history.sentSuccess' : sent > 0 ? 'rfq.create.sentPartial' : 'rfq.create.sentNone';
            const params = sent === total && total > 0 ? { count: sent } : { sent, total, failed: total - sent };
            this.snackBar.open(this.translate.instant(key, params), this.translate.instant('rfq.history.dismiss'), { duration: 5000 });
            this.loadRfq(id);
          },
          error: (err: unknown) => {
            this.actionKeys.onError(`send:${id}`, err);
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
    if (this.retrying()) return;
    if (!this.canSend()) return;
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
        if (this.retrying()) return;
        this.retrying.set(true);
        this.rfqApi.sendRfq(id, this.actionKeys.get(`send:${id}`)).subscribe({
          next: (res) => {
            this.actionKeys.clear(`send:${id}`);
            this.retrying.set(false);
            const total = res.recipients.length;
            const sent = res.recipients.filter((recipient) => recipient.status === 'sent').length;
            const key = sent === total && total > 0 ? 'rfq.history.sentSuccess' : sent > 0 ? 'rfq.create.sentPartial' : 'rfq.create.sentNone';
            const params = sent === total && total > 0 ? { count: sent } : { sent, total, failed: total - sent };
            this.snackBar.open(this.translate.instant(key, params), this.translate.instant('rfq.history.dismiss'), { duration: 5000 });
            this.loadRfq(id);
          },
          error: (err: unknown) => {
            this.actionKeys.onError(`send:${id}`, err);
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
}
