import { ComponentFixture, TestBed } from "@angular/core/testing";
import { signal } from "@angular/core";
import { MatDialog, MatDialogRef } from "@angular/material/dialog";
import { MatSnackBar } from "@angular/material/snack-bar";
import { provideRouter } from "@angular/router";
import { TranslateModule, TranslateService } from "@ngx-translate/core";
import { of } from "rxjs";

import enCatalog from "../../../../../../../packages/i18n/en.json";
import { ApiService } from "../../../core/api/api.service";
import type { Role, Supplier } from "../../../core/api/models";
import { SessionService } from "../../../core/auth/session.service";
import { SupplierListComponent } from "./supplier-list.component";

describe("SupplierListComponent (T024)", () => {
  let component: SupplierListComponent;
  let fixture: ComponentFixture<SupplierListComponent>;
  let apiService: jasmine.SpyObj<ApiService>;
  let dialogSpy: jasmine.SpyObj<MatDialog>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;

  const mockSuppliers: Supplier[] = [
    {
      id: "s1",
      name: "Acme Supplies",
      payment_terms: "Net 30",
      lead_time_days: 2,
      minimum_order_value: { amount: "100.00", currency: "GBP" },
      delivery_fee: { amount: "10.00", currency: "GBP" },
      status: "active",
      created_at: "2026-08-20T10:00:00Z",
    },
  ];

  beforeEach(async () => {
    apiService = jasmine.createSpyObj("ApiService", ["suppliers", "archiveSupplier"]);
    dialogSpy = jasmine.createSpyObj("MatDialog", ["open"]);
    snackBarSpy = jasmine.createSpyObj("MatSnackBar", ["open"]);

    apiService.suppliers.and.returnValue(of({ items: mockSuppliers, next_cursor: null }));

    const mockSession = {
      hasRole: jasmine.createSpy("hasRole").and.returnValue(true),
      role: signal<Role | null>("buyer"),
      currentMember: signal(null),
      isAuthenticated: signal(true),
      tenant: signal(null),
      activeLocale: signal("en"),
    };

    await TestBed.configureTestingModule({
      imports: [SupplierListComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        { provide: ApiService, useValue: apiService },
        { provide: SessionService, useValue: mockSession },
      ],
    })
      .overrideComponent(SupplierListComponent, {
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

    fixture = TestBed.createComponent(SupplierListComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it("should load suppliers on init and display explicit currency", () => {
    expect(apiService.suppliers).toHaveBeenCalledWith({ status: "active" });
    expect(component.suppliers().length).toBe(1);
    expect(component.suppliers()[0].minimum_order_value?.currency).toBe("GBP");
  });

  it("should archive supplier when confirmed in dialog", () => {
    apiService.archiveSupplier.and.returnValue(of(undefined));
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(true),
    } as MatDialogRef<unknown, unknown>);

    component.openArchiveDialog(mockSuppliers[0]);

    expect(apiService.archiveSupplier).toHaveBeenCalledWith("s1");
    expect(apiService.suppliers).toHaveBeenCalledTimes(2);
    expect(snackBarSpy.open).toHaveBeenCalled();
  });
});
