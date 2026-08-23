import type { ComponentFixture } from "@angular/core/testing";
import { TestBed } from "@angular/core/testing";
import { MAT_DIALOG_DATA, MatDialogRef } from "@angular/material/dialog";
import { provideNoopAnimations } from "@angular/platform-browser/animations";
import { TranslateModule, TranslateService } from "@ngx-translate/core";
import { of, throwError } from "rxjs";

import enCatalog from "../../../../../../../packages/i18n/en.json";
import { ApiService } from "../../../core/api/api.service";
import type { Branch, Member } from "../../../core/api/models";
import {
  ChangeRoleDialogComponent,
  type ChangeRoleDialogResult,
} from "./change-role-dialog.component";

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
  let dialogRefSpy: jasmine.SpyObj<MatDialogRef<ChangeRoleDialogComponent, ChangeRoleDialogResult>>;
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
    apiService = jasmine.createSpyObj("ApiService", ["listBranches"]);
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

  it("should close with the role and a null branchId when no branch is involved", async () => {
    const { component } = await createDialog();

    component.form.controls.role.setValue("viewer");
    component.onConfirm();

    expect(dialogRefSpy.close).toHaveBeenCalledWith({ role: "viewer", branchId: null });
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

  it("should close with branchId: null when a branch-scopable role is confirmed without a branch", async () => {
    const { component } = await createDialog();

    component.form.controls.role.setValue("branch_manager");
    component.onConfirm();

    // Assigning a branch is optional — a plain role change must still go through.
    expect(dialogRefSpy.close).toHaveBeenCalledWith({ role: "branch_manager", branchId: null });
  });

  it("should close with the picked branchId alongside the role — it does NOT call the API itself", async () => {
    const { component } = await createDialog();

    component.form.controls.role.setValue("approver");
    component.form.controls.branch_id.setValue("b1");

    component.onConfirm();

    // The dialog only COLLECTS the pick; the parent (TeamComponent) sequences the role change
    // and the assignment as two separate API calls, in that order — see the component's own
    // doc comment on ChangeRoleDialogResult for why.
    expect(dialogRefSpy.close).toHaveBeenCalledWith({ role: "approver", branchId: "b1" });
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

  it("should cancel without a close value", async () => {
    const { component } = await createDialog();

    component.onCancel();

    expect(dialogRefSpy.close).toHaveBeenCalledOnceWith();
  });
});
