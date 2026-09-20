import { CommonModule } from '@angular/common';
import { Component, Input, inject } from '@angular/core';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import type { AuditTrailEntry } from '../../../core/api/models';
import { FormatDatePipe } from '../../../core/format/date.pipe';

@Component({
  selector: 'app-quotation-audit-trail',
  standalone: true,
  imports: [
    CommonModule,
    MatExpansionModule,
    MatIconModule,
    MatProgressSpinnerModule,
    TranslatePipe,
    FormatDatePipe,
  ],
  templateUrl: './quotation-audit-trail.component.html',
  styleUrl: './quotation-audit-trail.component.scss',
})
export class QuotationAuditTrailComponent {
  private readonly translate = inject(TranslateService);

  @Input({ required: true }) auditTrail: AuditTrailEntry[] = [];
  @Input({ required: true }) isLoading = false;

  auditActionLabel(action: string): string {
    const actionKeys: Record<string, string> = {
      'quotation.archived': 'quotations.audit.actions.archived',
      'quotation.restored': 'quotations.audit.actions.restored',
      'quotation.extraction_retried': 'quotations.audit.actions.extraction_retried',
      'quotation.exported': 'quotations.audit.actions.exported',
      'quotation.confirmed': 'quotations.audit.actions.confirmed',
      'matching.task_routed': 'quotations.audit.actions.matchingTaskRouted',
      'matching.auto_accepted': 'quotations.audit.actions.matchingAutoAccepted',
      'matching.resolved': 'quotations.audit.actions.matchingResolved',
      'quotation.refused': 'quotations.audit.actions.refused',
      'quotation.reviewed': 'quotations.audit.actions.reviewed',
    };
    return this.translate.instant(actionKeys[action] ?? 'quotations.audit.actions.unknown');
  }

  auditDetailLines(entry: AuditTrailEntry): string[] {
    const target = entry.target;
    if (!target) {
      return [];
    }

    if (
      entry.action === 'matching.auto_accepted' ||
      entry.action === 'matching.resolved' ||
      entry.action === 'matching.task_routed'
    ) {
      return this.matchingDetailLines(target);
    }

    if (entry.action === 'quotation.reviewed') {
      return this.reviewedDetailLines(target);
    }

    return [];
  }

  private matchingDetailLines(target: Record<string, unknown>): string[] {
    const lines: string[] = [];
    const lineLabel = this.lineLabel(target);
    if (lineLabel) {
      lines.push(lineLabel);
    }

    const productName = this.asNonEmptyString(target['matched_product_name']);
    if (productName) {
      lines.push(
        this.translate.instant('quotations.audit.details.matchedProduct', {
          name: productName,
        }),
      );
    }

    const outcome = this.asNonEmptyString(target['outcome']);
    if (outcome) {
      lines.push(
        this.translate.instant('quotations.audit.details.outcome', {
          outcome: this.outcomeLabel(outcome),
        }),
      );
    }

    const score = this.asNonEmptyString(target['score']);
    if (score) {
      lines.push(
        this.translate.instant('quotations.audit.details.score', {
          score,
        }),
      );
    }

    const reason = this.asNonEmptyString(target['reason']);
    if (reason) {
      lines.push(
        this.translate.instant('quotations.audit.details.reason', {
          reason: this.reasonLabel(reason),
        }),
      );
    }

    return lines;
  }

  private reviewedDetailLines(target: Record<string, unknown>): string[] {
    const lines: string[] = [];
    const corrections = this.asNumber(target['corrections_count']);
    const added = this.asNumber(target['added_lines_count']);
    const removed = this.asNumber(target['removed_lines_count']);

    if (corrections !== null && corrections > 0) {
      lines.push(
        this.translate.instant('quotations.audit.details.corrections', {
          count: corrections,
        }),
      );
    }
    if (added !== null && added > 0) {
      lines.push(
        this.translate.instant('quotations.audit.details.addedLines', {
          count: added,
        }),
      );
    }
    if (removed !== null && removed > 0) {
      lines.push(
        this.translate.instant('quotations.audit.details.removedLines', {
          count: removed,
        }),
      );
    }
    return lines;
  }

  private lineLabel(target: Record<string, unknown>): string | null {
    const lineNumber = this.asNumber(target['line_number']);
    const lineText = this.asNonEmptyString(target['line_text']);
    if (lineNumber !== null && lineText) {
      return this.translate.instant('quotations.audit.details.lineWithText', {
        number: lineNumber,
        text: lineText,
      });
    }
    if (lineNumber !== null) {
      return this.translate.instant('quotations.audit.details.lineNumber', {
        number: lineNumber,
      });
    }
    if (lineText) {
      return this.translate.instant('quotations.audit.details.lineText', {
        text: lineText,
      });
    }
    return null;
  }

  private outcomeLabel(outcome: string): string {
    const key = `matching.resolution.outcomes.${outcome}.label`;
    const translated = this.translate.instant(key);
    return translated === key ? outcome : translated;
  }

  private reasonLabel(reason: string): string {
    const key = `matching.queue.reason.${reason}`;
    const translated = this.translate.instant(key);
    return translated === key ? reason : translated;
  }

  private asNonEmptyString(value: unknown): string | null {
    if (typeof value !== 'string') {
      return null;
    }
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : null;
  }

  private asNumber(value: unknown): number | null {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value;
    }
    if (typeof value === 'string' && value.trim() !== '') {
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : null;
    }
    return null;
  }
}
