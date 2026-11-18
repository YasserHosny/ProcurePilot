import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import enCatalog from '../../../../../../../packages/i18n/en.json';
import { I18nService } from '../../../core/i18n';
import type { FeedbackAttachment } from '../feedback-api';
import { FeedbackAttachmentComponent } from './feedback-attachment.component';

const image: FeedbackAttachment = {
  id: 'att-img',
  kind: 'image',
  content_type: 'image/png',
  size_bytes: 100,
  display_order: 1,
};
const audio: FeedbackAttachment = {
  id: 'att-audio',
  kind: 'audio',
  content_type: 'audio/webm',
  size_bytes: 100,
  display_order: 0,
};

describe('FeedbackAttachmentComponent (signed links, FR-016, FR-019)', () => {
  let fixture: ComponentFixture<FeedbackAttachmentComponent>;
  let http: HttpTestingController;
  const root = (): HTMLElement => fixture.nativeElement as HTMLElement;

  function create(attachment: FeedbackAttachment): void {
    fixture = TestBed.createComponent(FeedbackAttachmentComponent);
    fixture.componentRef.setInput('submissionId', 'sub-1');
    fixture.componentRef.setInput('attachment', attachment);
    fixture.componentRef.setInput('number', 2);
    fixture.detectChanges();
  }

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [FeedbackAttachmentComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideTranslateService(),
        { provide: I18nService, useValue: { currentLocale: signal('en') } },
      ],
    });
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.use('en');
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('asks for a short-lived link for a screenshot and shows it with alternative text', () => {
    create(image);
    http
      .expectOne('/api/v1/feedback/sub-1/attachments/att-img/url')
      .flush({ url: 'https://files.example/shot.png?sig=1', expires_in: 300 });
    fixture.detectChanges();
    const img = root().querySelector<HTMLImageElement>('img')!;
    expect(img.getAttribute('src')).toBe('https://files.example/shot.png?sig=1');
    expect(img.alt).toBe('Screenshot 2');
  });

  it('offers a retry when the link cannot be issued', () => {
    create(image);
    http
      .expectOne('/api/v1/feedback/sub-1/attachments/att-img/url')
      .flush({ code: 'not_found', message: 'x', trace_id: 't' }, { status: 404, statusText: 'Not Found' });
    fixture.detectChanges();
    expect(root().querySelector('img')).toBeNull();
    expect(root().textContent).toContain(enCatalog.feedback.list.attachmentError);

    root().querySelector<HTMLButtonElement>('[data-test="retry"]')!.click();
    http
      .expectOne('/api/v1/feedback/sub-1/attachments/att-img/url')
      .flush({ url: 'https://files.example/shot.png?sig=2', expires_in: 300 });
    fixture.detectChanges();
    expect(root().querySelector('img')).not.toBeNull();
  });

  it('refreshes an expired screenshot link when the image fails to load', () => {
    create(image);
    http
      .expectOne('/api/v1/feedback/sub-1/attachments/att-img/url')
      .flush({ url: 'https://files.example/old', expires_in: 300 });
    fixture.detectChanges();
    root().querySelector('img')!.dispatchEvent(new Event('error'));
    fixture.detectChanges();
    expect(root().querySelector('[data-test="retry"]')).not.toBeNull();
  });

  it('does not fetch voice messages until the member asks to play one', () => {
    create(audio);
    http.expectNone('/api/v1/feedback/sub-1/attachments/att-audio/url');
    root().querySelector<HTMLButtonElement>('[data-test="load-audio"]')!.click();
    http
      .expectOne('/api/v1/feedback/sub-1/attachments/att-audio/url')
      .flush({ url: 'https://files.example/voice.webm?sig=1', expires_in: 300 });
    fixture.detectChanges();
    const player = root().querySelector<HTMLAudioElement>('audio')!;
    expect(player.getAttribute('src')).toBe('https://files.example/voice.webm?sig=1');
    expect(player.controls).toBeTrue();
  });
});
