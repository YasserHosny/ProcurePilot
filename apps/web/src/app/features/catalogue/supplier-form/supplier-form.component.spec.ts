import { ComponentFixture, TestBed } from "@angular/core/testing";
import { WritableSignal, signal } from "@angular/core";
import { MatSelect } from "@angular/material/select";
import { MatSnackBar } from "@angular/material/snack-bar";
import { By } from "@angular/platform-browser";
import { ActivatedRoute, provideRouter } from "@angular/router";
import { TranslateService, provideTranslateService } from "@ngx-translate/core";
import { of } from "rxjs";

import enCatalog from "../../../../../../../packages/i18n/en.json";
import { ApiService } from "../../../core/api/api.service";
import type { Me, Role, Supplier, Tenant } from "../../../core/api/models";
import { SessionService } from "../../../core/auth/session.service";
import {
  SupplierFormComponent,
  WORKSPACE_DEFAULT_LOCALE,
} from "./supplier-form.component";

describe("SupplierFormComponent (T025)", () => {
  let component: SupplierFormComponent;
  let fixture: ComponentFixture<SupplierFormComponent>;
  let apiService: jasmine.SpyObj<ApiService>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;
  let translate: TranslateService;
  let mockSession: {
    hasRole: jasmine.Spy;
    role: WritableSignal<Role | null>;
    currentMember: WritableSignal<Me | null>;
    isAuthenticated: WritableSignal<boolean>;
    tenant: WritableSignal<Tenant | null>;
    homeCurrency: WritableSignal<string | undefined>;
    activeLocale: WritableSignal<string>;
  };

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

    mockSession = {
      hasRole: jasmine.createSpy("hasRole").and.callFake((...roles: Role[]) => {
        const current = mockSession.role();
        return current !== null && roles.includes(current);
      }),
      role: signal<Role | null>("buyer"),
      currentMember: signal<Me | null>(null),
      isAuthenticated: signal<boolean>(true),
      tenant: signal<Tenant | null>(null),
      homeCurrency: signal<string | undefined>("EGP"),
      activeLocale: signal<string>("en"),
    };

    await TestBed.configureTestingModule({
      imports: [SupplierFormComponent],
      providers: [
        provideTranslateService(),
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

    translate = TestBed.inject(TranslateService);
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

  it("preselects the home currency for both new-supplier money fields", () => {
    expect(component.form.get("min_order_currency")?.value).toBe("EGP");
    expect(component.form.get("delivery_fee_currency")?.value).toBe("EGP");
  });

  it("omits empty money values from the create payload", () => {
    apiService.createSupplier.and.returnValue(of({
      id: "s-empty-money", name: "Test Supplier", status: "active" as const,
      created_at: "2026-08-20T10:00:00Z",
    }));
    component.form.patchValue({ name: "Test Supplier" });
    component.onSubmit();
    expect(apiService.createSupplier).toHaveBeenCalledWith(jasmine.objectContaining({
      name: "Test Supplier", payment_terms: null, lead_time_days: null, contact_email: null,
    }));
    expect(apiService.createSupplier.calls.mostRecent().args[0]).toEqual(jasmine.objectContaining({
      minimum_order_value: null,
      delivery_fee: null,
    }));
  });

  it("allows a currency to be preselected before an amount is entered", () => {
    component.form.patchValue({
      name: "Test Supplier",
      min_order_amount: "",
      min_order_currency: "GBP",
    });

    expect(component.form.valid).toBeTrue();
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
      preferred_locale: null,
    });
    expect(snackBarSpy.open).toHaveBeenCalled();
  });

  describe("PPS-134: Supplier Email Language (preferred_locale)", () => {
    it("create mode: displays Workspace default (Arabic) without opening the select", async () => {
      mockSession.tenant.set({
        id: "t-1", name: "Tenant 1", slug: "t1", region: "EG", currency: "EGP",
        tax_model: "standard", default_locale: "ar", created_at: "2026-08-20T10:00:00Z",
      });
      fixture.detectChanges();
      await fixture.whenStable();
      fixture.detectChanges();

      const select = fixture.debugElement.query(
        By.css('mat-select[formControlName="preferred_locale"]'),
      ).componentInstance as MatSelect;
      expect(select.panelOpen).toBeFalse();
      expect(select.triggerValue).toBe("Workspace default (Arabic)");
    });

    it("edit mode: displays Workspace default (Arabic) for a missing preferred_locale without opening the select", async () => {
      mockSession.tenant.set({
        id: "t-1", name: "Tenant 1", slug: "t1", region: "EG", currency: "EGP",
        tax_model: "standard", default_locale: "ar", created_at: "2026-08-20T10:00:00Z",
      });
      apiService.supplier.and.returnValue(of({
        id: "s-default", name: "Supplier Default", status: "active",
        created_at: "2026-08-20T10:00:00Z",
      }));
      component.isEditMode.set(true);
      component.supplierId.set("s-default");
      component["checkModeAndLoad"]();
      fixture.detectChanges();
      await fixture.whenStable();
      fixture.detectChanges();

      const select = fixture.debugElement.query(
        By.css('mat-select[formControlName="preferred_locale"]'),
      ).componentInstance as MatSelect;
      expect(select.panelOpen).toBeFalse();
      expect(select.triggerValue).toBe("Workspace default (Arabic)");
    });

    it("create mode: choosing Arabic sends preferred_locale: 'ar' in createSupplier", () => {
      apiService.createSupplier.and.returnValue(
        of({
          id: "s-created",
          name: "Test Supplier",
          status: "active" as const,
          created_at: "2026-08-20T10:00:00Z",
          preferred_locale: "ar",
        }),
      );

      component.form.patchValue({
        name: "Test Supplier",
        preferred_locale: "ar",
      });

      component.onSubmit();

      expect(apiService.createSupplier).toHaveBeenCalledWith(
        jasmine.objectContaining({
          name: "Test Supplier",
          preferred_locale: "ar",
        }),
      );
    });

    it("create mode: leaving the default sends preferred_locale: null in createSupplier", () => {
      apiService.createSupplier.and.returnValue(
        of({
          id: "s-created",
          name: "Test Supplier",
          status: "active" as const,
          created_at: "2026-08-20T10:00:00Z",
          preferred_locale: null,
        }),
      );

      component.form.patchValue({
        name: "Test Supplier",
      });

      component.onSubmit();

      expect(apiService.createSupplier).toHaveBeenCalledWith(
        jasmine.objectContaining({
          name: "Test Supplier",
          preferred_locale: null,
        }),
      );
    });

    it("edit mode: a supplier with preferred_locale: 'en' pre-fills 'en'", () => {
      const mockSupplier: Supplier = {
        id: "s-edit-1",
        name: "Supplier English",
        status: "active",
        created_at: "2026-08-20T10:00:00Z",
        preferred_locale: "en",
      };
      apiService.supplier.and.returnValue(of(mockSupplier));

      component.isEditMode.set(true);
      component.supplierId.set("s-edit-1");
      component["checkModeAndLoad"]();
      fixture.detectChanges();

      expect(component.form.get("preferred_locale")?.value).toBe("en");
    });

    it("edit mode: a supplier without preferred_locale pre-fills the default option", () => {
      const mockSupplier: Supplier = {
        id: "s-edit-2",
        name: "Supplier Default",
        status: "active",
        created_at: "2026-08-20T10:00:00Z",
        preferred_locale: null,
      };
      apiService.supplier.and.returnValue(of(mockSupplier));

      component.isEditMode.set(true);
      component.supplierId.set("s-edit-2");
      component["checkModeAndLoad"]();
      fixture.detectChanges();

      expect(component.form.get("preferred_locale")?.value).toBe(WORKSPACE_DEFAULT_LOCALE);
    });

    it("edit mode: switching to the default sends preferred_locale: null in updateSupplier", () => {
      const mockSupplier: Supplier = {
        id: "s-edit-3",
        name: "Supplier Edit Switching",
        status: "active",
        created_at: "2026-08-20T10:00:00Z",
        preferred_locale: "en",
      };
      apiService.supplier.and.returnValue(of(mockSupplier));
      apiService.updateSupplier.and.returnValue(
        of({ ...mockSupplier, preferred_locale: null }),
      );

      component.isEditMode.set(true);
      component.supplierId.set("s-edit-3");
      component["checkModeAndLoad"]();
      fixture.detectChanges();

      expect(component.form.get("preferred_locale")?.value).toBe("en");

      component.form.patchValue({ preferred_locale: null });
      component.onSubmit();

      expect(apiService.updateSupplier).toHaveBeenCalledWith(
        "s-edit-3",
        jasmine.objectContaining({
          name: "Supplier Edit Switching",
          preferred_locale: null,
        }),
      );
    });

    it("the default option's label names the workspace language when tenant default_locale is 'ar'", () => {
      mockSession.tenant.set({
        id: "t-1",
        name: "Tenant 1",
        slug: "t1",
        region: "EG",
        currency: "EGP",
        tax_model: "standard",
        default_locale: "ar",
        created_at: "2026-08-20T10:00:00Z",
      });
      fixture.detectChanges();

      const selectDebugEl = fixture.debugElement.query(
        By.css('mat-select[formControlName="preferred_locale"]'),
      );
      const matSelect = selectDebugEl.componentInstance as MatSelect;
      matSelect.open();
      fixture.detectChanges();

      const options = Array.from(document.querySelectorAll<HTMLElement>("mat-option"));
      const defaultOption = options[0];
      const arabicName = translate.instant("catalogue.suppliers.form.languageArabic");
      expect(defaultOption?.textContent).toContain(arabicName);
      expect(component.workspaceLanguageKey()).toBe("catalogue.suppliers.form.languageArabic");

      matSelect.close();
      fixture.detectChanges();
    });

    it("the default option's label falls back to plain workspace default when tenant default_locale is missing", () => {
      mockSession.tenant.set(null);
      fixture.detectChanges();

      const selectDebugEl = fixture.debugElement.query(
        By.css('mat-select[formControlName="preferred_locale"]'),
      );
      const matSelect = selectDebugEl.componentInstance as MatSelect;
      matSelect.open();
      fixture.detectChanges();

      const options = Array.from(document.querySelectorAll<HTMLElement>("mat-option"));
      const defaultOption = options[0];
      const plainText = translate.instant("catalogue.suppliers.form.emailLanguageDefaultPlain");
      expect(defaultOption?.textContent?.trim()).toBe(plainText);
      expect(component.workspaceLanguageKey()).toBeNull();

      matSelect.close();
      fixture.detectChanges();
    });

    it("disables preferred_locale for read-only members", () => {
      mockSession.role.set("viewer");
      component["checkModeAndLoad"]();
      fixture.detectChanges();

      expect(component.form.get("preferred_locale")?.disabled).toBeTrue();
    });
  });
});
