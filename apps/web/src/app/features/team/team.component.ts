import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { MatTabsModule } from '@angular/material/tabs';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { ApiService } from '../../core/api/api.service';
import type { ApiError, Invitation, Member, Role } from '../../core/api/models';
import { RoleDirective } from '../../core/auth/role.directive';
import { SessionService } from '../../core/auth/session.service';
import { FormatDatePipe } from '../../core/format';
import { ChangeRoleDialogComponent } from './change-role-dialog/change-role-dialog.component';
import { ConfirmDialogComponent } from './confirm-dialog/confirm-dialog.component';
import { InviteDialogComponent } from './invite-dialog/invite-dialog.component';

@Component({
  selector: 'app-team',
  standalone: true,
  imports: [
    MatCardModule,
    MatTableModule,
    MatTabsModule,
    MatButtonModule,
    MatIconModule,
    MatMenuModule,
    MatChipsModule,
    MatDividerModule,
    MatTooltipModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatDialogModule,
    TranslatePipe,
    FormatDatePipe,
    RoleDirective,
  ],
  templateUrl: './team.component.html',
  styleUrl: './team.component.scss',
})
export class TeamComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly session = inject(SessionService);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);

  readonly currentMember = this.session.currentMember;

  readonly isLoadingMembers = signal<boolean>(true);
  readonly isLoadingInvitations = signal<boolean>(true);
  readonly members = signal<Member[]>([]);
  readonly invitations = signal<Invitation[]>([]);
  readonly nextCursor = signal<string | null>(null);

  readonly errorMessage = signal<string | null>(null);
  readonly errorTraceId = signal<string | null>(null);

  readonly memberColumns: readonly string[] = [
    'email',
    'role',
    'status',
    'mfa',
    'joined',
    'actions',
  ];

  readonly invitationColumns: readonly string[] = [
    'email',
    'role',
    'status',
    'expires',
    'actions',
  ];

  ngOnInit(): void {
    this.loadMembers();
    this.loadInvitations();
  }

  loadMembers(): void {
    this.isLoadingMembers.set(true);
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    this.api.members().subscribe({
      next: (res) => {
        this.members.set(res.items);
        this.nextCursor.set(res.next_cursor);
        this.isLoadingMembers.set(false);
      },
      error: (err: unknown) => {
        this.isLoadingMembers.set(false);
        this.handleError(err);
      },
    });
  }

  loadInvitations(): void {
    this.isLoadingInvitations.set(true);
    this.api.invitations().subscribe({
      next: (res) => {
        this.invitations.set(res.items);
        this.isLoadingInvitations.set(false);
      },
      error: (err: unknown) => {
        this.isLoadingInvitations.set(false);
        this.handleError(err);
      },
    });
  }

  openInviteDialog(): void {
    const dialogRef = this.dialog.open(InviteDialogComponent, {
      width: '460px',
      disableClose: false,
    });

    dialogRef.afterClosed().subscribe((created) => {
      if (created) {
        this.loadInvitations();
        this.snackBar.open(this.translate.instant('team.inviteSuccess'), undefined, {
          duration: 3500,
        });
      }
    });
  }

  openChangeRoleDialog(member: Member): void {
    const dialogRef = this.dialog.open(ChangeRoleDialogComponent, {
      width: '420px',
      data: { member },
    });

    dialogRef.afterClosed().subscribe((newRole: Role | undefined) => {
      if (newRole && newRole !== member.role) {
        this.changeRole(member, newRole);
      }
    });
  }

  private changeRole(member: Member, newRole: Role): void {
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    this.api.changeMemberRole(member.id, newRole).subscribe({
      next: (updated) => {
        this.members.update((items) => items.map((m) => (m.id === updated.id ? updated : m)));
        this.snackBar.open(this.translate.instant('team.roleChangeSuccess'), undefined, {
          duration: 3500,
        });
      },
      error: (err: unknown) => {
        this.handleError(err);
      },
    });
  }

  openRemoveMemberDialog(member: Member): void {
    const dialogRef = this.dialog.open(ConfirmDialogComponent, {
      width: '440px',
      data: {
        titleKey: 'team.removeMemberDialog.title',
        messageKey: 'team.removeMemberDialog.message',
        email: member.email,
        confirmKey: 'team.removeMemberDialog.confirmButton',
        isDestructive: true,
      },
    });

    dialogRef.afterClosed().subscribe((confirmed: boolean | undefined) => {
      if (confirmed) {
        this.removeMember(member);
      }
    });
  }

  private removeMember(member: Member): void {
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    this.api.removeMember(member.id).subscribe({
      next: () => {
        // Refresh members list or mark status as removed
        this.loadMembers();
        this.snackBar.open(this.translate.instant('team.removeSuccess'), undefined, {
          duration: 3500,
        });
      },
      error: (err: unknown) => {
        this.handleError(err);
      },
    });
  }

  openRevokeInvitationDialog(invitation: Invitation): void {
    const dialogRef = this.dialog.open(ConfirmDialogComponent, {
      width: '440px',
      data: {
        titleKey: 'team.revokeInvitationDialog.title',
        messageKey: 'team.revokeInvitationDialog.message',
        email: invitation.email,
        confirmKey: 'team.revokeInvitationDialog.confirmButton',
        isDestructive: true,
      },
    });

    dialogRef.afterClosed().subscribe((confirmed: boolean | undefined) => {
      if (confirmed) {
        this.revokeInvitation(invitation);
      }
    });
  }

  private revokeInvitation(invitation: Invitation): void {
    this.errorMessage.set(null);
    this.errorTraceId.set(null);

    this.api.revokeInvitation(invitation.id).subscribe({
      next: () => {
        this.loadInvitations();
        this.snackBar.open(this.translate.instant('team.revokeSuccess'), undefined, {
          duration: 3500,
        });
      },
      error: (err: unknown) => {
        this.handleError(err);
      },
    });
  }

  private handleError(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      const apiError = err.error as ApiError | undefined;
      this.errorTraceId.set(apiError?.trace_id ?? null);

      // FR-012: Removing or demoting the last owner is refused by server with 409
      if (err.status === 409) {
        this.errorMessage.set(this.translate.instant('team.lastOwnerErrorMessage'));
        return;
      }

      this.errorMessage.set(
        apiError?.message ?? err.message ?? this.translate.instant('team.genericError'),
      );
      return;
    }

    this.errorMessage.set(this.translate.instant('team.genericError'));
  }
}
