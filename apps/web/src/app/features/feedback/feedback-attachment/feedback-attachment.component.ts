import { ChangeDetectionStrategy, Component, OnInit, inject, input, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { TranslatePipe } from '@ngx-translate/core';

import { FeedbackApiService, type FeedbackAttachment } from '../feedback-api';

type LoadState = 'idle' | 'loading' | 'ready' | 'error';

/**
 * One screenshot or voice message of a submission. Files are never publicly addressable: each is
 * shown through a short-lived link the API issues after an access check (FR-016, FR-019), so the
 * link is requested when the item is shown and re-requested if it has expired.
 */
@Component({
  selector: 'app-feedback-attachment',
  standalone: true,
  imports: [MatButtonModule, MatIconModule, MatProgressSpinnerModule, TranslatePipe],
  templateUrl: './feedback-attachment.component.html',
  styleUrl: './feedback-attachment.component.scss',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class FeedbackAttachmentComponent implements OnInit {
  private readonly api = inject(FeedbackApiService);

  readonly submissionId = input.required<string>();
  readonly attachment = input.required<FeedbackAttachment>();
  /** 1-based position among the submission's screenshots, for the image's alternative text. */
  readonly number = input(1);

  readonly state = signal<LoadState>('idle');
  readonly url = signal<string | null>(null);

  ngOnInit(): void {
    // Screenshots show themselves; audio waits for a request to play, so a long list does not
    // sign and fetch every recording.
    if (this.attachment().kind === 'image') this.load();
  }

  load(): void {
    this.state.set('loading');
    this.api.attachmentUrl(this.submissionId(), this.attachment().id).subscribe({
      next: (signed) => {
        this.url.set(signed.url);
        this.state.set('ready');
      },
      error: () => {
        this.url.set(null);
        this.state.set('error');
      },
    });
  }

  /** The link expired between issue and display. */
  onMediaError(): void {
    this.url.set(null);
    this.state.set('error');
  }
}
