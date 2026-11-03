import { TestBed } from '@angular/core/testing';
import { Observable, of } from 'rxjs';
import { quotationReviewGuard, CanComponentDeactivate } from './quotation-review.guard';

describe('quotationReviewGuard', () => {
  it('allows deactivation when component is null or undefined', () => {
    const result = TestBed.runInInjectionContext(() =>
      quotationReviewGuard(null as unknown as CanComponentDeactivate, null as never, null as never, null as never),
    );
    expect(result).toBeTrue();
  });

  it('allows deactivation when component has no canDeactivate method', () => {
    const result = TestBed.runInInjectionContext(() =>
      quotationReviewGuard({} as CanComponentDeactivate, null as never, null as never, null as never),
    );
    expect(result).toBeTrue();
  });

  it('delegates to component.canDeactivate when provided', (done) => {
    const mockComponent: CanComponentDeactivate = {
      canDeactivate: jasmine.createSpy('canDeactivate').and.returnValue(of(false)),
    };
    const result$ = TestBed.runInInjectionContext(() =>
      quotationReviewGuard(mockComponent, null as never, null as never, null as never),
    ) as Observable<boolean>;

    result$.subscribe((allowed: boolean) => {
      expect(allowed).toBeFalse();
      expect(mockComponent.canDeactivate).toHaveBeenCalled();
      done();
    });
  });
});
