import { RfqActionKeys } from '../rfq-api';
import { Component, OnInit, inject, signal, computed, DestroyRef, ChangeDetectionStrategy } from '@angular/core';
import { BidiModule } from '@angular/cdk/bidi';
import { A11yModule } from '@angular/cdk/a11y';
import { OverlayModule, ConnectedPosition } from '@angular/cdk/overlay';
import { BreakpointObserver } from '@angular/cdk/layout';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { HttpErrorResponse } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { RouterModule, Router } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { MatMenuModule } from '@angular/material/menu';
import { MatSnackBar } from '@angular/material/snack-bar';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { RfqApi, RfqRecipient, RfqSummary } from '../rfq-api';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatService } from '../../../core/format/format.service';
import { parseIsoDateLocal } from '../../../core/format/iso-date';
import { RoleDirective } from '../../../core/auth/role.directive';
import { CatalogueConfirmDialogComponent } from '../../catalogue/confirm-dialog/confirm-dialog.component';
import { ApiService } from '../../../core/api/api.service';
import { SessionService } from '../../../core/auth/session.service';

export function isDateInPast(date: Date | string | null | undefined): boolean {
  if (!date) return false;
  const d = typeof date === 'string' ? parseIsoDateLocal(date) : date;
  if (!d || isNaN(d.getTime())) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  return target.getTime() < today.getTime();
}

export interface RecipientsCacheEntry {
  loading: boolean;
  error: boolean;
  recipients?: RfqRecipient[];
}

@Component({
  selector: 'app-rfq-history',
  standalone: true,
  imports: [
    CommonModule,
    A11yModule,
    BidiModule,
    OverlayModule,
    RouterModule,
    MatCardModule,
    MatTableModule,
    MatProgressSpinnerModule,
    MatIconModule,
    MatChipsModule,
    MatButtonModule,
    MatDialogModule,
    MatMenuModule,
    TranslatePipe,
    FormatDatePipe,
    RoleDirective,
  ],
  templateUrl: './history.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './history.component.scss'
})
export class HistoryComponent implements OnInit {
  private readonly actionKeys = new RfqActionKeys();
  private readonly rfqApi = inject(RfqApi);
  private readonly router = inject(Router);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly formatService = inject(FormatService);
  private readonly breakpoint = inject(BreakpointObserver);
  private readonly destroyRef = inject(DestroyRef);

  readonly currentMembershipId = signal<string | null>(null);

  readonly isBelow1200 = signal(false);
  readonly isBelow768 = signal(false);

  readonly displayedColumns = computed(() => {
    if (this.isBelow768()) {
      return ['status', 'neededBy', 'actions'];
    }
    if (this.isBelow1200()) {
      return ['status', 'neededBy', 'sentAt', 'actions'];
    }
    return ['status', 'neededBy', 'sentAt', 'recipients', 'responses', 'actions'];
  });

  readonly showCountsInMenu = computed(() => this.isBelow1200());

  readonly loading = signal<boolean>(true);
  readonly loadError = signal<boolean>(false);
  readonly loadingMore = signal<boolean>(false);
  readonly loadMoreError = signal<boolean>(false);
  readonly draftActionsUnavailable = signal<boolean>(false);
  readonly rfqs = signal<RfqSummary[]>([]);
  readonly nextCursor = signal<string | null>(null);
  private listGeneration = 0;
  readonly recipientsCache = signal<Record<string, RecipientsCacheEntry>>({});

  readonly openRecipientsId = signal<string | null>(null);
  private recipientsTrigger: HTMLButtonElement | null = null;
  readonly recipientsPositions: ConnectedPosition[] = [
    { originX: 'end', originY: 'bottom', overlayX: 'end', overlayY: 'top', offsetY: 8 },
    { originX: 'end', originY: 'top', overlayX: 'end', overlayY: 'bottom', offsetY: -8 },
  ];

  get recipientsDirection(): 'rtl' | 'ltr' {
    return (this.translate.getCurrentLang() || this.session.activeLocale()) === 'ar' ? 'rtl' : 'ltr';
  }

  toggleRecipients(rfq: RfqSummary, trigger: HTMLButtonElement): void {
    if (this.openRecipientsId() === rfq.id) {
      this.closeRecipients();
      return;
    }
    this.recipientsTrigger = trigger;
    trigger.focus();
    this.openRecipientsId.set(rfq.id);
    this.loadRecipients(rfq.id);
  }

  closeRecipients(rfqId = this.openRecipientsId()): void {
    // A previous row can detach after another disclosure has opened.
    if (rfqId !== this.openRecipientsId()) return;
    this.openRecipientsId.set(null);
    this.recipientsTrigger?.focus();
    this.recipientsTrigger = null;
  }

  onRecipientsKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      this.closeRecipients();
    }
  }

  readonly timeFormatOptions: Intl.DateTimeFormatOptions = { timeStyle: 'short' };

  ngOnInit(): void {
    this.breakpoint
      .observe('(max-width: 1199.98px)')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((res) => {
        this.isBelow1200.set(res.matches);
      });

    this.breakpoint
      .observe('(max-width: 767.98px)')
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((res) => {
        this.isBelow768.set(res.matches);
      });

    this.api.members().subscribe({
      next: ({ items }) => {
        const email = this.session.currentMember()?.email;
        this.currentMembershipId.set(items.find((member) => member.email === email)?.id ?? null);
      },
      error: () => {
        const fallbackId = this.session.currentMember()?.membership_id;
        if (fallbackId) {
          this.currentMembershipId.set(fallbackId);
        } else {
          this.currentMembershipId.set(null);
          this.draftActionsUnavailable.set(true);
        }
      },
    });
    this.loadRfqs();
  }

  loadRfqs(): void {
    const generation = ++this.listGeneration;
    this.recipientsCache.set({});
    this.loading.set(true);
    this.loadError.set(false);
    this.loadMoreError.set(false);
    this.loadingMore.set(false);
    this.rfqApi.listRfqs().subscribe({
      next: (response) => {
        if (generation !== this.listGeneration) {
          return;
        }
        this.rfqs.set(response.items);
        this.nextCursor.set(response.next_cursor);
        this.loading.set(false);
      },
      error: () => {
        if (generation !== this.listGeneration) {
          return;
        }
        this.loading.set(false);
        this.loadError.set(true);
      },
    });
  }

  loadMore(): void {
    const cursor = this.nextCursor();
    if (this.loadingMore() || !cursor) {
      return;
    }

    const generation = this.listGeneration;
    this.loadingMore.set(true);
    this.loadMoreError.set(false);
    this.rfqApi.listRfqs(undefined, cursor).subscribe({
      next: (response) => {
        if (generation !== this.listGeneration) {
          return;
        }
        const current = this.rfqs();
        const existingIds = new Set(current.map((item) => item.id));
        const uniqueItems = response.items.filter((item) => !existingIds.has(item.id));
        this.rfqs.set([...current, ...uniqueItems]);
        this.nextCursor.set(response.next_cursor);
        this.loadingMore.set(false);
      },
      error: () => {
        if (generation !== this.listGeneration) {
          return;
        }
        this.loadingMore.set(false);
        this.loadMoreError.set(true);
      },
    });
  }

  showingRfqsText(): string {
    const count = this.rfqs().length;
    const locale = this.translate.getCurrentLang() || this.session.activeLocale?.() || this.translate.getFallbackLang() || 'en';
    const category = new Intl.PluralRules(locale).select(count);
    const key = `rfq.history.showingCount.${category}`;
    const formatted = this.formatService.formatNumber(count);
    const translated = this.translate.instant(key, { count: formatted });
    if (translated && translated !== key) {
      return translated;
    }
    return this.translate.instant('rfq.history.showingRfqs', { count: formatted });
  }

  getRowAccessibleName(rfq: RfqSummary): string {
    const statusKey = `rfq.history.status_${rfq.status}`;
    const statusText = this.translate.instant(statusKey);
    const dateText = this.formatService.formatDate(rfq.needed_by_date);
    return this.translate.instant('rfq.history.openRfqAriaLabel', {
      status: statusText,
      date: dateText,
    });
  }

  getRecipientsAriaLabel(count: number): string {
    const locale = this.translate.getCurrentLang() || this.session.activeLocale?.() || this.translate.getFallbackLang() || 'en';
    const category = new Intl.PluralRules(locale).select(count);
    const key = `rfq.history.recipientsAriaLabel.${category}`;
    const rawCount = String(count);
    const translated = this.translate.instant(key, { count: rawCount });
    if (translated && translated !== key) {
      return translated;
    }
    return this.translate.instant('rfq.history.recipientsAriaLabelFallback', { count: rawCount });
  }

  getResponsesAriaLabel(count: number): string {
    const locale = this.translate.getCurrentLang() || this.session.activeLocale?.() || this.translate.getFallbackLang() || 'en';
    const category = new Intl.PluralRules(locale).select(count);
    const key = `rfq.history.responsesAriaLabel.${category}`;
    const rawCount = String(count);
    const translated = this.translate.instant(key, { count: rawCount });
    if (translated && translated !== key) {
      return translated;
    }
    return this.translate.instant('rfq.history.responsesAriaLabelFallback', { count: rawCount });
  }

  loadRecipients(rfqId: string): void {
    const existing = this.recipientsCache()[rfqId];
    if (existing?.loading || existing?.recipients) {
      return;
    }

    this.recipientsCache.update((cache) => ({
      ...cache,
      [rfqId]: { loading: true, error: false },
    }));

    this.rfqApi.getRfq(rfqId).subscribe({
      next: (detail) => {
        this.recipientsCache.update((cache) => ({
          ...cache,
          [rfqId]: { loading: false, error: false, recipients: detail.recipients },
        }));
      },
      error: () => {
        this.recipientsCache.update((cache) => ({
          ...cache,
          [rfqId]: { loading: false, error: true },
        }));
      },
    });
  }

  getStatusClass(status: string): string {
    switch (status) {
      case 'draft': return 'status-draft';
      case 'sent': return 'status-sent';
      case 'responded': return 'status-responded';
      case 'expired': return 'status-expired';
      case 'converted': return 'status-converted';
      default: return '';
    }
  }

  onRowClick(rfq: RfqSummary, event?: Event): void {
    event?.stopPropagation();
    if (rfq.status === 'draft') {
      this.router.navigate(this.isCreator(rfq)
        ? ['/rfq', rfq.id, 'edit'] : ['/rfq', rfq.id]);
    } else if (rfq.status === 'converted') {
      const ids = rfq.converted_purchase_request_ids;
      if (ids && ids.length > 1) {
        this.router.navigate(['/rfq', rfq.id]);
      } else {
        const singleId = ids && ids.length === 1 ? ids[0] : rfq.converted_purchase_request_id;
        if (singleId) {
          this.router.navigate(['/requests', singleId]);
        } else {
          this.router.navigate(['/rfq', rfq.id]);
        }
      }
    } else {
      this.router.navigate(['/rfq', rfq.id]);
    }
  }

  onEditDraft(rfq: RfqSummary, event?: Event): void {
    event?.stopPropagation();
    if (!this.isCreator(rfq)) return;
    this.router.navigate(['/rfq', rfq.id, 'edit']);
  }

  onSendDraft(rfq: RfqSummary, event?: Event): void {
    event?.stopPropagation();
    if (!this.isCreator(rfq)) return;

    if (isDateInPast(rfq.needed_by_date)) {
      const dialogRef = this.dialog.open(CatalogueConfirmDialogComponent, {
        width: '440px',
        data: {
          titleKey: 'rfq.history.neededByPassedTitle',
          messageKey: 'rfq.history.neededByPassedMessage',
          confirmKey: 'rfq.history.neededByPassedConfirm',
          cancelKey: 'rfq.history.neededByPassedCancel',
          isDestructive: false,
        },
      });

      dialogRef.afterClosed().subscribe((confirmed: boolean | undefined) => {
        if (confirmed) {
          this.router.navigate(['/rfq', rfq.id, 'edit']);
        }
      });
      return;
    }

    const formattedDate = this.formatService.formatDate(rfq.needed_by_date);
    const dialogRef = this.dialog.open(CatalogueConfirmDialogComponent, {
      width: '440px',
      data: {
        titleKey: 'rfq.history.confirmSendTitle',
        messageKey: 'rfq.history.confirmSendMessage',
        messageParams: { count: rfq.recipient_count, date: formattedDate },
        date: formattedDate,
        confirmKey: 'rfq.history.confirmSendButton',
        cancelKey: 'rfq.history.cancelSendButton',
        isDestructive: false,
      },
    });

    dialogRef.afterClosed().subscribe((confirmed: boolean | undefined) => {
      if (confirmed) {
        this.sendRfq(rfq);
      }
    });
  }

  private readonly sendingIds = new Set<string>();

  private sendRfq(rfq: RfqSummary): void {
    if (this.sendingIds.has(rfq.id)) return;
    this.sendingIds.add(rfq.id);
    const action = `send:${rfq.id}`;
    this.rfqApi.sendRfq(rfq.id, this.actionKeys.get(action)).subscribe({
      next: (res) => {
        this.sendingIds.delete(rfq.id);
        this.actionKeys.clear(action);
        const total = res.recipients.length;
        const sent = res.recipients.filter((recipient) => recipient.status === 'sent').length;
        if (sent === total && total > 0) this.showSendMessage('rfq.history.sentSuccess', { count: sent });
        else if (sent > 0) this.showSendMessage('rfq.create.sentPartial', { sent, total, failed: total - sent });
        else this.showSendMessage('rfq.create.sentNone');
        this.loadRfqs();
      },
      error: (err: unknown) => {
        this.sendingIds.delete(rfq.id);
        this.actionKeys.onError(action, err);
        const key = err instanceof HttpErrorResponse && err.status === 403 ? 'rfq.creatorOnly' : 'rfq.history.sendError';
        this.showSendMessage(key);
      },
    });
  }

  isCreator(rfq: RfqSummary): boolean { return rfq.created_by_membership_id === this.currentMembershipId(); }

  private showSendMessage(key: string, params?: Record<string, number>): void {
    this.snackBar.open(this.translate.instant(key, params), this.translate.instant('rfq.history.dismiss'), { duration: 5000 });
  }
}
