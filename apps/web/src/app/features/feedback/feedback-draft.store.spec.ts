import { TestBed } from '@angular/core/testing';

import { FeedbackDraftStore } from './feedback-draft.store';

function png(name = 'a.png'): File {
  return new File([new Uint8Array(4)], name, { type: 'image/png' });
}

describe('FeedbackDraftStore', () => {
  let store: FeedbackDraftStore;

  beforeEach(() => {
    store = TestBed.inject(FeedbackDraftStore);
  });

  it('is empty until text or an attachment is added', () => {
    expect(store.isEmpty()).toBeTrue();
    store.text.set('   ');
    expect(store.isEmpty()).toBeTrue();
    store.text.set('hello');
    expect(store.isEmpty()).toBeFalse();
    store.text.set('');
    store.addImage(png());
    expect(store.isEmpty()).toBeFalse();
  });

  it('adds, removes and revokes image previews', () => {
    const revoke = spyOn(URL, 'revokeObjectURL').and.callThrough();
    store.addImage(png('a.png'));
    store.addImage(png('b.png'));
    const [first] = store.images();
    expect(first.previewUrl).toMatch(/^blob:/);
    store.removeImage(first.id);
    expect(store.images().map((i) => i.file.name)).toEqual(['b.png']);
    expect(revoke).toHaveBeenCalledWith(first.previewUrl);
  });

  it('replaces the audio and revokes the previous preview', () => {
    const revoke = spyOn(URL, 'revokeObjectURL').and.callThrough();
    store.setAudio(new File([new Uint8Array(2)], 'a.webm', { type: 'audio/webm' }));
    const first = store.audio()!.previewUrl;
    store.setAudio(new File([new Uint8Array(2)], 'b.webm', { type: 'audio/webm' }));
    expect(store.audio()!.file.name).toBe('b.webm');
    expect(revoke).toHaveBeenCalledWith(first);
  });

  it('keeps one idempotency key until the draft is reset', () => {
    let n = 0;
    const create = (): string => `key-${++n}`;
    expect(store.idempotencyKey(create)).toBe('key-1');
    expect(store.idempotencyKey(create)).toBe('key-1');
    store.reset();
    expect(store.idempotencyKey(create)).toBe('key-2');
  });

  it('clears the draft when a different member claims it', () => {
    store.claim('user-a|tenant-1');
    store.text.set('private note');
    store.category.set('bug');
    store.claim('user-a|tenant-1');
    expect(store.text()).toBe('private note');
    store.claim('user-b|tenant-1');
    expect(store.text()).toBe('');
    expect(store.category()).toBeNull();
    store.text.set('x');
    store.claim('user-a|tenant-2');
    expect(store.text()).toBe('');
  });
});
