import { Component, OnInit, inject, signal, ChangeDetectionStrategy } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink, Router } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { EMPTY, Subject } from 'rxjs';
import { catchError, switchMap } from 'rxjs/operators';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { CursorPager } from '../../../layout/list-pager/cursor-pager';
import { ListPagerComponent } from '../../../layout/list-pager/list-pager.component';
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
    ListPagerComponent,
    FormatDatePipe,
  ],
  templateUrl: './history.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './history.component.scss',
})
export class AnalystHistoryComponent implements OnInit {
  private readonly api = inject(AnalystApiService);
  private readonly router = inject(Router);

  readonly isLoading = signal(false);
  readonly conversations = signal<AnalystConversation[]>([]);
  readonly pager = new CursorPager('analyst-history');

  private readonly reloadSubject = new Subject<{ limit: number; cursor?: string }>();

  constructor() {
    this.reloadSubject
      .pipe(
        switchMap(({ limit, cursor }) => {
          this.isLoading.set(true);

          return this.api.listConversations(limit, cursor).pipe(
            catchError(() => {
              this.isLoading.set(false);
              if (!this.pager.failed()) this.conversations.set([]);
              return EMPTY;
            }),
          );
        }),
        takeUntilDestroyed(),
      )
      .subscribe((res) => {
        if (!this.pager.loaded(res)) {
          this.loadHistory();
          return;
        }
        this.conversations.set([...res.items]);
        this.isLoading.set(false);
      });
  }

  ngOnInit(): void {
    this.loadHistory();
  }

  loadHistory(): void {
    this.reloadSubject.next(this.pager.params());
  }

  openConversation(id: string): void {
    this.router.navigate(['/analyst', id]);
  }
}
