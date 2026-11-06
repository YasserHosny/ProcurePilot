import { formatScorePercent, localizeDigits, percentSign } from './format.service';

// P-159: match scores were raw `85%` in Latin digits while quantities and totals use Arabic-Indic digits.
describe('formatScorePercent', () => {
  it('formats a whole-number score in English', () => {
    expect(formatScorePercent(85, 'en')).toBe('85%');
  });

  it('uses Arabic-Indic digits and the Arabic percent sign in Arabic', () => {
    const out = formatScorePercent(85, 'ar');
    expect(out).toMatch(/^[٠-٩]{2}\s?٪/);
  });

  it('rounds to a whole percent and shows a dash for missing values', () => {
    expect(formatScorePercent(84.6, 'en')).toBe('85%');
    expect(formatScorePercent(null, 'en')).toBe('—');
    expect(formatScorePercent(undefined, 'ar')).toBe('—');
  });
});

describe('percentSign', () => {
  it('is the locale percent sign', () => {
    expect(percentSign('en')).toBe('%');
    expect(percentSign('ar')).toMatch(/^٪/);
  });
});

describe('localizeDigits', () => {
  it('leaves English text exactly as given', () => {
    expect(localizeDigits('1 × 2.0', 'en')).toBe('1 × 2.0');
  });

  it('turns Latin digits and the decimal point into Arabic-Indic ones in Arabic, keeping the text', () => {
    expect(localizeDigits('1 × 2.0', 'ar')).toBe('١ × ٢٫٠');
    expect(localizeDigits('SKU-12 x 0.5', 'ar')).toBe('SKU-١٢ x ٠٫٥');
  });

  it('does not touch a full stop that ends a sentence', () => {
    expect(localizeDigits('Pack of 6.', 'ar')).toBe('Pack of ٦.');
  });
});
