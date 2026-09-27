import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormArray, FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatNativeDateModule } from '@angular/material/core';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ActivatedRoute, Router } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { forkJoin, of, type Observable } from 'rxjs';
import { catchError, finalize, tap } from 'rxjs/operators';

import { ApiService } from '../../../core/api/api.service';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import type {
  ApiError,
  Branch,
  BranchList,
  CostCentre,
  CostCentreList,
  Member,
  PurchaseRequest,
  PurchaseRequestLine,
} from '../../../core/api/models';
import { OrganisationApiService } from '../../settings/organisation-api';
import { RequestsApiService } from '../requests-api';

const I18N = 'requests';

interface LineFormGroup {
  workspace_product_id: FormControl<string>;
  quantity: FormControl<string>;
  note: FormControl<string>;
}

@Component({
  selector: 'app-request-form',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatDatepickerModule,
    MatNativeDateModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    TranslatePipe,
    FormatDatePipe,
  ],
  templateUrl: './request-form.component.html',
  styleUrl: './request-form.component.scss',
})
export class RequestFormComponent implements OnInit {
  private readonly requestsApi = inject(RequestsApiService);
  private readonly organisationApi = inject(OrganisationApiService);
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(false);
  readonly isSaving = signal<boolean>(false);
  readonly isSubmitting = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly branches = signal<Branch[]>([]);
  readonly costCentres = signal<CostCentre[]>([]);
  readonly members = signal<Member[]>([]);
  readonly existingRequest = signal<PurchaseRequest | null>(null);
  readonly isEditMode = signal<boolean>(false);

  readonly memberEmailById = computed<Map<string, string>>(() => {
    const byId = new Map<string, string>();
    for (const member of this.members()) {
      byId.set(member.id, member.email);
    }
    return byId;
  });

  readonly form = new FormGroup({
    branch_id: new FormControl<string>('', { nonNullable: true, validators: [Validators.required] }),
    cost_centre_id: new FormControl<string>('', { nonNullable: true }),
    required_by_date: new FormControl<string>('', {
      nonNullable: true,
      validators: [Validators.required],
    }),
    lines: new FormArray<FormGroup<LineFormGroup>>([]),
  });

  get lines(): FormArray<FormGroup<LineFormGroup>> {
    return this.form.controls.lines;
  }

  ngOnInit(): void {
    this.isLoading.set(true);

    const requestId = this.route.snapshot.paramMap.get('id');
    const isEditMode = requestId !== null;
    if (isEditMode) {
      this.isEditMode.set(true);
      this.loadMembers();
    }

    forkJoin({
      branches: this.loadBranches(),
      costCentres: this.loadCostCentres(),
      request: requestId ? this.loadRequest(requestId) : of(null),
    })
      .pipe(
        finalize(() => {
          this.isLoading.set(false);
          if (!isEditMode) {
            this.addLine();
          }
        }),
      )
      .subscribe({
        error: (err: unknown) => this.handleError(err),
      });
  }

  addLine(): void {
    this.lines.push(
      new FormGroup<LineFormGroup>({
        workspace_product_id: new FormControl<string>('', {
          nonNullable: true,
          validators: [Validators.required],
        }),
        quantity: new FormControl<string>('', {
          nonNullable: true,
          validators: [Validators.required, Validators.pattern(/^\d+(\.\d+)?$/)],
        }),
        note: new FormControl<string>('', { nonNullable: true }),
      }),
    );
  }

  removeLine(index: number): void {
    this.lines.removeAt(index);
  }

  saveDraft(): void {
    if (this.form.invalid || this.lines.length === 0) {
      return;
    }

    this.isSaving.set(true);
    this.errorMessage.set(null);

    const value = this.form.getRawValue();
    const body = {
      branch_id: value.branch_id,
      cost_centre_id: value.cost_centre_id || null,
      required_by_date: value.required_by_date,
      lines: value.lines.map((l) => ({
        workspace_product_id: l.workspace_product_id,
        // The API contract carries quantity as a decimal string (monetary-rule style), while
        // the number input's value accessor stores a JS number — serialise at the boundary.
        quantity: String(l.quantity),
        note: l.note || null,
      })),
    };

    const existing = this.existingRequest();
    const obs = existing
      ? this.requestsApi.updateRequest(existing.id, body)
      : this.requestsApi.createRequest(body);

    obs.subscribe({
      next: (saved) => {
        this.isSaving.set(false);
        this.existingRequest.set(saved);
        this.isEditMode.set(true);
        this.snackBar.open(this.translate.instant(`${I18N}.createSuccess`), undefined, {
          duration: 3500,
        });
        this.router.navigate(['/requests', saved.id]);
      },
      error: (err: unknown) => {
        this.isSaving.set(false);
        this.handleError(err);
      },
    });
  }

  submitRequest(): void {
    const existing = this.existingRequest();
    if (!existing) {
      return;
    }

    this.isSubmitting.set(true);
    this.errorMessage.set(null);

    this.requestsApi.submitRequest(existing.id).subscribe({
      next: () => {
        this.isSubmitting.set(false);
        this.snackBar.open(this.translate.instant(`${I18N}.submitSuccess`), undefined, {
          duration: 3500,
        });
        this.router.navigate(['/requests']);
      },
      error: (err: unknown) => {
        this.isSubmitting.set(false);
        this.handleError(err);
      },
    });
  }

  cancel(): void {
    this.router.navigate(['/requests']);
  }

  formatEstimate(line: PurchaseRequestLine): string {
    if (!line.estimated_unit_price) {
      return this.translate.instant(`${I18N}.form.noEstimateAvailable`);
    }
    return `${line.estimated_unit_price.currency} ${line.estimated_unit_price.amount}`;
  }

  private loadBranches(): Observable<BranchList> {
    return this.organisationApi
      .listBranches({ is_active: true })
      .pipe(tap((res) => this.branches.set([...res.items])));
  }

  private loadCostCentres(): Observable<CostCentreList> {
    return this.organisationApi
      .listCostCentres({ is_archived: false })
      .pipe(tap((res) => this.costCentres.set([...res.items])));
  }

  private loadMembers(): void {
    this.api
      .members()
      .pipe(
        catchError(() =>
          of<{ items: Member[]; next_cursor: string | null }>({
            items: [],
            next_cursor: null,
          }),
        ),
      )
      .subscribe((res) => this.members.set([...res.items]));
  }

  private loadRequest(requestId: string): Observable<PurchaseRequest> {
    return this.requestsApi.getRequest(requestId).pipe(
      tap((req) => {
        this.existingRequest.set(req);
        this.form.patchValue({
          branch_id: req.branch_id,
          cost_centre_id: req.cost_centre_id ?? '',
          required_by_date: req.required_by_date,
        });

        this.lines.clear();
        for (const line of req.lines) {
          const group = new FormGroup<LineFormGroup>({
            workspace_product_id: new FormControl<string>(line.workspace_product_id, {
              nonNullable: true,
              validators: [Validators.required],
            }),
            quantity: new FormControl<string>(line.quantity, {
              nonNullable: true,
              validators: [Validators.required, Validators.pattern(/^\d+(\.\d+)?$/)],
            }),
            note: new FormControl<string>(line.note ?? '', { nonNullable: true }),
          });
          this.lines.push(group);
        }

        if (req.status !== 'draft') {
          this.form.disable();
        }
      }),
    );
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorMessage.set(
        apiError?.message ?? err.message ?? this.translate.instant(`${I18N}.genericError`),
      );
      return;
    }
    this.errorMessage.set(this.translate.instant(`${I18N}.genericError`));
  }
}
