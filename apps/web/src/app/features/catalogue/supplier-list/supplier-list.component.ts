import { HttpErrorResponse } from "@angular/common/http";
import { Component, OnInit, computed, inject, signal } from "@angular/core";
import { FormsModule } from "@angular/forms";
import { MatButtonModule } from "@angular/material/button";
import { MatCardModule } from "@angular/material/card";
import { MatChipsModule } from "@angular/material/chips";
import { MatDialog, MatDialogModule } from "@angular/material/dialog";
import { MatFormFieldModule } from "@angular/material/form-field";
import { MatIconModule } from "@angular/material/icon";
import { MatInputModule } from "@angular/material/input";
import { MatMenuModule } from "@angular/material/menu";
import { MatProgressSpinnerModule } from "@angular/material/progress-spinner";
import { MatSelectModule } from "@angular/material/select";
import { MatSnackBar, MatSnackBarModule } from "@angular/material/snack-bar";
import { MatTableModule } from "@angular/material/table";
import { MatTooltipModule } from "@angular/material/tooltip";
import { RouterLink } from "@angular/router";
import { TranslatePipe, TranslateService } from "@ngx-translate/core";

import { ApiService } from "../../../core/api/api.service";
import type { ApiError, Supplier } from "../../../core/api/models";
import { RoleDirective } from "../../../core/auth/role.directive";
import { SessionService } from "../../../core/auth/session.service";
import { FormatMoneyPipe } from "../../../core/format";
import { CatalogueConfirmDialogComponent } from "../confirm-dialog/confirm-dialog.component";

@Component({
  selector: "app-supplier-list",
  standalone: true,
  imports: [
    FormsModule,
    RouterLink,
    MatCardModule,
    MatTableModule,
    MatButtonModule,
    MatIconModule,
    MatMenuModule,
    MatChipsModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatDialogModule,
    MatTooltipModule,
    TranslatePipe,
    FormatMoneyPipe,
    RoleDirective,
  ],
  templateUrl: "./supplier-list.component.html",
  styleUrl: "./supplier-list.component.scss",
})
export class SupplierListComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(true);
  readonly suppliers = signal<Supplier[]>([]);
  readonly statusFilter = signal<"active" | "preferred" | "blocked" | "archived" | "all">("active");
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);

  readonly isWriter = computed<boolean>(() => this.session.hasRole("owner", "buyer"));

  readonly displayedColumns: readonly string[] = [
    "name",
    "paymentTerms",
    "leadTime",
    "minOrderValue",
    "deliveryFee",
    "status",
    "actions",
  ];

  ngOnInit(): void {
    this.loadSuppliers();
  }

  loadSuppliers(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    const status = this.statusFilter();

    this.api.suppliers({ status }).subscribe({
      next: (res) => {
        this.suppliers.set(res.items);
        this.isLoading.set(false);
      },
      error: (err: unknown) => {
        this.isLoading.set(false);
        this.handleError(err);
      },
    });
  }

  onFilterChange(status: "active" | "preferred" | "blocked" | "archived" | "all"): void {
    this.statusFilter.set(status);
    this.loadSuppliers();
  }

  openArchiveDialog(supplier: Supplier): void {
    const dialogRef = this.dialog.open(CatalogueConfirmDialogComponent, {
      width: "440px",
      data: {
        titleKey: "catalogue.suppliers.archiveDialog.title",
        messageKey: "catalogue.suppliers.archiveDialog.message",
        itemName: supplier.name,
        confirmKey: "catalogue.suppliers.archiveDialog.confirmButton",
        cancelKey: "catalogue.suppliers.archiveDialog.cancelButton",
        isDestructive: true,
      },
    });

    dialogRef.afterClosed().subscribe((confirmed: boolean | undefined) => {
      if (confirmed) {
        this.archiveSupplier(supplier);
      }
    });
  }

  private archiveSupplier(supplier: Supplier): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    this.api.archiveSupplier(supplier.id).subscribe({
      next: () => {
        this.loadSuppliers();
        this.snackBar.open(
          this.translate.instant("catalogue.suppliers.archiveSuccess"),
          undefined,
          { duration: 3500 },
        );
      },
      error: (err: unknown) => {
        this.isLoading.set(false);
        if (err instanceof HttpErrorResponse && err.status === 409) {
          this.errorMessage.set(this.translate.instant("catalogue.suppliers.archiveConflictMessage"));
          return;
        }
        this.handleError(err);
      },
    });
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorTraceId.set(apiError?.trace_id ?? null);
      this.errorMessage.set(
        apiError?.message ??
          err.message ??
          this.translate.instant("catalogue.suppliers.form.genericError"),
      );
      return;
    }
    this.errorMessage.set(this.translate.instant("catalogue.suppliers.form.genericError"));
  }
}
