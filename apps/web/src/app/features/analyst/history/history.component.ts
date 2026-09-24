import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink, Router } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { AnalystApiService, type AnalystConversation } from '../analyst-api';

@Component({
  selector: 'app-analyst-history',
  standalone: true,
  imports: [
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    MatProgressSpinnerModule,
    TranslatePipe,
    FormatDatePipe,
  ],
  templateUrl: './history.component.html',
  styleUrl: './history.component.scss',
})
export class AnalystHistoryComponent implements OnInit {
  private readonly api = inject(AnalystApiService);
  private readonly router = inject(Router);

  readonly isLoading = signal(false);
  readonly isLoadingMore = signal(false);
  readonly conversations = signal<AnalystConversation[]>([]);
  readonly nextCursor = signal<string | null>(null);

  ngOnInit(): void {
    this.loadHistory();
  }

  private loadHistory(): void {
    this.isLoading.set(true);
    this.api.listConversations(50).subscribe({
      next: (res) => {
        this.conversations.set(res.items);
        this.nextCursor.set(res.next_cursor);
        this.isLoading.set(false);
      },
      error: () => this.isLoading.set(false),
    });
  }

  loadMore(): void {
    const cursor = this.nextCursor();
    if (!cursor || this.isLoadingMore()) return;

    this.isLoadingMore.set(true);
    this.api.listConversations(50, cursor).subscribe({
      next: (res) => {
        this.conversations.update((curr) => [...curr, ...res.items]);
        this.nextCursor.set(res.next_cursor);
        this.isLoadingMore.set(false);
      },
      error: () => this.isLoadingMore.set(false),
    });
  }

  openConversation(id: string): void {
    this.router.navigate(['/analyst', id]);
  }
}
