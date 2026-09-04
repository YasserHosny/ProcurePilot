import { HttpErrorResponse } from "@angular/common/http";
import { Component, OnInit, computed, inject, signal } from "@angular/core";
import { MatButtonModule } from "@angular/material/button";
import { MatCardModule } from "@angular/material/card";
import { MatDialog, MatDialogModule } from "@angular/material/dialog";
import { MatIconModule } from "@angular/material/icon";
import { MatProgressSpinnerModule } from "@angular/material/progress-spinner";
import { MatSnackBar, MatSnackBarModule } from "@angular/material/snack-bar";
import { MatTableModule } from "@angular/material/table";
import { MatTooltipModule } from "@angular/material/tooltip";
import { TranslatePipe, TranslateService } from "@ngx-translate/core";

import type { ApiError, Branch } from "../../../core/api/models";
import { RoleDirective } from "../../../core/auth/role.directive";
import { SessionService } from "../../../core/auth/session.service";
import { OrganisationApiService } from "../organisation-api";
import {
  BranchFormDialogComponent,
  BranchFormDialogData,
} from "./branch-form-dialog/branch-form-dialog.component";
import {
  BranchDependentsConfirmDialogComponent,
  DependentsConfirmDialogData,
} from "./dependents-confirm-dialog/dependents-confirm-dialog.component";

const BRANCHES_I18N = "organisation.branches";

@Component({
  selector: "app-branch-list",
  standalone: true,
  imports: [
    MatCardModule,
    MatTableModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatDialogModule,
    MatTooltipModule,
    TranslatePipe,
    RoleDirective,
  ],
  templateUrl: "./branch-list.component.html",
  styleUrl: "./branch-list.component.scss",
})
export class BranchListComponent implements OnInit {
  private readonly organisationApi = inject(OrganisationApiService);
  private readonly session = inject(SessionService);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(true);
  readonly branches = signal<Branch[]>([]);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);

  readonly isOwner = computed<boolean>(() => this.session.hasRole("owner"));

  readonly displayedColumns = computed<readonly string[]>(() =>
    this.isOwner()
      ? ["name", "address", "region", "status", "actions"]
      : ["name", "address", "region", "status"],
  );

  ngOnInit(): void {
    this.loadBranches();
  }

  loadBranches(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    this.organisationApi.listBranches().subscribe({
      next: (res) => {
        this.branches.set([...res.items]);
        this.isLoading.set(false);
      },
      error: (err: unknown) => {
        this.isLoading.set(false);
        this.handleError(err);
      },
    });
  }

  openCreateDialog(): void {
    const dialogRef = this.dialog.open(BranchFormDialogComponent, {
      width: "480px",
      data: { mode: "create" } satisfies BranchFormDialogData,
    });

    dialogRef.afterClosed().subscribe((result) => {
      if (result) {
        this.loadBranches();
        this.snackBar.open(
          this.translate.instant(`${BRANCHES_I18N}.createSuccess`),
          undefined,
          { duration: 3500 },
        );
      }
    });
  }

  openEditDialog(branch: Branch): void {
    const dialogRef = this.dialog.open(BranchFormDialogComponent, {
      width: "480px",
      data: { mode: "edit", branch } satisfies BranchFormDialogData,
    });

    dialogRef.afterClosed().subscribe((result) => {
      if (result) {
        this.loadBranches();
      }
    });
  }

  deactivateBranch(branch: Branch): void {
    this.organisationApi.updateBranch(branch.id, { is_active: false }).subscribe({
      next: () => this.onDeactivateSuccess(),
      error: (err: unknown) => {
        const dependentCount = this.readDependentCount(err);
        if (dependentCount !== null) {
          this.confirmDeactivateWithDependents(branch, dependentCount);
          return;
        }
        this.handleError(err);
      },
    });
  }

  private confirmDeactivateWithDependents(branch: Branch, dependentCount: number): void {
    const dialogRef = this.dialog.open(BranchDependentsConfirmDialogComponent, {
      width: "440px",
      data: { dependentCount } satisfies DependentsConfirmDialogData,
    });

    dialogRef.afterClosed().subscribe((confirmed: boolean | undefined) => {
      if (!confirmed) {
        return;
      }
      this.organisationApi
        .updateBranch(branch.id, { is_active: false, confirm_dependents: true })
        .subscribe({
          next: () => this.onDeactivateSuccess(),
          error: (err: unknown) => this.handleError(err),
        });
    });
  }

  /**
   * Returns the combined cost-centre + branch-role-assignment count when the API refused the
   * deactivation pending explicit confirmation of dependents; null for any other failure.
   */
  private readDependentCount(err: unknown): number | null {
    if (!(err instanceof HttpErrorResponse) || err.status !== 422) {
      return null;
    }
    const apiError = err.error as ApiError | undefined;
    const details = apiError?.details;
    if (details?.["reason"] !== "dependents_confirmation_required") {
      return null;
    }
    const costCentres =
      typeof details["cost_centre_count"] === "number" ? details["cost_centre_count"] : 0;
    const roleAssignments =
      typeof details["branch_role_assignment_count"] === "number"
        ? details["branch_role_assignment_count"]
        : 0;
    return costCentres + roleAssignments;
  }

  private onDeactivateSuccess(): void {
    this.loadBranches();
    this.snackBar.open(
      this.translate.instant(`${BRANCHES_I18N}.deactivateSuccess`),
      undefined,
      { duration: 3500 },
    );
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorTraceId.set(apiError?.trace_id ?? null);
      this.errorMessage.set(
        apiError?.message ?? err.message ?? this.translate.instant(`${BRANCHES_I18N}.genericError`),
      );
      return;
    }
    this.errorMessage.set(this.translate.instant(`${BRANCHES_I18N}.genericError`));
  }
}
