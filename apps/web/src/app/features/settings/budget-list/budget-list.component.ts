import { HttpErrorResponse } from "@angular/common/http";
import { Component, OnInit, computed, inject, signal } from "@angular/core";
import { MatButtonModule } from "@angular/material/button";
import { MatCardModule } from "@angular/material/card";
import { MatDialog, MatDialogModule } from "@angular/material/dialog";
import { MatIconModule } from "@angular/material/icon";
import { MatProgressSpinnerModule } from "@angular/material/progress-spinner";
import { MatSnackBar, MatSnackBarModule } from "@angular/material/snack-bar";
import { MatTableModule } from "@angular/material/table";
import { TranslatePipe, TranslateService } from "@ngx-translate/core";
import { of } from "rxjs";
import { catchError } from "rxjs/operators";

import type {
  ApiError,
  Branch,
  BranchList,
  Budget,
  BudgetCreated,
  CostCentre,
  CostCentreList,
} from "../../../core/api/models";
import { FormatMoneyPipe } from "../../../core/format";
import { RoleDirective } from "../../../core/auth/role.directive";
import { OrganisationApiService } from "../organisation-api";
import { BudgetFormDialogComponent } from "./budget-form-dialog/budget-form-dialog.component";

const BUDGETS_I18N = "organisation.budgets";

@Component({
  selector: "app-budget-list",
  standalone: true,
  imports: [
    MatCardModule,
    MatTableModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatDialogModule,
    TranslatePipe,
    RoleDirective,
    FormatMoneyPipe,
  ],
  templateUrl: "./budget-list.component.html",
  styleUrl: "./budget-list.component.scss",
})
export class BudgetListComponent implements OnInit {
  private readonly organisationApi = inject(OrganisationApiService);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(true);
  readonly budgets = signal<Budget[]>([]);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);

  /**
   * FR-005: an overlapping budget is still saved. This flag only surfaces the API's
   * informational overlap_warning after a create; it never blocks or errors.
   */
  readonly overlapWarningVisible = signal<boolean>(false);

  /** Display-only lookups for the "applies to" column; absence degrades to raw IDs. */
  private readonly branches = signal<Branch[]>([]);
  private readonly costCentres = signal<CostCentre[]>([]);

  /** Budgets have no row actions in this chunk (no edit/archive), so no owner-drop trick. */
  readonly displayedColumns: readonly string[] = [
    "amount",
    "currency",
    "period",
    "scope",
    "scopeTarget",
  ];

  readonly branchNameById = computed<Map<string, string>>(() => {
    const byId = new Map<string, string>();
    for (const branch of this.branches()) {
      byId.set(branch.id, branch.name);
    }
    return byId;
  });

  readonly costCentreNameById = computed<Map<string, string>>(() => {
    const byId = new Map<string, string>();
    for (const costCentre of this.costCentres()) {
      byId.set(costCentre.id, costCentre.name);
    }
    return byId;
  });

  ngOnInit(): void {
    this.loadBudgets();
    this.loadReferenceData();
  }

  loadBudgets(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);
    this.loadReferenceData();

    this.organisationApi.listBudgets().subscribe({
      next: (res) => {
        this.budgets.set([...res.items]);
        this.isLoading.set(false);
      },
      error: (err: unknown) => {
        this.isLoading.set(false);
        this.handleError(err);
      },
    });
  }

  scopeTargetLabel(budget: Budget): string {
    if (budget.scope === "branch" && budget.branch_id) {
      return this.branchNameById().get(budget.branch_id) ?? budget.branch_id;
    }
    if (budget.scope === "cost_centre" && budget.cost_centre_id) {
      return this.costCentreNameById().get(budget.cost_centre_id) ?? budget.cost_centre_id;
    }
    // Organisation-scope budgets have no single target row to name.
    return "—";
  }

  openCreateDialog(): void {
    const dialogRef = this.dialog.open(BudgetFormDialogComponent, {
      width: "480px",
    });

    dialogRef.afterClosed().subscribe((result: BudgetCreated | boolean | undefined) => {
      if (result) {
        this.overlapWarningVisible.set(
          (result as BudgetCreated).overlap_warning === true,
        );
        this.loadBudgets();
        this.snackBar.open(
          this.translate.instant(`${BUDGETS_I18N}.createSuccess`),
          undefined,
          { duration: 3500 },
        );
      }
    });
  }

  /** Branches and cost centres feed the "applies to" column only; fail soft to raw IDs. */
  loadReferenceData(): void {
    this.organisationApi
      .listBranches()
      .pipe(catchError(() => of<BranchList>({ items: [], next_cursor: null })))
      .subscribe((res) => this.branches.set([...res.items]));

    this.organisationApi
      .listCostCentres()
      .pipe(catchError(() => of<CostCentreList>({ items: [], next_cursor: null })))
      .subscribe((res) => this.costCentres.set([...res.items]));
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorTraceId.set(apiError?.trace_id ?? null);
      this.errorMessage.set(
        apiError?.message ??
          err.message ??
          this.translate.instant(`${BUDGETS_I18N}.genericError`),
      );
      return;
    }
    this.errorMessage.set(this.translate.instant(`${BUDGETS_I18N}.genericError`));
  }
}
