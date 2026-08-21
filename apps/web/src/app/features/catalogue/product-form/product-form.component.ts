import { HttpErrorResponse } from "@angular/common/http";
import { Component, OnInit, computed, inject, signal } from "@angular/core";
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from "@angular/forms";
import { MatButtonModule } from "@angular/material/button";
import { MatCardModule } from "@angular/material/card";
import { MatDividerModule } from "@angular/material/divider";
import { MatFormFieldModule } from "@angular/material/form-field";
import { MatIconModule } from "@angular/material/icon";
import { MatInputModule } from "@angular/material/input";
import { MatProgressSpinnerModule } from "@angular/material/progress-spinner";
import { MatSelectModule } from "@angular/material/select";
import { MatSnackBar, MatSnackBarModule } from "@angular/material/snack-bar";
import { ActivatedRoute, Router, RouterLink } from "@angular/router";
import { TranslatePipe, TranslateService } from "@ngx-translate/core";

import { ApiService } from "../../../core/api/api.service";
import type { ApiError, BaseUnit, LimitCheck, Product, ProductCreate, ProductUpdate, Supplier } from "../../../core/api/models";
import { SessionService } from "../../../core/auth/session.service";
import { I18nService } from "../../../core/i18n/i18n.service";
import { computeBaseQuantity } from "../normalisation";

