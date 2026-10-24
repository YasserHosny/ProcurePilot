
import {
  Component,
  DestroyRef,
  ElementRef,
  EventEmitter,
  Input,
  Output,
  inject,
  ChangeDetectionStrategy,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import type { SafeResourceUrl } from '@angular/platform-browser';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import type { FieldExtraction, QuotationDetail } from '../../../core/api/models';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatExtractionPipe, isExtractionJsonFallback } from '../../../core/format/extraction-value.pipe';

@Component({
  selector: 'app-quotation-doc-preview',
  standalone: true,
  imports: [
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    TranslatePipe,
    FormatDatePipe,
    FormatExtractionPipe
],
  templateUrl: './quotation-doc-preview.component.html',
  changeDetection: ChangeDetectionStrategy.Eager,
  styleUrl: './quotation-doc-preview.component.scss',
})
export class QuotationDocPreviewComponent {
  readonly isExtractionJson = isExtractionJsonFallback;
  previewLoaded = false;
  private _safePreviewUrl: SafeResourceUrl | null = null;

  @Input({ required: true }) quotation!: QuotationDetail;
  @Input({ required: true })
  get safePreviewUrl(): SafeResourceUrl | null {
    return this._safePreviewUrl;
  }
  set safePreviewUrl(value: SafeResourceUrl | null) {
    this._safePreviewUrl = value;
    this.previewLoaded = false;
  }
  @Input({ required: true }) documentFileName = '';
  @Input({ required: true }) activeExtraction: FieldExtraction | null = null;
  @Input({ required: true }) isWriter = false;
  @Input({ required: true }) isReplacingDocument = false;

  @Output() readonly replaceDocumentSelected = new EventEmitter<Event>();
  @Output() readonly download = new EventEmitter<void>();

  private readonly translate = inject(TranslateService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly elementRef = inject<ElementRef<HTMLElement>>(ElementRef);

  private static readonly GUARD_WINDOW_MS = 1500;
  private guardTimer: ReturnType<typeof setTimeout> | null = null;
  private isGuarded = false;

  constructor() {
    this.destroyRef.onDestroy(() => {
      this.closeGuardWindow();
    });
  }

  onPreviewLoad(): void {
    this.previewLoaded = true;
    this.openGuardWindow();
  }

  private openGuardWindow(): void {
    this.closeGuardWindow();
    this.isGuarded = true;
    document.addEventListener('focusout', this.onFocusOutCapture, true);
    this.guardTimer = setTimeout(() => {
      this.closeGuardWindow();
    }, QuotationDocPreviewComponent.GUARD_WINDOW_MS);
  }

  private closeGuardWindow(): void {
    if (this.guardTimer !== null) {
      clearTimeout(this.guardTimer);
      this.guardTimer = null;
    }
    if (this.isGuarded) {
      this.isGuarded = false;
      document.removeEventListener('focusout', this.onFocusOutCapture, true);
    }
  }

  private readonly onFocusOutCapture = (event: FocusEvent): void => {
    if (!this.isGuarded) return;
    const target = event.target;
    if (!this.isEditableElement(target)) return;

    let start: number | null = null;
    let end: number | null = null;
    if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) {
      try {
        start = target.selectionStart;
        end = target.selectionEnd;
      } catch {
        // Some input types do not support selection
      }
    }

    setTimeout(() => {
      if (!this.isGuarded || !target.isConnected) return;
      const iframe = this.previewIframe;
      if (iframe && document.activeElement === iframe) {
        target.focus();
        if (
          start !== null &&
          end !== null &&
          (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement)
        ) {
          try {
            target.setSelectionRange(start, end);
          } catch {
            // ignore
          }
        }
      }
    }, 0);
  };

  private get previewIframe(): HTMLIFrameElement | null {
    return this.elementRef.nativeElement.querySelector('iframe.pdf-preview-frame');
  }

  private isEditableElement(el: EventTarget | null): el is HTMLElement {
    if (!(el instanceof HTMLElement)) return false;
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) return true;
    return el.isContentEditable;
  }

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
