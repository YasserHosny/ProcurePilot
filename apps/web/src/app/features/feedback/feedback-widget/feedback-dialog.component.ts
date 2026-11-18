import { HttpErrorResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  Injector,
  afterNextRender,
  computed,
  effect,
  inject,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';

import {
  FEEDBACK_TEXT_MAX,
  checkAudio,
  checkImage,
  hasImageSignature,
  type AttachmentRejection,
} from '../attachment-rules';
import { AudioRecorderService } from '../audio-recorder.service';
import {
  FEEDBACK_CATEGORIES,
  FeedbackApiService,
  type FeedbackCategory,
} from '../feedback-api';
import { FeedbackDraftStore } from '../feedback-draft.store';

export interface FeedbackDialogData {
  readonly afterCapture?: boolean;
}

interface Message {
  readonly key: string;
  readonly params?: Record<string, string | number>;
}

const IMAGE_EXTENSION: Record<string, string> = {
  'image/png': 'png',
  'image/jpeg': 'jpg',
  'image/webp': 'webp',
};

@Component({
  selector: 'app-feedback-dialog',
  standalone: true,
  imports: [
    MatButtonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatSelectModule,
    RouterLink,
    TranslatePipe,
  ],
  // The audio recorder holds the microphone, so it lives and dies with this dialog.
  providers: [AudioRecorderService],
  templateUrl: './feedback-dialog.component.html',
  styleUrl: './feedback-dialog.component.scss',
  changeDetection: ChangeDetectionStrategy.Eager,
})
export class FeedbackDialogComponent {
  private readonly dialogRef = inject(MatDialogRef<FeedbackDialogComponent>);
  private readonly data = inject<FeedbackDialogData | null>(MAT_DIALOG_DATA, { optional: true });
  private readonly api = inject(FeedbackApiService);
  private readonly injector = inject(Injector);
  private readonly destroyRef = inject(DestroyRef);
  readonly draft = inject(FeedbackDraftStore);
  readonly recorder = inject(AudioRecorderService);

  readonly textMax = FEEDBACK_TEXT_MAX;
  readonly categories = FEEDBACK_CATEGORIES;

  private readonly textArea = viewChild<ElementRef<HTMLTextAreaElement>>('area');
  private readonly dropzone = viewChild<ElementRef<HTMLElement>>('dropzone');
  private readonly successHeading = viewChild<ElementRef<HTMLElement>>('successHeading');

  readonly submitting = signal(false);
  readonly success = signal(false);
  readonly textError = signal(false);
  readonly formError = signal<Message | null>(null);
  readonly cooldownSeconds = signal(0);
  /** Fixed at the moment the cooldown starts, so a screen reader hears it once, not every second. */
  readonly cooldownAnnouncement = signal<Message | null>(null);
  readonly attachmentMessages = signal<readonly Message[]>([]);
  readonly audioMessage = signal<Message | null>(null);
  readonly dragging = signal(false);
  readonly afterCapture = signal(this.data?.afterCapture ?? false);
  readonly failedImageIds = signal<ReadonlySet<string>>(new Set());
  readonly audioPreviewFailed = signal(false);

  readonly remaining = computed(() => this.textMax - this.draft.text().length);
  readonly counter = computed<Message>(() => ({
    key: 'feedback.widget.charsLeft',
    params: { count: this.remaining() },
  }));
  /** A recorder failure (permission, no microphone), shown unless a file problem is newer. */
  readonly shownAudioMessage = computed<Message | null>(() => {
    const local = this.audioMessage();
    if (local) return local;
    const error = this.recorder.error();
    return error ? { key: `feedback.audio.${error}` } : null;
  });
  readonly elapsedLabel = computed(() => {
    const total = this.recorder.elapsedSeconds();
    const minutes = Math.floor(total / 60);
    const seconds = String(total % 60).padStart(2, '0');
    return `${minutes}:${seconds}`;
  });
  readonly showDraftKept = computed(
    () => this.formError()?.key !== 'feedback.errors.sessionExpired',
  );

  private cooldownTimer: ReturnType<typeof setInterval> | null = null;

  constructor() {
    if (this.afterCapture()) {
      afterNextRender(
        () => {
          this.dropzone()?.nativeElement.focus();
        },
        { injector: this.injector },
      );
    }
    // A real MediaRecorder hands over its data after stop() returns, so the file arrives as a signal.
    effect(() => {
      if (this.recorder.result()) {
        untracked(() => {
          const recorded = this.recorder.takeResult();
          if (recorded) this.acceptAudio(recorded);
        });
      }
    });
    this.destroyRef.onDestroy(() => this.clearCooldownTimer());
  }

  // --- text and category ---------------------------------------------------------------------

  onText(event: Event): void {
    const value = (event.target as HTMLTextAreaElement).value.slice(0, this.textMax);
    this.draft.text.set(value);
    if (value.trim()) this.textError.set(false);
  }

  onCategory(value: FeedbackCategory | null): void {
    this.draft.category.set(value);
  }

  // --- screenshots ---------------------------------------------------------------------------

  onImagesChosen(event: Event): void {
    const input = event.target as HTMLInputElement;
    void this.addImages(Array.from(input.files ?? []));
    input.value = '';
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    this.dragging.set(true);
  }

  onDragLeave(): void {
    this.dragging.set(false);
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.dragging.set(false);
    void this.addImages(Array.from(event.dataTransfer?.files ?? []));
  }

  onPaste(event: ClipboardEvent): void {
    const data = event.clipboardData;
    if (!data) return;
    const files = Array.from(data.files ?? []);
    if (files.length === 0) {
      // Pasting words into the message box is ordinary editing; only a paste that could not
      // have been text (or landed outside a text field) deserves an explanation.
      const inTextField = (event.target as HTMLElement | null)?.closest('textarea, input') !== null;
      const hasText = data.types.includes('text/plain') || data.types.includes('text/html');
      if (!(inTextField && hasText)) {
        this.attachmentMessages.set([{ key: 'feedback.attachments.pasteNoImage' }]);
      }
      return;
    }
    event.preventDefault();
    const images = files.filter((f) => f.type.startsWith('image/'));
    if (images.length === 0) {
      this.attachmentMessages.set([{ key: 'feedback.attachments.pasteBadType' }]);
      return;
    }
    void this.addImages(images.map((f) => this.nameScreenshot(f)));
  }

  hideToCapture(): void {
    this.dialogRef.close('capture');
  }

  onImageError(id: string): void {
    this.failedImageIds.update((set) => {
      const next = new Set(set);
      next.add(id);
      return next;
    });
  }

  removeImage(id: string): void {
    this.draft.removeImage(id);
    this.failedImageIds.update((set) => {
      if (!set.has(id)) return set;
      const next = new Set(set);
      next.delete(id);
      return next;
    });
    this.attachmentMessages.set([]);
    this.clearAttachmentSendError();
  }

  /**
   * The images being checked right now (their first bytes are read asynchronously). Adds run one
   * after another, so the five-image limit holds however fast files arrive.
   */
  imageCheck: Promise<void> = Promise.resolve();

  /** Image batches still being checked. Send waits for them so no chosen screenshot is left out. */
  readonly checkingImages = signal(0);

  private addImages(files: File[]): Promise<void> {
    this.checkingImages.update((n) => n + 1);
    this.imageCheck = this.imageCheck
      .then(() => this.checkAndAddImages(files))
      // A batch that fails must not stall the queue for the rest of the dialog's life.
      .catch(() => undefined)
      .finally(() => this.checkingImages.update((n) => n - 1));
    return this.imageCheck;
  }

  private async checkAndAddImages(files: File[]): Promise<void> {
    this.clearAttachmentSendError();
    const messages: Message[] = [];
    const refuse = (reason: AttachmentRejection, name: string): void => {
      if (reason !== 'count') messages.push(rejection(reason, name));
      else if (!messages.some((m) => m.key === 'feedback.attachments.count')) {
        messages.push({ key: 'feedback.attachments.count' });
      }
    };
    for (const file of files) {
      const reason = checkImage(file, this.draft.images().length);
      if (reason !== null) {
        refuse(reason, file.name);
        continue;
      }
      let isImage: boolean;
      try {
        isImage = await hasImageSignature(file);
      } catch {
        messages.push({ key: 'feedback.attachments.readFailed', params: { name: file.name } });
        continue;
      }
      if (!isImage) {
        refuse('type', file.name);
        continue;
      }
      this.draft.addImage(file);
      this.afterCapture.set(false);
    }
    this.attachmentMessages.set(messages);
  }

  /** A refused-type or too-large send error describes attachments that have since changed. */
  private clearAttachmentSendError(): void {
    const key = this.formError()?.key;
    if (
      key === 'feedback.errors.unsupportedType' ||
      key === 'feedback.errors.unsupportedTypeNamed' ||
      key === 'feedback.errors.tooLarge'
    ) {
      this.formError.set(null);
    }
  }

  /** A pasted image arrives as `image.png` every time, which tells nobody anything. */
  private nameScreenshot(file: File): File {
    const extension = IMAGE_EXTENSION[file.type] ?? 'png';
    const name = `screenshot-${this.draft.images().length + 1}.${extension}`;
    return new File([file], name, { type: file.type });
  }

  // --- voice message -------------------------------------------------------------------------

  onRecord(): void {
    this.audioMessage.set(null);
    void this.recorder.start();
  }

  onReRecord(): void {
    this.draft.clearAudio();
    this.audioPreviewFailed.set(false);
    this.onRecord();
  }

  onStopRecording(): void {
    this.recorder.stop();
  }

  onDiscardAudio(): void {
    this.clearAttachmentSendError();
    this.draft.clearAudio();
    this.audioMessage.set(null);
    this.audioPreviewFailed.set(false);
  }

  onAudioError(): void {
    this.audioPreviewFailed.set(true);
  }

  onAudioChosen(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (file) this.acceptAudio(file);
  }

  private acceptAudio(file: File): void {
    this.audioPreviewFailed.set(false);
    const reason = checkAudio(file);
    if (reason) {
      this.audioMessage.set(rejection(reason, file.name));
      return;
    }
    this.audioMessage.set(null);
    this.clearAttachmentSendError();
    this.draft.setAudio(file);
  }

  // --- sending -------------------------------------------------------------------------------

  send(): void {
    // The guard is what makes a double-click create one submission: the button is only disabled
    // after the next change-detection pass, the second click can arrive before it.
    if (this.submitting() || this.cooldownSeconds() > 0 || this.checkingImages() > 0) return;
    const text = this.draft.text().trim();
    if (!text) {
      this.textError.set(true);
      this.textArea()?.nativeElement.focus();
      return;
    }
    this.textError.set(false);
    this.formError.set(null);
    this.submitting.set(true);

    const key = this.draft.idempotencyKey(() => this.api.newIdempotencyKey());
    this.api
      .submit(
        {
          text,
          category: this.draft.category(),
          images: this.draft.images().map((image) => image.file),
          audio: this.draft.audio()?.file ?? null,
        },
        key,
      )
      .subscribe({
        next: () => {
          this.submitting.set(false);
          this.draft.reset();
          this.success.set(true);
          afterNextRender(() => this.successHeading()?.nativeElement.focus(), {
            injector: this.injector,
          });
        },
        error: (error: unknown) => {
          this.submitting.set(false);
          this.onSendError(error);
        },
      });
  }

  close(): void {
    this.dialogRef.close();
  }

  private onSendError(error: unknown): void {
    const status = error instanceof HttpErrorResponse ? error.status : 0;
    const body = error instanceof HttpErrorResponse ? (error.error as ErrorBody | null) : null;
    if (status === 429 && body?.code === 'feedback.cooldown') {
      const wait = Number(body.details?.retry_after_seconds);
      this.startCooldown(Number.isFinite(wait) && wait > 0 ? Math.ceil(wait) : 30);
      return;
    }
    const name = body?.details?.name;
    if (status === 415 && typeof name === 'string' && name) {
      this.formError.set({ key: 'feedback.errors.unsupportedTypeNamed', params: { name } });
      return;
    }
    this.formError.set({ key: errorKey(status) });
  }

  private startCooldown(seconds: number): void {
    this.clearCooldownTimer();
    this.cooldownSeconds.set(seconds);
    this.cooldownAnnouncement.set({ key: 'feedback.widget.cooldown', params: { seconds } });
    this.cooldownTimer = setInterval(() => {
      this.cooldownSeconds.update((s) => Math.max(0, s - 1));
      if (this.cooldownSeconds() === 0) this.clearCooldownTimer();
    }, 1000);
  }

  private clearCooldownTimer(): void {
    if (this.cooldownTimer !== null) {
      clearInterval(this.cooldownTimer);
      this.cooldownTimer = null;
    }
  }
}

interface ErrorBody {
  readonly code?: string;
  readonly details?: { readonly retry_after_seconds?: unknown; readonly name?: unknown };
}

function rejection(reason: AttachmentRejection, name: string): Message {
  switch (reason) {
    case 'audioType':
      return { key: 'feedback.audio.errorType', params: { name } };
    case 'audioSize':
      return { key: 'feedback.audio.errorSize', params: { name } };
    case 'count':
      return { key: 'feedback.attachments.count' };
    case 'size':
      return { key: 'feedback.attachments.size', params: { name } };
    case 'type':
      return { key: 'feedback.attachments.type', params: { name } };
  }
}

function errorKey(status: number): string {
  switch (status) {
    case 0:
      return 'feedback.errors.network';
    case 401:
      return 'feedback.errors.sessionExpired';
    case 413:
      return 'feedback.errors.tooLarge';
    case 415:
      return 'feedback.errors.unsupportedType';
    case 422:
      return 'feedback.errors.invalid';
    case 429:
      return 'feedback.errors.rateLimited';
    default:
      return 'feedback.errors.server';
  }
}
