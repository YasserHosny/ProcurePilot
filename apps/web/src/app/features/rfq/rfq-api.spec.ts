import { TestBed } from "@angular/core/testing";
import { HttpClient, HttpParams, provideHttpClient, withXhr } from "@angular/common/http";
import { HttpTestingController, provideHttpClientTesting } from "@angular/common/http/testing";
import { of } from "rxjs";
import { RfqApi } from "./rfq-api";
import { RfqActionKeys, RfqRecipient, RfqReminderPreview, formatRfqReference } from './rfq-api';

describe('formatRfqReference', () => {
  it('pads references without truncating and omits missing values', () => {
    expect(formatRfqReference(1)).toBe('RFQ-000001');
    expect(formatRfqReference(123456)).toBe('RFQ-123456');
    expect(formatRfqReference(null)).toBe('');
    expect(formatRfqReference(undefined)).toBe('');
  });
});

describe('RfqActionKeys', () => {
  it('reuses a key while the payload it was created for is unchanged', () => {
    const keys = new RfqActionKeys();
    const first = keys.get('create:new', '{"quantity":"10"}');
    expect(keys.get('create:new', '{"quantity":"10"}')).toBe(first);
  });

  it('rotates the key when the payload changes, so edits are never swallowed by a replay', () => {
    const keys = new RfqActionKeys();
    const first = keys.get('update:rfq-1', '{"quantity":"10"}');
    const edited = keys.get('update:rfq-1', '{"quantity":"12"}');
    expect(edited).not.toBe(first);
    expect(keys.get('update:rfq-1', '{"quantity":"12"}')).toBe(edited);
  });

  it('keeps the previous behaviour for actions without a payload', () => {
    const keys = new RfqActionKeys();
    const first = keys.get('send:rfq-1');
    expect(keys.get('send:rfq-1')).toBe(first);
    keys.clear('send:rfq-1');
    expect(keys.get('send:rfq-1')).not.toBe(first);
  });
});

describe('RfqApi list parameters', () => {
  it('omits blank search and default sort, and sends trimmed search with explicit sort', () => {
    const http = jasmine.createSpyObj<HttpClient>('HttpClient', ['get']);
    http.get.and.returnValue(of({ items: [], next_cursor: null }));
    TestBed.configureTestingModule({ providers: [RfqApi, { provide: HttpClient, useValue: http }] });
    const api = TestBed.inject(RfqApi);
    api.listRfqs(undefined, undefined, undefined, '   ', 'created_desc');
    let params = http.get.calls.mostRecent().args[1]?.params as HttpParams;
    expect(params.has('q')).toBeFalse();
    expect(params.has('sort')).toBeFalse();
    api.listRfqs('sent', '20', 20, ' bolt ', 'needed_asc');
    params = http.get.calls.mostRecent().args[1]?.params as HttpParams;
    expect(params.get('q')).toBe('bolt');
    expect(params.get('sort')).toBe('needed_asc');
    expect(params.get('status')).toBe('sent');
    expect(params.get('cursor')).toBe('20');
    expect(params.get('limit')).toBe('20');
  });
});

describe('RfqApi reminder endpoints', () => {
  let api: RfqApi;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(withXhr()), provideHttpClientTesting()] });
    api = TestBed.inject(RfqApi);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('fetches the reminder preview for a recipient', () => {
    let result: RfqReminderPreview | undefined;
    api.previewReminder('rfq-1', 'rec-1').subscribe((preview) => { result = preview; });

    const request = http.expectOne((req) => req.url.endsWith('/rfq/rfq-1/recipients/rec-1/reminder-preview'));
    expect(request.request.method).toBe('GET');
    const preview: RfqReminderPreview = {
      subject: 'Reminder: RFQ-000001',
      body_text: 'Hello supplier',
      locale: 'ar',
      allowed: true,
      blocked_reason: null,
    };
    request.flush(preview);

    expect(result).toEqual(preview);
  });

  it('posts a reminder with the caller-supplied idempotency key and no body', () => {
    const keys = new RfqActionKeys();
    const key = keys.get('remind:rfq-1:rec-1');
    let result: RfqRecipient | undefined;
    api.sendReminder('rfq-1', 'rec-1', key).subscribe((recipient) => { result = recipient; });

    const request = http.expectOne((req) => req.url.endsWith('/rfq/rfq-1/recipients/rec-1/reminder'));
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toBeNull();
    expect(request.request.headers.get('Idempotency-Key')).toBe(key);

    request.flush({ id: 'rec-1', reminder_count: 1, can_remind: false });
    expect(result?.reminder_count).toBe(1);
    expect(result?.can_remind).toBeFalse();
  });

  it('generates a fallback idempotency key when the caller does not supply one', () => {
    api.sendReminder('rfq-1', 'rec-1').subscribe();

    const request = http.expectOne((req) => req.url.endsWith('/rfq/rfq-1/recipients/rec-1/reminder'));
    expect(request.request.headers.get('Idempotency-Key')).toEqual(jasmine.any(String));
    request.flush({ id: 'rec-1' });
  });
});
