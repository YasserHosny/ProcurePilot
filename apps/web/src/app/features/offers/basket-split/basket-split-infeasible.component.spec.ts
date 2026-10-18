import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

import en from '../../../../../../../packages/i18n/en.json';
import ar from '../../../../../../../packages/i18n/ar.json';
import type { BasketSplitJob } from '../offers-api';
import { BasketSplitInfeasibleComponent } from './basket-split-infeasible.component';

function failedJob(code?: string, productIds: string[] = []): BasketSplitJob {
  return {
    id: 'job-x',
    supplier_ids: ['s1', 's2'],
    items: [],
    status: 'failed',
    result_url: '/api/v1/baskets/job-x',
    created_at: '2026-10-17T12:00:00Z',
    error: code ? { code, message: 'server text', product_ids: productIds } : null,
  };
}

describe('BasketSplitInfeasibleComponent — optimiser unavailable', () => {
  let fixture: ComponentFixture<BasketSplitInfeasibleComponent>;
  let translate: TranslateService;

  function render(job: BasketSplitJob, products: { id: string; tenant_name: string }[] = []): HTMLElement {
    fixture.componentRef.setInput('uiState', 'failed');
    fixture.componentRef.setInput('currentJob', job);
    fixture.componentRef.setInput('isWriter', true);
    fixture.componentRef.setInput('isSubmitting', false);
    fixture.componentRef.setInput('errorMessage', null);
    fixture.componentRef.setInput('suppliers', []);
    fixture.componentRef.setInput('products', products);
    fixture.componentRef.setInput('violatedConstraints', []);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [BasketSplitInfeasibleComponent, TranslateModule.forRoot()],
      providers: [provideNoopAnimations()],
    });
    translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', en);
    translate.setTranslation('ar', ar);
    translate.use('en');
    fixture = TestBed.createComponent(BasketSplitInfeasibleComponent);
  });

  it('shows the service-unavailable message and a retry button', () => {
    const el = render(failedJob('optimiser_unavailable'));
    expect(el.querySelector('.failed-message')?.textContent).toContain(
      'optimisation service is not responding',
    );
    let emitted = false;
    fixture.componentInstance.rerun.subscribe(() => (emitted = true));
    (el.querySelector('.rerun-btn') as HTMLButtonElement).click();
    expect(emitted).toBeTrue();
  });

  it('maps missing current offers to localized product names', () => {
    const el = render(failedJob('no_offers_for_products', ['p1']), [{ id: 'p1', tenant_name: 'Rice' }]);
    expect(el.querySelector('.failed-message')?.textContent).toContain('No current offers');
    expect(el.querySelector('.failed-message')?.textContent).toContain('Rice');
    translate.use('ar');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('لا توجد عروض حالية');
  });

  it('shows the timeout message', () => {
    const el = render(failedJob('optimiser_timeout'));
    expect(el.querySelector('.failed-message')?.textContent).toContain('did not finish in time');
  });

  it('falls back to the generic message for other failures', () => {
    const el = render(failedJob('basket_split_failed'));
    expect(el.querySelector('.failed-message')?.textContent).toContain('solver execution');
  });

  it('has Arabic copy for both stuck-job messages', () => {
    translate.use('ar');
    expect(translate.instant('basketSplit.status.unavailableMessage')).not.toContain(
      'basketSplit.',
    );
    expect(translate.instant('basketSplit.status.timeoutMessage')).not.toContain('basketSplit.');
  });
});
