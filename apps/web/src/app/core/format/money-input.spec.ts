import { parseMoneyInput } from './money-input';

describe('parseMoneyInput', () => {
  it('parses mixed thousands and decimal separators correctly', () => {
    expect(parseMoneyInput('1.234,56')).toBe('1234.56');
    expect(parseMoneyInput('1,234.56')).toBe('1234.56');
    expect(parseMoneyInput('1,234,567.89')).toBe('1234567.89');
  });

  it('parses Arabic-Indic and Extended Arabic-Indic digits with Arabic separators', () => {
    expect(parseMoneyInput('١٬٢٣٤٫٥٦')).toBe('1234.56');
    expect(parseMoneyInput('١٢٣')).toBe('123');
    expect(parseMoneyInput('۱۲٫۵')).toBe('12.5');
  });

  it('handles spaces, NBSP, narrow NBSP, and apostrophes as thousands separators', () => {
    expect(parseMoneyInput('1 234,56')).toBe('1234.56');
    expect(parseMoneyInput('1\u00A0234,56')).toBe('1234.56'); // NBSP
    expect(parseMoneyInput('1\u202F234,56')).toBe('1234.56'); // Narrow NBSP
    expect(parseMoneyInput("1'234.56")).toBe('1234.56');
    expect(parseMoneyInput('1’234.56')).toBe('1234.56');
  });

  it('differentiates single comma as decimal vs thousands separator', () => {
    expect(parseMoneyInput('12,5')).toBe('12.5');
    expect(parseMoneyInput('1,234')).toBe('1234');
    expect(parseMoneyInput('0,500')).toBe('0.500');
  });

  it('differentiates single dot as decimal vs multiple dots as thousands separator', () => {
    expect(parseMoneyInput('1.234')).toBe('1.234');
    expect(parseMoneyInput('1.234.567')).toBe('1234567');
  });

  it('strips currency symbols and text', () => {
    expect(parseMoneyInput('SAR 1,500.00')).toBe('1500.00');
    expect(parseMoneyInput('1,500 ج.م')).toBe('1500');
    expect(parseMoneyInput('£12')).toBe('12');
    expect(parseMoneyInput('12.50 ج.م.')).toBe('12.50');
    expect(parseMoneyInput('12.50 L.E.')).toBe('12.50');
    expect(parseMoneyInput('1,500.00 L.E.')).toBe('1500.00');
    expect(parseMoneyInput('E.G.P. 1,500')).toBe('1500');
  });

  it('rejects dot-separated groups that are not thousands separators', () => {
    expect(parseMoneyInput('1.5.2')).toBeNull();
  });

  it('handles negative amounts and finite numbers', () => {
    expect(parseMoneyInput('-250')).toBe('-250');
    expect(parseMoneyInput(12.5)).toBe('12.5');
    expect(parseMoneyInput(0)).toBe('0');
  });

  it('returns null for empty, whitespace, non-numeric, multiple minuses, or invalid inputs', () => {
    expect(parseMoneyInput('')).toBeNull();
    expect(parseMoneyInput('  ')).toBeNull();
    expect(parseMoneyInput('abc')).toBeNull();
    expect(parseMoneyInput('--')).toBeNull();
    expect(parseMoneyInput(null)).toBeNull();
    expect(parseMoneyInput(undefined)).toBeNull();
    expect(parseMoneyInput(NaN)).toBeNull();
  });
});
