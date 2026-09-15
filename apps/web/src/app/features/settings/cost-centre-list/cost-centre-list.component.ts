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
import { of } from "rxjs";
import { catchError } from "rxjs/operators";

import type {
  ApiError,
  Branch,
  BranchList,
  CostCentre,
  Member,
  OrphanReason,
} from "../../../core/api/models";
import { ApiService } from "../../../core/api/api.service";
import { RoleDirective } from "../../../core/auth/role.directive";
import { SessionService } from "../../../core/auth/session.service";
import {
  CatalogueConfirmDialogComponent,
  ConfirmDialogData,
} from "../../catalogue/confirm-dialog/confirm-dialog.component";
import { OrganisationApiService } from "../organisation-api";
import {
  CostCentreFormDialogComponent,
  CostCentreFormDialogData,
} from "./cost-centre-form-dialog/cost-centre-form-dialog.component";

const COST_CENTRES_I18N = "organisation.costCentres";

@Component({
  selector: "app-cost-centre-list",
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
  templateUrl: "./cost-centre-list.component.html",
  styleUrl: "./cost-centre-list.component.scss",
})
export class CostCentreListComponent implements OnInit {
  private readonly organisationApi = inject(OrganisationApiService);
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(true);
  readonly costCentres = signal<CostCentre[]>([]);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);

  private readonly members = signal<Member[]>([]);
  private readonly branches = signal<Branch[]>([]);

  readonly isOwner = computed<boolean>(() => this.session.hasRole("owner"));

  readonly displayedColumns = computed<readonly string[]>(() =>
    this.isOwner()
      ? ["name", "code", "budgetOwner", "branch", "status", "actions"]
      : ["name", "code", "budgetOwner", "branch", "status"],
  );

  readonly memberEmailById = computed<Map<string, string>>(() => {
    const byId = new Map<string, string>();
    for (const member of this.members()) {
      byId.set(member.id, member.email);
    }
    return byId;
  });

  readonly branchNameById = computed<Map<string, string>>(() => {
    const byId = new Map<string, string>();
    for (const branch of this.branches()) {
      byId.set(branch.id, branch.name);
    }
    return byId;
  });

  ngOnInit(): void {
    this.loadCostCentres();
    this.loadReferenceData();
  }

  loadCostCentres(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);
    this.loadReferenceData();

    this.organisationApi.listCostCentres().subscribe({
      next: (res) => {
        this.costCentres.set([...res.items]);
        this.isLoading.set(false);
      },
      error: (err: unknown) => {
        this.isLoading.set(false);
        this.handleError(err);
      },
    });
  }

  budgetOwnerLabel(costCentre: CostCentre): string {
    const membershipId = costCentre.budget_owner_membership_id;
    if (!membershipId) {
      return "—";
    }
    return this.memberEmailById().get(membershipId) ?? membershipId;
  }

  orphanReasonKey(costCentre: CostCentre): string | null {
    if (!costCentre.is_orphaned) {
      return null;
    }
    const reason: OrphanReason | null | undefined = costCentre.orphan_reason;
    if (reason === "branch_deactivated" || reason === "owner_removed") {
      return `${COST_CENTRES_I18N}.orphanReasons.${reason}`;
    }
    return null;
  }

  openCreateDialog(): void {
    const dialogRef = this.dialog.open(CostCentreFormDialogComponent, {
      width: "480px",
      data: { mode: "create" } satisfies CostCentreFormDialogData,
    });

    dialogRef.afterClosed().subscribe((result) => {
      if (result) {
        this.loadCostCentres();
        this.snackBar.open(
          this.translate.instant(`${COST_CENTRES_I18N}.form.createSuccess`),
          undefined,
          { duration: 3500 },
        );
      }
    });
  }

  openEditDialog(costCentre: CostCentre): void {
    const dialogRef = this.dialog.open(CostCentreFormDialogComponent, {
      width: "480px",
      data: { mode: "edit", costCentre } satisfies CostCentreFormDialogData,
    });

    dialogRef.afterClosed().subscribe((result) => {
      if (result) {
        this.loadCostCentres();
      }
    });
  }

  openArchiveDialog(costCentre: CostCentre): void {
    const dialogRef = this.dialog.open(CatalogueConfirmDialogComponent, {
      width: "440px",
      data: {
        titleKey: `${COST_CENTRES_I18N}.archiveDialog.title`,
        messageKey: `${COST_CENTRES_I18N}.archiveDialog.message`,
        itemName: costCentre.name,
        confirmKey: `${COST_CENTRES_I18N}.archiveDialog.confirmButton`,
        cancelKey: `${COST_CENTRES_I18N}.archiveDialog.cancelButton`,
        isDestructive: true,
      } satisfies ConfirmDialogData,
    });

    dialogRef.afterClosed().subscribe((confirmed: boolean | undefined) => {
      if (confirmed) {
        this.archiveCostCentre(costCentre);
      }
    });
  }

  private archiveCostCentre(costCentre: CostCentre): void {
    this.organisationApi.updateCostCentre(costCentre.id, { is_archived: true }).subscribe({
      next: () => this.onArchiveSuccess(),
      error: (err: unknown) => this.handleError(err),
    });
  }

  private onArchiveSuccess(): void {
    this.loadCostCentres();
    this.snackBar.open(
      this.translate.instant(`${COST_CENTRES_I18N}.archiveSuccess`),
      undefined,
      { duration: 3500 },
    );
  }

  /** Members and branches are display-only lookups; their absence degrades to raw IDs. */
  private loadReferenceData(): void {
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

    this.organisationApi
      .listBranches()
      .pipe(catchError(() => of<BranchList>({ items: [], next_cursor: null })))
      .subscribe((res) => this.branches.set([...res.items]));
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorTraceId.set(apiError?.trace_id ?? null);
      this.errorMessage.set(
        apiError?.message ??
          err.message ??
          this.translate.instant(`${COST_CENTRES_I18N}.genericError`),
      );
      return;
    }
    this.errorMessage.set(this.translate.instant(`${COST_CENTRES_I18N}.genericError`));
  }
}
