import { HttpErrorResponse } from "@angular/common/http";
import { signal } from "@angular/core";
import type { ComponentFixture } from "@angular/core/testing";
import { TestBed } from "@angular/core/testing";
import type { WritableSignal } from "@angular/core";
import { MAT_DIALOG_DATA, MatDialog, MatDialogRef } from "@angular/material/dialog";
import { MatSnackBar } from "@angular/material/snack-bar";
import { provideRouter } from "@angular/router";
import { TranslateModule, TranslateService } from "@ngx-translate/core";
import { of, throwError } from "rxjs";

import enCatalog from "../../../../../../../packages/i18n/en.json";
import { ApiService } from "../../../core/api/api.service";
import type { Branch, CostCentre, Member, Role } from "../../../core/api/models";
import { SessionService } from "../../../core/auth/session.service";
import {
  CatalogueConfirmDialogComponent,
  ConfirmDialogData,
} from "../../catalogue/confirm-dialog/confirm-dialog.component";
import { OrganisationApiService } from "../organisation-api";
import {
  CostCentreFormDialogComponent,
  CostCentreFormDialogData,
} from "./cost-centre-form-dialog/cost-centre-form-dialog.component";
import { CostCentreListComponent } from "./cost-centre-list.component";

const mockMembers: Member[] = [
  {
    id: "m1",
    email: "dana@example.com",
    role: "owner",
    status: "active",
    mfa_enabled: false,
    created_at: "2026-08-01T09:00:00Z",
  },
  {
    id: "m2",
    email: "omar@example.com",
    role: "approver",
    status: "active",
    mfa_enabled: true,
    created_at: "2026-08-02T09:00:00Z",
  },
];

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
    budget_owner_membership_id: "m1",
    branch_id: null,
    is_orphaned: false,
    orphan_reason: null,
    is_archived: false,
    created_at: "2026-08-10T09:00:00Z",
  },
  {
    id: "cc2",
    name: "Warehouse Ops",
    code: "WHS",
    budget_owner_membership_id: "ghost-membership-id",
    branch_id: "b1",
    is_orphaned: false,
    orphan_reason: null,
    is_archived: false,
    created_at: "2026-08-11T09:00:00Z",
  },
  {
    id: "cc3",
    name: "Legacy Ops",
    code: "LGC",
    budget_owner_membership_id: "m2",
    branch_id: "b2",
    is_orphaned: true,
    orphan_reason: "branch_deactivated",
    is_archived: false,
    created_at: "2026-08-12T09:00:00Z",
  },
  {
    id: "cc4",
    name: "Events",
    code: "EVN",
    budget_owner_membership_id: "ghost-membership-id",
    branch_id: null,
    is_orphaned: true,
    orphan_reason: "owner_removed",
    is_archived: false,
    created_at: "2026-08-13T09:00:00Z",
  },
  {
    id: "cc5",
    name: "Facilities",
    code: "FAC",
    budget_owner_membership_id: null,
    branch_id: null,
    is_orphaned: true,
    orphan_reason: null,
    is_archived: false,
    created_at: "2026-08-14T09:00:00Z",
  },
  {
    id: "cc6",
    name: "Old Admin",
    code: "ADM",
    budget_owner_membership_id: "m1",
    branch_id: null,
    is_orphaned: false,
    orphan_reason: null,
    is_archived: true,
    created_at: "2026-08-15T09:00:00Z",
  },
];

