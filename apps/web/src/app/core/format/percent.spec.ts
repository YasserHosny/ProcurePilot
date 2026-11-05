import { formatScorePercent, percentSign } from './format.service';

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
