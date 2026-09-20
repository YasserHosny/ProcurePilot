import { HttpErrorResponse } from "@angular/common/http";
import { ComponentFixture, TestBed } from "@angular/core/testing";
import { signal } from "@angular/core";
import { MatSnackBar } from "@angular/material/snack-bar";
import { ActivatedRoute, provideRouter } from "@angular/router";
import { TranslateModule, TranslateService } from "@ngx-translate/core";
import { of, throwError } from "rxjs";

import enCatalog from "../../../../../../../packages/i18n/en.json";
import { ApiService } from "../../../core/api/api.service";
import type { Role } from "../../../core/api/models";
import { SessionService } from "../../../core/auth/session.service";
import { PosApiService } from "../../pos/pos-api";
import { ProductFormComponent } from "./product-form.component";

describe("ProductFormComponent (T017, T029)", () => {
  let component: ProductFormComponent;
  let fixture: ComponentFixture<ProductFormComponent>;
  let apiService: jasmine.SpyObj<ApiService>;
  let posApiService: jasmine.SpyObj<PosApiService>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;

  beforeEach(async () => {
    apiService = jasmine.createSpyObj("ApiService", [
      "baseUnits",
      "suppliers",
      "product",
      "createProduct",
      "updateProduct",
    ]);
    posApiService = jasmine.createSpyObj("PosApiService", ["listSignals"]);
    snackBarSpy = jasmine.createSpyObj("MatSnackBar", ["open"]);

    posApiService.listSignals.and.returnValue(of({ items: [], next_cursor: null }));

    apiService.baseUnits.and.returnValue(
      of({
        items: [
          { code: "litre", label_en: "Litre (L)", label_ar: "لتر (L)", dimension: "volume" },
        ],
      }),
    );
    apiService.suppliers.and.returnValue(of({ items: [], next_cursor: null }));

    const mockSession = {
      hasRole: jasmine.createSpy("hasRole").and.returnValue(true),
      role: signal<Role | null>("buyer"),
      currentMember: signal(null),
      isAuthenticated: signal(true),
      tenant: signal(null),
      activeLocale: signal("en"),
    };

    await TestBed.configureTestingModule({
      imports: [ProductFormComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        { provide: ApiService, useValue: apiService },
        { provide: PosApiService, useValue: posApiService },
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
      .overrideComponent(ProductFormComponent, {
        set: {
          providers: [{ provide: MatSnackBar, useValue: snackBarSpy }],
        },
      })
      .compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation("en", enCatalog);
    translate.use("en");

    fixture = TestBed.createComponent(ProductFormComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it("should update normalised quantity live as pack count and unit size change (6 x 5 = 30)", () => {
    component.form.patchValue({
      pack_count: 6,
      unit_size: "5.000000",
      base_unit: "litre",
    });
    fixture.detectChanges();

    expect(component.liveNormalisedQuantity()).toBe("30");
  });

  it("should create product when form is valid and submitted", () => {
    const mockCreated = {
      id: "p-new",
      tenant_name: "Fresh Milk",
      canonical_name: "Fresh Milk",
      base_unit: "litre",
      pack: { pack_count: 6, unit_size: "5.000000", base_quantity: "30.000000" },
      status: "active" as const,
      created_at: "2026-08-20T10:00:00Z",
    };
    apiService.createProduct.and.returnValue(of(mockCreated));

    component.form.patchValue({
      tenant_name: "Fresh Milk",
      base_unit: "litre",
      pack_count: 6,
      unit_size: "5.000000",
    });

    component.onSubmit();

    expect(apiService.createProduct).toHaveBeenCalledWith({
      tenant_name: "Fresh Milk",
      brand: null,
      canonical_name: null,
      variant: null,
      gtin: null,
      base_unit: "litre",
      pack: { pack_count: 6, unit_size: "5.000000" },
      preferred_supplier_id: null,
    });
    expect(snackBarSpy.open).toHaveBeenCalled();
  });

  describe("T029: Inline POS Signals", () => {
    it("does not render inline POS signals when no signal exists for product", () => {
      expect(fixture.nativeElement.querySelector('[data-testid="pos-inline-context"]')).toBeNull();
    });

    it("T031: renders product form fields normally when POS signals return not connected", () => {
      const mockProd = {
        id: "p-existing",
        tenant_name: "Espresso Roast",
        canonical_name: "Espresso Roast",
        brand: "CoffeeCo",
        variant: null,
        gtin: null,
        base_unit: "kg",
        pack: { pack_count: 1, unit_size: "1.000000", base_quantity: "1.000000" },
        preferred_supplier_id: null,
        status: "active" as const,
        created_at: "2026-08-20T10:00:00Z",
      };
      apiService.product.and.returnValue(of(mockProd));
      posApiService.listSignals.and.returnValue(
        throwError(
          () =>
            new HttpErrorResponse({
              status: 404,
              statusText: "Not Found",
              error: { code: "not_found", message: "No POS connection exists" },
            }),
        ),
      );

      component.productId.set("p-existing");
      component['checkModeAndLoad']();
      fixture.detectChanges();

      expect(component.errorMessage()).toBeNull();
      expect(component.isLoading()).toBeFalse();
      expect(component.form.controls["tenant_name"].value).toBe("Espresso Roast");
      expect(component.form.controls["base_unit"].value).toBe("kg");
      expect(fixture.nativeElement.querySelector("form.product-form")).toBeTruthy();
      expect(fixture.nativeElement.querySelector('[data-testid="pos-inline-context"]')).toBeNull();
    });

    it("renders stock and full velocity inline when matched signal exists for existing product", () => {
      const mockProd = {
        id: "p-existing",
        tenant_name: "Espresso Roast",
        canonical_name: "Espresso Roast",
        brand: "CoffeeCo",
        variant: null,
        gtin: null,
        base_unit: "kg",
        pack: { pack_count: 1, unit_size: "1.000000", base_quantity: "1.000000" },
        preferred_supplier_id: null,
        status: "active" as const,
        created_at: "2026-08-20T10:00:00Z",
      };
      apiService.product.and.returnValue(of(mockProd));
      posApiService.listSignals.and.returnValue(
        of({
          items: [
            {
              id: "sig-p1",
              external_item_name: "Square Espresso",
              matched: true,
              matched_workspace_product_id: "p-existing",
              stock_on_hand: "18.500",
              stock_synced_at: "2026-09-19T10:00:00Z",
              sales_velocity_per_day: "2.800",
              velocity_window_days: 30,
              velocity_window_days_observed: 30,
              velocity_computed_at: "2026-09-19T10:00:00Z",
            },
          ],
          next_cursor: null,
        }),
      );

      component.productId.set("p-existing");
      component['checkModeAndLoad']();
      fixture.detectChanges();

      const context = fixture.nativeElement.querySelector('[data-testid="pos-inline-context"]');
      expect(context).toBeTruthy();

      const stock = fixture.nativeElement.querySelector('[data-testid="pos-stock-on-hand"]');
      expect(stock?.textContent).toContain("18.500");

      const velocity = fixture.nativeElement.querySelector('[data-testid="pos-sales-velocity"]');
      expect(velocity?.textContent).toContain("2.800 units/day · 30-day avg");
      expect(fixture.nativeElement.querySelector('[data-testid="pos-velocity-provisional"]')).toBeNull();
    });

    it("renders velocity as provisional when observed window days is less than target window", () => {
      const mockProd = {
        id: "p-existing",
        tenant_name: "Espresso Roast",
        canonical_name: "Espresso Roast",
        brand: "CoffeeCo",
        variant: null,
        gtin: null,
        base_unit: "kg",
        pack: { pack_count: 1, unit_size: "1.000000", base_quantity: "1.000000" },
        preferred_supplier_id: null,
        status: "active" as const,
        created_at: "2026-08-20T10:00:00Z",
      };
      apiService.product.and.returnValue(of(mockProd));
      posApiService.listSignals.and.returnValue(
        of({
          items: [
            {
              id: "sig-p2",
              external_item_name: "Square Espresso",
              matched: true,
              matched_workspace_product_id: "p-existing",
              stock_on_hand: null,
              stock_synced_at: null,
              sales_velocity_per_day: "3.200",
              velocity_window_days: 30,
              velocity_window_days_observed: 5,
              velocity_computed_at: "2026-09-19T10:00:00Z",
            },
          ],
          next_cursor: null,
        }),
      );

      component.productId.set("p-existing");
      component['checkModeAndLoad']();
      fixture.detectChanges();

      const provisional = fixture.nativeElement.querySelector('[data-testid="pos-velocity-provisional"]');
      expect(provisional).toBeTruthy();

      const velocity = fixture.nativeElement.querySelector('[data-testid="pos-sales-velocity"]');
      expect(velocity?.textContent).toContain("≈3.200 units/day · based on 5 of 30 days");
      expect(fixture.nativeElement.querySelector('[data-testid="pos-stock-on-hand"]')).toBeNull();
    });
  });
});
