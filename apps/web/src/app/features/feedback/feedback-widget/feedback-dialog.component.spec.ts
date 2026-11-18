import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { MatDialogRef } from '@angular/material/dialog';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { I18nService } from '../../../core/i18n';
import { AudioRecorderService } from '../audio-recorder.service';
import { FeedbackDraftStore } from '../feedback-draft.store';
import type { Submission } from '../feedback-api';
import { FeedbackDialogComponent } from './feedback-dialog.component';

const en = enCatalog.feedback;

const created: Submission = {
  id: '11111111-1111-4111-8111-111111111111',
  text: 'It broke',
  category: 'bug',
  status: 'new',
  member_role: 'viewer',
  page_path: '/home',
  locale: 'en',
  created_at: '2026-11-18T10:00:00Z',
  can_withdraw: true,
  attachments: [],
};

function makeRecorder(supported = true) {
  const rec = {
    supported,
    state: signal<'idle' | 'recording'>('idle'),
    elapsedSeconds: signal(0),
    error: signal<'denied' | 'unavailable' | 'failed' | null>(null),
    autoStopped: signal(false),
    result: signal<File | null>(null),
    start: jasmine.createSpy('start').and.resolveTo(),
    stop: jasmine.createSpy('stop'),
    cancel: jasmine.createSpy('cancel'),
    takeResult: jasmine.createSpy('takeResult'),
  };
  rec.takeResult.and.callFake(() => {
    const file = rec.result();
    rec.result.set(null);
    return file;
  });
  return rec;
}

function file(name: string, type: string, size = 10): File {
  return new File([new Uint8Array(size)], name, { type });
}

