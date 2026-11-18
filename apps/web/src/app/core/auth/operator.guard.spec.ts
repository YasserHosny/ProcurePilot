import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import {
  ActivatedRouteSnapshot,
  Router,
  RouterStateSnapshot,
  UrlTree,
} from '@angular/router';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { operatorGuard } from './operator.guard';
import { OperatorService } from './operator.service';
import { SessionService } from './session.service';

describe('operatorGuard and OperatorService', () => {
  const meUrl = `${environment.apiBaseUrl}/platform/feedback/me`;
  const member = signal<{ id: string } | null>({ id: 'u1' });
  let http: HttpTestingController;
  let router: jasmine.SpyObj<Router>;
  const redirect = {} as UrlTree;

  function run(): Observable<boolean | UrlTree> {
    return TestBed.runInInjectionContext(() =>
      operatorGuard({} as ActivatedRouteSnapshot, {} as RouterStateSnapshot),
    ) as Observable<boolean | UrlTree>;
  }

  beforeEach(() => {
    member.set({ id: 'u1' });
    router = jasmine.createSpyObj<Router>('Router', ['createUrlTree']);
    router.createUrlTree.and.returnValue(redirect);
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: Router, useValue: router },
        { provide: SessionService, useValue: { currentMember: member } },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('allows an operator and exposes the digest preference', () => {
    let result: boolean | UrlTree | undefined;
    run().subscribe((r) => (result = r));
    http.expectOne(meUrl).flush({ digest_enabled: true, digest_locale: 'en' });
    expect(result).toBeTrue();
    const operator = TestBed.inject(OperatorService);
    expect(operator.isOperator()).toBeTrue();
    expect(operator.profile()?.digest_enabled).toBeTrue();
  });

  it('redirects home on 404 (not an operator) and caches the answer', () => {
    let result: boolean | UrlTree | undefined;
    run().subscribe((r) => (result = r));
    http.expectOne(meUrl).flush({ code: 'not_found' }, { status: 404, statusText: 'Not Found' });
    expect(result).toBe(redirect);
    expect(router.createUrlTree).toHaveBeenCalledWith(['/']);
    expect(TestBed.inject(OperatorService).isOperator()).toBeFalse();

    run().subscribe();
    http.expectNone(meUrl);
  });

  it('does not cache a transient failure', () => {
    let result: boolean | UrlTree | undefined;
    run().subscribe((r) => (result = r));
    http.expectOne(meUrl).flush('boom', { status: 500, statusText: 'Server Error' });
    expect(result).toBe(redirect);

    run().subscribe();
    http.expectOne(meUrl).flush({ digest_enabled: false, digest_locale: 'en' });
  });

  it('asks again when a different user signs in', () => {
    run().subscribe();
    http.expectOne(meUrl).flush({ digest_enabled: false, digest_locale: 'en' });
    const operator = TestBed.inject(OperatorService);
    expect(operator.isOperator()).toBeTrue();

    member.set({ id: 'u2' });
    expect(operator.isOperator()).toBeFalse();
    operator.load().subscribe();
    http.expectOne(meUrl).flush({ code: 'not_found' }, { status: 404, statusText: 'Not Found' });
    expect(operator.isOperator()).toBeFalse();
  });
});
