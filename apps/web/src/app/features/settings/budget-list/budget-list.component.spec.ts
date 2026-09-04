import { HttpErrorResponse } from "@angular/common/http";
import { signal } from "@angular/core";
import type { ComponentFixture } from "@angular/core/testing";
import { TestBed } from "@angular/core/testing";
import type { WritableSignal } from "@angular/core";
import { MatDialog, MatDialogRef } from "@angular/material/dialog";
import { MatSnackBar } from "@angular/material/snack-bar";
import { provideRouter } from "@angular/router";
import { TranslateModule, TranslateService } from "@ngx-translate/core";
import { of, throwError } from "rxjs";

import enCatalog from "../../../../../../../packages/i18n/en.json";
import { ApiService } from "../../../core/api/api.service";
import type {
  Branch,
  Budget,
  BudgetCreated,
  CostCentre,
  ReferenceOption,
  Role,
  Tenant,
} from "../../../core/api/models";
import { SessionService } from "../../../core/auth/session.service";
import { OrganisationApiService } from "../organisation-api";
import { BudgetFormDialogComponent } from "./budget-form-dialog/budget-form-dialog.component";
import { BudgetListComponent } from "./budget-list.component";

const mockBranches: Branch[] = [
  {
    id: "b1",
    name: "Main Branch",
    address: null,
    region: null,
    is_active: true,
    created_at: "2026-08-03T09:00:00Z",
  },
  {
    id: "b2",
    name: "Old Branch",
    address: null,
    region: null,
    is_active: false,
    created_at: "2026-08-04T09:00:00Z",
  },
];

const mockCostCentres: CostCentre[] = [
  {
    id: "cc1",
    name: "Marketing",
    code: "MKT",
    budget_owner_membership_id: null,
    branch_id: "b1",
    is_orphaned: false,
    orphan_reason: null,
    is_archived: false,
    created_at: "2026-08-10T09:00:00Z",
  },
  {
    id: "cc2",
    name: "Warehouse Ops",
    code: "WHS",
    budget_owner_membership_id: null,
    branch_id: null,
    is_orphaned: false,
    orphan_reason: null,
    is_archived: true,
    created_at: "2026-08-11T09:00:00Z",
  },
];

const mockBudgets: Budget[] = [
  {
    id: "bg1",
    amount: { amount: "12000", currency: "USD" },
    period: "monthly",
    period_start: "2026-09-01",
    scope: "organisation",
    branch_id: null,
    cost_centre_id: null,
    created_at: "2026-08-15T09:00:00Z",
  },
  {
    id: "bg2",
    amount: { amount: "50000", currency: "EGP" },
    period: "annual",
    period_start: "2026-01-01",
    scope: "branch",
    branch_id: "b1",
    cost_centre_id: null,
    created_at: "2026-08-16T09:00:00Z",
  },
  {
    id: "bg3",
    amount: { amount: "8000.5", currency: "SAR" },
    period: "quarterly",
    period_start: "2026-07-01",
    scope: "cost_centre",
    branch_id: null,
    cost_centre_id: "cc1",
    created_at: "2026-08-17T09:00:00Z",
  },
];

const mockCurrencies: ReferenceOption[] = [
  { code: "EGP", label_en: "Egyptian Pound", label_ar: "جنيه مصري" },
  { code: "USD", label_en: "US Dollar", label_ar: "دولار أمريكي" },
  { code: "EUR", label_en: "Euro", label_ar: "يورو" },
];

