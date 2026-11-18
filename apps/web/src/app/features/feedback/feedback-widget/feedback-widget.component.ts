import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { SessionService } from '../../../core/auth/session.service';
import { FeedbackDraftStore } from '../feedback-draft.store';
import { FeedbackDialogComponent } from './feedback-dialog.component';

/**
 * The persistent feedback control (FR-001): a floating button that opens the feedback dialog.
 * Mounted once in the shell as a sibling of the main content, so it is on every signed-in page.
 */
@Component({
  selector: 'app-feedback-widget',
  standalone: true,
  imports: [MatButtonModule, MatIconModule, TranslatePipe],
  templateUrl: './feedback-widget.component.html',
  styleUrl: './feedback-widget.component.scss',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class FeedbackWidgetComponent {
  private readonly dialog = inject(MatDialog);
  private readonly session = inject(SessionService);
  private readonly translate = inject(TranslateService);
  private readonly draft = inject(FeedbackDraftStore);

  private dialogRef: MatDialogRef<FeedbackDialogComponent> | null = null;

  /** Who the draft belongs to: member and workspace, so it never crosses to another person. */
  private readonly ownerKey = computed(() => {
    const member = this.session.currentMember();
    return member ? `${member.id}|${this.session.tenant()?.id ?? ''}` : null;
  });

  readonly hasDraft = computed(
    () => !this.draft.isEmpty() && this.draft.owner() !== null && this.draft.owner() === this.ownerKey(),
  );

  label(): string {
    const open = this.translate.instant('feedback.widget.open');
    return this.hasDraft()
      ? `${open} (${this.translate.instant('feedback.widget.draftBadge')})`
      : open;
  }

  open(): void {
    if (this.dialogRef) return;
    this.draft.claim(this.ownerKey());
    // Focus returns to the button on close (restoreFocus), and Material traps it meanwhile.
    this.dialogRef = this.dialog.open(FeedbackDialogComponent, {
      width: '560px',
      maxWidth: 'calc(100vw - 16px)',
      restoreFocus: true,
      ariaModal: true,
      autoFocus: 'first-tabbable',
    });
    this.dialogRef.afterClosed().subscribe(() => {
      this.dialogRef = null;
    });
  }
}
