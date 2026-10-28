import { normaliseSearchText } from './search-normalise';

describe('normaliseSearchText', () => {
  it('finds «أرز بسمتي» with «ارز» query', () => {
    const target = normaliseSearchText('أرز بسمتي');
    const query = normaliseSearchText('ارز');
    expect(target).toContain(query);
  });

  it('finds «سكر» inside «سكر أبيض ناعم 10 كجم»', () => {
    const target = normaliseSearchText('سكر أبيض ناعم 10 كجم');
    const query = normaliseSearchText('سكر');
    expect(target).toContain(query);
  });

  it('strips tashkeel/diacritics and tatweel', () => {
    expect(normaliseSearchText('سُكَّرٌ')).toBe('سكر');
    expect(normaliseSearchText('أرز بـسـمـتـي')).toBe('ارز بسمتي');
  });

  it('unifies alef variants (أ/إ/آ/ٱ -> ا), ى -> ي, and ة -> ه', () => {
    expect(normaliseSearchText('إبريق')).toBe('ابريق');
    expect(normaliseSearchText('آلات')).toBe('الات');
    expect(normaliseSearchText('حلوى')).toBe('حلوي');
    expect(normaliseSearchText('طازجة')).toBe('طازجه');
  });

  it('lowercases latin characters and collapses whitespace', () => {
    expect(normaliseSearchText('  Basmati   RICE  ')).toBe('basmati rice');
  });

  it('handles null, undefined, and empty string safely', () => {
    expect(normaliseSearchText(null)).toBe('');
    expect(normaliseSearchText(undefined)).toBe('');
    expect(normaliseSearchText('')).toBe('');
  });
});
