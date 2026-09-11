import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  OnInit,
  TemplateRef,
  ViewChild,
  computed,
  inject,
  signal,
} from '@angular/core';
import {
  AbstractControl,
  FormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import {
  MatDialog,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { ApiService } from '../../../core/api/api.service';
import type {
  ApprovalDelegation,
  ApprovalDelegationCreate,
  ApprovalDelegationList,
  ApiError,
  Member,
} from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import { ApprovalsApiService } from '../../approvals/approvals-api';

const DELEGATIONS_I18N = 'approvals.delegations';

function dateRangeValidator(group: AbstractControl): ValidationErrors | null {
  const startsOn = group.get('starts_on')?.value as string | null | undefined;
  const endsOn = group.get('ends_on')?.value as string | null | undefined;
  if (!startsOn || !endsOn) {
    return null;
  }
  if (endsOn < startsOn) {
    return { endsOnBeforeStartsOn: true };
  }
  return null;
}

@Component({
  selector: 'app-delegation-list',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    MatCardModule,
    MatTableModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatTooltipModule,
    TranslatePipe,
  ],
  templateUrl: './delegation-list.component.html',
  styleUrl: './delegation-list.component.scss',
})
export class DelegationListComponent implements OnInit {
  private readonly approvalsApi = inject(ApprovalsApiService);
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);
  private readonly fb = inject(FormBuilder);

  @ViewChild('delegationDialog') readonly delegationDialogTemplate!: TemplateRef<unknown>;
  @ViewChild('cancelDialog') readonly cancelDialogTemplate!: TemplateRef<unknown>;

  delegationDialogRef: MatDialogRef<unknown> | null = null;
  cancelDialogRef: MatDialogRef<unknown> | null = null;

  readonly isLoading = signal<boolean>(true);
  readonly delegations = signal<ApprovalDelegation[]>([]);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);

  readonly isSubmitting = signal<boolean>(false);
  readonly dialogErrorMessage = signal<string | null>(null);
  readonly dialogErrorTraceId = signal<string | null>(null);

  readonly isCancelling = signal<boolean>(false);
  readonly cancellingDelegation = signal<ApprovalDelegation | null>(null);
  readonly cancelErrorMessage = signal<string | null>(null);
  readonly cancelErrorTraceId = signal<string | null>(null);

  readonly members = signal<Member[]>([]);

  readonly currentMemberId = computed<string | null>(() => this.session.currentMember()?.id ?? null);

  readonly displayedColumns = computed<readonly string[]>(() => [
    'delegate',
    'startsOn',
    'endsOn',
    'actions',
  ]);

  readonly memberEmailById = computed<Map<string, string>>(() => {
    const byId = new Map<string, string>();
    for (const member of this.members()) {
      byId.set(member.id, member.email);
    }
    return byId;
  });

  readonly availableMembers = computed<Member[]>(() => {
    const selfId = this.currentMemberId();
    if (!selfId) {
      return this.members();
    }
    return this.members().filter((member) => member.id !== selfId);
  });

  readonly form = this.fb.group(
    {
      delegate_membership_id: this.fb.nonNullable.control('', [Validators.required]),
      starts_on: this.fb.nonNullable.control('', [Validators.required]),
      ends_on: this.fb.nonNullable.control('', [Validators.required]),
    },
    { validators: [dateRangeValidator] },
  );

  ngOnInit(): void {
    this.loadDelegations();
    this.loadMembers();
  }

  loadDelegations(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    const membershipId = this.currentMemberId();
    const params = membershipId ? { membership_id: membershipId } : undefined;

    this.approvalsApi.listApprovalDelegations(params).subscribe({
      next: (res: ApprovalDelegationList) => {
        this.delegations.set([...res.items]);
        this.isLoading.set(false);
      },
      error: (err: unknown) => {
        this.isLoading.set(false);
        this.handleError(err);
      },
    });
  }

  delegateLabel(delegation: ApprovalDelegation): string {
    return (
      this.memberEmailById().get(delegation.delegate_membership_id) ??
      delegation.delegate_membership_id
    );
  }

  isMemberInList(id: string): boolean {
    return this.members().some((member) => member.id === id);
  }

  openCreateDialog(): void {
    this.dialogErrorMessage.set(null);
    this.dialogErrorTraceId.set(null);

    this.form.reset({
      delegate_membership_id: '',
      starts_on: '',
      ends_on: '',
    });

    this.delegationDialogRef = this.dialog.open(this.delegationDialogTemplate, {
      width: '500px',
    });
  }

  closeDelegationDialog(): void {
    this.delegationDialogRef?.close();
    this.delegationDialogRef = null;
  }

  saveDelegation(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.isSubmitting.set(true);
    this.dialogErrorMessage.set(null);
    this.dialogErrorTraceId.set(null);

    const raw = this.form.getRawValue();
    const payload: ApprovalDelegationCreate = {
      delegate_membership_id: raw.delegate_membership_id.trim(),
      starts_on: raw.starts_on,
      ends_on: raw.ends_on,
    };

    this.approvalsApi.createApprovalDelegation(payload).subscribe({
      next: () => {
        this.isSubmitting.set(false);
        this.closeDelegationDialog();
        this.loadDelegations();
        this.snackBar.open(
          this.translate.instant(`${DELEGATIONS_I18N}.createSuccess`),
          undefined,
          { duration: 3500 },
        );
      },
      error: (err: unknown) => {
        this.isSubmitting.set(false);
        this.handleDialogError(err);
      },
    });
  }

  openCancelDialog(delegation: ApprovalDelegation): void {
    this.cancellingDelegation.set(delegation);
    this.cancelErrorMessage.set(null);
    this.cancelErrorTraceId.set(null);

    this.cancelDialogRef = this.dialog.open(this.cancelDialogTemplate, {
      width: '440px',
    });
  }

  closeCancelDialog(): void {
    this.cancelDialogRef?.close();
    this.cancelDialogRef = null;
    this.cancellingDelegation.set(null);
  }

  confirmCancel(): void {
    const delegation = this.cancellingDelegation();
    if (!delegation) {
      return;
    }

    this.isCancelling.set(true);
    this.cancelErrorMessage.set(null);
    this.cancelErrorTraceId.set(null);

    this.approvalsApi.cancelApprovalDelegation(delegation.id).subscribe({
      next: () => {
        this.isCancelling.set(false);
        this.closeCancelDialog();
        this.loadDelegations();
        this.snackBar.open(
          this.translate.instant(`${DELEGATIONS_I18N}.cancelSuccess`),
          undefined,
          { duration: 3500 },
        );
      },
      error: (err: unknown) => {
        this.isCancelling.set(false);
        this.handleCancelError(err);
      },
    });
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

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorTraceId.set(apiError?.trace_id ?? null);
      this.errorMessage.set(
        apiError?.message ??
          err.message ??
          this.translate.instant(`${DELEGATIONS_I18N}.genericError`),
      );
      return;
    }
    this.errorMessage.set(this.translate.instant(`${DELEGATIONS_I18N}.genericError`));
  }

  private handleDialogError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.dialogErrorTraceId.set(apiError?.trace_id ?? null);
      this.dialogErrorMessage.set(
        apiError?.message ??
          err.message ??
          this.translate.instant(`${DELEGATIONS_I18N}.genericError`),
      );
      return;
    }
    this.dialogErrorMessage.set(
      this.translate.instant(`${DELEGATIONS_I18N}.genericError`),
    );
  }

  private handleCancelError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.cancelErrorTraceId.set(apiError?.trace_id ?? null);
      this.cancelErrorMessage.set(
        apiError?.message ??
          err.message ??
          this.translate.instant(`${DELEGATIONS_I18N}.genericError`),
      );
      return;
    }
    this.cancelErrorMessage.set(
      this.translate.instant(`${DELEGATIONS_I18N}.genericError`),
    );
  }
}
