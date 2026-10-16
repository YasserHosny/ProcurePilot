import { toIsoDate } from './iso-date';

describe('toIsoDate', () => {
  it('preserves the local calendar day across times of day', () => {
    expect(toIsoDate(new Date(2026, 9, 20))).toBe('2026-10-20');
    expect(toIsoDate(new Date(2026, 9, 20, 0, 0))).toBe('2026-10-20');
    expect(toIsoDate(new Date(2026, 9, 20, 23, 59))).toBe('2026-10-20');
  });
});