describe("BudgetListComponent (T030)", () => {
  let component: BudgetListComponent;
  let fixture: ComponentFixture<BudgetListComponent>;
  let organisationApi: jasmine.SpyObj<OrganisationApiService>;
  let apiService: jasmine.SpyObj<ApiService>;
  let dialogSpy: jasmine.SpyObj<MatDialog>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;
  let roleSignal: WritableSignal<Role | null>;
  let sessionMock: {
    hasRole: jasmine.Spy;
    role: WritableSignal<Role | null>;
    currentMember: unknown;
    isAuthenticated: unknown;
    tenant: unknown;
    activeLocale: unknown;
  };

  beforeEach(async () => {
    organisationApi = jasmine.createSpyObj("OrganisationApiService", [
      "listBudgets",
      "createBudget",
      "listBranches",
      "listCostCentres",
    ]);
    apiService = jasmine.createSpyObj("ApiService", ["configOptions"]);
    dialogSpy = jasmine.createSpyObj("MatDialog", ["open"]);
    snackBarSpy = jasmine.createSpyObj("MatSnackBar", ["open"]);

    roleSignal = signal<Role | null>("owner");
    sessionMock = {
      hasRole: jasmine.createSpy("hasRole").and.callFake((...roles: readonly Role[]) => {
        const current = roleSignal();
        return current !== null && roles.includes(current);
      }),
      role: roleSignal,
      currentMember: signal(null),
      isAuthenticated: signal(true),
      tenant: signal(null),
      activeLocale: signal("en"),
    };

    organisationApi.listBudgets.and.returnValue(of({ items: mockBudgets, next_cursor: null }));
    organisationApi.listBranches.and.returnValue(of({ items: mockBranches, next_cursor: null }));
    organisationApi.listCostCentres.and.returnValue(
      of({ items: mockCostCentres, next_cursor: null }),
    );
    apiService.configOptions.and.returnValue(
      of({ regions: [], currencies: mockCurrencies, tax_models: [] }),
    );

    await TestBed.configureTestingModule({
      imports: [BudgetListComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        { provide: OrganisationApiService, useValue: organisationApi },
        { provide: ApiService, useValue: apiService },
        { provide: SessionService, useValue: sessionMock },
      ],
    })
      .overrideComponent(BudgetListComponent, {
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

    fixture = TestBed.createComponent(BudgetListComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  function rowCells(index: number): readonly string[] {
    const compiled = fixture.nativeElement as HTMLElement;
    const rows = compiled.querySelectorAll<HTMLTableRowElement>("tr[mat-row]");
    return Array.from(rows[index].querySelectorAll("td")).map((cell) =>
      (cell.textContent ?? "").trim(),
    );
  }

  it("should load budgets and reference data on init", () => {
    expect(organisationApi.listBudgets).toHaveBeenCalledWith();
    expect(organisationApi.listBranches).toHaveBeenCalledWith();
    expect(organisationApi.listCostCentres).toHaveBeenCalledWith();
    expect(component.budgets().length).toBe(mockBudgets.length);
    expect(component.isLoading()).toBeFalse();
    expect(component.errorMessage()).toBeNull();
  });

  it("should render amount, currency, period, scope, and resolved target per row", () => {
    fixture.detectChanges();

    const firstRow = rowCells(0);
    expect(firstRow[0]).toContain("12,000.00");
    expect(firstRow[1]).toBe("USD");
    expect(firstRow[2]).toBe("Monthly");
    expect(firstRow[3]).toBe("Whole organisation");
    expect(firstRow[4]).toBe("—");

    const secondRow = rowCells(1);
    expect(secondRow[1]).toBe("EGP");
    expect(secondRow[2]).toBe("Annual");
    expect(secondRow[3]).toBe("Branch");
    expect(secondRow[4]).toBe("Main Branch");

    const thirdRow = rowCells(2);
    expect(thirdRow[2]).toBe("Quarterly");
    expect(thirdRow[3]).toBe("Cost centre");
    expect(thirdRow[4]).toBe("Marketing");
  });

  it("should show the empty state when no budgets exist", () => {
    organisationApi.listBudgets.and.returnValue(of({ items: [], next_cursor: null }));
    component.loadBudgets();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector(".empty-state")).toBeTruthy();
    expect(compiled.querySelector(".budgets-table")).toBeNull();
  });

  it("should fall back to raw IDs when reference data is unavailable", () => {
    organisationApi.listBranches.and.returnValue(throwError(() => new Error("offline")));
    component.loadReferenceData();
    fixture.detectChanges();

    const secondRow = rowCells(1);
    expect(secondRow[4]).toBe("b1");
  });

  it("should open the create dialog and reload with a success snack-bar on close", () => {
    const created: BudgetCreated = { ...mockBudgets[0], id: "bg9", overlap_warning: false };
    organisationApi.createBudget.and.returnValue(of(created));
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(created),
    } as MatDialogRef<unknown, unknown>);

    component.openCreateDialog();

    const [dialogType] = dialogSpy.open.calls.mostRecent().args;
    expect(dialogType).toBe(BudgetFormDialogComponent);
    expect(component.overlapWarningVisible()).toBeFalse();
    expect(organisationApi.listBudgets).toHaveBeenCalledTimes(2);
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      "Budget defined successfully.",
      undefined,
      { duration: 3500 },
    );
  });

  it("should show the overlap warning banner when the API flags overlap and still reload", () => {
    const created: BudgetCreated = { ...mockBudgets[0], id: "bg9", overlap_warning: true };
    organisationApi.createBudget.and.returnValue(of(created));
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(created),
    } as MatDialogRef<unknown, unknown>);

    component.openCreateDialog();
    fixture.detectChanges();

    // The budget IS saved — the warning is informational, never an error state.
    expect(component.overlapWarningVisible()).toBeTrue();
    expect(organisationApi.listBudgets).toHaveBeenCalledTimes(2);
    expect(component.errorMessage()).toBeNull();
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      "Budget defined successfully.",
      undefined,
      { duration: 3500 },
    );
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector(".info-banner")?.textContent).toContain(
      "A budget already exists for this scope",
    );
  });

  it("should hide the create affordance for non-owner roles", () => {
    roleSignal.set("viewer");
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector(".action-btn")).toBeNull();
    expect(rowCells(0)[0]).toContain("12,000.00");
  });
});

