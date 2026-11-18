import { HttpErrorResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  OnChanges,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { TranslatePipe } from '@ngx-translate/core';

import { FormatDatePipe } from '../../../../core/format/date.pipe';
import {
  CATEGORY_LABEL_KEYS,
  ROLE_LABEL_KEYS,
  STATUS_ACTION_KEYS,
  STATUS_LABEL_KEYS,
} from '../feedback-labels';
import {
  type FeedbackAttachment,
  type FeedbackStatus,
  MAX_LABELS,
  MAX_LABEL_LENGTH,
  type OperatorSubmission,
  PlatformFeedbackApiService,
  nextStatuses,
} from '../platform-feedback-api';

type LabelProblem = 'tooLong' | 'duplicate' | 'max' | null;

@Component({
  selector: 'app-feedback-detail',
  standalone: true,
  imports: [
    FormsModule,
    MatButtonModule,
    MatChipsModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    TranslatePipe,
    FormatDatePipe,
  ],
  templateUrl: './feedback-detail.component.html',
  styleUrl: './feedback-detail.component.scss',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class FeedbackDetailComponent implements OnChanges {
  private readonly api = inject(PlatformFeedbackApiService);

  /** The row picked in the list; the full record is fetched so the view is audited server-side. */
  readonly feedbackId = input.required<string>();
  readonly updated = output<OperatorSubmission>();
  readonly filterWorkspace = output<string>();

  readonly item = signal<OperatorSubmission | null>(null);
  readonly loading = signal(false);
  readonly loadFailed = signal(false);
  readonly saving = signal(false);
  /** Translation key of the last action error, or null. */
  readonly actionError = signal<string | null>(null);
  readonly urls = signal<Readonly<Record<string, string>>>({});
  readonly failedAttachments = signal<ReadonlySet<string>>(new Set());
  readonly labelDraft = signal('');
  readonly labelProblem = signal<LabelProblem>(null);

  readonly statusLabelKeys = STATUS_LABEL_KEYS;
  readonly statusActionKeys = STATUS_ACTION_KEYS;
  readonly categoryLabelKeys = CATEGORY_LABEL_KEYS;
  readonly roleLabelKeys = ROLE_LABEL_KEYS;
  readonly maxLabelLength = MAX_LABEL_LENGTH;
  readonly nextStatuses = nextStatuses;

  private loadedFor: string | null = null;

  ngOnChanges(): void {
    const id = this.feedbackId();
    if (id !== this.loadedFor) this.load(id);
  }

  load(id: string = this.feedbackId()): void {
    this.loadedFor = id;
    this.item.set(null);
    this.urls.set({});
    this.failedAttachments.set(new Set());
    this.actionError.set(null);
    this.labelDraft.set('');
    this.labelProblem.set(null);
    this.loadFailed.set(false);
    this.loading.set(true);
    this.api.get(id).subscribe({
      next: (item) => {
        if (this.loadedFor !== id) return;
        this.item.set(item);
        this.loading.set(false);
        for (const attachment of item.attachments) this.fetchUrl(item.id, attachment);
      },
      error: () => {
        if (this.loadedFor !== id) return;
        this.loading.set(false);
        this.loadFailed.set(true);
      },
    });
  }

  images(item: OperatorSubmission): readonly FeedbackAttachment[] {
    return item.attachments.filter((a) => a.kind === 'image');
  }

  audio(item: OperatorSubmission): readonly FeedbackAttachment[] {
    return item.attachments.filter((a) => a.kind === 'audio');
  }

  moveTo(status: FeedbackStatus): void {
    this.patch({ status });
  }

  addLabel(): void {
    const item = this.item();
    if (!item) return;
    const label = this.labelDraft().trim();
    if (!label) return;
    if (label.length > MAX_LABEL_LENGTH) return this.labelProblem.set('tooLong');
    if (item.labels.some((l) => l.toLowerCase() === label.toLowerCase())) {
      return this.labelProblem.set('duplicate');
    }
    if (item.labels.length >= MAX_LABELS) return this.labelProblem.set('max');
    this.labelProblem.set(null);
    this.patch({ labels: [...item.labels, label] }, () => this.labelDraft.set(''));
  }

  removeLabel(label: string): void {
    const item = this.item();
    if (!item) return;
    this.labelProblem.set(null);
    this.patch({ labels: item.labels.filter((l) => l !== label) });
  }

  private patch(
    body: { status?: FeedbackStatus; labels?: readonly string[] },
    onSaved?: () => void,
  ): void {
    const item = this.item();
    if (!item || this.saving()) return;
    this.saving.set(true);
    this.actionError.set(null);
    this.api.update(item.id, body).subscribe({
      next: (saved) => {
        this.saving.set(false);
        this.item.set(saved);
        this.updated.emit(saved);
        onSaved?.();
      },
      error: (err: unknown) => {
        this.saving.set(false);
        const code = err instanceof HttpErrorResponse ? (err.error as { code?: string })?.code : '';
        this.actionError.set(
          code === 'feedback.invalid_transition'
            ? 'platform.feedback.actions.invalidTransition'
            : 'platform.feedback.actions.saveError',
        );
        // A refused move means our copy is stale: show the server's truth.
        if (code === 'feedback.invalid_transition') this.refresh(item.id);
      },
    });
  }

  private refresh(id: string): void {
    this.api.get(id).subscribe({
      next: (fresh) => {
        if (this.loadedFor !== id) return;
        this.item.set(fresh);
        this.updated.emit(fresh);
      },
    });
  }

  private fetchUrl(id: string, attachment: FeedbackAttachment): void {
    this.api.attachmentUrl(id, attachment.id).subscribe({
      next: ({ url }) => {
        if (this.loadedFor !== id) return;
        this.urls.update((current) => ({ ...current, [attachment.id]: url }));
      },
      error: () => {
        if (this.loadedFor !== id) return;
        this.failedAttachments.update((current) => new Set(current).add(attachment.id));
      },
    });
  }
}
