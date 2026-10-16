/** Format a calendar date using its local year, month, and day. */
export function toIsoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/** Serialize a calendar date as local midnight with its explicit UTC offset. */
export function toLocalMidnightIso(value: Date | string): string {
  const date = typeof value === 'string'
    ? (() => {
      const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
      if (!match) throw new RangeError('Expected a YYYY-MM-DD date');
      return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
    })()
    : value;
  const offsetMinutes = -date.getTimezoneOffset();
  const sign = offsetMinutes < 0 ? '-' : '+';
  const absoluteOffset = Math.abs(offsetMinutes);
  const offsetHours = String(Math.floor(absoluteOffset / 60)).padStart(2, '0');
  const offsetRemainder = String(absoluteOffset % 60).padStart(2, '0');
  return `${toIsoDate(date)}T00:00:00${sign}${offsetHours}:${offsetRemainder}`;
}

export function toLocalMidnightIsoOrNull(value: Date | string | null | undefined): string | null {
  if (value == null || value === '') return null;
  return toLocalMidnightIso(value);
}

export function toIsoDateOrNull(value: Date | string | null | undefined): string | null {
  if (value == null || value === '') return null;
  if (typeof value === 'string') return value.slice(0, 10);
  return toIsoDate(value);
}
