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
import { ProductFormComponent } from "./product-form.component";

describe("ProductFormComponent (T017)", () => {
  let component: ProductFormComponent;
  let fixture: ComponentFixture<ProductFormComponent>;
  let apiService: jasmine.SpyObj<ApiService>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;

  beforeEach(async () => {
    apiService = jasmine.createSpyObj("ApiService", [
      "baseUnits",
      "suppliers",
      "product",
      "createProduct",
      "updateProduct",
    ]);
    snackBarSpy = jasmine.createSpyObj("MatSnackBar", ["open"]);

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
});
