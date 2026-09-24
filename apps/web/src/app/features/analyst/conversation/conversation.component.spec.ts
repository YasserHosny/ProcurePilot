import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';

import { AnalystApiService, type AnalystConversation, type AnalystTurn } from '../analyst-api';
import { AnalystConversationComponent } from './conversation.component';

describe('AnalystConversationComponent (R4.2)', () => {
  let component: AnalystConversationComponent;
  let fixture: ComponentFixture<AnalystConversationComponent>;
  let analystApi: jasmine.SpyObj<AnalystApiService>;

  const citedTurn: AnalystTurn = {
    id: 'turn-1',
    conversation_id: 'conversation-1',
    creating_member_id: 'member-1',
    question_text: 'How much have we spent this month?',
    category: 'spend_savings',
    answer_text: 'Total spend: GBP 500.00 across 1 record(s).',
    calculation_version: 'analyst-retrieval-v1',
    release_posture: 'g3_unmet',
    calculation: {
      inputs: [{ label: 'spend records', count: 1, currency: 'GBP' }],
      formula: 'sum of all spend amounts',
      result: { amount: '500.0000', currency: 'GBP' },
    },
    citations: [
      {
        id: 'citation-1',
        turn_id: 'turn-1',
        source_kind: 'purchase_order',
        source_id: 'order-1',
        created_at: '2026-09-24T00:00:00Z',
      },
    ],
    next_step_url: null,
    created_at: '2026-09-24T00:00:00Z',
  };

  const refusalTurn: AnalystTurn = {
    ...citedTurn,
    id: 'turn-2',
    question_text: "What's the meaning of life?",
    answer_text: "I can't answer that question yet. This analyst only supports...",
    calculation: null,
    citations: [],
  };

  function conversationWith(turn: AnalystTurn): AnalystConversation {
    return {
      id: turn.conversation_id,
      tenant_id: 'tenant-1',
      creating_member_id: turn.creating_member_id,
      created_at: turn.created_at,
      turns: [turn],
    };
  }

  beforeEach(async () => {
    analystApi = jasmine.createSpyObj<AnalystApiService>('AnalystApiService', ['askQuestion']);

    await TestBed.configureTestingModule({
      imports: [AnalystConversationComponent, TranslateModule.forRoot()],
      providers: [provideNoopAnimations(), { provide: AnalystApiService, useValue: analystApi }],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', {
      common: { loading: 'Loading' },
      analyst: {
        title: 'Procurement Analyst',
        subtitle: 'Ask a question about your own data.',
        g3: { title: 'G3 evidence is still unmet', message: 'Advisory only.' },
        form: { label: 'Ask a question', submit: 'Ask' },
        empty: { title: 'No questions yet', message: 'Ask your first question.' },
        threadLabel: 'Conversation',
        calculation: { title: 'Show calculation' },
        citations: {
          label: 'Sources:',
          kind: { purchase_order: 'Purchase order' },
        },
        nextStep: { label: 'View details' },
        errors: { ask: 'The question could not be answered.' },
      },
    });
    translate.use('en');

    fixture = TestBed.createComponent(AnalystConversationComponent);
    component = fixture.componentInstance;
  });

  it('creates', () => {
    expect(component).toBeTruthy();
  });

  it('shows the empty state before any question is asked', () => {
    fixture.detectChanges();
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('No questions yet');
  });

  it('asks a question and renders a cited, calculated answer', () => {
    analystApi.askQuestion.and.returnValue(of(conversationWith(citedTurn)));
    fixture.detectChanges();

    component.questionText.set('How much have we spent this month?');
    component.ask();
    fixture.detectChanges();

    expect(analystApi.askQuestion).toHaveBeenCalledWith('How much have we spent this month?');
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('[data-testid="analyst-answer-text"]')?.textContent).toContain(
      'Total spend',
    );
    expect(el.querySelector('[data-testid="analyst-citations"]')).toBeTruthy();
    expect(component.isRefusal(citedTurn)).toBeFalse();
    // The question box clears after a successful ask.
    expect(component.questionText()).toBe('');
  });

  it('renders the unsupported-category refusal with no citations', () => {
    analystApi.askQuestion.and.returnValue(of(conversationWith(refusalTurn)));
    fixture.detectChanges();

    component.questionText.set("What's the meaning of life?");
    component.ask();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('[data-testid="analyst-answer-text"]')?.textContent).toContain(
      "can't answer",
    );
    expect(el.querySelector('[data-testid="analyst-citations"]')).toBeFalsy();
    expect(component.isRefusal(refusalTurn)).toBeTrue();
  });

  it('shows an error message when the question cannot be answered', () => {
    analystApi.askQuestion.and.returnValue(throwError(() => new Error('boom')));
    fixture.detectChanges();

    component.questionText.set('anything');
    component.ask();
    fixture.detectChanges();

    expect(component.errorMessage()).toBe('The question could not be answered.');
  });

  it('does not submit an empty or whitespace-only question', () => {
    fixture.detectChanges();
    component.questionText.set('   ');
    component.ask();
    expect(analystApi.askQuestion).not.toHaveBeenCalled();
  });
});
