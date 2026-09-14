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
}
