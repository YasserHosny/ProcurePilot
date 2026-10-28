import { Component, OnInit, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { MatCardModule } from '@angular/material/card';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTableModule } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { RfqApi, RfqDetail } from '../rfq-api';
import { FormatService } from '../../../core/format/format.service';
import { ApiService } from '../../../core/api/api.service';
import { SessionService } from '../../../core/auth/session.service';
import { CatalogueConfirmDialogComponent } from '../../catalogue/confirm-dialog/confirm-dialog.component';
import { CompareComponent } from '../compare/compare.component';

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

  readonly rfqId = signal<string>('');
  readonly rfqDetail = signal<RfqDetail | null>(null);
  readonly responseCount = signal<number>(0);
  readonly loading = signal<boolean>(true);
  readonly isNotFound = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly selectedTabIndex = signal<number>(0);
  readonly currentMembershipId = signal<string | null>(null);

  readonly displayedItemColumns = ['product', 'quantity'];
  readonly displayedRecipientColumns = ['supplier', 'contactEmail', 'status', 'sentAt'];

  ngOnInit(): void {
    this.api.members().subscribe(({ items }) => {
      const email = this.session.currentMember()?.email;
      this.currentMembershipId.set(items.find((m) => m.email === email)?.id ?? null);
    });

    this.route.paramMap.subscribe((params) => {
      const id = params.get('id');
      if (id) {
        this.loadRfq(id);
      }
    });

    this.route.queryParamMap.subscribe((queryParams) => {
      const tabParam = queryParams.get('tab');
      if (tabParam && tabParam in TAB_MAP) {
        this.selectedTabIndex.set(TAB_MAP[tabParam]);
      }
    });
  }

  loadRfq(id: string): void {
    this.rfqId.set(id);
    this.loading.set(true);
    this.isNotFound.set(false);
    this.errorMessage.set(null);

    this.rfqApi.getRfq(id).subscribe({
      next: (detail) => {
        this.rfqDetail.set(detail);
        this.loading.set(false);
      },
      error: (err: unknown) => {
        this.loading.set(false);
        if (err instanceof HttpErrorResponse && err.status === 404) {
          this.isNotFound.set(true);
        } else {
          this.errorMessage.set(this.translate.instant('rfq.detail.loadError'));
        }
      },
    });

    this.rfqApi.listResponses(id).subscribe({
      next: (res) => {
        this.responseCount.set(res.items.length);
      },
      error: () => {
        this.responseCount.set(0);
      },
    });
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

  isCreator(): boolean {
    return this.rfqDetail()?.rfq.created_by_membership_id === this.currentMembershipId();
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

    const dialogRef = this.dialog.open(CatalogueConfirmDialogComponent, {
      width: '440px',
      data: {
        titleKey: 'rfq.history.confirmSendTitle',
        messageKey: 'rfq.history.confirmSendMessage',
        messageParams: { count: recipientCount },
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
            const key = err instanceof HttpErrorResponse && err.status === 403 ? 'rfq.creatorOnly' : 'rfq.history.sendError';
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
