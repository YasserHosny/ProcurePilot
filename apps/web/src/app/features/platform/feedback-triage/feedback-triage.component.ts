import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { TranslatePipe } from '@ngx-translate/core';

import { OperatorService } from '../../../core/auth/operator.service';
import { SessionService } from '../../../core/auth/session.service';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FeedbackDetailComponent } from './feedback-detail/feedback-detail.component';
import { CATEGORY_LABEL_KEYS, ROLE_LABEL_KEYS, STATUS_LABEL_KEYS } from './feedback-labels';
import {
  FEEDBACK_CATEGORIES,
  FEEDBACK_STATUSES,
  type FeedbackCategory,
  type FeedbackStatus,
  type OperatorSubmission,
  PlatformFeedbackApiService,
} from './platform-feedback-api';

export type DemoFilter = 'all' | 'demo' | 'real';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

@Component({
  selector: 'app-feedback-triage',
  standalone: true,
  imports: [
    FormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSlideToggleModule,
    TranslatePipe,
    FormatDatePipe,
    FeedbackDetailComponent,
  ],
  templateUrl: './feedback-triage.component.html',
  styleUrl: './feedback-triage.component.scss',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class FeedbackTriageComponent implements OnInit {
  private readonly api = inject(PlatformFeedbackApiService);
  private readonly operator = inject(OperatorService);
  private readonly session = inject(SessionService);

  readonly statuses = FEEDBACK_STATUSES;
  readonly categories = FEEDBACK_CATEGORIES;
  readonly statusLabelKeys = STATUS_LABEL_KEYS;
  readonly categoryLabelKeys = CATEGORY_LABEL_KEYS;
  readonly roleLabelKeys = ROLE_LABEL_KEYS;

  readonly status = signal<FeedbackStatus | null>(null);
  readonly category = signal<FeedbackCategory | null>(null);
  readonly demo = signal<DemoFilter>('all');
  readonly workspaceDraft = signal('');
  readonly workspaceInvalid = signal(false);
  private readonly workspace = signal<string | null>(null);

  readonly items = signal<readonly OperatorSubmission[]>([]);
  readonly nextCursor = signal<string | null>(null);
  readonly loading = signal(false);
  readonly loadFailed = signal(false);
  readonly selectedId = signal<string | null>(null);

  readonly digestEnabled = computed(() => this.operator.profile()?.digest_enabled ?? false);
  readonly digestSaving = signal(false);
  readonly digestFailed = signal(false);

  private requestSeq = 0;

  ngOnInit(): void {
    this.reload();
  }

  setStatus(value: FeedbackStatus | null): void {
    this.status.set(value);
    this.reload();
  }

  setCategory(value: FeedbackCategory | null): void {
    this.category.set(value);
    this.reload();
  }

  setDemo(value: DemoFilter): void {
    this.demo.set(value);
    this.reload();
  }

  applyWorkspace(): void {
    const value = this.workspaceDraft().trim();
    if (value && !UUID.test(value)) {
      this.workspaceInvalid.set(true);
      return;
    }
    this.workspaceInvalid.set(false);
    this.workspace.set(value || null);
    this.reload();
  }

  /** Narrows the list to one workspace, from the detail pane. */
  filterToWorkspace(tenantId: string): void {
    this.workspaceDraft.set(tenantId);
    this.workspaceInvalid.set(false);
    this.workspace.set(tenantId);
    this.reload();
  }

  clearFilters(): void {
    this.status.set(null);
    this.category.set(null);
    this.demo.set('all');
    this.workspaceDraft.set('');
    this.workspaceInvalid.set(false);
    this.workspace.set(null);
    this.reload();
  }

  select(item: OperatorSubmission): void {
    this.selectedId.set(item.id);
  }

  onUpdated(saved: OperatorSubmission): void {
    this.items.update((list) => list.map((i) => (i.id === saved.id ? saved : i)));
  }

  reload(): void {
    this.items.set([]);
    this.nextCursor.set(null);
    this.fetch(null);
  }

  loadMore(): void {
    const cursor = this.nextCursor();
    if (cursor && !this.loading()) this.fetch(cursor);
  }

  setDigest(enabled: boolean): void {
    this.digestSaving.set(true);
    this.digestFailed.set(false);
    this.api.setDigestPreference(enabled, this.session.activeLocale()).subscribe({
      next: (me) => {
        this.digestSaving.set(false);
        this.operator.updateProfile(me);
      },
      error: () => {
        this.digestSaving.set(false);
        this.digestFailed.set(true);
      },
    });
  }

  private fetch(cursor: string | null): void {
    const seq = ++this.requestSeq;
    this.loading.set(true);
    this.loadFailed.set(false);
    const demo = this.demo();
    this.api
      .list({
        status: this.status(),
        category: this.category(),
        tenantId: this.workspace(),
        isDemo: demo === 'all' ? null : demo === 'demo',
      }, cursor)
      .subscribe({
        next: (page) => {
          if (seq !== this.requestSeq) return;
          this.items.update((list) => [...list, ...page.items]);
          this.nextCursor.set(page.next_cursor ?? null);
          this.loading.set(false);
        },
        error: () => {
          if (seq !== this.requestSeq) return;
          this.loading.set(false);
          this.loadFailed.set(true);
        },
      });
  }

  preview(text: string): string {
    return text.length > 90 ? `${text.slice(0, 90)}…` : text;
  }
}
