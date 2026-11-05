import { ChangeDetectionStrategy, Component, inject, input, output } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import type { BulkApprovalDecisionResponse, Money } from '../../../core/api/models';
import { FormatService } from '../../../core/format/format.service';

export interface BulkFailure {
  readonly requestId: string;
  readonly label: string;
  readonly reasonKey: string;
}

@Component({
  selector: 'app-approval-bulk-panel', standalone: true,
  imports: [MatButtonModule, MatProgressSpinnerModule, TranslatePipe, RouterLink],
  templateUrl: './approval-bulk-panel.component.html',
  styleUrl: './approval-bulk-panel.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ApprovalBulkPanelComponent {
  private readonly translate = inject(TranslateService);
  private readonly format = inject(FormatService);
  readonly count = input.required<number>();
  readonly totals = input.required<readonly Money[]>();
  readonly incomplete = input(false);
  readonly busy = input(false);
  readonly disabled = input(false);
  readonly error = input(false);
  readonly result = input<BulkApprovalDecisionResponse | null>(null);
  readonly failures = input<readonly BulkFailure[]>([]);
  readonly approve = output<void>();
  readonly reject = output<void>();
  readonly clearSelection = output<void>();
  plural(key: string, count: number): string {
    const category = new Intl.PluralRules(this.format.locale()).select(count);
    return this.translate.instant(`approvals.bulk.${key}.${category}`, {count: this.format.formatNumber(count, {numberingSystem: 'latn'})});
  }
  money(value: Money): string { return this.format.formatCurrencyAmount(value, 'en'); }
}
