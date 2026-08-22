import { HttpErrorResponse } from "@angular/common/http";
import type { ComponentFixture } from "@angular/core/testing";
import { TestBed } from "@angular/core/testing";
import { signal } from "@angular/core";
import { MAT_DIALOG_DATA, MatDialog, MatDialogRef } from "@angular/material/dialog";
import { MatSnackBar } from "@angular/material/snack-bar";
import { provideRouter } from "@angular/router";
import { TranslateModule, TranslateService } from "@ngx-translate/core";
import type { WritableSignal } from "@angular/core";
import { of, throwError } from "rxjs";

import enCatalog from "../../../../../../../packages/i18n/en.json";
import type { Branch, Role } from "../../../core/api/models";
import { SessionService } from "../../../core/auth/session.service";
import { OrganisationApiService } from "../organisation-api";
import {
  BranchFormDialogComponent,
  BranchFormDialogData,
} from "./branch-form-dialog/branch-form-dialog.component";
import { BranchListComponent } from "./branch-list.component";
import {
  BranchDependentsConfirmDialogComponent,
  DependentsConfirmDialogData,
} from "./dependents-confirm-dialog/dependents-confirm-dialog.component";

const mockBranches: Branch[] = [
  {
    id: "b1",
    name: "Main Branch",
    address: "12 High St",
    region: "GB",
    is_active: true,
    created_at: "2026-08-20T10:00:00Z",
  },
  {
    id: "b2",
    name: "Coastal Branch",
    address: null,
    region: null,
    is_active: false,
    created_at: "2026-08-21T10:00:00Z",
  },
];

