import { TestBed, discardPeriodicTasks, fakeAsync, tick } from '@angular/core/testing';

import { MAX_AUDIO_SECONDS } from './attachment-rules';
import {
  AudioRecorderService,
  MEDIA_DEVICES,
  MEDIA_RECORDER_CTOR,
  type MediaRecorderLike,
} from './audio-recorder.service';

class FakeRecorder implements MediaRecorderLike {
  static supported = ['audio/webm;codecs=opus', 'audio/mp4'];
  static last: FakeRecorder | null = null;
  static isTypeSupported(type: string): boolean {
    return FakeRecorder.supported.includes(type);
  }
  state: 'inactive' | 'recording' = 'inactive';
  mimeType: string;
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  constructor(
    public stream: MediaStream,
    options?: { mimeType?: string },
  ) {
    this.mimeType = options?.mimeType ?? '';
    FakeRecorder.last = this;
  }
  start(): void {
    this.state = 'recording';
  }
  stop(): void {
    this.state = 'inactive';
    this.ondataavailable?.({ data: new Blob(['abc'], { type: this.mimeType }) });
    this.onstop?.();
  }
}

function fakeStream(): { stream: MediaStream; stopped: jasmine.Spy } {
  const stopped = jasmine.createSpy('trackStop');
  const stream = { getTracks: () => [{ stop: stopped }] } as unknown as MediaStream;
  return { stream, stopped };
}

interface Devices {
  getUserMedia: () => Promise<MediaStream>;
}

describe('AudioRecorderService (FR-004, FR-006)', () => {
  function setup(opts: {
    devices?: Devices | null;
    ctor?: typeof FakeRecorder | null;
  }): AudioRecorderService {
    TestBed.configureTestingModule({
      providers: [
        AudioRecorderService,
        { provide: MEDIA_DEVICES, useValue: opts.devices ?? null },
        { provide: MEDIA_RECORDER_CTOR, useValue: opts.ctor ?? null },
      ],
    });
    return TestBed.inject(AudioRecorderService);
  }

  beforeEach(() => {
    FakeRecorder.last = null;
    FakeRecorder.supported = ['audio/webm;codecs=opus', 'audio/mp4'];
  });

  it('reports recording as unsupported without getUserMedia', () => {
    expect(setup({ devices: null, ctor: FakeRecorder }).supported).toBeFalse();
  });

  it('releases a microphone granted after the dialog closed and never records', async () => {
    const { stream, stopped } = fakeStream();
    let grant!: (s: MediaStream) => void;
    const service = setup({
      devices: { getUserMedia: () => new Promise<MediaStream>((resolve) => (grant = resolve)) },
      ctor: FakeRecorder,
    });
    const starting = service.start();
    service.ngOnDestroy();
    grant(stream);
    await starting;
    expect(stopped).toHaveBeenCalled();
    expect(FakeRecorder.last).toBeNull();
    expect(service.state()).toBe('idle');
  });

  it('releases a microphone granted after cancel() and never records', async () => {
    const { stream, stopped } = fakeStream();
    let grant!: (s: MediaStream) => void;
    const service = setup({
      devices: { getUserMedia: () => new Promise<MediaStream>((resolve) => (grant = resolve)) },
      ctor: FakeRecorder,
    });
    const starting = service.start();
    service.cancel();
    grant(stream);
    await starting;
    expect(stopped).toHaveBeenCalled();
    expect(FakeRecorder.last).toBeNull();
    expect(service.state()).toBe('idle');
  });

  it('reports recording as unsupported without a recorder constructor', () => {
    const { stream } = fakeStream();
    const service = setup({ devices: { getUserMedia: () => Promise.resolve(stream) }, ctor: null });
    expect(service.supported).toBeFalse();
  });

  it('records, stops and exposes a playable file', async () => {
    const { stream, stopped } = fakeStream();
    const service = setup({
      devices: { getUserMedia: () => Promise.resolve(stream) },
      ctor: FakeRecorder,
    });
    expect(service.supported).toBeTrue();
    await service.start();
    expect(service.state()).toBe('recording');
    service.stop();
    expect(service.state()).toBe('idle');
    const result = service.takeResult();
    expect(result).not.toBeNull();
    expect(result!.name).toBe('voice-message.webm');
    expect(result!.type).toContain('audio/webm');
    expect(stopped).toHaveBeenCalled();
    expect(service.takeResult()).toBeNull();
  });

  it('falls back to MP4/AAC for Safari and names the file .m4a', async () => {
    FakeRecorder.supported = ['audio/mp4'];
    const { stream } = fakeStream();
    const service = setup({
      devices: { getUserMedia: () => Promise.resolve(stream) },
      ctor: FakeRecorder,
    });
    await service.start();
    service.stop();
    expect(FakeRecorder.last!.mimeType).toBe('audio/mp4');
    expect(service.takeResult()!.name).toBe('voice-message.m4a');
  });

  it('explains a refused microphone permission', async () => {
    const devices: Devices = {
      getUserMedia: () => Promise.reject(new DOMException('no', 'NotAllowedError')),
    };
    const service = setup({ devices, ctor: FakeRecorder });
    await service.start();
    expect(service.state()).toBe('idle');
    expect(service.error()).toBe('denied');
  });

  it('reports a missing microphone', async () => {
    const devices: Devices = {
      getUserMedia: () => Promise.reject(new DOMException('none', 'NotFoundError')),
    };
    const service = setup({ devices, ctor: FakeRecorder });
    await service.start();
    expect(service.error()).toBe('unavailable');
  });

  it('counts elapsed seconds and stops by itself at the 120 s cap', fakeAsync(() => {
    const { stream, stopped } = fakeStream();
    const service = setup({
      devices: { getUserMedia: () => Promise.resolve(stream) },
      ctor: FakeRecorder,
    });
    void service.start();
    tick(0);
    expect(service.state()).toBe('recording');
    tick(5000);
    expect(service.elapsedSeconds()).toBe(5);
    tick((MAX_AUDIO_SECONDS - 5) * 1000);
    expect(service.state()).toBe('idle');
    expect(service.autoStopped()).toBeTrue();
    expect(service.elapsedSeconds()).toBe(MAX_AUDIO_SECONDS);
    expect(service.takeResult()).not.toBeNull();
    expect(stopped).toHaveBeenCalled();
    discardPeriodicTasks();
  }));

  it('discards a recording in progress without producing a file', async () => {
    const { stream, stopped } = fakeStream();
    const service = setup({
      devices: { getUserMedia: () => Promise.resolve(stream) },
      ctor: FakeRecorder,
    });
    await service.start();
    service.cancel();
    expect(service.state()).toBe('idle');
    expect(service.takeResult()).toBeNull();
    expect(stopped).toHaveBeenCalled();
  });

  it('releases the microphone when the service is destroyed mid-recording', async () => {
    const { stream, stopped } = fakeStream();
    const service = setup({
      devices: { getUserMedia: () => Promise.resolve(stream) },
      ctor: FakeRecorder,
    });
    await service.start();
    service.ngOnDestroy();
    expect(stopped).toHaveBeenCalled();
  });
});
