import { Injectable, InjectionToken, OnDestroy, inject, signal } from '@angular/core';

import { MAX_AUDIO_SECONDS } from './attachment-rules';

/** The slice of MediaRecorder this service uses, so a spec can supply a fake. */
export interface MediaRecorderLike {
  state: string;
  mimeType: string;
  ondataavailable: ((event: { data: Blob }) => void) | null;
  onstop: (() => void) | null;
  start(): void;
  stop(): void;
}

export interface MediaRecorderCtor {
  new (stream: MediaStream, options?: { mimeType?: string }): MediaRecorderLike;
  isTypeSupported?(type: string): boolean;
}

export interface MediaDevicesLike {
  getUserMedia(constraints: { audio: boolean }): Promise<MediaStream>;
}

export const MEDIA_DEVICES = new InjectionToken<MediaDevicesLike | null>('MEDIA_DEVICES', {
  providedIn: 'root',
  factory: () => (typeof navigator !== 'undefined' ? (navigator.mediaDevices ?? null) : null),
});

export const MEDIA_RECORDER_CTOR = new InjectionToken<MediaRecorderCtor | null>(
  'MEDIA_RECORDER_CTOR',
  {
    providedIn: 'root',
    factory: () =>
      typeof MediaRecorder !== 'undefined' ? (MediaRecorder as unknown as MediaRecorderCtor) : null,
  },
);

export type RecorderState = 'idle' | 'recording';
export type RecorderError = 'denied' | 'unavailable' | 'failed';

/** Container types the API accepts for audio, in order of preference (Chrome and Firefox, then Safari). */
const PREFERRED_TYPES: readonly string[] = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'];

/**
 * Browser voice recording behind feature detection (FR-004, FR-006). Component-scoped: it holds the
 * microphone, so it must be released with the dialog that asked for it.
 */
@Injectable()
export class AudioRecorderService implements OnDestroy {
  private readonly devices = inject(MEDIA_DEVICES);
  private readonly recorderCtor = inject(MEDIA_RECORDER_CTOR);

  readonly state = signal<RecorderState>('idle');
  readonly elapsedSeconds = signal(0);
  readonly error = signal<RecorderError | null>(null);
  /** True when the last recording ended at the cap rather than by the member's choice. */
  readonly autoStopped = signal(false);

  private recorder: MediaRecorderLike | null = null;
  private stream: MediaStream | null = null;
  private chunks: Blob[] = [];
  /**
   * The finished recording. A signal because a real MediaRecorder delivers its data after stop()
   * returns, so a caller has to wait for it rather than read it straight away.
   */
  readonly result = signal<File | null>(null);
  private discard = false;
  private timer: ReturnType<typeof setInterval> | null = null;
  /**
   * Bumped by every start() and cancel(). A microphone grant that resolves after the dialog closed
   * (or after a newer start) no longer matches and is released at once instead of recording.
   */
  private generation = 0;
  private destroyed = false;

  /** False hides the record control; text, screenshots and file upload keep working. */
  get supported(): boolean {
    return !!this.devices?.getUserMedia && !!this.recorderCtor;
  }

  async start(): Promise<void> {
    if (!this.supported || this.destroyed || this.state() === 'recording') return;
    const generation = ++this.generation;
    this.error.set(null);
    this.autoStopped.set(false);
    this.result.set(null);
    this.discard = false;
    this.chunks = [];

    let stream: MediaStream;
    try {
      stream = await this.devices!.getUserMedia({ audio: true });
    } catch (e) {
      if (generation === this.generation && !this.destroyed) this.error.set(errorKind(e));
      return;
    }
    if (generation !== this.generation || this.destroyed) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }

    const ctor = this.recorderCtor!;
    const mimeType = ctor.isTypeSupported
      ? PREFERRED_TYPES.find((type) => ctor.isTypeSupported!(type))
      : undefined;
    let recorder: MediaRecorderLike;
    try {
      recorder = new ctor(stream, mimeType ? { mimeType } : undefined);
    } catch {
      stream.getTracks().forEach((track) => track.stop());
      this.error.set('failed');
      return;
    }

    this.stream = stream;
    this.recorder = recorder;
    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) this.chunks.push(event.data);
    };
    recorder.onstop = () => this.finish(mimeType ?? recorder.mimeType);
    recorder.start();
    this.elapsedSeconds.set(0);
    this.state.set('recording');
    this.timer = setInterval(() => {
      this.elapsedSeconds.update((s) => s + 1);
      if (this.elapsedSeconds() >= MAX_AUDIO_SECONDS) {
        this.autoStopped.set(true);
        this.stop();
      }
    }, 1000);
  }

  /** Ends the recording and keeps it; collect it with takeResult(). */
  stop(): void {
    if (this.recorder && this.recorder.state !== 'inactive') this.recorder.stop();
    else this.release();
  }

  /** Ends the recording and throws it away. */
  cancel(): void {
    this.generation++;
    this.discard = true;
    this.stop();
  }

  /** The finished recording, once; null when none is waiting. */
  takeResult(): File | null {
    const file = this.result();
    this.result.set(null);
    return file;
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    this.cancel();
  }

  private finish(mimeType: string): void {
    const keep = !this.discard && this.chunks.length > 0;
    if (keep) {
      const type = baseType(mimeType) || 'audio/webm';
      const ext = type === 'audio/mp4' ? 'm4a' : 'webm';
      this.result.set(new File(this.chunks, `voice-message.${ext}`, { type: mimeType || type }));
    }
    this.chunks = [];
    this.release();
  }

  private release(): void {
    if (this.timer !== null) {
      clearInterval(this.timer);
      this.timer = null;
    }
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    this.recorder = null;
    this.state.set('idle');
  }
}

function baseType(type: string): string {
  return type.split(';')[0].trim().toLowerCase();
}

function errorKind(error: unknown): RecorderError {
  const name = error instanceof DOMException || error instanceof Error ? error.name : '';
  if (name === 'NotAllowedError' || name === 'SecurityError' || name === 'PermissionDeniedError') {
    return 'denied';
  }
  if (name === 'NotFoundError' || name === 'OverconstrainedError' || name === 'NotReadableError') {
    return 'unavailable';
  }
  return 'failed';
}
