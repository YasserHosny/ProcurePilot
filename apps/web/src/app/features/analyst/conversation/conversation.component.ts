import { JsonPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { finalize } from 'rxjs';

import { AnalystApiService, type AnalystTurn } from '../analyst-api';

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
    TranslatePipe,
  ],
  templateUrl: './conversation.component.html',
  styleUrl: './conversation.component.scss',
})
export class AnalystConversationComponent {
  private readonly analystApi = inject(AnalystApiService);
  private readonly translate = inject(TranslateService);

  readonly questionText = signal('');
  readonly turns = signal<AnalystTurn[]>([]);
  readonly isAsking = signal(false);
  readonly errorMessage = signal<string | null>(null);

  ask(): void {
    const question = this.questionText().trim();
    if (!question || this.isAsking()) {
      return;
    }
    this.isAsking.set(true);
    this.errorMessage.set(null);
    this.analystApi
      .askQuestion(question)
      .pipe(finalize(() => this.isAsking.set(false)))
      .subscribe({
        next: (conversation) => {
          this.turns.update((existing) => [...existing, ...conversation.turns]);
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
}
