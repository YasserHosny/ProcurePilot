import { ChangeDetectionStrategy, Component } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { TranslatePipe } from '@ngx-translate/core';

/** Asks before a withdrawal, which deletes the message and its files for everyone. Closes with true to proceed. */
@Component({
  selector: 'app-feedback-withdraw-dialog',
  standalone: true,
  imports: [MatButtonModule, MatDialogModule, MatIconModule, TranslatePipe],
  changeDetection: ChangeDetectionStrategy.Eager,
  template: `
    <h2 mat-dialog-title>
      <mat-icon class="warning-icon" aria-hidden="true">warning</mat-icon>
      {{ 'feedback.withdraw.title' | translate }}
    </h2>
    <mat-dialog-content>
      <p class="message">{{ 'feedback.withdraw.message' | translate }}</p>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button type="button" [mat-dialog-close]="false" cdkFocusInitial>
        {{ 'feedback.withdraw.cancel' | translate }}
      </button>
      <button mat-flat-button color="warn" type="button" data-test="confirm" [mat-dialog-close]="true">
        {{ 'feedback.withdraw.confirm' | translate }}
      </button>
    </mat-dialog-actions>
  `,
  styles: `
    .warning-icon {
      color: var(--pp-error);
      vertical-align: middle;
      margin-inline-end: 0.5rem;
    }
    .message {
      margin: 0;
      color: var(--pp-text-muted);
      line-height: 1.5;
    }
  `,
})
export class WithdrawDialogComponent {}
