import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Router } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { MatSnackBar } from '@angular/material/snack-bar';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

import { RfqApi, RfqSummary } from '../rfq-api';
import { FormatDatePipe } from '../../../core/format/date.pipe';

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
    TranslateModule,
    FormatDatePipe,
  ],
  templateUrl: './history.component.html',
  styleUrl: './history.component.scss'
})
export class HistoryComponent implements OnInit {
  private readonly rfqApi = inject(RfqApi);
  private readonly router = inject(Router);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly loading = signal<boolean>(true);
  readonly rfqs = signal<RfqSummary[]>([]);
  readonly nextCursor = signal<string | null>(null);

  readonly displayedColumns = ['status', 'neededBy', 'sentAt', 'recipients', 'responses', 'actions'];

  ngOnInit(): void {
    this.loadRfqs();
  }

  loadRfqs(): void {
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
    if (rfq.status === 'converted' && rfq.converted_purchase_request_id) {
      this.router.navigate(['/requests', rfq.converted_purchase_request_id]);
    } else {
      this.router.navigate(['/rfq/compare', rfq.id]);
    }
  }
}
