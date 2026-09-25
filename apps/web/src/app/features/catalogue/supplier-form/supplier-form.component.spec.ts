import { ComponentFixture, TestBed } from "@angular/core/testing";
import { signal } from "@angular/core";
import { MatSnackBar } from "@angular/material/snack-bar";
import { ActivatedRoute, provideRouter } from "@angular/router";
import { TranslateModule, TranslateService } from "@ngx-translate/core";
import { of } from "rxjs";

import enCatalog from "../../../../../../../packages/i18n/en.json";
import { ApiService } from "../../../core/api/api.service";
import type { Role } from "../../../core/api/models";
import { SessionService } from "../../../core/auth/session.service";
import { SupplierFormComponent } from "./supplier-form.component";

describe("SupplierFormComponent (T025)", () => {
  let component: SupplierFormComponent;
  let fixture: ComponentFixture<SupplierFormComponent>;
  let apiService: jasmine.SpyObj<ApiService>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;

  beforeEach(async () => {
    apiService = jasmine.createSpyObj("ApiService", [
      "configOptions",
      "supplier",
      "createSupplier",
      "updateSupplier",
    ]);
    snackBarSpy = jasmine.createSpyObj("MatSnackBar", ["open"]);

    apiService.configOptions.and.returnValue(
      of({
        regions: [],
        currencies: [
          { code: "GBP", label_en: "GBP (£)", label_ar: "جنيه إسترليني (£)" },
          { code: "EUR", label_en: "EUR (€)", label_ar: "يورو (€)" },
        ],
        tax_models: [],
      }),
    );

    const mockSession = {
      hasRole: jasmine.createSpy("hasRole").and.returnValue(true),
      role: signal<Role | null>("buyer"),
      currentMember: signal(null),
      isAuthenticated: signal(true),
      tenant: signal(null),
      activeLocale: signal("en"),
    };

    await TestBed.configureTestingModule({
      imports: [SupplierFormComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        { provide: ApiService, useValue: apiService },
        { provide: SessionService, useValue: mockSession },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              paramMap: {
                get: (key: string) => (key === "id" ? "new" : null),
              },
            },
          },
        },
      ],
    })
      .overrideComponent(SupplierFormComponent, {
        set: {
          providers: [{ provide: MatSnackBar, useValue: snackBarSpy }],
        },
      })
      .compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation("en", enCatalog);
    translate.use("en");

    fixture = TestBed.createComponent(SupplierFormComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it("should refuse monetary amount without currency", () => {
    component.form.patchValue({
      name: "Test Supplier",
      min_order_amount: "150.00",
      min_order_currency: "",
    });

    expect(component.form.invalid).toBeTrue();
    expect(component.form.get("min_order_currency")?.hasError("currencyRequired")).toBeTrue();
  });

  it("should refuse currency selection without monetary amount", () => {
    component.form.patchValue({
      name: "Test Supplier",
      min_order_amount: "",
      min_order_currency: "GBP",
    });

    expect(component.form.invalid).toBeTrue();
    expect(component.form.get("min_order_amount")?.hasError("amountRequired")).toBeTrue();
  });

  it("should create supplier when valid with explicit money currency", () => {
    const mockCreated = {
      id: "s-created",
      name: "Test Supplier",
      minimum_order_value: { amount: "150.00", currency: "GBP" },
      status: "active" as const,
      created_at: "2026-08-20T10:00:00Z",
    };
    apiService.createSupplier.and.returnValue(of(mockCreated));

    component.form.patchValue({
      name: "Test Supplier",
      min_order_amount: "150.00",
      min_order_currency: "GBP",
    });

    component.onSubmit();

    expect(apiService.createSupplier).toHaveBeenCalledWith({
      name: "Test Supplier",
      payment_terms: null,
      lead_time_days: null,
      minimum_order_value: { amount: "150.00", currency: "GBP" },
      delivery_fee: null,
      contact_email: null,
    });
    expect(snackBarSpy.open).toHaveBeenCalled();
  });
});
