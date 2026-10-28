/**
 * Arabic-aware text normalisation for search / autocomplete matching.
 *
 * - Case-insensitive (lowercased)
 * - Strips Arabic tashkeel / diacritics and tatweel (ـ)
 * - Unifies alef variants (أ / إ / آ / ٱ -> ا)
 * - Unifies alef maqsura (ى -> ي)
 * - Unifies ta marbuta (ة -> ه)
 * - Trims and collapses multiple whitespace characters
 */
export function normaliseSearchText(text: string | null | undefined): string {
  if (!text) return '';

  return text
    .toLowerCase()
    .replace(/[\u064B-\u065F\u0670]/g, '')
    .replace(/\u0640/g, '')
    .replace(/[أإآٱ]/g, 'ا')
    .replace(/ى/g, 'ي')
    .replace(/ة/g, 'ه')
    .trim()
    .replace(/\s+/g, ' ');
}
