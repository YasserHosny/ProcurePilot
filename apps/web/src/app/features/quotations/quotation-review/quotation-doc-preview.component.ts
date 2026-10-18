import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import type { SafeResourceUrl } from '@angular/platform-browser';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

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

  private readonly translate = inject(TranslateService);

  fieldLabel(fieldName: string): string {
    const key = `quotations.review.fieldLabels.${fieldName}`;
    const label: string = this.translate.instant(key);
    return label === key ? fieldName.replace(/_/g, ' ') : label;
  }

  /** Extraction provider and model, for the details tooltip only — not shown on the screen. */
  technicalDetails(fe: FieldExtraction): string {
    return [fe.extraction_method, fe.model_version].filter(Boolean).join(' · ');
  }

  formatConfidence(score: string | number): number {
    const numeric = typeof score === 'string' ? parseFloat(score) : score;
    return isNaN(numeric) ? 0 : Math.round(numeric * 100);
  }
}
