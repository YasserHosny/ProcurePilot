import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import type { SafeResourceUrl } from '@angular/platform-browser';
import { TranslatePipe } from '@ngx-translate/core';

import type { FieldExtraction, QuotationDetail } from '../../../core/api/models';
import { FormatDatePipe } from '../../../core/format/date.pipe';

@Component({
  selector: 'app-quotation-doc-preview',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    TranslatePipe,
    FormatDatePipe,
  ],
  templateUrl: './quotation-doc-preview.component.html',
  styleUrl: './quotation-doc-preview.component.scss',
})
export class QuotationDocPreviewComponent {
  @Input({ required: true }) quotation!: QuotationDetail;
  @Input({ required: true }) safePreviewUrl: SafeResourceUrl | null = null;
  @Input({ required: true }) documentFileName = '';
  @Input({ required: true }) activeExtraction: FieldExtraction | null = null;
  @Input({ required: true }) isWriter = false;
  @Input({ required: true }) isReplacingDocument = false;

  @Output() readonly replaceDocumentSelected = new EventEmitter<Event>();
  @Output() readonly download = new EventEmitter<void>();

  fieldLabel(fieldName: string): string {
    const labels: Record<string, string> = {
      currency: 'Currency',
      issue_date: 'Issue Date',
      expiry_date: 'Expiry Date',
      stated_total: 'Stated Total',
      quantity: 'Quantity',
      unit_price: 'Unit Price',
      discount: 'Discount',
      delivery_fee: 'Delivery Fee',
      vat_rate: 'VAT Rate',
      original_text: 'Description',
      pack_details: 'Pack Details',
    };
    return labels[fieldName] || fieldName.replace(/_/g, ' ');
  }

  formatConfidence(score: string | number): number {
    const numeric = typeof score === 'string' ? parseFloat(score) : score;
    return isNaN(numeric) ? 0 : Math.round(numeric * 100);
  }
}
