import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';

import { SessionService } from '../../../core/auth/session.service';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import {
  NegotiationBrief,
  NegotiationBriefEvidenceRef,
  SupplierRiskApiService,
} from '../supplier-risk-api';

type BriefError = 'load' | 'action';

@Component({
  selector: 'app-brief-detail',
  standalone: true,
  imports: [
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    RouterLink,
    TranslatePipe,
    FormatDatePipe,
  ],
  templateUrl: './brief-detail.component.html',
  styleUrl: './brief-detail.component.scss',
})
export class BriefDetailComponent implements OnInit {
  private readonly api = inject(SupplierRiskApiService);
  private readonly session = inject(SessionService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);

  readonly brief = signal<NegotiationBrief | null>(null);
  readonly isLoading = signal(true);
  readonly isActing = signal(false);
  readonly error = signal<BriefError | null>(null);
  readonly dismissReason = signal('');
  readonly dismissReasonError = signal(false);
  readonly isWriter = computed(() => this.session.hasRole('owner', 'buyer'));
  readonly canAct = computed(() => this.isWriter() && this.brief()?.status === 'prepared');
  readonly isStale = computed(() => {
    const validUntil = this.brief()?.valid_until;
    return validUntil ? Date.parse(validUntil) <= Date.now() : false;
  });

  ngOnInit(): void {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
      const id = params.get('id');
      if (id) this.load(id);
    });
  }

  load(id: string): void {
    this.isLoading.set(true);
    this.error.set(null);
    this.brief.set(null);
    this.api.getBrief(id).subscribe({
      next: (brief) => {
        this.brief.set(brief);
        this.isLoading.set(false);
      },
      error: () => {
        this.error.set('load');
        this.isLoading.set(false);
      },
    });
  }

  acknowledge(): void {
    const current = this.brief();
    if (!current || !this.canAct() || this.isActing()) return;
    this.runAction(this.api.acknowledgeBrief(current.id));
  }

  dismiss(): void {
    const current = this.brief();
    if (!current || !this.canAct() || this.isActing()) return;
    const reason = this.dismissReason().trim();
    if (!reason) {
      this.dismissReasonError.set(true);
      return;
    }
    this.dismissReasonError.set(false);
    this.runAction(this.api.dismissBrief(current.id, reason));
  }

  updateDismissReason(event: Event): void {
    this.dismissReason.set((event.target as HTMLTextAreaElement).value);
    this.dismissReasonError.set(false);
  }

  sourceRoute(ref: NegotiationBriefEvidenceRef): string[] | null {
    if (ref.source_kind === 'purchase_order') return ['/orders', ref.source_id];
    if (ref.source_kind === 'workspace_product') return ['/products', ref.source_id];
    return null;
  }

  percent(value: string | null): string {
    if (value === null) return '-';
    const numeric = Number(value);
    return Number.isFinite(numeric) ? `${(numeric * 100).toFixed(1)}%` : '-';
  }

  private runAction(action: ReturnType<SupplierRiskApiService['acknowledgeBrief']>): void {
    this.error.set(null);
    this.isActing.set(true);
    action.subscribe({
      next: (brief) => {
        this.brief.set(brief);
        this.isActing.set(false);
      },
      error: () => {
        this.error.set('action');
        this.isActing.set(false);
      },
    });
  }
}
