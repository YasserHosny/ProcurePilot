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
import type { ApiError, LimitCheck, Product } from "../../../core/api/models";
import { RoleDirective } from "../../../core/auth/role.directive";
import { SessionService } from "../../../core/auth/session.service";
import { CatalogueConfirmDialogComponent } from "../confirm-dialog/confirm-dialog.component";
import { computeBaseQuantity } from "../normalisation";

@Component({
  selector: "app-product-list",
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
    RoleDirective,
  ],
  templateUrl: "./product-list.component.html",
  styleUrl: "./product-list.component.scss",
})
export class ProductListComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly isLoading = signal<boolean>(true);
  readonly products = signal<Product[]>([]);
  readonly statusFilter = signal<"active" | "archived" | "all">("active");
  readonly searchQuery = signal<string>("");
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);
  readonly planLimitCheck = signal<LimitCheck | null>(null);

  readonly isWriter = computed<boolean>(() => this.session.hasRole("owner", "buyer"));

  readonly displayedColumns: readonly string[] = [
    "name",
    "brand",
    "gtin",
    "pack",
    "normalised",
    "status",
    "actions",
  ];

  ngOnInit(): void {
    this.loadProducts();
  }

  loadProducts(): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    const q = this.searchQuery().trim() || undefined;
    const status = this.statusFilter();

    if (this.api.checkActiveCatalogueProductsLimit) {
      this.api.checkActiveCatalogueProductsLimit().subscribe({
        next: (check) => this.planLimitCheck.set(check),
        error: () => undefined,
      });
    }

    this.api.products({ status, q }).subscribe({
      next: (res) => {
        this.products.set(res.items);
        this.isLoading.set(false);
      },
      error: (err: unknown) => {
        this.isLoading.set(false);
        this.handleError(err);
      },
    });
  }

  onFilterChange(status: "active" | "archived" | "all"): void {
    this.statusFilter.set(status);
    this.loadProducts();
  }

  onSearch(): void {
    this.loadProducts();
  }

  clearSearch(): void {
    this.searchQuery.set("");
    this.loadProducts();
  }

  formatPack(product: Product): string {
    if (!product.pack) return "—";
    return `${product.pack.pack_count} × ${product.pack.unit_size} ${product.base_unit}`;
  }

  formatNormalised(product: Product): string {
    if (!product.pack) return "—";
    const qty =
      product.pack.base_quantity ||
      computeBaseQuantity(product.pack.pack_count, product.pack.unit_size) ||
      "—";
    return `${qty} ${product.base_unit}`;
  }

  openArchiveDialog(product: Product): void {
    const dialogRef = this.dialog.open(CatalogueConfirmDialogComponent, {
      width: "440px",
      data: {
        titleKey: "catalogue.products.archiveDialog.title",
        messageKey: "catalogue.products.archiveDialog.message",
        itemName: product.tenant_name,
        confirmKey: "catalogue.products.archiveDialog.confirmButton",
        cancelKey: "catalogue.products.archiveDialog.cancelButton",
        isDestructive: true,
      },
    });

    dialogRef.afterClosed().subscribe((confirmed: boolean | undefined) => {
      if (confirmed) {
        this.archiveProduct(product);
      }
    });
  }

  private archiveProduct(product: Product): void {
    this.isLoading.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    this.api.archiveProduct(product.id).subscribe({
      next: () => {
        this.loadProducts();
        this.snackBar.open(
          this.translate.instant("catalogue.products.archiveSuccess"),
          undefined,
          { duration: 3500 },
        );
      },
      error: (err: unknown) => {
        this.isLoading.set(false);
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
          this.translate.instant("catalogue.products.form.genericError"),
      );
      return;
    }
    this.errorMessage.set(this.translate.instant("catalogue.products.form.genericError"));
  }
}
