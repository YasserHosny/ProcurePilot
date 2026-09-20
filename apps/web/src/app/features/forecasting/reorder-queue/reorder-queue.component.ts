import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { finalize, switchMap } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import type { Branch } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import {
  ForecastingApiService,
  type ReorderProposal,
} from '../forecasting-api';

@Component({
  selector: 'app-reorder-queue',
  standalone: true,
  imports: [
    FormsModule,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSnackBarModule,
    TranslatePipe,
    FormatDatePipe,
  ],
  templateUrl: './reorder-queue.component.html',
  styleUrl: './reorder-queue.component.scss',
})
export class ReorderQueueComponent implements OnInit {
  private readonly forecastingApi = inject(ForecastingApiService);
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly proposals = signal<ReorderProposal[]>([]);
  readonly branches = signal<Branch[]>([]);
  readonly isLoading = signal(false);
  readonly isRecomputing = signal(false);
  readonly preparingIds = signal<Set<string>>(new Set());
  readonly errorMessage = signal<string | null>(null);
  readonly selectedBranchId = signal('');
  readonly requiredByDate = signal(defaultRequiredByDate());
  readonly isWriter = computed(() => this.session.hasRole('owner', 'buyer'));

  ngOnInit(): void {
    this.loadBranches();
    this.loadProposals();
  }

  loadBranches(): void {
    this.api.listBranches({ is_active: true, limit: 100 }).subscribe({
      next: (result) => {
        this.branches.set([...result.items]);
        if (!this.selectedBranchId() && result.items.length > 0) {
          this.selectedBranchId.set(result.items[0].id);
        }
      },
    });
  }

  loadProposals(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.forecastingApi
      .listProposals({ limit: 100 })
      .pipe(finalize(() => this.isLoading.set(false)))
      .subscribe({
        next: (result) => this.proposals.set(result.items),
        error: () => this.errorMessage.set(this.translate.instant('forecasting.errors.load')),
      });
  }

  recompute(): void {
    if (!this.isWriter()) return;
    this.isRecomputing.set(true);
    this.forecastingApi
      .recompute()
      .pipe(
        switchMap(() => this.forecastingApi.listProposals({ limit: 100 })),
        finalize(() => this.isRecomputing.set(false)),
      )
      .subscribe({
        next: (result) => {
          this.proposals.set(result.items);
          this.snackBar.open(this.translate.instant('forecasting.recompute.success'), undefined, {
            duration: 3000,
          });
        },
        error: () =>
          this.snackBar.open(this.translate.instant('forecasting.errors.recompute'), undefined, {
            duration: 3500,
          }),
      });
  }

  prepareRequest(proposal: ReorderProposal): void {
    const branchId = this.selectedBranchId();
    if (!this.isWriter() || !branchId || proposal.status !== 'open' || !proposal.suggested_quantity) {
      return;
    }
    this.preparingIds.update((ids) => new Set(ids).add(proposal.id));
    this.forecastingApi
      .prepareRequest(proposal.id, {
        branch_id: branchId,
        required_by_date: this.requiredByDate(),
      })
      .pipe(
        finalize(() =>
          this.preparingIds.update((ids) => {
            const next = new Set(ids);
            next.delete(proposal.id);
            return next;
          }),
        ),
      )
      .subscribe({
        next: (result) => {
          this.proposals.update((items) =>
            items.map((item) => (item.id === result.proposal.id ? result.proposal : item)),
          );
          this.snackBar.open(this.translate.instant('forecasting.prepare.success'), undefined, {
            duration: 3500,
          });
        },
        error: () =>
          this.snackBar.open(this.translate.instant('forecasting.errors.prepare'), undefined, {
            duration: 3500,
          }),
      });
  }

  isPreparing(proposalId: string): boolean {
    return this.preparingIds().has(proposalId);
  }

  trackById(_index: number, proposal: ReorderProposal): string {
    return proposal.id;
  }
}

function defaultRequiredByDate(): string {
  const date = new Date();
  date.setDate(date.getDate() + 14);
  return date.toISOString().slice(0, 10);
}
