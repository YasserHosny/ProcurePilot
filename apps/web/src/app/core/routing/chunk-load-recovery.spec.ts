import { TestBed } from '@angular/core/testing';
import { Router, provideRouter, withNavigationErrorHandler } from '@angular/router';
import {
  CHUNK_LOAD_PAGE_RELOAD,
  chunkLoadErrorHandler,
  isChunkLoadError,
} from './chunk-load-recovery';

describe('chunkLoadRecovery', () => {
  let reloadSpy: jasmine.Spy<(url: string) => void>;
  let router: Router;

  beforeEach(() => {
    sessionStorage.clear();
    reloadSpy = jasmine.createSpy('reloadSpy');

    TestBed.configureTestingModule({
      providers: [
        provideRouter(
          [
            {
              path: 'orders/:id',
              loadComponent: () =>
                Promise.reject(
                  new TypeError(
                    'Failed to fetch dynamically imported module: https://x/chunk-AB12.js',
                  ),
                ),
            },
            {
              path: 'other-error',
              loadComponent: () => Promise.reject(new Error('Network disconnected')),
            },
          ],
          withNavigationErrorHandler(chunkLoadErrorHandler),
        ),
        {
          provide: CHUNK_LOAD_PAGE_RELOAD,
          useValue: reloadSpy,
        },
      ],
    });

    router = TestBed.inject(Router);
  });

  afterEach(() => {
    sessionStorage.clear();
  });

  it('recognizes chunk load errors from error message signatures', () => {
    expect(
      isChunkLoadError(
        new TypeError('Failed to fetch dynamically imported module: https://x/chunk-AB12.js'),
      ),
    ).toBeTrue();
    expect(isChunkLoadError(new Error('Importing a module script failed.'))).toBeTrue();
    expect(isChunkLoadError(new Error('error loading dynamically imported module'))).toBeTrue();
    expect(
      isChunkLoadError(
        new Error(
          'Expected a JavaScript module script but the server responded with a MIME type of "text/html"',
        ),
      ),
    ).toBeTrue();
    expect(isChunkLoadError(new Error('ChunkLoadError: Loading chunk 4 failed'))).toBeTrue();
    expect(isChunkLoadError(new Error('Loading chunk 2 failed'))).toBeTrue();
    expect(isChunkLoadError(new Error('Unrelated error'))).toBeFalse();
    expect(isChunkLoadError(null)).toBeFalse();
  });

  it('navigating to /orders/po-1 calls the reload spy once with /orders/po-1', async () => {
    try {
      await router.navigateByUrl('/orders/po-1');
    } catch {
      // navigation rejection is expected
    }
    expect(reloadSpy).toHaveBeenCalledTimes(1);
    expect(reloadSpy).toHaveBeenCalledWith('/orders/po-1');
  });

  it('a non-chunk error does not call the reload spy', async () => {
    try {
      await router.navigateByUrl('/other-error');
    } catch {
      // navigation rejection is expected
    }
    expect(reloadSpy).not.toHaveBeenCalled();
  });

  it('a second failure for the same URL within 30 s does not call reload again', async () => {
    try {
      await router.navigateByUrl('/orders/po-1');
    } catch {
      // navigation rejection is expected
    }

    expect(reloadSpy).toHaveBeenCalledTimes(1);

    try {
      await router.navigateByUrl('/orders/po-1');
    } catch {
      // navigation rejection is expected
    }

    expect(reloadSpy).toHaveBeenCalledTimes(1);
  });
});
