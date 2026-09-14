import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';

import type { Money, QuotationDetail } from '../../../core/api/models';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';

@Component({
  selector: 'app-quotation-review-banners',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    MatButtonModule,
    MatCheckboxModule,
    MatIconModule,
    MatTooltipModule,
    TranslatePipe,
    FormatMoneyPipe,
  ],
  templateUrl: './quotation-review-banners.component.html',
  styleUrl: './quotation-review-banners.component.scss',
})
export class QuotationReviewBannersComponent {
  @Input({ required: true }) quotation!: QuotationDetail | null;
  @Input({ required: true }) hasArithmeticMismatch = false;
  @Input({ required: true }) isReconciled = false;
  @Input({ required: true }) computedLinesTotal: Money | null = null;
  @Input({ required: true }) arithmeticDifference: string | null = '0.00';
  @Input({ required: true }) inferredVatPct: number | null = null;
  @Input({ required: true }) mismatchAcknowledged = false;
  @Input({ required: true }) isWriter = false;
  @Input({ required: true }) confirmBlockedReason: string | null = null;
  @Input({ required: true }) errorMessage: string | null = null;
  @Input({ required: true }) errorTraceId: string | null = null;
  @Input({ required: true }) flaggedFieldsCount = 0;
  @Input({ required: true }) currentFlaggedIndex = 0;

  @Output() readonly mismatchAcknowledgedChange = new EventEmitter<boolean>();
  @Output() readonly prevFlagged = new EventEmitter<void>();
  @Output() readonly nextFlagged = new EventEmitter<void>();
}
