import { toIsoDate, toLocalMidnightIso, toLocalMidnightIsoOrNull } from './iso-date';

describe('toIsoDate', () => {
  it('preserves the local calendar day across times of day', () => {
    expect(toIsoDate(new Date(2026, 9, 20))).toBe('2026-10-20');
    expect(toIsoDate(new Date(2026, 9, 20, 0, 0))).toBe('2026-10-20');
    expect(toIsoDate(new Date(2026, 9, 20, 23, 59))).toBe('2026-10-20');
  });
});

describe('toLocalMidnightIso', () => {
  it('preserves the local calendar day and includes the current zone offset', () => {
    const input = new Date(2026, 9, 20, 17, 45);
    const offset = -input.getTimezoneOffset();
    const sign = offset < 0 ? '-' : '+';
    const abs = Math.abs(offset);
    const expectedOffset = `${sign}${String(Math.floor(abs / 60)).padStart(2, '0')}:${String(abs % 60).padStart(2, '0')}`;
    const result = toLocalMidnightIso(input);
    const parsed = new Date(result);

    expect(result).toBe(`2026-10-20T00:00:00${expectedOffset}`);
    expect(result).toMatch(/T00:00:00[+-]\d\d:\d\d$/);
    expect(parsed.getFullYear()).toBe(input.getFullYear());
    expect(parsed.getMonth()).toBe(input.getMonth());
    expect(parsed.getDate()).toBe(input.getDate());
  });

  it('parses date strings as local calendar dates and supports null values', () => {
    expect(toLocalMidnightIso('2026-10-20')).toBe(toLocalMidnightIso(new Date(2026, 9, 20)));
    expect(toLocalMidnightIsoOrNull(null)).toBeNull();
    expect(toLocalMidnightIsoOrNull('')).toBeNull();
  });
});
