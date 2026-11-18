import { Injectable, computed, signal } from '@angular/core';

import type { FeedbackCategory } from './feedback-api';

export interface DraftImage {
  readonly id: string;
  readonly file: File;
  readonly previewUrl: string;
}

export interface DraftAudio {
  readonly file: File;
  readonly previewUrl: string;
}

/**
 * The feedback being composed. It outlives the dialog on purpose: a dropped connection, a closed
 * dialog or an expired session (which navigates to sign-in) must not cost the member their draft.
 * It never outlives the person: it is claimed per member and workspace and cleared on a mismatch,
 * so a colleague signing in on the same browser does not see it.
 */
@Injectable({ providedIn: 'root' })
export class FeedbackDraftStore {
  readonly text = signal('');
  readonly category = signal<FeedbackCategory | null>(null);
  readonly images = signal<readonly DraftImage[]>([]);
  readonly audio = signal<DraftAudio | null>(null);
  readonly owner = signal<string | null>(null);

  private key: string | null = null;
  private nextId = 0;

  readonly isEmpty = computed(
    () => this.text().trim().length === 0 && this.images().length === 0 && this.audio() === null,
  );

  /** Binds the draft to a member; a different member starts from a blank draft. */
  claim(owner: string | null): void {
    if (this.owner() !== owner) {
      this.reset();
      this.owner.set(owner);
    }
  }

  /** One key per composition, so retrying the same draft cannot create a second submission. */
  idempotencyKey(create: () => string): string {
    this.key ??= create();
    return this.key;
  }

  addImage(file: File): void {
    const image: DraftImage = {
      id: `img-${this.nextId++}`,
      file,
      previewUrl: URL.createObjectURL(file),
    };
    this.images.update((list) => [...list, image]);
  }

  removeImage(id: string): void {
    const removed = this.images().find((image) => image.id === id);
    if (removed) URL.revokeObjectURL(removed.previewUrl);
    this.images.update((list) => list.filter((image) => image.id !== id));
  }

  setAudio(file: File): void {
    this.clearAudio();
    this.audio.set({ file, previewUrl: URL.createObjectURL(file) });
  }

  clearAudio(): void {
    const current = this.audio();
    if (current) URL.revokeObjectURL(current.previewUrl);
    this.audio.set(null);
  }

  /** Clears everything, including the key: the next draft is a new submission. */
  reset(): void {
    this.images().forEach((image) => URL.revokeObjectURL(image.previewUrl));
    this.clearAudio();
    this.images.set([]);
    this.text.set('');
    this.category.set(null);
    this.key = null;
  }
}
