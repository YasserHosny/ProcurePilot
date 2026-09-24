import { Pipe, PipeTransform } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter, Router } from '@angular/router';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';

import { FormatDatePipe } from '../../../core/format/date.pipe';
import {
  AnalystApiService,
  type AnalystConversation,
  type AnalystConversationList,
} from '../analyst-api';
import { AnalystHistoryComponent } from './history.component';

// FormatDatePipe pulls in a chain of services down to HttpClient — stub it out here
// the same way quotation-audit-trail.component.spec.ts does, rather than provide a
// real HTTP client just to render a date string.
@Pipe({ name: 'formatDate', standalone: true })
class FormatDatePipeStub implements PipeTransform {
  transform(value: string | Date | number | null | undefined): string {
    return value == null ? '' : String(value);
  }
}

describe('AnalystHistoryComponent (R4.2)', () => {
  let component: AnalystHistoryComponent;
  let fixture: ComponentFixture<AnalystHistoryComponent>;
  let analystApi: jasmine.SpyObj<AnalystApiService>;

  const conversation: AnalystConversation = {
    id: 'conversation-1',
    tenant_id: 'tenant-1',
    creating_member_id: 'member-1',
    created_at: '2026-09-24T00:00:00Z',
    turns: [
      {
        id: 'turn-1',
        conversation_id: 'conversation-1',
        creating_member_id: 'member-1',
        question_text: 'How much have we spent this month?',
        category: 'spend_savings',
        answer_text: 'Total spend: GBP 500.00 across 1 record(s).',
        calculation_version: 'analyst-retrieval-v1',
        release_posture: 'g3_unmet',
        calculation: null,
        citations: [],
        next_step_url: null,
        created_at: '2026-09-24T00:00:00Z',
      },
    ],
  };

  function pageOf(items: AnalystConversation[], next_cursor: string | null = null): AnalystConversationList {
    return { items, next_cursor };
  }

  beforeEach(async () => {
    analystApi = jasmine.createSpyObj<AnalystApiService>('AnalystApiService', [
      'listConversations',
    ]);
    analystApi.listConversations.and.returnValue(of(pageOf([])));

    await TestBed.configureTestingModule({
      imports: [AnalystHistoryComponent, TranslateModule.forRoot()],
      providers: [
        provideNoopAnimations(),
        provideRouter([]),
        { provide: AnalystApiService, useValue: analystApi },
      ],
    })
      .overrideComponent(AnalystHistoryComponent, {
        remove: { imports: [FormatDatePipe] },
        add: { imports: [FormatDatePipeStub] },
      })
      .compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', {
      analyst: {
        history: {
          title: 'Question History',
          newConversation: 'New Conversation',
          empty: 'No past conversations found.',
          turns: '{{count}} turn(s)',
          noTurns: 'Empty conversation',
          loadMore: 'Load More',
        },
      },
    });
    translate.use('en');

    fixture = TestBed.createComponent(AnalystHistoryComponent);
    component = fixture.componentInstance;
  });

  it('creates and loads history on init', () => {
    fixture.detectChanges();
    expect(component).toBeTruthy();
    expect(analystApi.listConversations).toHaveBeenCalledWith(50);
  });

  it('shows the empty state when there are no past conversations', () => {
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('[data-testid="analyst-history-empty"]')).toBeTruthy();
  });

  it('renders one item per past conversation', () => {
    analystApi.listConversations.and.returnValue(of(pageOf([conversation])));
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    const items = el.querySelectorAll('[data-testid="analyst-history-item"]');
    expect(items.length).toBe(1);
    expect(items[0].textContent).toContain('How much have we spent this month?');
  });

  it('navigates to the conversation when an item is opened', () => {
    analystApi.listConversations.and.returnValue(of(pageOf([conversation])));
    fixture.detectChanges();

    const router = TestBed.inject(Router);
    const navigateSpy = spyOn(router, 'navigate');
    component.openConversation(conversation.id);

    expect(navigateSpy).toHaveBeenCalledWith(['/analyst', conversation.id]);
  });

  it('requests the next page with the returned cursor on load more', () => {
    analystApi.listConversations.and.returnValue(of(pageOf([conversation], 'cursor-abc')));
    fixture.detectChanges();

    analystApi.listConversations.and.returnValue(of(pageOf([])));
    component.loadMore();

    expect(analystApi.listConversations).toHaveBeenCalledWith(50, 'cursor-abc');
  });
});