describe("CostCentreListComponent (T023)", () => {
  let component: CostCentreListComponent;
  let fixture: ComponentFixture<CostCentreListComponent>;
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
      "listCostCentres",
      "createCostCentre",
      "updateCostCentre",
      "listBranches",
    ]);
    apiService = jasmine.createSpyObj("ApiService", ["members"]);
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

    organisationApi.listCostCentres.and.returnValue(
      of({ items: mockCostCentres, next_cursor: null }),
    );
    organisationApi.listBranches.and.returnValue(of({ items: mockBranches, next_cursor: null }));
    apiService.members.and.returnValue(of({ items: mockMembers, next_cursor: null }));

    await TestBed.configureTestingModule({
      imports: [CostCentreListComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        { provide: OrganisationApiService, useValue: organisationApi },
        { provide: ApiService, useValue: apiService },
        { provide: SessionService, useValue: sessionMock },
      ],
    })
      .overrideComponent(CostCentreListComponent, {
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

    fixture = TestBed.createComponent(CostCentreListComponent);
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

  it("should load cost centres and reference data on init", () => {
    expect(organisationApi.listCostCentres).toHaveBeenCalledWith();
    expect(organisationApi.listBranches).toHaveBeenCalledWith();
    expect(apiService.members).toHaveBeenCalledWith();
    expect(component.costCentres().length).toBe(mockCostCentres.length);
    expect(component.isLoading()).toBeFalse();
    expect(component.errorMessage()).toBeNull();
  });

  it("should show the empty state when no cost centres exist", () => {
    organisationApi.listCostCentres.and.returnValue(of({ items: [], next_cursor: null }));
    component.loadCostCentres();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector(".empty-state")).toBeTruthy();
    expect(compiled.querySelector(".cost-centres-table")).toBeNull();
  });

  it("should resolve budget-owner emails and branch names with raw-ID fallbacks", () => {
    fixture.detectChanges();

    const firstRow = rowCells(0);
    expect(firstRow[2]).toBe("dana@example.com");
    expect(firstRow[3]).toBe("Organisation-wide");

    const secondRow = rowCells(1);
    expect(secondRow[2]).toBe("ghost-membership-id");
    expect(secondRow[3]).toBe("Main Branch");

    const unownedRow = rowCells(4);
    expect(unownedRow[2]).toBe("—");
  });

  it("should open the create dialog and reload with a success snack-bar on close", () => {
    const createdCostCentre: CostCentre = { ...mockCostCentres[0], id: "cc9", name: "R&D" };
    organisationApi.createCostCentre.and.returnValue(of(createdCostCentre));
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(createdCostCentre),
    } as MatDialogRef<unknown, unknown>);

    component.openCreateDialog();

    const [dialogType, config] = dialogSpy.open.calls.mostRecent().args;
    expect(dialogType).toBe(CostCentreFormDialogComponent);
    expect((config as { data: CostCentreFormDialogData }).data).toEqual({ mode: "create" });
    expect(organisationApi.listCostCentres).toHaveBeenCalledTimes(2);
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      "Cost centre created successfully.",
      undefined,
      { duration: 3500 },
    );
  });

  it("should pass the existing cost centre to the edit dialog pre-filled and reload on success", () => {
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(mockCostCentres[0]),
    } as MatDialogRef<unknown, unknown>);

    component.openEditDialog(mockCostCentres[0]);

    const [dialogType, config] = dialogSpy.open.calls.mostRecent().args;
    expect(dialogType).toBe(CostCentreFormDialogComponent);
    expect((config as { data: CostCentreFormDialogData }).data).toEqual({
      mode: "edit",
      costCentre: mockCostCentres[0],
    });
    expect(organisationApi.listCostCentres).toHaveBeenCalledTimes(2);
  });

  it("should archive a cost centre after explicit confirmation without a dependents flow", () => {
    organisationApi.updateCostCentre.and.returnValue(of({ ...mockCostCentres[0], is_archived: true }));
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(true),
    } as MatDialogRef<unknown, boolean>);

    component.openArchiveDialog(mockCostCentres[0]);

    const [dialogType, config] = dialogSpy.open.calls.mostRecent().args;
    expect(dialogType).toBe(CatalogueConfirmDialogComponent);
    const data = (config as { data: ConfirmDialogData }).data;
    expect(data.titleKey).toBe("organisation.costCentres.archiveDialog.title");
    expect(data.messageKey).toBe("organisation.costCentres.archiveDialog.message");
    expect(data.itemName).toBe("Marketing");
    expect(data.isDestructive).toBeTrue();

    expect(organisationApi.updateCostCentre).toHaveBeenCalledWith("cc1", { is_archived: true });
    expect(organisationApi.listCostCentres).toHaveBeenCalledTimes(2);
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      "Cost centre archived successfully.",
      undefined,
      { duration: 3500 },
    );
  });

  it("should not archive or reload when confirmation is cancelled", () => {
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(false),
    } as MatDialogRef<unknown, boolean>);

    component.openArchiveDialog(mockCostCentres[0]);

    expect(organisationApi.updateCostCentre).not.toHaveBeenCalled();
    expect(organisationApi.listCostCentres).toHaveBeenCalledTimes(1);
    expect(snackBarSpy.open).not.toHaveBeenCalled();
  });

  it("should render orphan badges with reason-specific tooltips for each reason", () => {
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelectorAll(".status-orphaned").length).toBe(3);

    expect(component.orphanReasonKey(mockCostCentres[2])).toBe(
      "organisation.costCentres.orphanReasons.branch_deactivated",
    );
    expect(component.orphanReasonKey(mockCostCentres[3])).toBe(
      "organisation.costCentres.orphanReasons.owner_removed",
    );
    expect(component.orphanReasonKey(mockCostCentres[4])).toBeNull();
    expect(component.orphanReasonKey(mockCostCentres[0])).toBeNull();

    const translate = TestBed.inject(TranslateService);
    expect(translate.instant(component.orphanReasonKey(mockCostCentres[2]) as string)).toContain(
      "deactivated",
    );
    expect(translate.instant(component.orphanReasonKey(mockCostCentres[3]) as string)).toContain(
      "removed",
    );
  });

  it("should hide the archive action on already-archived rows", () => {
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelectorAll(".danger-action").length).toBe(
      mockCostCentres.filter((cc) => !cc.is_archived).length,
    );
    expect(rowCells(5)[4]).toBe("Archived");
  });

  it("should surface load failures through the error banner with trace id", () => {
    const error500 = new HttpErrorResponse({
      status: 500,
      error: { code: "internal", message: "Boom", trace_id: "tr_500" },
    });
    organisationApi.listCostCentres.and.returnValue(throwError(() => error500));

    component.loadCostCentres();
    fixture.detectChanges();

    expect(component.errorMessage()).toBe("Boom");
    expect(component.errorTraceId()).toBe("tr_500");
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector(".error-banner")).toBeTruthy();
  });

  it("should hide create/edit/archive affordances for non-owner roles", () => {
    expect(component.isOwner()).toBeTrue();

    roleSignal.set("viewer");
    fixture.detectChanges();

    expect(component.isOwner()).toBeFalse();
    expect(component.displayedColumns()).not.toContain("actions");
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector(".action-btn")).toBeNull();
    expect(compiled.querySelector(".danger-action")).toBeNull();
    expect(compiled.querySelectorAll(".actions-cell").length).toBe(0);
  });
});

