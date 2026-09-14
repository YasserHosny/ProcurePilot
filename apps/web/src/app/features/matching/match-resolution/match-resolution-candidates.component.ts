import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslatePipe } from '@ngx-translate/core';

import type { MatchCandidate, MatchOutcome } from '../../../core/api/models';

@Component({
  selector: 'app-match-resolution-candidates',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatIconModule,
    MatDividerModule,
    MatTooltipModule,
    TranslatePipe,
  ],
  templateUrl: './match-resolution-candidates.component.html',
  styleUrl: './match-resolution-candidates.component.scss',
})
export class MatchResolutionCandidatesComponent {
  @Input({ required: true }) candidates: MatchCandidate[] = [];
  @Input({ required: true }) selectedCandidateId: string | null = null;
  @Input({ required: true }) selectedOutcome: MatchOutcome = 'same_product';
  @Input({ required: true }) isWriter = false;
  @Input({ required: true }) hasDecision = false;

  @Output() readonly candidateSelected = new EventEmitter<string>();

  formatScore(score: string | number | undefined | null): number {
    if (score === undefined || score === null) return 0;
    const num = typeof score === 'string' ? parseFloat(score) : score;
    return Math.round(num * 100);
  }

  shouldShowSemanticSignal(candidate: MatchCandidate): boolean {
    return candidate.embedding_model !== 'stub-hash-v1';
  }
}
