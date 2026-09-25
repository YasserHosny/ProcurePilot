import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatTableModule } from '@angular/material/table';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatIconModule } from '@angular/material/icon';
import { TranslateModule, TranslatePipe, TranslateService } from '@ngx-translate/core';

import { ApiService } from '../../../core/api/api.service';
import { RfqApi, RfqResponseComparison } from '../rfq-api';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import type { ApiError, Branch } from '../../../core/api/models';

@Component({
  selector: 'app-rfq-compare',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatCardModule,
    MatButtonModule,
    MatTableModule,
    MatSnackBarModule,
    MatSelectModule,
    MatFormFieldModule,
    MatInputModule,
    MatDatepickerModule,
    MatNativeDateModule,
    MatProgressSpinnerModule,
    MatIconModule,
    TranslateModule,
    TranslatePipe,
    FormatMoneyPipe,
    FormatDatePipe,
  ],
  templateUrl: './compare.component.html',
  styleUrl: './compare.component.scss',
})
export class CompareComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly api = inject(ApiService);
  private readonly rfqApi = inject(RfqApi);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly rfqId = signal<string>('');
  readonly isLoading = signal<boolean>(false);
  readonly responses = signal<RfqResponseComparison[]>([]);
  readonly branches = signal<readonly Branch[]>([]);
  readonly selectedBranchId = signal<string>('');
  readonly requiredByDate = signal<Date>(new Date());
  readonly supplierNames = signal<Record<string, string>>({});
  readonly productNames = signal<Record<string, string>>({});
  readonly errorMessage = signal<string | null>(null);

  readonly displayedColumns = ['product', 'quantity', 'unitPrice', 'totalValue'];

  ngOnInit(): void {
    this.route.paramMap.subscribe((params) => {
      const id = params.get('id');
      if (id) {
        this.rfqId.set(id);
        this.loadData(id);
      }
    });

    this.loadBranches();
  }

  loadData(rfqId: string): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);

    this.rfqApi.listResponses(rfqId).subscribe({
      next: (res) => {
        this.responses.set(res.items);
        this.resolveSuppliers();
        this.resolveProducts();
        this.isLoading.set(false);
      },
      error: (err: unknown) => {
        this.isLoading.set(false);
        this.responses.set([]);
        if (err instanceof HttpErrorResponse) {
          const apiError = err.error as ApiError | undefined;
          this.errorMessage.set(apiError?.message ?? err.message);
        } else {
          this.errorMessage.set(this.translate.instant('rfq.compare.loadError'));
        }
      },
    });
  }

  loadBranches(): void {
    this.api.listBranches({ is_active: true, limit: 100 }).subscribe({
      next: (res) => {
        this.branches.set(res.items);
        if (res.items.length > 0) {
          this.selectedBranchId.set(res.items[0].id);
        }
      },
      error: () => {
        // Soft fail
      },
    });
  }

  resolveSuppliers(): void {
    this.api.suppliers({ limit: 100 }).subscribe({
      next: (res) => {
        const names: Record<string, string> = { ...this.supplierNames() };
        for (const s of res.items) {
          names[s.id] = s.name;
        }
        this.supplierNames.set(names);
      }
    });
  }

  resolveProducts(): void {
    this.api.products({ limit: 100 }).subscribe({
      next: (res) => {
        const names: Record<string, string> = { ...this.productNames() };
        for (const p of res.items) {
          names[p.id] = p.tenant_name;
        }
        this.productNames.set(names);
      }
    });
  }

  isEligible(response: RfqResponseComparison): boolean {
    return response.lines.every(l => !l.pending_match);
  }

  prepareRequest(response: RfqResponseComparison): void {
    if (!this.isEligible(response)) {
      this.snackBar.open(this.translate.instant('rfq.compare.cannotPreparePending'), 'OK', { duration: 3000 });
      return;
    }

    const payload = {
      rfq_response_id: response.id,
      branch_id: this.selectedBranchId(),
      required_by_date: this.requiredByDate().toISOString().split('T')[0],
    };

    this.rfqApi.prepareRequest(this.rfqId(), payload).subscribe({
      next: (res) => {
        const snackRef = this.snackBar.open(
          this.translate.instant('rfq.compare.prepareSuccess'),
          this.translate.instant('rfq.compare.viewRequest'),
          { duration: 5000 }
        );
        snackRef.onAction().subscribe(() => {
          this.router.navigate(['/requests', res.purchase_request_id]);
        });
      },
      error: (err: unknown) => {
        if (err instanceof HttpErrorResponse) {
          const apiError = err.error as ApiError | undefined;
          this.snackBar.open(apiError?.message ?? this.translate.instant('rfq.compare.prepareError'), 'OK', { duration: 5000 });
        } else {
          this.snackBar.open(this.translate.instant('rfq.compare.prepareError'), 'OK', { duration: 5000 });
        }
      }
    });
  }
}
