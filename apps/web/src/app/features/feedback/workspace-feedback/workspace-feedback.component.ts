import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';

import { FeedbackCardComponent } from '../feedback-card/feedback-card.component';
import {
  FEEDBACK_CATEGORIES,
  FEEDBACK_STATUSES,
  FeedbackApiService,
  type FeedbackCategory,
  type FeedbackStatus,
} from '../feedback-api';
import { FEEDBACK_PAGE_SIZE, PagedSubmissions } from '../paged-submissions';

/**
 * The owner's read-only inbox of the workspace's feedback (FR-013). It is a support surface:
 * it offers no status, label or delete action, and no withdrawal either. The route is owner-only
 * for convenience; the API answers 404 to every other role and is the real control.
 */
@Component({
  selector: 'app-workspace-feedback',
  standalone: true,
  imports: [
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    RouterLink,
    TranslatePipe,
    FeedbackCardComponent,
  ],
  templateUrl: './workspace-feedback.component.html',
  styleUrl: '../my-feedback/my-feedback.component.scss',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class WorkspaceFeedbackComponent implements OnInit {
  private readonly api = inject(FeedbackApiService);

  readonly statuses = FEEDBACK_STATUSES;
  readonly categories = FEEDBACK_CATEGORIES;
  readonly status = signal<FeedbackStatus | null>(null);
  readonly category = signal<FeedbackCategory | null>(null);

  readonly list = new PagedSubmissions((cursor) =>
    this.api.listWorkspace({
      cursor,
      limit: FEEDBACK_PAGE_SIZE,
      status: this.status(),
      category: this.category(),
    }),
  );

  ngOnInit(): void {
    this.list.reload();
  }

  onStatusFilter(value: FeedbackStatus | null): void {
    this.status.set(value);
    this.list.reload();
  }

  onCategoryFilter(value: FeedbackCategory | null): void {
    this.category.set(value);
    this.list.reload();
  }
}