describe("BudgetFormDialogComponent (T030)", () => {
  let dialogRefSpy: jasmine.SpyObj<MatDialogRef<BudgetFormDialogComponent, unknown>>;
  let organisationApi: jasmine.SpyObj<OrganisationApiService>;
  let apiService: jasmine.SpyObj<ApiService>;

  const mockTenant: Tenant = {
    id: "t1",
    name: "Acme",
    slug: "acme",
    region: "MENA",
    currency: "EGP",
    tax_model: "vat",
    default_locale: "en",
    created_at: "2026-01-01T00:00:00Z",
  };

  async function createDialog(tenant: Tenant | null): Promise<{
    component: BudgetFormDialogComponent;
    fixture: ComponentFixture<BudgetFormDialogComponent>;
  }> {
    const tenantSignal = signal<Tenant | null>(tenant);
    // The dialog pulls I18nService in for currency labels, which reads several
    // session members on construction — mirror the real surface it touches.
    const sessionMock = {
      hasRole: jasmine.createSpy("hasRole").and.returnValue(true),
      role: signal<Role | null>("owner"),
      currentMember: signal(null),
      isAuthenticated: signal(true),
      tenant: tenantSignal,
      activeLocale: signal("en"),
    };

    await TestBed.configureTestingModule({
      imports: [BudgetFormDialogComponent, TranslateModule.forRoot()],
      providers: [
        { provide: OrganisationApiService, useValue: organisationApi },
        { provide: ApiService, useValue: apiService },
        { provide: SessionService, useValue: sessionMock },
        { provide: MatDialogRef, useValue: dialogRefSpy },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation("en", enCatalog);
    translate.use("en");

    const fixture = TestBed.createComponent(BudgetFormDialogComponent);
    const component = fixture.componentInstance;
    fixture.detectChanges();
    return { component, fixture };
  }

  function fieldLabels(fixture: ComponentFixture<BudgetFormDialogComponent>): readonly string[] {
    const compiled = fixture.nativeElement as HTMLElement;
    return Array.from(compiled.querySelectorAll("mat-label")).map((label) =>
      (label.textContent ?? "").trim(),
    );
  }

  beforeEach(() => {
    organisationApi = jasmine.createSpyObj("OrganisationApiService", [
      "listBranches",
      "listCostCentres",
      "createBudget",
    ]);
    apiService = jasmine.createSpyObj("ApiService", ["configOptions"]);
    dialogRefSpy = jasmine.createSpyObj("MatDialogRef", ["close"]);

    organisationApi.listBranches.and.returnValue(of({ items: mockBranches, next_cursor: null }));
    organisationApi.listCostCentres.and.returnValue(
      of({ items: mockCostCentres, next_cursor: null }),
    );
    apiService.configOptions.and.returnValue(
      of({ regions: [], currencies: mockCurrencies, tax_models: [] }),
    );
  });

  it("should load branches, cost centres, and currencies for the pickers on init", async () => {
    await createDialog(mockTenant);

    expect(organisationApi.listBranches).toHaveBeenCalledWith();
    expect(organisationApi.listCostCentres).toHaveBeenCalledWith();
    expect(apiService.configOptions).toHaveBeenCalledWith();
  });

  it("should default the currency to the tenant's own currency but let an explicit choice stick", async () => {
    const { component } = await createDialog(mockTenant);

    expect(component.form.controls.currency.value).toBe("EGP");

    component.form.controls.currency.setValue("USD");
    expect(component.form.controls.currency.value).toBe("USD");
    expect(component.form.controls.currency.valid).toBeTrue();
  });

  it("should show neither target picker for organisation scope", async () => {
    const { component, fixture } = await createDialog(mockTenant);

    component.form.controls.scope.setValue("organisation");
    fixture.detectChanges();

    const labels = fieldLabels(fixture);
    expect(labels).not.toContain("Branch");
    expect(labels).not.toContain("Cost Centre");
    expect(component.selectedScope()).toBe("organisation");
    expect(component.form.controls.branch_id.hasError("required")).toBeFalse();
    expect(component.form.controls.cost_centre_id.hasError("required")).toBeFalse();
  });

  it("should show only a required branch picker for branch scope", async () => {
    const { component, fixture } = await createDialog(mockTenant);

    component.form.controls.scope.setValue("branch");
    fixture.detectChanges();

    const labels = fieldLabels(fixture);
    expect(labels).toContain("Branch");
    expect(labels).not.toContain("Cost Centre");
    expect(component.form.controls.branch_id.hasError("required")).toBeTrue();
    expect(component.form.controls.cost_centre_id.hasError("required")).toBeFalse();
    expect(component.form.controls.branch_id.value).toBeNull();

    component.form.controls.branch_id.setValue("b1");
    expect(component.form.controls.branch_id.valid).toBeTrue();
  });

  it("should show only a required cost-centre picker for cost_centre scope", async () => {
    const { component, fixture } = await createDialog(mockTenant);

    component.form.controls.scope.setValue("cost_centre");
    fixture.detectChanges();

    const labels = fieldLabels(fixture);
    expect(labels).toContain("Cost Centre");
    expect(labels).not.toContain("Branch");
    expect(component.form.controls.cost_centre_id.hasError("required")).toBeTrue();
    expect(component.form.controls.branch_id.hasError("required")).toBeFalse();

    component.form.controls.cost_centre_id.setValue("cc1");
    expect(component.form.controls.cost_centre_id.valid).toBeTrue();
  });

  it("should clear the previous target value when scope changes away from its picker", async () => {
    const { component } = await createDialog(mockTenant);

    component.form.controls.scope.setValue("branch");
    component.form.controls.branch_id.setValue("b1");
    expect(component.form.controls.branch_id.value).toBe("b1");

    component.form.controls.scope.setValue("cost_centre");
    expect(component.form.controls.branch_id.value).toBeNull();
    expect(component.form.controls.cost_centre_id.value).toBeNull();

    component.form.controls.scope.setValue("organisation");
    expect(component.form.controls.branch_id.value).toBeNull();
    expect(component.form.controls.cost_centre_id.value).toBeNull();
  });

  it("should submit a branch-scoped create with the other target nulled and close with the result", async () => {
    const { component } = await createDialog(mockTenant);

    component.form.controls.amount.setValue("12500.75");
    component.form.controls.currency.setValue("USD");
    component.form.controls.period.setValue("quarterly");
    component.form.controls.period_start.setValue("2026-10-01");
    component.form.controls.scope.setValue("branch");
    component.form.controls.branch_id.setValue("b1");

    const created: BudgetCreated = { ...mockBudgets[1], id: "bg9", overlap_warning: false };
    organisationApi.createBudget.and.returnValue(of(created));

    component.onSubmit();

    expect(organisationApi.createBudget).toHaveBeenCalledWith({
      amount: "12500.75",
      currency: "USD",
      period: "quarterly",
      period_start: "2026-10-01",
      scope: "branch",
      branch_id: "b1",
      cost_centre_id: null,
    });
    expect(dialogRefSpy.close).toHaveBeenCalledWith(created);
  });

  it("should reject negative or malformed amounts before submission", async () => {
    const { component } = await createDialog(mockTenant);

    for (const bad of ["-5", "12.12345", "abc", ""]) {
      component.form.controls.amount.setValue(bad);
      if (bad !== "") {
        expect(component.form.controls.amount.hasError("pattern")).withContext(bad).toBeTrue();
      }
    }

    component.form.controls.scope.setValue("organisation");
    component.onSubmit();

    // Form is invalid (amount + untouched required fields), so nothing was sent.
    expect(organisationApi.createBudget).not.toHaveBeenCalled();
    expect(dialogRefSpy.close).not.toHaveBeenCalled();
  });

  it("should surface API failures inline and stay open", async () => {
    const { component, fixture } = await createDialog(mockTenant);

    const error500 = new HttpErrorResponse({
      status: 500,
      error: { code: "internal", message: "Boom", trace_id: "tr_500" },
    });
    organisationApi.createBudget.and.returnValue(throwError(() => error500));

    component.form.controls.amount.setValue("1000");
    component.form.controls.currency.setValue("EGP");
    component.form.controls.period.setValue("monthly");
    component.form.controls.period_start.setValue("2026-10-01");
    component.form.controls.scope.setValue("organisation");
    component.onSubmit();
    fixture.detectChanges();

    expect(component.errorMessage()).toBe("Boom");
    expect(component.errorTraceId()).toBe("tr_500");
    expect(component.isSubmitting()).toBeFalse();
    expect(dialogRefSpy.close).not.toHaveBeenCalled();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector(".error-banner")?.textContent).toContain("Boom");
  });

  it("should close with false on cancel without calling the API", async () => {
    const { component } = await createDialog(mockTenant);

    component.onCancel();

    expect(dialogRefSpy.close).toHaveBeenCalledWith(false);
    expect(organisationApi.createBudget).not.toHaveBeenCalled();
  });
});
