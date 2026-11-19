/**
 * Client-side attachment rules (FR-003, FR-004, FR-005). They run before any upload so an invalid
 * file is refused with a reason. Images are also checked by their first bytes (hasImageSignature),
 * so a renamed file is caught here and named. The server repeats every check from the file's
 * CONTENT with libmagic, so these are a convenience, not the control.
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

const JPEG_SIGNATURE: readonly number[] = [0xff, 0xd8, 0xff];
const PNG_SIGNATURE: readonly number[] = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
const RIFF: readonly number[] = [0x52, 0x49, 0x46, 0x46];
const WEBP: readonly number[] = [0x57, 0x45, 0x42, 0x50];

/**
 * True when the file starts with a JPEG, PNG or WEBP signature. Name and browser-reported type say
 * nothing about the bytes: a renamed file passes checkImage and would only fail at the server.
 */
export async function hasImageSignature(file: Blob): Promise<boolean> {
  const head = new Uint8Array(await file.slice(0, 12).arrayBuffer());
  const startsWith = (signature: readonly number[], offset = 0): boolean =>
    signature.every((byte, i) => head[offset + i] === byte);
  return (
    startsWith(JPEG_SIGNATURE) ||
    startsWith(PNG_SIGNATURE) ||
    (startsWith(RIFF) && startsWith(WEBP, 8))
  );
}

/** The first rule a candidate audio file breaks, or null when it may be attached. */
export function checkAudio(file: Pick<File, 'name' | 'type' | 'size'>): AttachmentRejection | null {
  const type = baseType(file.type);
  const typeOk = type ? AUDIO_TYPES.includes(type) : isAudioFileName(file.name);
  if (!typeOk) return 'audioType';
  if (file.size > MAX_AUDIO_BYTES) return 'audioSize';
  return null;
}
