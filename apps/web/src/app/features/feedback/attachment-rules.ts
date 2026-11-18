/**
 * Client-side attachment rules (FR-003, FR-004, FR-005). They run before any upload so an invalid
 * file is refused with a reason. The server repeats every check from the file's CONTENT (a renamed
 * file passes here by name or type but not there), so these are a convenience, not the control.
 */

export const FEEDBACK_TEXT_MAX = 2000;
export const MAX_IMAGES = 5;
export const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
export const MAX_AUDIO_BYTES = 10 * 1024 * 1024;
export const MAX_AUDIO_SECONDS = 120;

export type AttachmentRejection = 'count' | 'type' | 'size' | 'audioType' | 'audioSize';

const IMAGE_TYPES: readonly string[] = ['image/jpeg', 'image/png', 'image/webp'];
const IMAGE_EXTENSIONS: readonly string[] = ['jpg', 'jpeg', 'png', 'webp'];

const AUDIO_TYPES: readonly string[] = [
  'audio/mpeg',
  'audio/mp3',
  'audio/mp4',
  'audio/x-m4a',
  'audio/m4a',
  'audio/wav',
  'audio/x-wav',
  'audio/wave',
  'audio/webm',
  'video/webm',
];
const AUDIO_EXTENSIONS: readonly string[] = ['mp3', 'm4a', 'wav', 'webm'];

/** Lower-cased MIME type without parameters such as `;codecs=opus`. */
function baseType(type: string): string {
  return type.split(';')[0].trim().toLowerCase();
}

function extension(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot < 0 ? '' : name.slice(dot + 1).toLowerCase();
}

export function isAudioFileName(name: string): boolean {
  return AUDIO_EXTENSIONS.includes(extension(name));
}

/** The first rule a candidate screenshot breaks, or null when it may be added. */
export function checkImage(
  file: Pick<File, 'name' | 'type' | 'size'>,
  currentCount: number,
): AttachmentRejection | null {
  if (currentCount >= MAX_IMAGES) return 'count';
  const type = baseType(file.type);
  const typeOk = type ? IMAGE_TYPES.includes(type) : IMAGE_EXTENSIONS.includes(extension(file.name));
  if (!typeOk) return 'type';
  if (file.size > MAX_IMAGE_BYTES) return 'size';
  return null;
}

/** The first rule a candidate audio file breaks, or null when it may be attached. */
export function checkAudio(file: Pick<File, 'name' | 'type' | 'size'>): AttachmentRejection | null {
  const type = baseType(file.type);
  const typeOk = type ? AUDIO_TYPES.includes(type) : isAudioFileName(file.name);
  if (!typeOk) return 'audioType';
  if (file.size > MAX_AUDIO_BYTES) return 'audioSize';
  return null;
}
