/** Trim fractional trailing zeroes without converting a decimal string to a JS number. */
export function trimDecimal(value: string): string {
  return value.includes('.') ? value.replace(/0+$/, '').replace(/\.$/, '') : value;
}
