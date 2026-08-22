/**
 * Pack size and base quantity normalisation arithmetic (Principle II, SC-007).
 *
 * Exact decimal string multiplication with BigInt representation so no binary float
 * rounding ever occurs.
 */
export function computeBaseQuantity(
  packCount: number | string | null | undefined,
  unitSize: string | null | undefined,
): string | null {
  if (packCount == null || unitSize == null) return null;

  const count = typeof packCount === "string" ? parseInt(packCount, 10) : packCount;
  if (!count || isNaN(count) || count <= 0 || !Number.isInteger(count)) return null;

  const trimmed = unitSize.trim();
  if (!trimmed || !/^\d+(\.\d+)?$/.test(trimmed)) return null;

  const num = parseFloat(trimmed);
  if (isNaN(num) || num <= 0) return null;

  const parts = trimmed.split(".");
  const decimals = parts.length > 1 ? parts[1].length : 0;
  const integerVal = BigInt(parts.join(""));
  const total = integerVal * BigInt(count);
  const totalStr = total.toString();

  if (decimals === 0) {
    return totalStr;
  }

  if (totalStr.length <= decimals) {
    const padded = totalStr.padStart(decimals + 1, "0");
    const integerPart = padded.slice(0, padded.length - decimals);
    const fracPart = padded.slice(padded.length - decimals).replace(/0+$/, "");
    return fracPart.length > 0 ? `${integerPart}.${fracPart}` : integerPart;
  }

  const integerPart = totalStr.slice(0, totalStr.length - decimals);
  const fracPart = totalStr.slice(totalStr.length - decimals).replace(/0+$/, "");
  return fracPart.length > 0 ? `${integerPart}.${fracPart}` : integerPart;
}
