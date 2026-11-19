import {
  FEEDBACK_TEXT_MAX,
  MAX_AUDIO_BYTES,
  MAX_AUDIO_SECONDS,
  MAX_IMAGES,
  MAX_IMAGE_BYTES,
  checkAudio,
  checkImage,
  isAudioFileName,
} from './attachment-rules';

function file(name: string, type: string, size = 10): File {
  return new File([new Uint8Array(size)], name, { type });
}

describe('feedback attachment rules (FR-003, FR-004, FR-005)', () => {
  it('exposes the limits from the spec', () => {
    expect(FEEDBACK_TEXT_MAX).toBe(2000);
    expect(MAX_IMAGES).toBe(5);
    expect(MAX_IMAGE_BYTES).toBe(5 * 1024 * 1024);
    expect(MAX_AUDIO_BYTES).toBe(10 * 1024 * 1024);
    expect(MAX_AUDIO_SECONDS).toBe(120);
  });

  describe('checkImage', () => {
    it('accepts JPEG, PNG and WEBP', () => {
      expect(checkImage(file('a.jpg', 'image/jpeg'), 0)).toBeNull();
      expect(checkImage(file('a.png', 'image/png'), 0)).toBeNull();
      expect(checkImage(file('a.webp', 'image/webp'), 0)).toBeNull();
    });

    it('accepts exactly 5 MiB and rejects one byte more', () => {
      expect(checkImage(file('a.png', 'image/png', MAX_IMAGE_BYTES), 0)).toBeNull();
      expect(checkImage(file('a.png', 'image/png', MAX_IMAGE_BYTES + 1), 0)).toBe('size');
    });

    it('rejects other image and non-image types', () => {
      expect(checkImage(file('a.gif', 'image/gif'), 0)).toBe('type');
      expect(checkImage(file('a.svg', 'image/svg+xml'), 0)).toBe('type');
      expect(checkImage(file('a.pdf', 'application/pdf'), 0)).toBe('type');
    });

    it('falls back to the extension when the browser reports no type', () => {
      expect(checkImage(file('shot.PNG', ''), 0)).toBeNull();
      expect(checkImage(file('notes.txt', ''), 0)).toBe('type');
    });

    it('refuses a sixth image', () => {
      expect(checkImage(file('a.png', 'image/png'), 4)).toBeNull();
      expect(checkImage(file('a.png', 'image/png'), 5)).toBe('count');
    });

    it('reports the count before the type once the limit is reached', () => {
      expect(checkImage(file('a.pdf', 'application/pdf'), 5)).toBe('count');
    });
  });

  describe('checkAudio', () => {
    it('accepts MP3, M4A, WAV and WebM, with or without codec parameters', () => {
      expect(checkAudio(file('a.mp3', 'audio/mpeg'))).toBeNull();
      expect(checkAudio(file('a.m4a', 'audio/mp4'))).toBeNull();
      expect(checkAudio(file('a.m4a', 'audio/x-m4a'))).toBeNull();
      expect(checkAudio(file('a.wav', 'audio/wav'))).toBeNull();
      expect(checkAudio(file('a.wav', 'audio/x-wav'))).toBeNull();
      expect(checkAudio(file('a.webm', 'audio/webm'))).toBeNull();
      expect(checkAudio(file('a.webm', 'audio/webm;codecs=opus'))).toBeNull();
      expect(checkAudio(file('a.webm', 'video/webm'))).toBeNull();
    });

    it('rejects other types', () => {
      expect(checkAudio(file('a.ogg', 'audio/ogg'))).toBe('audioType');
      expect(checkAudio(file('a.png', 'image/png'))).toBe('audioType');
    });

    it('falls back to the extension when no type is reported', () => {
      expect(checkAudio(file('a.mp3', ''))).toBeNull();
      expect(checkAudio(file('a.flac', ''))).toBe('audioType');
    });

    it('limits size to 10 MiB', () => {
      expect(checkAudio(file('a.mp3', 'audio/mpeg', MAX_AUDIO_BYTES))).toBeNull();
      expect(checkAudio(file('a.mp3', 'audio/mpeg', MAX_AUDIO_BYTES + 1))).toBe('audioSize');
    });
  });

  it('recognises supported audio extensions', () => {
    expect(isAudioFileName('voice.M4A')).toBeTrue();
    expect(isAudioFileName('voice.ogg')).toBeFalse();
  });
});
