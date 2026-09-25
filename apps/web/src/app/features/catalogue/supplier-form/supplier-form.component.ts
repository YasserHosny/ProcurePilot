import { HttpErrorResponse } from "@angular/common/http";
import { Component, OnInit, computed, inject, signal } from "@angular/core";
import {
  AbstractControl,
  FormBuilder,
  FormGroup,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from "@angular/forms";
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
import type {
  ApiError,
  ReferenceOption,
  Supplier,
  SupplierCreate,
  SupplierUpdate,
} from "../../../core/api/models";
import { SessionService } from "../../../core/auth/session.service";
import { I18nService } from "../../../core/i18n/i18n.service";

/** Money validator: amount and currency must either both be present or both empty (Constitution VII). */
function moneyGroupValidator(amountKey: string, currencyKey: string) {
  return (group: AbstractControl): ValidationErrors | null => {
    const amount = group.get(amountKey)?.value?.toString().trim();
    const currency = group.get(currencyKey)?.value?.toString().trim();

    if (amount && !currency) {
      group.get(currencyKey)?.setErrors({ currencyRequired: true });
      return { currencyRequired: true };
    }
    if (currency && !amount) {
      group.get(amountKey)?.setErrors({ amountRequired: true });
      return { amountRequired: true };
    }

    if (group.get(currencyKey)?.hasError("currencyRequired")) {
      group.get(currencyKey)?.setErrors(null);
    }
    if (group.get(amountKey)?.hasError("amountRequired")) {
      group.get(amountKey)?.setErrors(null);
    }
    return null;
  };
}

@Component({
  selector: "app-supplier-form",
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
  templateUrl: "./supplier-form.component.html",
  styleUrl: "./supplier-form.component.scss",
})
export class SupplierFormComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);
  readonly i18n = inject(I18nService);

  readonly isEditMode = signal<boolean>(false);
  readonly supplierId = signal<string | null>(null);
  readonly isLoading = signal<boolean>(true);
  readonly isSaving = signal<boolean>(false);
  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);

  readonly isWriter = computed<boolean>(() => this.session.hasRole("owner", "buyer"));

  readonly currencies = signal<ReferenceOption[]>([
    { code: "GBP", label_en: "GBP (£)", label_ar: "جنيه إسترليني (£)" },
    { code: "EUR", label_en: "EUR (€)", label_ar: "يورو (€)" },
    { code: "USD", label_en: "USD ($)", label_ar: "دولار أمريكي ($)" },
    { code: "SAR", label_en: "SAR (ر.س)", label_ar: "ريال سعودي (ر.س)" },
    { code: "AED", label_en: "AED (د.إ)", label_ar: "درهم إماراتي (د.إ)" },
    { code: "EGP", label_en: "EGP (ج.م)", label_ar: "جنيه مصري (ج.م)" },
  ]);

  readonly form: FormGroup = this.fb.group(
    {
      name: ["", [Validators.required, Validators.maxLength(200)]],
      payment_terms: [""],
      lead_time_days: [null, [Validators.min(0)]],
      min_order_amount: ["", [Validators.pattern(/^\d+(\.\d{1,4})?$/)]],
      min_order_currency: [""],
      delivery_fee_amount: ["", [Validators.pattern(/^\d+(\.\d{1,4})?$/)]],
      delivery_fee_currency: [""],
      contact_email: ["", [Validators.email]],
      status: ["active"],
    },
    {
      validators: [
        moneyGroupValidator("min_order_amount", "min_order_currency"),
        moneyGroupValidator("delivery_fee_amount", "delivery_fee_currency"),
      ],
    },
  );

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get("id");
    if (id && id !== "new") {
      this.isEditMode.set(true);
      this.supplierId.set(id);
    }

    this.loadCurrencies();
  }

  private loadCurrencies(): void {
    this.isLoading.set(true);
    this.api.configOptions().subscribe({
      next: (config) => {
        if (config.currencies && config.currencies.length > 0) {
          this.currencies.set(config.currencies as ReferenceOption[]);
        }
        this.checkModeAndLoad();
      },
      error: () => {
        this.checkModeAndLoad();
      },
    });
  }

  private checkModeAndLoad(): void {
    const id = this.supplierId();
    if (id) {
      this.api.supplier(id).subscribe({
        next: (sup) => {
          this.populateForm(sup);
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

  private populateForm(sup: Supplier): void {
    this.form.patchValue({
      name: sup.name,
      payment_terms: sup.payment_terms || "",
      lead_time_days: sup.lead_time_days != null ? sup.lead_time_days : null,
      min_order_amount: sup.minimum_order_value ? sup.minimum_order_value.amount : "",
      min_order_currency: sup.minimum_order_value ? sup.minimum_order_value.currency : "",
      delivery_fee_amount: sup.delivery_fee ? sup.delivery_fee.amount : "",
      delivery_fee_currency: sup.delivery_fee ? sup.delivery_fee.currency : "",
      contact_email: sup.contact_email || "",
      status: sup.status || "active",
    });
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

    const minOrderVal =
      fv.min_order_amount?.trim() && fv.min_order_currency
        ? { amount: fv.min_order_amount.trim(), currency: fv.min_order_currency }
        : null;

    const deliveryFeeVal =
      fv.delivery_fee_amount?.trim() && fv.delivery_fee_currency
        ? { amount: fv.delivery_fee_amount.trim(), currency: fv.delivery_fee_currency }
        : null;

    const leadTime = fv.lead_time_days != null && fv.lead_time_days !== "" ? Number(fv.lead_time_days) : null;

    if (this.isEditMode()) {
      const id = this.supplierId()!;
      const updatePayload: SupplierUpdate = {
        name: fv.name.trim(),
        payment_terms: fv.payment_terms?.trim() || null,
        lead_time_days: leadTime,
        minimum_order_value: minOrderVal,
        delivery_fee: deliveryFeeVal,
        contact_email: fv.contact_email?.trim() || null,
        status: fv.status,
      };

      this.api.updateSupplier(id, updatePayload).subscribe({
        next: () => {
          this.isSaving.set(false);
          this.snackBar.open(
            this.translate.instant("catalogue.suppliers.form.updateSuccess"),
            undefined,
            { duration: 3500 },
          );
          this.router.navigate(["/suppliers"]);
        },
        error: (err: unknown) => {
          this.isSaving.set(false);
          this.handleError(err);
        },
      });
    } else {
      const createPayload: SupplierCreate = {
        name: fv.name.trim(),
        payment_terms: fv.payment_terms?.trim() || null,
        lead_time_days: leadTime,
        minimum_order_value: minOrderVal,
        delivery_fee: deliveryFeeVal,
        contact_email: fv.contact_email?.trim() || null,
      };

      this.api.createSupplier(createPayload).subscribe({
        next: () => {
          this.isSaving.set(false);
          this.snackBar.open(
            this.translate.instant("catalogue.suppliers.form.createSuccess"),
            undefined,
            { duration: 3500 },
          );
          this.router.navigate(["/suppliers"]);
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