@Component({
  selector: "app-product-form",
  standalone: true,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    MatIconModule,
    MatDividerModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    TranslatePipe,
  ],
  templateUrl: "./product-form.component.html",
  styleUrl: "./product-form.component.scss",
})
export class ProductFormComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);
  readonly i18n = inject(I18nService);

  readonly isEditMode = signal<boolean>(false);
  readonly productId = signal<string | null>(null);
  readonly isLoading = signal<boolean>(true);
  readonly isSaving = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);
  readonly planLimitExceeded = signal<boolean>(false);
  readonly planLimitCheck = signal<LimitCheck | null>(null);

  readonly isWriter = computed<boolean>(() => this.session.hasRole("owner", "buyer"));

  readonly baseUnits = signal<BaseUnit[]>([]);
  readonly suppliers = signal<Supplier[]>([]);

  readonly livePackCount = signal<number | null>(1);
  readonly liveUnitSize = signal<string>("");
  readonly liveBaseUnit = signal<string>("");

  readonly liveNormalisedQuantity = computed<string | null>(() => {
    const count = this.livePackCount();
    const size = this.liveUnitSize();
    return computeBaseQuantity(count, size);
  });

  readonly form: FormGroup = this.fb.group({
    tenant_name: ["", [Validators.required, Validators.maxLength(200)]],
    brand: [""],
    canonical_name: [""],
    variant: [""],
    gtin: ["", [Validators.pattern(/^(\d{8}|\d{12}|\d{13}|\d{14})?$/)]],
    base_unit: ["", [Validators.required]],
    pack_count: [1, [Validators.required, Validators.min(1)]],
    unit_size: ["", [Validators.required, Validators.pattern(/^\d+(\.\d+)?$/)]],
    preferred_supplier_id: [null],
  });

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get("id");
    if (id && id !== "new") {
      this.isEditMode.set(true);
      this.productId.set(id);
    }

    this.form.valueChanges.subscribe((vals) => {
      this.livePackCount.set(vals.pack_count ? Number(vals.pack_count) : null);
      this.liveUnitSize.set(vals.unit_size ? String(vals.unit_size) : "");
      this.liveBaseUnit.set(vals.base_unit ? String(vals.base_unit) : "");
    });

    if (!this.isEditMode() && this.api.checkActiveCatalogueProductsLimit) {
      this.api.checkActiveCatalogueProductsLimit().subscribe({
        next: (check) => {
          this.planLimitCheck.set(check);
          if (!check.allowed || (check.limit !== null && check.used >= check.limit)) {
            this.planLimitExceeded.set(true);
          }
        },
        error: () => undefined,
      });
    }

    this.loadReferenceData();
  }

  private loadReferenceData(): void {
    this.isLoading.set(true);
    this.api.baseUnits().subscribe({
      next: (res) => {
        this.baseUnits.set(res.items);
        this.loadSuppliers();
      },
      error: () => {
        // Fallback default units if reference endpoint unavailable
        this.baseUnits.set([
          { code: "litre", label_en: "Litre (L)", label_ar: "لتر (L)", dimension: "volume" },
          { code: "millilitre", label_en: "Millilitre (ml)", label_ar: "مليلتر (ml)", dimension: "volume" },
          { code: "kilogram", label_en: "Kilogram (kg)", label_ar: "كيلوغرام (kg)", dimension: "mass" },
          { code: "gram", label_en: "Gram (g)", label_ar: "غرام (g)", dimension: "mass" },
          { code: "each", label_en: "Each (item)", label_ar: "حبة / قطعة", dimension: "count" },
        ]);
        this.loadSuppliers();
      },
    });
  }

  private loadSuppliers(): void {
    this.api.suppliers({ status: "all" }).subscribe({
      next: (res) => {
        this.suppliers.set(res.items);
        this.checkModeAndLoad();
      },
      error: () => {
        this.checkModeAndLoad();
      },
    });
  }

  private checkModeAndLoad(): void {
    const id = this.productId();
    if (id) {
      this.api.product(id).subscribe({
        next: (prod) => {
          this.populateForm(prod);
          this.isLoading.set(false);
          if (!this.isWriter()) {
            this.form.disable();
          }
        },
        error: (err: unknown) => {
          this.isLoading.set(false);
          this.handleError(err);
        },
      });
    } else {
      this.isLoading.set(false);
      if (!this.isWriter()) {
        this.form.disable();
      }
    }
  }

  private populateForm(prod: Product): void {
    this.form.patchValue({
      tenant_name: prod.tenant_name,
      brand: prod.brand || "",
      canonical_name: prod.canonical_name || "",
      variant: prod.variant || "",
      gtin: prod.gtin || "",
      base_unit: prod.base_unit,
      pack_count: prod.pack.pack_count,
      unit_size: prod.pack.unit_size,
      preferred_supplier_id: prod.preferred_supplier_id || null,
    });
    this.livePackCount.set(prod.pack.pack_count);
    this.liveUnitSize.set(prod.pack.unit_size);
    this.liveBaseUnit.set(prod.base_unit);
  }

  onSubmit(): void {
    if (this.form.invalid || !this.isWriter()) {
      this.form.markAllAsTouched();
      return;
    }

    this.isSaving.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    const fv = this.form.value;
    const pack = {
      pack_count: Number(fv.pack_count),
      unit_size: String(fv.unit_size).trim(),
    };

    if (this.isEditMode()) {
      const id = this.productId()!;
      const updatePayload: ProductUpdate = {
        tenant_name: fv.tenant_name.trim(),
        gtin: fv.gtin?.trim() || null,
        pack,
        preferred_supplier_id: fv.preferred_supplier_id || null,
      };

      this.api.updateProduct(id, updatePayload).subscribe({
        next: () => {
          this.isSaving.set(false);
          this.snackBar.open(
            this.translate.instant("catalogue.products.form.updateSuccess"),
            undefined,
            { duration: 3500 },
          );
          this.router.navigate(["/products"]);
        },
        error: (err: unknown) => {
          this.isSaving.set(false);
          this.handleError(err);
        },
      });
    } else {
      const createPayload: ProductCreate = {
        tenant_name: fv.tenant_name.trim(),
        brand: fv.brand?.trim() || null,
        canonical_name: fv.canonical_name?.trim() || null,
        variant: fv.variant?.trim() || null,
        gtin: fv.gtin?.trim() || null,
        base_unit: fv.base_unit,
        pack,
        preferred_supplier_id: fv.preferred_supplier_id || null,
      };

      this.api.createProduct(createPayload).subscribe({
        next: () => {
          this.isSaving.set(false);
          this.snackBar.open(
            this.translate.instant("catalogue.products.form.createSuccess"),
            undefined,
            { duration: 3500 },
          );
          this.router.navigate(["/products"]);
        },
        error: (err: unknown) => {
          this.isSaving.set(false);
          this.handleError(err);
        },
      });
    }
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorTraceId.set(apiError?.trace_id ?? null);
      if (
        err.status === 403 ||
        err.status === 422 ||
        apiError?.code === "plan_limit_exceeded" ||
        apiError?.message?.toLowerCase().includes("limit")
      ) {
        this.planLimitExceeded.set(true);
      }
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
