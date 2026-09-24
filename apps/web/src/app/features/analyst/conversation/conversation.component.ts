import { JsonPipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { finalize } from 'rxjs';

import { AnalystApiService, type AnalystCategory, type AnalystTurn } from '../analyst-api';

const NEXT_STEP_LABEL_KEY_BY_CATEGORY: Partial<Record<AnalystCategory, string>> = {
  supplier_performance_risk: 'analyst.nextStep.negotiationBrief',
  reorder_forecasts: 'analyst.nextStep.reorderQueue',
  spend_savings: 'analyst.nextStep.report',
};

@Component({
  selector: 'app-analyst-conversation',
  standalone: true,
  imports: [
    FormsModule,
    JsonPipe,
    MatButtonModule,
    MatCardModule,
    MatExpansionModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    RouterLink,
    TranslatePipe,
  ],
  templateUrl: './conversation.component.html',
  styleUrl: './conversation.component.scss',
})
export class AnalystConversationComponent implements OnInit {
  private readonly analystApi = inject(AnalystApiService);
  private readonly translate = inject(TranslateService);

  readonly questionText = signal('');
  readonly turns = signal<AnalystTurn[]>([]);
  readonly isAsking = signal(false);
  readonly errorMessage = signal<string | null>(null);

  /** Set after the first successful ask (FR-008): later asks in this session pass
   * it through so the server treats them as follow-ups on the same conversation,
   * with context resolved from the immediately preceding turn, not client-side. */
  private readonly conversationId = signal<string | null>(null);
  private readonly route = inject(ActivatedRoute);

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('conversationId');
    if (id) {
      this.loadConversation(id);
    }
  }

  private loadConversation(id: string): void {
    this.isAsking.set(true);
    this.errorMessage.set(null);
    this.analystApi
      .getConversation(id)
      .pipe(finalize(() => this.isAsking.set(false)))
      .subscribe({
        next: (conversation) => {
          this.conversationId.set(conversation.id);
          this.turns.set(conversation.turns);
        },
        error: () => {
          this.errorMessage.set(this.translate.instant('analyst.errors.load'));
        },
      });
  }

  ask(): void {
    const question = this.questionText().trim();
    if (!question || this.isAsking()) {
      return;
    }
    this.isAsking.set(true);
    this.errorMessage.set(null);
    this.analystApi
      .askQuestion(question, this.conversationId() ?? undefined)
      .pipe(finalize(() => this.isAsking.set(false)))
      .subscribe({
        next: (conversation) => {
          this.conversationId.set(conversation.id);
          // The server returns the full thread for this conversation on every ask,
          // so replace rather than append — appending would duplicate earlier turns.
          this.turns.set(conversation.turns);
          this.questionText.set('');
        },
        error: () => {
          this.errorMessage.set(this.translate.instant('analyst.errors.ask'));
        },
      });
  }

  trackById(_index: number, turn: AnalystTurn): string {
    return turn.id;
  }

  isRefusal(turn: AnalystTurn): boolean {
    return turn.citations.length === 0 && turn.calculation === null;
  }

  nextStepLabelKey(turn: AnalystTurn): string {
    return NEXT_STEP_LABEL_KEY_BY_CATEGORY[turn.category] ?? 'analyst.nextStep.label';
  }
}
