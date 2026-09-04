import { HttpErrorResponse } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { MatSnackBar } from '@angular/material/snack-bar';
import { provideRouter } from '@angular/router';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';

import enCatalog from '../../../../../../packages/i18n/en.json';
import { ApiService } from '../../core/api/api.service';
import type { Invitation, Member, Role } from '../../core/api/models';
import { SessionService } from '../../core/auth/session.service';
import { TeamComponent } from './team.component';

describe('TeamComponent (T057)', () => {
  let component: TeamComponent;
  let fixture: ComponentFixture<TeamComponent>;
  let apiService: jasmine.SpyObj<ApiService>;
  let sessionService: jasmine.SpyObj<SessionService>;
  let dialogSpy: jasmine.SpyObj<MatDialog>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;

  const mockMembers: Member[] = [
    {
      id: 'm1',
      email: 'owner@example.com',
      role: 'owner',
      status: 'active',
      mfa_enabled: true,
      created_at: '2026-08-20T10:00:00Z',
    },
    {
      id: 'm2',
      email: 'buyer@example.com',
      role: 'buyer',
      status: 'active',
      mfa_enabled: false,
      created_at: '2026-08-20T11:00:00Z',
    },
  ];

  const mockInvitations: Invitation[] = [
    {
      id: 'inv1',
      email: 'pending@example.com',
      role: 'approver',
      status: 'pending',
      expires_at: '2026-08-27T10:00:00Z',
    },
  ];

  beforeEach(async () => {
    apiService = jasmine.createSpyObj('ApiService', [
      'members',
      'invitations',
      'changeMemberRole',
      'createBranchRoleAssignment',
      'removeMember',
      'revokeInvitation',
    ]);
    sessionService = jasmine.createSpyObj('SessionService', ['hasRole', 'currentMember', 'role']);
    dialogSpy = jasmine.createSpyObj('MatDialog', ['open']);
    snackBarSpy = jasmine.createSpyObj('MatSnackBar', ['open']);

    apiService.members.and.returnValue(of({ items: mockMembers, next_cursor: null }));
    apiService.invitations.and.returnValue(of({ items: mockInvitations }));
    sessionService.hasRole.and.returnValue(true);

    await TestBed.configureTestingModule({
      imports: [TeamComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        { provide: ApiService, useValue: apiService },
        { provide: SessionService, useValue: sessionService },
      ],
    })
      .overrideComponent(TeamComponent, {
        set: {
          providers: [
            { provide: MatDialog, useValue: dialogSpy },
            { provide: MatSnackBar, useValue: snackBarSpy },
          ],
        },
      })
      .compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(TeamComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should load members and invitations on init', () => {
    expect(apiService.members).toHaveBeenCalled();
    expect(apiService.invitations).toHaveBeenCalled();
    expect(component.members().length).toBe(2);
    expect(component.invitations().length).toBe(1);
  });

  it('should update member role when changed successfully', () => {
    const updatedMember: Member = { ...mockMembers[1], role: 'approver' };
    apiService.changeMemberRole.and.returnValue(of(updatedMember));

    dialogSpy.open.and.returnValue({
      afterClosed: () => of({ role: 'approver' as Role, branchId: null }),
    } as MatDialogRef<unknown, unknown>);

    component.openChangeRoleDialog(mockMembers[1]);

    expect(apiService.changeMemberRole).toHaveBeenCalledWith('m2', 'approver');
    expect(component.members().find((m) => m.id === 'm2')?.role).toBe('approver');
    expect(snackBarSpy.open).toHaveBeenCalled();
    expect(apiService.createBranchRoleAssignment).not.toHaveBeenCalled();
  });

  it('should display specific 409 error message when server refuses last owner demotion/removal', () => {
    const error409 = new HttpErrorResponse({
      status: 409,
      error: {
        code: 'last_owner',
        message: 'Cannot demote the last owner',
        trace_id: 'tr_409',
      },
    });
    apiService.changeMemberRole.and.returnValue(throwError(() => error409));

    dialogSpy.open.and.returnValue({
      afterClosed: () => of({ role: 'viewer' as Role, branchId: null }),
    } as MatDialogRef<unknown, unknown>);

    component.openChangeRoleDialog(mockMembers[0]);

    expect(component.errorMessage()).toContain('must retain at least one active owner');
    expect(component.errorTraceId()).toBe('tr_409');
  });

  it('should assign the branch only AFTER the role change succeeds, in that order', () => {
    // The backend requires the membership to already hold branch_manager/approver before an
    // assignment can be created — so the role PATCH must complete first, never alongside it.
    const updatedMember: Member = { ...mockMembers[1], role: 'branch_manager' };
    apiService.changeMemberRole.and.returnValue(of(updatedMember));
    apiService.createBranchRoleAssignment.and.returnValue(
      of({ id: 'bra1', membership_id: 'm2', branch_id: 'b1', created_at: '2026-08-23T09:00:00Z' }),
    );

    dialogSpy.open.and.returnValue({
      afterClosed: () => of({ role: 'branch_manager' as Role, branchId: 'b1' }),
    } as MatDialogRef<unknown, unknown>);

    component.openChangeRoleDialog(mockMembers[1]);

    expect(apiService.changeMemberRole).toHaveBeenCalledWith('m2', 'branch_manager');
    expect(apiService.createBranchRoleAssignment).toHaveBeenCalledWith({
      membership_id: 'm2',
      branch_id: 'b1',
    });
    expect(component.members().find((m) => m.id === 'm2')?.role).toBe('branch_manager');
  });

  it('should not attempt a branch assignment when the role change itself fails', () => {
    apiService.changeMemberRole.and.returnValue(
      throwError(
        () =>
          new HttpErrorResponse({
            status: 500,
            error: { code: 'internal', message: 'Boom', trace_id: 'tr_500' },
          }),
      ),
    );

    dialogSpy.open.and.returnValue({
      afterClosed: () => of({ role: 'branch_manager' as Role, branchId: 'b1' }),
    } as MatDialogRef<unknown, unknown>);

    component.openChangeRoleDialog(mockMembers[1]);

    expect(apiService.createBranchRoleAssignment).not.toHaveBeenCalled();
  });

  it('should surface a duplicate-assignment message via a snack bar without touching the role-change error state', () => {
    const updatedMember: Member = { ...mockMembers[1], role: 'branch_manager' };
    apiService.changeMemberRole.and.returnValue(of(updatedMember));
    apiService.createBranchRoleAssignment.and.returnValue(
      throwError(
        () =>
          new HttpErrorResponse({
            status: 409,
            error: { code: 'conflict', message: 'duplicate', trace_id: 'tr_409b' },
          }),
      ),
    );

    dialogSpy.open.and.returnValue({
      afterClosed: () => of({ role: 'branch_manager' as Role, branchId: 'b1' }),
    } as MatDialogRef<unknown, unknown>);

    component.openChangeRoleDialog(mockMembers[1]);

    // The role change DID succeed — that's not treated as a failure just because the
    // subsequent assignment failed.
    expect(component.members().find((m) => m.id === 'm2')?.role).toBe('branch_manager');
    expect(component.errorMessage()).toBeNull();
    expect(snackBarSpy.open).toHaveBeenCalledWith(
      enCatalog.team.changeRoleDialog.duplicateAssignmentError,
      undefined,
      { duration: 5000 },
    );
  });

  it('should remove member when confirmed', () => {
    apiService.removeMember.and.returnValue(of(undefined));
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(true),
    } as MatDialogRef<unknown, unknown>);

    component.openRemoveMemberDialog(mockMembers[1]);

    expect(apiService.removeMember).toHaveBeenCalledWith('m2');
    expect(apiService.members).toHaveBeenCalledTimes(2);
    expect(snackBarSpy.open).toHaveBeenCalled();
  });

  it('should revoke invitation when confirmed', () => {
    apiService.revokeInvitation.and.returnValue(of(undefined));
    dialogSpy.open.and.returnValue({
      afterClosed: () => of(true),
    } as MatDialogRef<unknown, unknown>);

    component.openRevokeInvitationDialog(mockInvitations[0]);

    expect(apiService.revokeInvitation).toHaveBeenCalledWith('inv1');
    expect(apiService.invitations).toHaveBeenCalledTimes(2);
    expect(snackBarSpy.open).toHaveBeenCalled();
  });
});
