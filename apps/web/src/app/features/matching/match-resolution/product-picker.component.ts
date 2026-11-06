import { ChangeDetectionStrategy, Component, DestroyRef, inject, input, output, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { TranslatePipe } from '@ngx-translate/core';
import { EMPTY, Subject, catchError, debounceTime, distinctUntilChanged, of, switchMap, tap } from 'rxjs';

import { ApiService } from '../../../core/api/api.service';
import type { MatchCandidate, Product } from '../../../core/api/models';

const MIN_CHARS = 2;
const DEBOUNCE_MS = 300;
const RESULT_LIMIT = 8;

/**
 * Search the catalogue and record the chosen product as a candidate for the line (P-151).
 * A decision must point at a candidate, so picking a product the matcher never proposed
 * first records it as a manual candidate; the parent then selects it like any other.
 */
@Component({
  selector: 'app-product-picker',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [MatButtonModule, MatFormFieldModule, MatIconModule, MatInputModule, TranslatePipe],
  templateUrl: './product-picker.component.html',
  styleUrl: './product-picker.component.scss',
})
export class ProductPickerComponent {
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly terms = new Subject<string>();

  readonly lineId = input.required<string>();
  readonly picked = output<MatchCandidate>();

  readonly results = signal<Product[]>([]);
  readonly searched = signal(false);
  readonly searching = signal(false);
  readonly error = signal<'search' | 'pick' | null>(null);
  readonly adding = signal(false);

  constructor() {
    this.terms
      .pipe(
        debounceTime(DEBOUNCE_MS),
        distinctUntilChanged(),
        tap((term) => {
          if (term.length < MIN_CHARS) {
            this.results.set([]);
            this.searched.set(false);
            this.error.set(null);
          }
        }),
        switchMap((term) => {
          if (term.length < MIN_CHARS) {
            return EMPTY;
          }
          this.searching.set(true);
          this.error.set(null);
          return this.api.products({ q: term, limit: RESULT_LIMIT, status: 'active' }).pipe(
            catchError(() => {
              this.error.set('search');
              return of(null);
            }),
          );
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((page) => {
        this.searching.set(false);
        if (page) {
          this.results.set(page.items);
          this.searched.set(true);
        }
      });
  }

  onInput(event: Event): void {
    this.terms.next((event.target as HTMLInputElement).value.trim());
  }

  pick(product: Product): void {
    if (this.adding()) {
      return;
    }
    this.adding.set(true);
    this.error.set(null);
    this.api.addManualCandidate(this.lineId(), product.id).subscribe({
      next: (candidate) => {
        this.adding.set(false);
        this.results.set([]);
        this.searched.set(false);
        this.picked.emit(candidate);
      },
      error: () => {
        this.adding.set(false);
        this.error.set('pick');
      },
    });
  }
}
