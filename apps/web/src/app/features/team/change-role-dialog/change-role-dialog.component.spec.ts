import { HttpErrorResponse } from "@angular/common/http";
import type { ComponentFixture } from "@angular/core/testing";
import { TestBed } from "@angular/core/testing";
import { MAT_DIALOG_DATA, MatDialogRef } from "@angular/material/dialog";
import { provideNoopAnimations } from "@angular/platform-browser/animations";
import { TranslateModule, TranslateService } from "@ngx-translate/core";
import { of, throwError } from "rxjs";

import enCatalog from "../../../../../../../packages/i18n/en.json";
import { ApiService } from "../../../core/api/api.service";
import type { Branch, Member, Role } from "../../../core/api/models";
import { ChangeRoleDialogComponent } from "./change-role-dialog.component";

const mockMember: Member = {
  id: "m1",
  email: "buyer@acme.test",
  role: "buyer",
  status: "active",
  mfa_enabled: false,
  created_at: "2026-08-01T09:00:00Z",
};

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

describe("ChangeRoleDialogComponent (T037)", () => {
  let dialogRefSpy: jasmine.SpyObj<MatDialogRef<ChangeRoleDialogComponent, Role>>;
  let apiService: jasmine.SpyObj<ApiService>;

  async function createDialog(
    member: Member = mockMember,
  ): Promise<{
    component: ChangeRoleDialogComponent;
    fixture: ComponentFixture<ChangeRoleDialogComponent>;
  }> {
    await TestBed.configureTestingModule({
      imports: [ChangeRoleDialogComponent, TranslateModule.forRoot()],
      providers: [
        provideNoopAnimations(),
        { provide: ApiService, useValue: apiService },
        { provide: MatDialogRef, useValue: dialogRefSpy },
        { provide: MAT_DIALOG_DATA, useValue: { member } },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation("en", enCatalog);
    translate.use("en");

    const fixture = TestBed.createComponent(ChangeRoleDialogComponent);
    const component = fixture.componentInstance;
    fixture.detectChanges();
    return { component, fixture };
  }

  function fieldLabels(fixture: ComponentFixture<ChangeRoleDialogComponent>): readonly string[] {
    const compiled = fixture.nativeElement as HTMLElement;
    return Array.from(compiled.querySelectorAll("mat-label")).map((label) =>
      (label.textContent ?? "").trim(),
    );
  }

  beforeEach(() => {
    apiService = jasmine.createSpyObj("ApiService", [
      "listBranches",
      "createBranchRoleAssignment",
    ]);
    dialogRefSpy = jasmine.createSpyObj("MatDialogRef", ["close"]);

    apiService.listBranches.and.returnValue(of({ items: mockBranches, next_cursor: null }));
  });

  it("should render the role select with exactly the five workspace roles", async () => {
    const { component, fixture } = await createDialog();

    expect(component.roles).toEqual(["owner", "buyer", "branch_manager", "approver", "viewer"]);

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector("mat-select[formcontrolname='role']")).toBeTruthy();
    const labels = fieldLabels(fixture);
    expect(labels).toContain("New Role");
    expect(labels).not.toContain("Assign to Branch");
  });

  it("should load branches for the picker on init", async () => {
    const { component } = await createDialog();

    expect(apiService.listBranches).toHaveBeenCalledWith();
    expect(component.branches().map((b) => b.id)).toEqual(["b1", "b2"]);
  });

  it("should fail soft when the branch list is unavailable and still open the dialog", async () => {
    apiService.listBranches.and.returnValue(throwError(() => new Error("offline")));

    const { component } = await createDialog();

    expect(component.branches()).toEqual([]);
    expect(component.form.controls.role.value).toBe("buyer");
    expect(dialogRefSpy.close).not.toHaveBeenCalled();
  });

  it("should disable confirm while the role is unchanged", async () => {
    const { fixture } = await createDialog();

    const submit = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
      "button[type=submit]",
    );
    expect(submit?.disabled).toBeTrue();
  });

  it("should close with just the selected role when no branch is involved", async () => {
    const { component } = await createDialog();

    component.form.controls.role.setValue("viewer");
    component.onConfirm();

    expect(apiService.createBranchRoleAssignment).not.toHaveBeenCalled();
    expect(dialogRefSpy.close).toHaveBeenCalledWith("viewer");
  });

  it("should show the branch picker only for branch_manager and approver", async () => {
    const { component, fixture } = await createDialog();

    component.form.controls.role.setValue("branch_manager");
    fixture.detectChanges();
    expect(fieldLabels(fixture)).toContain("Assign to Branch");

    component.form.controls.role.setValue("approver");
    fixture.detectChanges();
    expect(fieldLabels(fixture)).toContain("Assign to Branch");
    expect(component.branches().length).toBe(mockBranches.length);

    component.form.controls.role.setValue("owner");
    fixture.detectChanges();
    expect(fieldLabels(fixture)).not.toContain("Assign to Branch");

    component.form.controls.role.setValue("buyer");
    fixture.detectChanges();
    expect(fieldLabels(fixture)).not.toContain("Assign to Branch");

    component.form.controls.role.setValue("viewer");
    fixture.detectChanges();
    expect(fieldLabels(fixture)).not.toContain("Assign to Branch");
  });

  it("should close with just the role when a branch-scopable role is confirmed without a branch", async () => {
    const { component } = await createDialog();

    component.form.controls.role.setValue("branch_manager");
    component.onConfirm();

    // Assigning a branch is optional — a plain role change must still go through.
    expect(apiService.createBranchRoleAssignment).not.toHaveBeenCalled();
    expect(dialogRefSpy.close).toHaveBeenCalledWith("branch_manager");
  });

  it("should create the branch role assignment with the right payload before closing with the role", async () => {
    const { component } = await createDialog();

    component.form.controls.role.setValue("approver");
    component.form.controls.branch_id.setValue("b1");
    apiService.createBranchRoleAssignment.and.returnValue(
      of({
        id: "bra1",
        membership_id: mockMember.id,
        branch_id: "b1",
        created_at: "2026-08-20T09:00:00Z",
      }),
    );

    component.onConfirm();

    expect(apiService.createBranchRoleAssignment).toHaveBeenCalledTimes(1);
    expect(apiService.createBranchRoleAssignment).toHaveBeenCalledWith({
      membership_id: mockMember.id,
      branch_id: "b1",
    });
    expect(component.isSubmitting()).toBeFalse();
    expect(dialogRefSpy.close).toHaveBeenCalledWith("approver");
  });

  it("should keep the dialog open and show the duplicate-specific message on a 409", async () => {
    const { component, fixture } = await createDialog();

    const error409 = new HttpErrorResponse({
      status: 409,
      error: {
        code: "branch_role_assignment_duplicate",
        message: "duplicate assignment",
        trace_id: "tr_409",
      },
    });
    apiService.createBranchRoleAssignment.and.returnValue(throwError(() => error409));

    component.form.controls.role.setValue("branch_manager");
    component.form.controls.branch_id.setValue("b1");
    component.onConfirm();
    fixture.detectChanges();

    expect(component.errorMessage()).toBe(
      enCatalog.team.changeRoleDialog.duplicateAssignmentError,
    );
    expect(dialogRefSpy.close).not.toHaveBeenCalled();
    expect(component.isSubmitting()).toBeFalse();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector(".error-banner")?.textContent).toContain(
      enCatalog.team.changeRoleDialog.duplicateAssignmentError,
    );
  });

  it("should surface non-409 assignment failures inline with the API message and trace id", async () => {
    const { component, fixture } = await createDialog();

    const error500 = new HttpErrorResponse({
      status: 500,
      error: { code: "internal", message: "Boom", trace_id: "tr_500" },
    });
    apiService.createBranchRoleAssignment.and.returnValue(throwError(() => error500));

    component.form.controls.role.setValue("approver");
    component.form.controls.branch_id.setValue("b1");
    component.onConfirm();
    fixture.detectChanges();

    expect(component.errorMessage()).toBe("Boom");
    expect(component.errorTraceId()).toBe("tr_500");
    expect(dialogRefSpy.close).not.toHaveBeenCalled();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector(".error-banner")?.textContent).toContain("Boom");
  });

  it("should clear a previously-picked branch when the role changes away from branch-scopable", async () => {
    const { component } = await createDialog();

    component.form.controls.role.setValue("branch_manager");
    component.form.controls.branch_id.setValue("b1");
    expect(component.form.controls.branch_id.value).toBe("b1");

    component.form.controls.role.setValue("buyer");
    expect(component.form.controls.branch_id.value).toBeNull();
    expect(component.selectedRole()).toBe("buyer");
  });

  it("should cancel without calling the assignment endpoint or a close value", async () => {
    const { component } = await createDialog();

    component.onCancel();

    expect(apiService.createBranchRoleAssignment).not.toHaveBeenCalled();
    expect(dialogRefSpy.close).toHaveBeenCalledOnceWith();
  });
});
