import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { TranslatePipe } from '@ngx-translate/core';

import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FeedbackAttachmentComponent } from '../feedback-attachment/feedback-attachment.component';
import type { FeedbackAttachment, Submission } from '../feedback-api';

/** One submission, as members and owners see it. Operator labels are never part of this view. */
@Component({
  selector: 'app-feedback-card',
  standalone: true,
  imports: [
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    TranslatePipe,
    FormatDatePipe,
    FeedbackAttachmentComponent,
  ],
  templateUrl: './feedback-card.component.html',
  styleUrl: './feedback-card.component.scss',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class FeedbackCardComponent {
  readonly submission = input.required<Submission>();
  /** The owner inbox names the sender; a member's own list does not need to. */
  readonly showSubmitter = input(false);
  /** The owner inbox is read-only, so it passes false and no action is drawn. */
  readonly allowWithdraw = input(false);
  readonly withdraw = output<Submission>();

  readonly dateOptions: Intl.DateTimeFormatOptions = { dateStyle: 'medium', timeStyle: 'short' };

  readonly images = computed<readonly FeedbackAttachment[]>(() =>
    this.byOrder(this.submission().attachments.filter((a) => a.kind === 'image')),
  );
  readonly audio = computed<readonly FeedbackAttachment[]>(() =>
    this.byOrder(this.submission().attachments.filter((a) => a.kind === 'audio')),
  );
  readonly canWithdraw = computed(() => this.allowWithdraw() && this.submission().can_withdraw === true);

  private byOrder(list: readonly FeedbackAttachment[]): readonly FeedbackAttachment[] {
    return [...list].sort((a, b) => a.display_order - b.display_order);
  }
}
