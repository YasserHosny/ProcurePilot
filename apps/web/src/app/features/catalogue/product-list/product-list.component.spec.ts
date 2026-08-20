import { ComponentFixture, TestBed } from "@angular/core/testing";
import { signal } from "@angular/core";
import { MatDialog, MatDialogRef } from "@angular/material/dialog";
import { MatSnackBar } from "@angular/material/snack-bar";
import { provideRouter } from "@angular/router";
import { TranslateModule, TranslateService } from "@ngx-translate/core";
import { of } from "rxjs";

import enCatalog from "../../../../../../../packages/i18n/en.json";
import { ApiService } from "../../../core/api/api.service";
import type { Product, Role } from "../../../core/api/models";
import { SessionService } from "../../../core/auth/session.service";
import { ProductListComponent } from "./product-list.component";

describe("ProductListComponent (T016)", () => {
  let component: ProductListComponent;
  let fixture: ComponentFixture<ProductListComponent>;
  let apiService: jasmine.SpyObj<ApiService>;
  let dialogSpy: jasmine.SpyObj<MatDialog>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;

  const mockProducts: Product[] = [
    {
      id: "p1",
      tenant_name: "Milk 5L",
      canonical_name: "Milk",
      brand: "Dairy",
      variant: "Semi-Skimmed",
      gtin: "5012345678900",
      base_unit: "litre",
      pack: {
        pack_count: 6,
        unit_size: "5.000000",
        base_quantity: "30.000000",
      },
      status: "active",
      created_at: "2026-08-20T10:00:00Z",
    },
  ];

  beforeEach(async () => {
    apiService = jasmine.createSpyObj("ApiService", ["products", "archiveProduct"]);
    dialogSpy = jasmine.createSpyObj("MatDialog", ["open"]);
    snackBarSpy = jasmine.createSpyObj("MatSnackBar", ["open"]);

    apiService.products.and.returnValue(of({ items: mockProducts, next_cursor: null }));

    const mockSession = {
      hasRole: jasmine.createSpy("hasRole").and.returnValue(true),
      role: signal<Role | null>("buyer"),
      currentMember: signal(null),
      isAuthenticated: signal(true),
      tenant: signal(null),
      activeLocale: signal("en"),
    };

    await TestBed.configureTestingModule({
      imports: [ProductListComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        { provide: ApiService, useValue: apiService },
        { provide: SessionService, useValue: mockSession },
      ],
    })
      .overrideComponent(ProductListComponent, {
        set: {
          providers: [
            { provide: MatDialog, useValue: dialogSpy },
            { provide: MatSnackBar, useValue: snackBarSpy },
          ],
        },
      })
      .compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation("en", enCatalog);
    translate.use("en");

    fixture = TestBed.createComponent(ProductListComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it("should load products on init and display normalised quantity", () => {
    expect(apiService.products).toHaveBeenCalledWith({ status: "active", q: undefined });
    expect(component.products().length).toBe(1);
    expect(component.formatNormalised(mockProducts[0])).toBe("30.000000 litre");
  });

  it("should archive product when confirmed in dialog", () => {
    apiService.archiveProduct.and.returnValue(of(undefined));
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(true),
    } as MatDialogRef<unknown, unknown>);

    component.openArchiveDialog(mockProducts[0]);

    expect(apiService.archiveProduct).toHaveBeenCalledWith("p1");
    expect(apiService.products).toHaveBeenCalledTimes(2);
    expect(snackBarSpy.open).toHaveBeenCalled();
  });
});