describe("CostCentreFormDialogComponent (T023)", () => {
  let dialogRefSpy: jasmine.SpyObj<MatDialogRef<CostCentreFormDialogComponent, unknown>>;
  let organisationApi: jasmine.SpyObj<OrganisationApiService>;
  let apiService: jasmine.SpyObj<ApiService>;

  async function createDialog(data: CostCentreFormDialogData): Promise<{
    component: CostCentreFormDialogComponent;
    fixture: ComponentFixture<CostCentreFormDialogComponent>;
  }> {
    await TestBed.configureTestingModule({
      imports: [CostCentreFormDialogComponent, TranslateModule.forRoot()],
      providers: [
        { provide: OrganisationApiService, useValue: organisationApi },
        { provide: ApiService, useValue: apiService },
        { provide: MatDialogRef, useValue: dialogRefSpy },
        { provide: MAT_DIALOG_DATA, useValue: data },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation("en", enCatalog);
    translate.use("en");

    const fixture = TestBed.createComponent(CostCentreFormDialogComponent);
    const component = fixture.componentInstance;
    fixture.detectChanges();
    return { component, fixture };
  }

  beforeEach(() => {
    organisationApi = jasmine.createSpyObj("OrganisationApiService", [
      "listBranches",
      "createCostCentre",
      "updateCostCentre",
    ]);
    apiService = jasmine.createSpyObj("ApiService", ["members"]);
    dialogRefSpy = jasmine.createSpyObj("MatDialogRef", ["close"]);

    organisationApi.listBranches.and.returnValue(of({ items: mockBranches, next_cursor: null }));
    apiService.members.and.returnValue(of({ items: mockMembers, next_cursor: null }));
  });

  it("should load members and branches for the pickers on init", async () => {
    await createDialog({ mode: "create" });

    expect(apiService.members).toHaveBeenCalledWith();
    expect(organisationApi.listBranches).toHaveBeenCalledWith();
  });

  it("should submit a create with unset pickers sent as nulls and close with the result", async () => {
    const { component } = await createDialog({ mode: "create" });

    expect(component.isEditMode).toBeFalse();
    expect(component.form.controls.budget_owner_membership_id.value).toBeNull();
    expect(component.form.controls.branch_id.value).toBeNull();

    const created: CostCentre = { ...mockCostCentres[0], id: "cc9" };
    organisationApi.createCostCentre.and.returnValue(of(created));

    component.form.controls.name.setValue("Research & Development");
    component.form.controls.code.setValue("RND");
    component.onSubmit();

    expect(organisationApi.createCostCentre).toHaveBeenCalledWith({
      name: "Research & Development",
      code: "RND",
      budget_owner_membership_id: null,
      branch_id: null,
    });
    expect(organisationApi.updateCostCentre).not.toHaveBeenCalled();
    expect(dialogRefSpy.close).toHaveBeenCalledWith(created);
  });

  it("should pre-fill the form in edit mode and submit an update", async () => {
    const { component } = await createDialog({ mode: "edit", costCentre: mockCostCentres[1] });

    expect(component.isEditMode).toBeTrue();
    expect(component.form.controls.name.value).toBe("Warehouse Ops");
    expect(component.form.controls.code.value).toBe("WHS");
    expect(component.form.controls.budget_owner_membership_id.value).toBe("ghost-membership-id");
    expect(component.form.controls.branch_id.value).toBe("b1");

    const updated: CostCentre = { ...mockCostCentres[1], name: "Fulfilment Ops", branch_id: null };
    organisationApi.updateCostCentre.and.returnValue(of(updated));

    component.form.controls.name.setValue("Fulfilment Ops");
    component.form.controls.branch_id.setValue(null);
    component.onSubmit();

    expect(organisationApi.updateCostCentre).toHaveBeenCalledWith("cc2", {
      name: "Fulfilment Ops",
      code: "WHS",
      budget_owner_membership_id: "ghost-membership-id",
      branch_id: null,
    });
    expect(organisationApi.createCostCentre).not.toHaveBeenCalled();
    expect(dialogRefSpy.close).toHaveBeenCalledWith(updated);
  });

  it("should block submission while required fields are missing", async () => {
    const { component } = await createDialog({ mode: "create" });

    component.onSubmit();

    expect(organisationApi.createCostCentre).not.toHaveBeenCalled();
    expect(dialogRefSpy.close).not.toHaveBeenCalled();
    expect(component.form.controls.name.hasError("required")).toBeTrue();
    expect(component.form.controls.code.hasError("required")).toBeTrue();
  });

  it("should surface a duplicate-code 409 inline via duplicateCodeError and stay open", async () => {
    const { component, fixture } = await createDialog({ mode: "create" });

    const error409 = new HttpErrorResponse({
      status: 409,
      error: { code: "conflict", message: "code already exists", trace_id: "tr_409" },
    });
    organisationApi.createCostCentre.and.returnValue(throwError(() => error409));

    component.form.controls.name.setValue("Duplicate");
    component.form.controls.code.setValue("MKT");
    component.onSubmit();
    fixture.detectChanges();

    expect(component.errorMessage()).toBe(
      "This code is already in use by another cost centre in your organisation. Cost centre codes must be unique.",
    );
    expect(component.isSubmitting()).toBeFalse();
    expect(dialogRefSpy.close).not.toHaveBeenCalled();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector(".error-banner")?.textContent).toContain(
      "This code is already in use",
    );
  });

  it("should surface non-conflict errors using the API message instead", async () => {
    const { component } = await createDialog({ mode: "edit", costCentre: mockCostCentres[0] });

    const error500 = new HttpErrorResponse({
      status: 500,
      error: { code: "internal", message: "Boom", trace_id: "tr_500" },
    });
    organisationApi.updateCostCentre.and.returnValue(throwError(() => error500));

    component.onSubmit();

    expect(component.errorMessage()).toBe("Boom");
    expect(component.errorTraceId()).toBe("tr_500");
    expect(component.errorMessage()).not.toBe(
      "This code is already in use by another cost centre in your organisation. Cost centre codes must be unique.",
    );
    expect(dialogRefSpy.close).not.toHaveBeenCalled();
  });
});
