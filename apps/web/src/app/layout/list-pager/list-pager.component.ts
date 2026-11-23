import { ChangeDetectionStrategy, Component, inject, input, output } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { TranslatePipe } from '@ngx-translate/core';

import { FormatService } from '../../core/format/format.service';
import { CursorPager, PAGE_SIZE_OPTIONS } from './cursor-pager';

/**
 * The pagination bar under a list table: rows per page, the visible range with the total,
 * and Previous / Next (PPS-228, design system «Pagination»). The host reloads on
 * `pageChange`; the bar moves the shared {@link CursorPager} before emitting.
 */
@Component({
  selector: 'app-list-pager',
  standalone: true,
  imports: [MatButtonModule, MatFormFieldModule, MatIconModule, MatSelectModule, TranslatePipe],
  templateUrl: './list-pager.component.html',
  styleUrl: './list-pager.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ListPagerComponent {
  private readonly format = inject(FormatService);

  readonly pager = input.required<CursorPager>();
  /** Accessible name of the navigation landmark, e.g. «Purchase request pages». */
  readonly label = input.required<string>();
  readonly busy = input<boolean>(false);
  readonly pageChange = output<void>();

  readonly sizes = PAGE_SIZE_OPTIONS;

  /** Translation key and params for the range; a method so a language switch re-renders it. */
  range(): { key: string; params: Record<string, string> } {
    const pager = this.pager();
    const from = this.format.formatNumber(pager.from());
    const to = this.format.formatNumber(pager.to());
    const total = pager.total();
    return total === null
      ? { key: 'common.pager.rangeOpen', params: { from, to } }
      : { key: 'common.pager.range', params: { from, to, total: this.format.formatNumber(total) } };
  }

  onPageSize(size: number): void {
    if (this.pager().setPageSize(size)) this.pageChange.emit();
  }

  onPrevious(): void {
    if (this.pager().goPrevious()) this.pageChange.emit();
  }

  onNext(): void {
    if (this.pager().goNext()) this.pageChange.emit();
  }
}
