import { DOCUMENT } from '@angular/common';
import { InjectionToken, inject } from '@angular/core';
import type { NavigationError } from '@angular/router';

const CHUNK_LOAD_ERROR_PATTERNS: readonly string[] = [
  'Failed to fetch dynamically imported module',
  'Importing a module script failed',
  'error loading dynamically imported module',
  'Expected a JavaScript',
  'ChunkLoadError',
  'Loading chunk',
];

export function isChunkLoadError(error: unknown): boolean {
  if (!error) {
    return false;
  }
  if (typeof error === 'object' && error !== null && 'error' in error) {
    const inner = (error as { error: unknown }).error;
    if (inner && isChunkLoadError(inner)) {
      return true;
    }
  }
  const msg =
    error instanceof Error || (typeof error === 'object' && 'message' in error)
      ? String((error as { message: unknown }).message)
      : typeof error === 'string'
        ? error
        : '';

  if (!msg) {
    return false;
  }
  return CHUNK_LOAD_ERROR_PATTERNS.some((pattern) => msg.includes(pattern));
}

export const CHUNK_LOAD_PAGE_RELOAD = new InjectionToken<(url: string) => void>(
  'CHUNK_LOAD_PAGE_RELOAD',
  {
    providedIn: 'root',
    factory: () => {
      const doc = inject(DOCUMENT);
      return (url: string) => doc.location.assign(url);
    },
  },
);

export function chunkLoadErrorHandler(error: NavigationError): void {
  const cause = error.error ?? error;
  if (!isChunkLoadError(cause)) {
    return;
  }

  const reload = inject(CHUNK_LOAD_PAGE_RELOAD);
  const url = error.url;
  const storageKey = `pp.chunk_reload:${url}`;
  const now = Date.now();

  try {
    const lastReloadStr = sessionStorage.getItem(storageKey);
    if (lastReloadStr) {
      const lastReload = parseInt(lastReloadStr, 10);
      if (!isNaN(lastReload) && now - lastReload < 30_000) {
        return;
      }
    }
    sessionStorage.setItem(storageKey, now.toString());
  } catch {
    return;
  }

  reload(url);
}
