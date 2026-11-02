/**
 * Pure money input parsing helper.
 * Converts user-entered money/numeric strings into canonical decimal strings (/^-?\d+(\.\d+)?$/) or null.
 */
export function parseMoneyInput(raw: unknown): string | null {
  if (raw === null || raw === undefined) {
    return null;
  }

  let str: string;
  if (typeof raw === 'number') {
    if (!Number.isFinite(raw)) {
      return null;
    }
    str = String(raw);
  } else if (typeof raw === 'string') {
    str = raw.trim();
  } else {
    return null;
  }

  if (!str) {
    return null;
  }

  // Convert Arabic-Indic (٠-٩) and Extended Arabic-Indic (۰-۹) digits to ASCII
  str = str.replace(/[\u0660-\u0669]/g, (d) => String(d.charCodeAt(0) - 0x0660));
  str = str.replace(/[\u06F0-\u06F9]/g, (d) => String(d.charCodeAt(0) - 0x06F0));

  // Arabic decimal separator ٫ (U+066B) -> '.'
  str = str.replace(/\u066B/g, '.');

  // Arabic thousands separator ٬ (U+066C), spaces, NBSP (\u00A0), narrow NBSP (\u202F), apostrophes (', ’) removed
  str = str.replace(/[\u066C\s\u00A0\u202F'’]/g, '');

  // Check minus signs: keep one leading '-'
  const minusMatches = str.match(/[-\u2212]/g);
  if (minusMatches && minusMatches.length > 1) {
    return null;
  }

  const isNegative = minusMatches ? minusMatches.length === 1 : false;
  if (isNegative) {
    const minusIndex = str.search(/[-\u2212]/);
    const firstDigitIndex = str.search(/\d/);
    if (firstDigitIndex === -1 || minusIndex > firstDigitIndex) {
      return null;
    }
  }

  // Handle dots adjacent to letters (like abbreviations: "ج.م", "E.G.P.")
  str = str.replace(/\p{L}+\.\p{L}+/gu, '');
  str = str.replace(/\p{L}+\./gu, '');
  str = str.replace(/\.\p{L}+/gu, '');

  // Drop currency symbols (\p{Sc}) and letters (\p{L})
  str = str.replace(/[\p{Sc}\p{L}]/gu, '');

  // Remove any remaining minus signs as we already noted isNegative
  str = str.replace(/[-\u2212]/g, '');

  // Must have digits and only digits, '.', ','
  if (!/\d/.test(str) || /[^\d.,]/.test(str)) {
    return null;
  }

  const hasDot = str.includes('.');
  const hasComma = str.includes(',');

  let canonical: string;

  if (hasDot && hasComma) {
    // If both '.' and ',' occur, the LAST one is the decimal separator and the other is a thousands separator.
    const lastDot = str.lastIndexOf('.');
    const lastComma = str.lastIndexOf(',');
    if (lastDot > lastComma) {
      const cleaned = str.replace(/,/g, '');
      if (cleaned.indexOf('.') !== cleaned.lastIndexOf('.')) {
        return null;
      }
      canonical = cleaned;
    } else {
      const cleaned = str.replace(/\./g, '');
      if (cleaned.indexOf(',') !== cleaned.lastIndexOf(',')) {
        return null;
      }
      canonical = cleaned.replace(',', '.');
    }
  } else if (hasDot && !hasComma) {
    const dotCount = (str.match(/\./g) || []).length;
    if (dotCount > 1) {
      canonical = str.replace(/\./g, '');
    } else {
      canonical = str;
    }
  } else if (hasComma && !hasDot) {
    const commaCount = (str.match(/,/g) || []).length;
    if (commaCount > 1) {
      canonical = str.replace(/,/g, '');
    } else {
      // If ',' occurs once: it is a thousands separator when exactly three digits follow it
      // AND the integer part before it is 1-3 digits and not "0"; otherwise it is decimal.
      const commaIndex = str.indexOf(',');
      const before = str.slice(0, commaIndex);
      const after = str.slice(commaIndex + 1);
      const isThousands =
        after.length === 3 &&
        before.length >= 1 &&
        before.length <= 3 &&
        before !== '0' &&
        /^\d+$/.test(before) &&
        /^\d+$/.test(after);

      if (isThousands) {
        canonical = before + after;
      } else {
        canonical = before + '.' + after;
      }
    }
  } else {
    canonical = str;
  }

  if (canonical.startsWith('.')) {
    canonical = '0' + canonical;
  }
  if (canonical.endsWith('.')) {
    canonical = canonical.slice(0, -1);
  }

  const result = (isNegative ? '-' : '') + canonical;

  if (!/^-?\d+(\.\d+)?$/.test(result)) {
    return null;
  }

  return result;
}