describe('FeedbackDialogComponent (widget form, US1 to US3)', () => {
  let fixture: ComponentFixture<FeedbackDialogComponent>;
  let http: HttpTestingController;
  let dialogRef: jasmine.SpyObj<MatDialogRef<FeedbackDialogComponent>>;
  let draft: FeedbackDraftStore;
  let recorder: ReturnType<typeof makeRecorder>;

  const root = (): HTMLElement => fixture.nativeElement as HTMLElement;
  const q = <T extends HTMLElement = HTMLElement>(selector: string): T | null =>
    root().querySelector<T>(selector);
  const text = (selector: string): string => (q(selector)?.textContent ?? '').replace(/\s+/g, ' ').trim();

  function typeText(value: string): void {
    const area = q<HTMLTextAreaElement>('textarea')!;
    area.value = value;
    area.dispatchEvent(new Event('input'));
    fixture.detectChanges();
  }

  function click(selector: string): void {
    q<HTMLButtonElement>(selector)!.click();
    fixture.detectChanges();
  }

  function chooseImages(files: File[]): void {
    const input = q<HTMLInputElement>('input[data-test="image-input"]')!;
    const transfer = new DataTransfer();
    files.forEach((f) => transfer.items.add(f));
    input.files = transfer.files;
    input.dispatchEvent(new Event('change'));
    fixture.detectChanges();
  }

  function chooseAudio(f: File): void {
    const input = q<HTMLInputElement>('input[data-test="audio-input"]')!;
    const transfer = new DataTransfer();
    transfer.items.add(f);
    input.files = transfer.files;
    input.dispatchEvent(new Event('change'));
    fixture.detectChanges();
  }

  function paste(target: HTMLElement, files: File[], plainText?: string): void {
    const transfer = new DataTransfer();
    files.forEach((f) => transfer.items.add(f));
    if (plainText) transfer.setData('text/plain', plainText);
    target.dispatchEvent(
      new ClipboardEvent('paste', { clipboardData: transfer, bubbles: true, cancelable: true }),
    );
    fixture.detectChanges();
  }

  async function setup(opts: { recorderSupported?: boolean } = {}): Promise<void> {
    recorder = makeRecorder(opts.recorderSupported ?? true);
    dialogRef = jasmine.createSpyObj('MatDialogRef', ['close']);
    await TestBed.configureTestingModule({
      imports: [FeedbackDialogComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        provideRouter([]),
        provideTranslateService(),
        { provide: I18nService, useValue: { currentLocale: signal('en') } },
        { provide: MatDialogRef, useValue: dialogRef },
      ],
    })
      .overrideComponent(FeedbackDialogComponent, {
        set: { providers: [{ provide: AudioRecorderService, useValue: recorder }] },
      })
      .compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');

    http = TestBed.inject(HttpTestingController);
    draft = TestBed.inject(FeedbackDraftStore);
    draft.reset();
    fixture = TestBed.createComponent(FeedbackDialogComponent);
    fixture.detectChanges();
  }

  afterEach(() => {
    http.verify();
    draft.reset();
  });

  describe('composing text (US1)', () => {
    beforeEach(async () => setup());

    it('shows the staff-visibility notice, a message box, an optional category and Send', () => {
      expect(text('[data-test="notice"]')).toBe(en.notice);
      expect(q('textarea')).not.toBeNull();
      expect(q('mat-select')).not.toBeNull();
      expect(q('[data-test="send"]')).not.toBeNull();
      expect(text('[data-test="counter"]')).toBe('2000 characters left');
    });

    it('limits the box to 2000 characters and counts down to 0', () => {
      expect(q<HTMLTextAreaElement>('textarea')!.maxLength).toBe(2000);
      typeText('x'.repeat(1990));
      expect(text('[data-test="counter"]')).toBe('10 characters left');
      typeText('x'.repeat(2000));
      expect(text('[data-test="counter"]')).toBe('0 characters left');
    });

    it('blocks an empty message with a validation message and sends nothing', () => {
      click('[data-test="send"]');
      expect(text('[data-test="text-error"]')).toBe(en.errors.textRequired);
      expect(q('textarea')!.getAttribute('aria-invalid')).toBe('true');
      http.expectNone('/api/v1/feedback');
    });

    it('treats whitespace-only text as empty', () => {
      typeText('   \n  ');
      click('[data-test="send"]');
      expect(q('[data-test="text-error"]')).not.toBeNull();
      http.expectNone('/api/v1/feedback');
    });

    it('sends text without a category, then shows the success state and clears the draft', () => {
      typeText('  It broke  ');
      click('[data-test="send"]');
      const req = http.expectOne('/api/v1/feedback');
      const body = req.request.body as FormData;
      expect(body.get('text')).toBe('It broke');
      expect(body.has('category')).toBeFalse();
      expect(q<HTMLButtonElement>('[data-test="send"]')!.disabled).toBeTrue();

      req.flush(created, { status: 201, statusText: 'Created' });
      fixture.detectChanges();

      expect(text('[data-test="success"]')).toContain(en.widget.successTitle);
      expect(q('textarea')).toBeNull();
      expect(text('[data-test="notice"]')).toBe(en.notice);
      expect(draft.text()).toBe('');
    });

    it('sends the chosen category', () => {
      draft.category.set('idea');
      typeText('Add dark mode');
      click('[data-test="send"]');
      const body = http.expectOne('/api/v1/feedback').request.body as FormData;
      expect(body.get('category')).toBe('idea');
    });

    it('creates one submission when Send is double-clicked', () => {
      typeText('Once only');
      const button = q<HTMLButtonElement>('[data-test="send"]')!;
      button.click();
      button.click();
      http.expectOne('/api/v1/feedback');
    });

    it('closes the dialog from the Close button', () => {
      click('[data-test="close"]');
      expect(dialogRef.close).toHaveBeenCalled();
    });

    it('keeps the draft and says so when the connection is lost, retrying once first', fakeAsync(() => {
      typeText('Draft survives');
      click('[data-test="send"]');
      http.expectOne('/api/v1/feedback').error(new ProgressEvent('error'), { status: 0 });
      tick(1000);
      http.expectOne('/api/v1/feedback').error(new ProgressEvent('error'), { status: 0 });
      fixture.detectChanges();

      expect(text('[data-test="form-error"]')).toContain(en.errors.network);
      expect(text('[data-test="form-error"]')).toContain(en.widget.draftKept);
      expect(q<HTMLTextAreaElement>('textarea')!.value).toBe('Draft survives');
      expect(q<HTMLButtonElement>('[data-test="send"]')!.disabled).toBeFalse();
    }));

    it('reuses the Idempotency-Key when the same draft is sent again, and a new one after success', () => {
      typeText('Same draft');
      click('[data-test="send"]');
      const first = http.expectOne('/api/v1/feedback');
      const key = first.request.headers.get('Idempotency-Key');
      first.flush(
        { code: 'server', message: 'x', trace_id: 't' },
        { status: 500, statusText: 'Server Error' },
      );
      fixture.detectChanges();
      expect(text('[data-test="form-error"]')).toContain(en.errors.server);

      click('[data-test="send"]');
      const second = http.expectOne('/api/v1/feedback');
      expect(second.request.headers.get('Idempotency-Key')).toBe(key);
      second.flush(created, { status: 201, statusText: 'Created' });
      fixture.detectChanges();

      draft.text.set('Next draft');
      const next = TestBed.createComponent(FeedbackDialogComponent);
      next.detectChanges();
      (next.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('[data-test="send"]')!.click();
      const third = http.expectOne('/api/v1/feedback');
      expect(third.request.headers.get('Idempotency-Key')).not.toBe(key);
      third.flush(created, { status: 201, statusText: 'Created' });
    });

    it('refuses a second send inside the cooldown, shows the time left and counts down', fakeAsync(() => {
      typeText('Too soon');
      click('[data-test="send"]');
      http.expectOne('/api/v1/feedback').flush(
        {
          code: 'feedback.cooldown',
          message: 'wait',
          details: { retry_after_seconds: 12 },
          trace_id: 't',
        },
        { status: 429, statusText: 'Too Many Requests' },
      );
      fixture.detectChanges();

      expect(text('[data-test="cooldown"]')).toContain('12 s');
      expect(q<HTMLButtonElement>('[data-test="send"]')!.disabled).toBeTrue();
      expect(q<HTMLTextAreaElement>('textarea')!.value).toBe('Too soon');

      tick(5000);
      fixture.detectChanges();
      expect(text('[data-test="cooldown"]')).toContain('7 s');

      tick(7000);
      fixture.detectChanges();
      expect(q('[data-test="cooldown"]')).toBeNull();
      expect(q<HTMLButtonElement>('[data-test="send"]')!.disabled).toBeFalse();
    }));

    it('shows a generic message for a rate limit that is not the cooldown', () => {
      typeText('Spam?');
      click('[data-test="send"]');
      http
        .expectOne('/api/v1/feedback')
        .flush(
          { code: 'rate_limited', message: 'slow', trace_id: 't' },
          { status: 429, statusText: 'Too Many Requests' },
        );
      fixture.detectChanges();
      expect(text('[data-test="form-error"]')).toContain(en.errors.rateLimited);
      expect(q('[data-test="cooldown"]')).toBeNull();
    });

    it('prompts sign-in and keeps the draft when the session has expired', () => {
      typeText('Mid-compose');
      click('[data-test="send"]');
      http
        .expectOne('/api/v1/feedback')
        .flush(
          { code: 'auth.unauthorized', message: 'no', trace_id: 't' },
          { status: 401, statusText: 'Unauthorized' },
        );
      fixture.detectChanges();
      expect(text('[data-test="form-error"]')).toContain(en.errors.sessionExpired);
      expect(draft.text()).toBe('Mid-compose');
    });

    it('maps 413, 415 and 422 to specific messages', () => {
      const cases: [number, string][] = [
        [413, en.errors.tooLarge],
        [415, en.errors.unsupportedType],
        [422, en.errors.invalid],
      ];
      for (const [status, message] of cases) {
        typeText('Try');
        click('[data-test="send"]');
        http
          .expectOne('/api/v1/feedback')
          .flush({ code: 'x', message: 'x', trace_id: 't' }, { status, statusText: 'Err' });
        fixture.detectChanges();
        expect(text('[data-test="form-error"]')).toContain(message);
      }
    });
  });

  describe('screenshots (US2)', () => {
    beforeEach(async () => setup());

    it('adds previews from the picker and removes one on request', () => {
      chooseImages([file('a.png', 'image/png'), file('b.jpg', 'image/jpeg')]);
      expect(root().querySelectorAll('[data-test="thumb"]').length).toBe(2);
      click('[data-test="remove-image"]');
      expect(root().querySelectorAll('[data-test="thumb"]').length).toBe(1);
      expect(draft.images()[0].file.name).toBe('b.jpg');
    });

    it('refuses a sixth screenshot with a message', () => {
      chooseImages(Array.from({ length: 5 }, (_, i) => file(`s${i}.png`, 'image/png')));
      chooseImages([file('six.png', 'image/png')]);
      expect(root().querySelectorAll('[data-test="thumb"]').length).toBe(5);
      expect(text('[data-test="attachment-messages"]')).toContain(en.attachments.count);
    });

    it('rejects a wrong type or an oversized file before any upload, naming the reason', () => {
      chooseImages([file('anim.gif', 'image/gif'), file('huge.png', 'image/png', 5 * 1024 * 1024 + 1)]);
      const messages = text('[data-test="attachment-messages"]');
      expect(messages).toContain('anim.gif was not added: only JPEG, PNG and WEBP');
      expect(messages).toContain('huge.png was not added: images can be at most 5 MB');
      expect(root().querySelectorAll('[data-test="thumb"]').length).toBe(0);
      http.expectNone('/api/v1/feedback');
    });

    it('adds a dropped image', () => {
      const transfer = new DataTransfer();
      transfer.items.add(file('drop.webp', 'image/webp'));
      const zone = q('[data-test="dropzone"]')!;
      const event = new DragEvent('drop', { dataTransfer: transfer, bubbles: true, cancelable: true });
      zone.dispatchEvent(event);
      fixture.detectChanges();
      expect(event.defaultPrevented).toBeTrue();
      expect(draft.images().length).toBe(1);
    });

    it('adds a pasted screenshot with a preview', () => {
      paste(q('[data-test="dropzone"]')!, [file('image.png', 'image/png')]);
      expect(root().querySelectorAll('[data-test="thumb"]').length).toBe(1);
      expect(draft.images()[0].file.name).toBe('screenshot-1.png');
    });

    it('says so when the clipboard holds no image', () => {
      paste(q('[data-test="dropzone"]')!, []);
      expect(draft.images().length).toBe(0);
      expect(text('[data-test="attachment-messages"]')).toContain(en.attachments.pasteNoImage);
    });

    it('says so when the pasted file is not a supported image type', () => {
      paste(q('[data-test="dropzone"]')!, [file('doc.pdf', 'application/pdf')]);
      expect(draft.images().length).toBe(0);
      expect(text('[data-test="attachment-messages"]')).toContain(en.attachments.pasteBadType);
    });

    it('leaves an ordinary text paste into the message box alone', () => {
      paste(q('textarea')!, [], 'some copied words');
      expect(draft.images().length).toBe(0);
      expect(q('[data-test="attachment-messages"]')?.textContent?.trim() ?? '').toBe('');
    });

    it('sends the screenshots in the same request as the text', () => {
      chooseImages([file('a.png', 'image/png'), file('b.png', 'image/png')]);
      typeText('See screenshots');
      click('[data-test="send"]');
      const body = http.expectOne('/api/v1/feedback').request.body as FormData;
      expect(body.getAll('images').length).toBe(2);
    });
  });

  describe('voice message (US3)', () => {
    it('records, stops, previews and can be discarded', async () => {
      await setup();
      click('[data-test="record"]');
      expect(recorder.start).toHaveBeenCalled();

      recorder.state.set('recording');
      fixture.detectChanges();
      expect(q('[data-test="record"]')).toBeNull();
      click('[data-test="stop-recording"]');
      expect(recorder.stop).toHaveBeenCalled();

      recorder.state.set('idle');
      recorder.result.set(file('voice-message.webm', 'audio/webm'));
      fixture.detectChanges();
      expect(q('audio[data-test="audio-preview"]')).not.toBeNull();
      expect(draft.audio()?.file.name).toBe('voice-message.webm');

      click('[data-test="discard-audio"]');
      expect(q('audio[data-test="audio-preview"]')).toBeNull();
      expect(draft.audio()).toBeNull();
    });

    it('lets the member record again over an existing recording', async () => {
      await setup();
      draft.setAudio(file('old.webm', 'audio/webm'));
      fixture.detectChanges();
      click('[data-test="re-record"]');
      expect(draft.audio()).toBeNull();
      expect(recorder.start).toHaveBeenCalled();
    });

    it('tells the member when a recording stopped at the 2-minute cap', async () => {
      await setup();
      draft.setAudio(file('voice-message.webm', 'audio/webm'));
      recorder.autoStopped.set(true);
      fixture.detectChanges();
      expect(text('[data-test="audio-notice"]')).toContain(en.audio.autoStopped);
    });

    it('hides recording, explains why, and keeps file upload when the browser cannot record', async () => {
      await setup({ recorderSupported: false });
      expect(q('[data-test="record"]')).toBeNull();
      expect(text('[data-test="audio-unsupported"]')).toBe(en.audio.unsupported);
      expect(q('[data-test="upload-audio"]')).not.toBeNull();
      expect(q('textarea')).not.toBeNull();
    });

    it('explains a refused microphone permission', async () => {
      await setup();
      recorder.error.set('denied');
      fixture.detectChanges();
      expect(text('[data-test="audio-error"]')).toBe(en.audio.denied);
      expect(q('[data-test="upload-audio"]')).not.toBeNull();
    });

    it('accepts an uploaded audio file and previews it', async () => {
      await setup();
      chooseAudio(file('note.m4a', 'audio/mp4'));
      expect(q('audio[data-test="audio-preview"]')).not.toBeNull();
      expect(draft.audio()?.file.name).toBe('note.m4a');
    });

    it('rejects an unsupported or oversized audio file before upload', async () => {
      await setup();
      chooseAudio(file('song.ogg', 'audio/ogg'));
      expect(text('[data-test="audio-error"]')).toContain('song.ogg was not added');
      expect(draft.audio()).toBeNull();
      chooseAudio(file('long.mp3', 'audio/mpeg', 10 * 1024 * 1024 + 1));
      expect(text('[data-test="audio-error"]')).toContain('audio can be at most 10 MB');
      http.expectNone('/api/v1/feedback');
    });

    it('sends one audio attachment with the text', async () => {
      await setup();
      chooseAudio(file('note.wav', 'audio/wav'));
      typeText('With voice');
      click('[data-test="send"]');
      const body = http.expectOne('/api/v1/feedback').request.body as FormData;
      expect((body.get('audio') as File).name).toBe('note.wav');
    });
  });
});
