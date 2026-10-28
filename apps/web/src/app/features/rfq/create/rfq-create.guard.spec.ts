import { TestBed } from '@angular/core/testing';
import { Observable, of } from 'rxjs';
import { rfqDirtyGuard, CanComponentDeactivate } from './rfq-create.guard';

describe('rfqDirtyGuard', () => {
  let mockComponent: CanComponentDeactivate;

  it('asks only when dirty (allows leaving when pristine)', () => {
    mockComponent = {
      canDeactivate: jasmine.createSpy('canDeactivate').and.returnValue(true),
    };

    const result = TestBed.runInInjectionContext(() =>
      rfqDirtyGuard(mockComponent, null as never, null as never, null as never),
    );

    expect(result).toBeTrue();
    expect(mockComponent.canDeactivate).toHaveBeenCalled();
  });

  it('no prompt after save/send (returns true when component state is clean/saved)', () => {
    mockComponent = {
      canDeactivate: jasmine.createSpy('canDeactivate').and.returnValue(true),
    };

    const result = TestBed.runInInjectionContext(() =>
      rfqDirtyGuard(mockComponent, null as never, null as never, null as never),
    );

    expect(result).toBeTrue();
    expect(mockComponent.canDeactivate).toHaveBeenCalled();
  });

  it('prompts via confirm dialog when form is dirty, allows navigation when confirmed', (done) => {
    mockComponent = {
      canDeactivate: jasmine.createSpy('canDeactivate').and.returnValue(of(true)),
    };

    const result$ = TestBed.runInInjectionContext(() =>
      rfqDirtyGuard(mockComponent, null as never, null as never, null as never),
    ) as Observable<boolean>;

    result$.subscribe((allowed: boolean) => {
      expect(allowed).toBeTrue();
      expect(mockComponent.canDeactivate).toHaveBeenCalled();
      done();
    });
  });

  it('prompts via confirm dialog when form is dirty, cancels navigation when discarded', (done) => {
    mockComponent = {
      canDeactivate: jasmine.createSpy('canDeactivate').and.returnValue(of(false)),
    };

    const result$ = TestBed.runInInjectionContext(() =>
      rfqDirtyGuard(mockComponent, null as never, null as never, null as never),
    ) as Observable<boolean>;

    result$.subscribe((allowed: boolean) => {
      expect(allowed).toBeFalse();
      expect(mockComponent.canDeactivate).toHaveBeenCalled();
      done();
    });
  });
});
