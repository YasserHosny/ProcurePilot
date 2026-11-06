import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { EMPTY, Observable, Subject, catchError, expand, forkJoin, map, merge, of, reduce, switchMap, tap } from 'rxjs';
import { ApiService } from '../../../core/api/api.service';
import type { Branch, CostCentre, Money, Product, PurchaseRequest, PurchaseRequestLine } from '../../../core/api/models';
import { FormatService } from '../../../core/format/format.service';
import { RequestsApiService } from '../../requests/requests-api';
import { OrganisationApiService } from '../../settings/organisation-api';

import { buildApprovalTimeline } from './approval-timeline';

@Component({
  selector: 'app-approval-detail',
  standalone: true,
  imports: [RouterLink, TranslatePipe, MatProgressSpinnerModule],
  templateUrl: './approval-detail.component.html',
  styleUrl: './approval-detail.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ApprovalDetailComponent {
  private readonly requests = inject(RequestsApiService);
  private readonly organisation = inject(OrganisationApiService);
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  private readonly translate = inject(TranslateService);
  private readonly format = inject(FormatService);
  private readonly reload = new Subject<void>();
  readonly loading = signal(true);
  readonly error = signal<'notFound' | 'error' | null>(null);
  readonly request = signal<PurchaseRequest | null>(null);
  readonly branches = signal<readonly Branch[]>([]);
  readonly costCentres = signal<readonly CostCentre[]>([]);
  readonly products = signal<readonly Product[]>([]);
  readonly timeline = computed(() => buildApprovalTimeline(this.request(), this.unavailable()));

  constructor() {
    this.route.paramMap.pipe(
      switchMap(params => merge(of(undefined), this.reload).pipe(map(() => params.get('requestId') ?? ''))),
      tap(() => { this.loading.set(true); this.error.set(null); this.request.set(null); this.products.set([]); }),
      switchMap(id => this.requests.getRequest(id).pipe(
        switchMap(request => forkJoin({
          request: of(request),
          branches: this.allPages(params => this.organisation.listBranches(params)),
          costCentres: this.allPages(params => this.organisation.listCostCentres(params)),
          products: request.lines.some(line => !line.product_name)
            ? this.allPages(params => this.api.products({...params, status: 'all'})) : of<Product[]>([]),
        })),
        catchError((error: unknown) => {
          this.error.set(error instanceof HttpErrorResponse && [403, 404].includes(error.status) ? 'notFound' : 'error');
          this.loading.set(false);
          return EMPTY;
        }),
      )),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe(result => {
      this.request.set(result.request); this.branches.set(result.branches);
      this.costCentres.set(result.costCentres); this.products.set(result.products); this.loading.set(false);
    });
  }

  private allPages<T>(load: (params: {limit: number; cursor?: string}) => Observable<{items: readonly T[]; next_cursor?: string | null}>): Observable<T[]> {
    return load({limit: 100}).pipe(
      expand(page => page.next_cursor ? load({limit: 100, cursor: page.next_cursor}) : EMPTY),
      reduce((items: T[], page) => [...items, ...page.items], []),
      catchError(() => of<T[]>([])),
    );
  }

  retry(): void { this.reload.next(); }
  unavailable(): string { return this.translate.instant('approvals.detail.unavailable'); }
  requester(request: PurchaseRequest): string { return request.requester_name || request.requester_email || this.unavailable(); }
  assignee(request: PurchaseRequest): string { return request.approval_step?.assigned_name || request.approval_step?.assigned_email || this.unavailable(); }
  decider(request: PurchaseRequest): string { return request.approval_step?.decided_name || request.approval_step?.decided_email || this.unavailable(); }
  branch(id: string): string { return this.branches().find(branch => branch.id === id)?.name ?? this.unavailable(); }
  costCentre(id: string | null | undefined): string { return this.costCentres().find(centre => centre.id === id)?.name ?? this.unavailable(); }
  product(line: PurchaseRequestLine): string { return line.product_name || this.products().find(product => product.id === line.workspace_product_id)?.tenant_name || this.unavailable(); }
  money(value: Money | null | undefined): string { return this.format.formatCurrencyAmount(value, 'en'); }
  number(value: string): string { return this.format.formatNumber(value, {numberingSystem: 'latn', maximumFractionDigits: 6}); }
  date(value: string): string { return this.format.formatDate(value, {dateStyle: 'medium', numberingSystem: 'latn'}); }
  budget(request: PurchaseRequest): string {
    const budget = request.budget_status;
    return budget ? this.translate.instant(`approvals.budgetStatus.${budget.status ?? (budget.exceeds ? 'over' : budget.remaining_amount ? 'within' : 'no_budget')}`) : this.unavailable();
  }
  selfMark(request: PurchaseRequest): string {
    return request.approval_step?.status === 'approved' ? 'requests.approval.selfApproved' : request.approval_step?.status === 'rejected' ? 'requests.approval.selfRejected' : 'requests.approval.selfApprovalPending';
  }
}