describe("BranchListComponent (T016)", () => {
  let component: BranchListComponent;
  let fixture: ComponentFixture<BranchListComponent>;
  let organisationApi: jasmine.SpyObj<OrganisationApiService>;
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
      "listBranches",
      "createBranch",
      "updateBranch",
    ]);
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

    organisationApi.listBranches.and.returnValue(of({ items: mockBranches, next_cursor: null }));

    await TestBed.configureTestingModule({
      imports: [BranchListComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        { provide: OrganisationApiService, useValue: organisationApi },
        { provide: SessionService, useValue: sessionMock },
      ],
    })
      .overrideComponent(BranchListComponent, {
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

    fixture = TestBed.createComponent(BranchListComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it("should load branches on init", () => {
    expect(organisationApi.listBranches).toHaveBeenCalledWith();
    expect(component.branches().length).toBe(2);
    expect(component.branches()[0].name).toBe("Main Branch");
    expect(component.isLoading()).toBeFalse();
  });

  it("should show the empty state when no branches exist", () => {
    organisationApi.listBranches.and.returnValue(of({ items: [], next_cursor: null }));
    component.loadBranches();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector(".empty-state")).toBeTruthy();
    expect(compiled.querySelector(".branches-table")).toBeNull();
  });

  it("should open the create dialog and reload with a success snack-bar on close", () => {
    const createdBranch: Branch = {
      id: "b3",
      name: "Delta Branch",
      address: null,
      region: null,
      is_active: true,
      created_at: "2026-08-22T10:00:00Z",
    };
    organisationApi.createBranch.and.returnValue(of(createdBranch));
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(createdBranch),
    } as MatDialogRef<unknown, unknown>);

    component.openCreateDialog();

    const [dialogType, config] = dialogSpy.open.calls.mostRecent().args;
    expect(dialogType).toBe(BranchFormDialogComponent);
    expect((config as { data: BranchFormDialogData }).data).toEqual({ mode: "create" });
    expect(organisationApi.listBranches).toHaveBeenCalledTimes(2);
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      "Branch created successfully.",
      undefined,
      { duration: 3500 },
    );
  });

  it("should pass the existing branch to the edit dialog pre-filled and reload on success", () => {
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(mockBranches[0]),
    } as MatDialogRef<unknown, unknown>);

    component.openEditDialog(mockBranches[0]);

    const [dialogType, config] = dialogSpy.open.calls.mostRecent().args;
    expect(dialogType).toBe(BranchFormDialogComponent);
    expect((config as { data: BranchFormDialogData }).data).toEqual({
      mode: "edit",
      branch: mockBranches[0],
    });

    // The dialog itself pre-fills from that branch (see BranchFormDialogComponent suite below).
    expect(
      (config as { data: BranchFormDialogData }).data.branch?.name,
    ).toBe(mockBranches[0].name);

    expect(organisationApi.listBranches).toHaveBeenCalledTimes(2);
  });

  it("should deactivate a branch directly when there are no dependents", () => {
    organisationApi.updateBranch.and.returnValue(of(mockBranches[1]));

    component.deactivateBranch(mockBranches[1]);

    expect(organisationApi.updateBranch).toHaveBeenCalledWith("b2", { is_active: false });
    expect(organisationApi.listBranches).toHaveBeenCalledTimes(2);
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      "Branch deactivated successfully.",
      undefined,
      { duration: 3500 },
    );
    expect(dialogSpy.open).not.toHaveBeenCalled();
  });

  it("should confirm dependents via the dialog and retry with confirm_dependents on a 422", () => {
    const error422 = new HttpErrorResponse({
      status: 422,
      error: {
        code: "dependents_confirmation_required",
        message: "Dependents must be confirmed",
        trace_id: "tr_422",
        details: {
          reason: "dependents_confirmation_required",
          cost_centre_count: 2,
          branch_role_assignment_count: 3,
        },
      },
    });
    organisationApi.updateBranch.and.returnValues(
      throwError(() => error422),
      of(mockBranches[1]),
    );
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(true),
    } as MatDialogRef<unknown, boolean>);

    component.deactivateBranch(mockBranches[1]);

    expect(dialogSpy.open).toHaveBeenCalledTimes(1);
    const [dialogType, config] = dialogSpy.open.calls.mostRecent().args;
    expect(dialogType).toBe(BranchDependentsConfirmDialogComponent);
    expect((config as { data: DependentsConfirmDialogData }).data).toEqual({
      dependentCount: 5,
    });

    expect(organisationApi.updateBranch).toHaveBeenCalledWith("b2", { is_active: false });
    expect(organisationApi.updateBranch).toHaveBeenCalledWith("b2", {
      is_active: false,
      confirm_dependents: true,
    });
    expect(organisationApi.listBranches).toHaveBeenCalledTimes(2);
    expect(snackBarSpy.open).toHaveBeenCalled();
    expect(component.errorMessage()).toBeNull();
  });

  it("should not retry or reload when the dependents confirmation is cancelled", () => {
    const error422 = new HttpErrorResponse({
      status: 422,
      error: {
        code: "dependents_confirmation_required",
        message: "Dependents must be confirmed",
        trace_id: "tr_422",
        details: {
          reason: "dependents_confirmation_required",
          cost_centre_count: 1,
          branch_role_assignment_count: 0,
        },
      },
    });
    organisationApi.updateBranch.and.returnValue(throwError(() => error422));
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(false),
    } as MatDialogRef<unknown, boolean>);

    component.deactivateBranch(mockBranches[1]);

    expect(organisationApi.updateBranch).toHaveBeenCalledTimes(1);
    expect(organisationApi.updateBranch).toHaveBeenCalledWith("b2", { is_active: false });
    expect(organisationApi.listBranches).toHaveBeenCalledTimes(1);
    expect(snackBarSpy.open).not.toHaveBeenCalled();
    expect(component.errorMessage()).toBeNull();
  });

  it("should surface generic API errors through the error banner with trace id", () => {
    const error500 = new HttpErrorResponse({
      status: 500,
      error: { code: "internal", message: "Boom", trace_id: "tr_500" },
    });
    organisationApi.updateBranch.and.returnValue(throwError(() => error500));

    component.deactivateBranch(mockBranches[1]);

    expect(component.errorMessage()).toBe("Boom");
    expect(component.errorTraceId()).toBe("tr_500");
    expect(snackBarSpy.open).not.toHaveBeenCalled();
  });

  it("should hide create/edit/deactivate affordances for non-owner roles", () => {
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

describe("BranchFormDialogComponent (T016)", () => {
  let dialogRefSpy: jasmine.SpyObj<MatDialogRef<BranchFormDialogComponent, unknown>>;
  let organisationApi: jasmine.SpyObj<OrganisationApiService>;

  async function createDialog(data: BranchFormDialogData): Promise<{
    component: BranchFormDialogComponent;
    fixture: ComponentFixture<BranchFormDialogComponent>;
  }> {
    await TestBed.configureTestingModule({
      imports: [BranchFormDialogComponent, TranslateModule.forRoot()],
      providers: [
        { provide: OrganisationApiService, useValue: organisationApi },
        { provide: MatDialogRef, useValue: dialogRefSpy },
        { provide: MAT_DIALOG_DATA, useValue: data },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation("en", enCatalog);
    translate.use("en");

    const fixture = TestBed.createComponent(BranchFormDialogComponent);
    const component = fixture.componentInstance;
    fixture.detectChanges();
    return { component, fixture };
  }

  beforeEach(() => {
    organisationApi = jasmine.createSpyObj("OrganisationApiService", [
      "createBranch",
      "updateBranch",
    ]);
    dialogRefSpy = jasmine.createSpyObj("MatDialogRef", ["close"]);
  });

  it("should pre-fill the form when opened in edit mode and submit an update", async () => {
    const { component } = await createDialog({ mode: "edit", branch: mockBranches[0] });

    expect(component.isEditMode).toBeTrue();
    expect(component.form.controls.name.value).toBe("Main Branch");
    expect(component.form.controls.address.value).toBe("12 High St");
    expect(component.form.controls.region.value).toBe("GB");

    const updatedBranch: Branch = { ...mockBranches[0], name: "Renamed Branch" };
    organisationApi.updateBranch.and.returnValue(of(updatedBranch));

    component.form.controls.name.setValue("Renamed Branch");
    component.onSubmit();

    expect(organisationApi.updateBranch).toHaveBeenCalledWith("b1", {
      name: "Renamed Branch",
      address: "12 High St",
      region: "GB",
    });
    expect(organisationApi.createBranch).not.toHaveBeenCalled();
    expect(dialogRefSpy.close).toHaveBeenCalledWith(updatedBranch);
  });

  it("should submit a create and close with the new branch in create mode", async () => {
    const { component } = await createDialog({ mode: "create" });

    expect(component.isEditMode).toBeFalse();
    expect(component.form.controls.name.value).toBe("");

    const createdBranch: Branch = {
      id: "b9",
      name: "Harbour Branch",
      address: null,
      region: "AE",
      is_active: true,
      created_at: "2026-08-22T09:00:00Z",
    };
    organisationApi.createBranch.and.returnValue(of(createdBranch));

    component.form.controls.name.setValue("Harbour Branch");
    component.form.controls.region.setValue("AE");
    component.onSubmit();

    expect(organisationApi.createBranch).toHaveBeenCalledWith({
      name: "Harbour Branch",
      address: null,
      region: "AE",
    });
    expect(organisationApi.updateBranch).not.toHaveBeenCalled();
    expect(dialogRefSpy.close).toHaveBeenCalledWith(createdBranch);
  });

  it("should block submission while the required name is missing", async () => {
    const { component } = await createDialog({ mode: "create" });

    component.onSubmit();

    expect(organisationApi.createBranch).not.toHaveBeenCalled();
    expect(dialogRefSpy.close).not.toHaveBeenCalled();
    expect(component.form.controls.name.hasError("required")).toBeTrue();
  });

  it("should show API errors inline instead of closing the dialog", async () => {
    const { component } = await createDialog({ mode: "create" });

    const error409 = new HttpErrorResponse({
      status: 409,
      error: { code: "conflict", message: "Duplicate branch name", trace_id: "tr_409" },
    });
    organisationApi.createBranch.and.returnValue(throwError(() => error409));

    component.form.controls.name.setValue("Any Branch");
    component.onSubmit();

    expect(component.errorMessage()).toBe("Duplicate branch name");
    expect(component.errorTraceId()).toBe("tr_409");
    expect(component.isSubmitting()).toBeFalse();
    expect(dialogRefSpy.close).not.toHaveBeenCalled();
  });
});
