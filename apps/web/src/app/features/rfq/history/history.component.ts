import { Component, OnInit, inject, signal, computed, DestroyRef, ChangeDetectionStrategy } from '@angular/core';
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
  readonly rfqs = signal<RfqSummary[]>([]);
  readonly nextCursor = signal<string | null>(null);
  readonly recipientsCache = signal<Record<string, RecipientsCacheEntry>>({});

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

    this.api.members().subscribe(({ items }) => {
      const email = this.session.currentMember()?.email;
      this.currentMembershipId.set(items.find((member) => member.email === email)?.id ?? null);
    });
    this.loadRfqs();
  }

  loadRfqs(): void {
    this.recipientsCache.set({});
    this.loading.set(true);
    this.rfqApi.listRfqs().subscribe({
      next: (response) => {
        this.rfqs.set(response.items);
        this.nextCursor.set(response.next_cursor);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.snackBar.open(
          this.translate.instant('rfq.history.loadError'),
          this.translate.instant('rfq.history.dismiss'),
          { duration: 5000 },
        );
      }
    });
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

  onRowClick(rfq: RfqSummary): void {
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

  private sendRfq(rfq: RfqSummary): void {
    this.rfqApi.sendRfq(rfq.id).subscribe({
      next: (res) => {
        const total = res.recipients.length;
        const sent = res.recipients.filter((recipient) => recipient.status === 'sent').length;
        if (sent === total && total > 0) this.showSendMessage('rfq.history.sentSuccess', { count: sent });
        else if (sent > 0) this.showSendMessage('rfq.create.sentPartial', { sent, total, failed: total - sent });
        else this.showSendMessage('rfq.create.sentNone');
        this.loadRfqs();
      },
      error: (err: unknown) => {
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
