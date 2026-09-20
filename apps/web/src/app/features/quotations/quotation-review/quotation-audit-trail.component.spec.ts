import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Pipe, PipeTransform } from '@angular/core';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

import { FormatDatePipe } from '../../../core/format/date.pipe';
import { QuotationAuditTrailComponent } from './quotation-audit-trail.component';

@Pipe({ name: 'formatDate', standalone: true })
class FormatDatePipeStub implements PipeTransform {
  transform(value: string | Date | number | null | undefined): string {
    return value == null ? '' : String(value);
  }
}

describe('QuotationAuditTrailComponent', () => {
  let fixture: ComponentFixture<QuotationAuditTrailComponent>;
  let component: QuotationAuditTrailComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [QuotationAuditTrailComponent, TranslateModule.forRoot()],
    })
      .overrideComponent(QuotationAuditTrailComponent, {
        remove: { imports: [FormatDatePipe] },
        add: { imports: [FormatDatePipeStub] },
      })
      .compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', {
      quotations: {
        audit: {
          title: 'Audit Trail',
          empty: 'No audit events recorded',
          system: 'System',
          actions: {
            matchingAutoAccepted: 'Product match accepted automatically',
            matchingTaskRouted: 'Line routed for product matching review',
          },
          details: {
            lineWithText: 'Line {{number}}: {{text}}',
            matchedProduct: 'Matched product: {{name}}',
            outcome: 'Outcome: {{outcome}}',
            score: 'Match score: {{score}}',
            reason: 'Reason: {{reason}}',
          },
        },
      },
      matching: {
        queue: {
          reason: {
            no_candidate: 'No Candidate',
          },
        },
        resolution: {
          outcomes: {
            same_product: {
              label: 'Same Product',
            },
          },
        },
      },
    });
    translate.use('en');

    fixture = TestBed.createComponent(QuotationAuditTrailComponent);
    component = fixture.componentInstance;
  });

  it('renders enriched matching auto-accept details', () => {
    component.isLoading = false;
    component.auditTrail = [
      {
        id: 1,
        action: 'matching.auto_accepted',
        actor_email: 'buyer@example.test',
        outcome: 'success',
        target: {
          line_number: 1,
          line_text: 'A4 Copy Paper 80gsm (5-ream box)',
          matched_product_name: 'Office Plus / A4 Copy Paper 80gsm / White',
          outcome: 'same_product',
          score: '0.9650',
        },
        trace_id: null,
        occurred_at: '2026-09-19T13:05:26.868Z',
      },
    ];
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Product match accepted automatically');
    expect(text).toContain('Line 1: A4 Copy Paper 80gsm (5-ream box)');
    expect(text).toContain('Matched product: Office Plus / A4 Copy Paper 80gsm / White');
    expect(text).toContain('Outcome: Same Product');
    expect(text).toContain('Match score: 0.9650');
    expect(text).toContain('buyer@example.test');
  });

  it('renders routed-task reason details', () => {
    component.isLoading = false;
    component.auditTrail = [
      {
        id: 2,
        action: 'matching.task_routed',
        actor_email: null,
        outcome: 'success',
        target: {
          line_number: 2,
          line_text: 'Ballpoint Pen Blue (50-pack)',
          reason: 'no_candidate',
        },
        trace_id: null,
        occurred_at: '2026-09-19T13:05:27.586Z',
      },
    ];
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Line 2: Ballpoint Pen Blue (50-pack)');
    expect(text).toContain('Reason: No Candidate');
  });
});
