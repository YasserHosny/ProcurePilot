import { HttpErrorResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnInit,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar } from '@angular/material/snack-bar';
import { RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { SessionService } from '../../../core/auth/session.service';
import { FeedbackCardComponent } from '../feedback-card/feedback-card.component';
import { FeedbackApiService, type Submission } from '../feedback-api';
import { FEEDBACK_PAGE_SIZE, PagedSubmissions } from '../paged-submissions';
import { WithdrawDialogComponent } from './withdraw-dialog.component';

/** The member's own feedback with its current status, and withdrawal while it is still new (FR-012, FR-014). */
@Component({
  selector: 'app-my-feedback',
  standalone: true,
  imports: [
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    RouterLink,
    TranslatePipe,
    FeedbackCardComponent,
  ],
  templateUrl: './my-feedback.component.html',
  styleUrl: './my-feedback.component.scss',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class MyFeedbackComponent implements OnInit {
  private readonly api = inject(FeedbackApiService);
  private readonly dialog = inject(MatDialog);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);
  private readonly session = inject(SessionService);

  private readonly heading = viewChild<ElementRef<HTMLElement>>('heading');

  readonly list = new PagedSubmissions((cursor) =>
    this.api.listMine({ cursor, limit: FEEDBACK_PAGE_SIZE }),
  );
  /** A withdrawal that did not go through, in words (refused, or failed). */
  readonly withdrawMessage = signal<string | null>(null);
  readonly isOwner = computed(() => this.session.hasRole('owner'));

  ngOnInit(): void {
    this.list.reload();
  }

  onWithdraw(submission: Submission): void {
    this.withdrawMessage.set(null);
    this.dialog
      .open(WithdrawDialogComponent, { width: '420px', maxWidth: 'calc(100vw - 16px)', ariaModal: true })
      .afterClosed()
      .subscribe((confirmed: boolean | undefined) => {
        if (confirmed) this.withdraw(submission);
      });
  }

  private withdraw(submission: Submission): void {
    this.api.withdraw(submission.id).subscribe({
      next: () => {
        this.list.remove(submission.id);
        this.snackBar.open(this.translate.instant('feedback.withdraw.success'), undefined, {
          duration: 3000,
        });
        // The card that held focus is gone; keep keyboard users in the page, not at its top.
        this.heading()?.nativeElement.focus();
      },
      error: (error: unknown) => {
        const status = error instanceof HttpErrorResponse ? error.status : 0;
        if (status === 404) {
          // Already gone (withdrawn elsewhere, or past its retention): the list should say so too.
          this.list.remove(submission.id);
        } else if (status === 409) {
          this.withdrawMessage.set('feedback.withdraw.refused');
          // The status moved on: refresh so the card stops offering withdrawal.
          this.list.reload();
        } else {
          this.withdrawMessage.set('feedback.withdraw.failed');
        }
      },
    });
  }
}
