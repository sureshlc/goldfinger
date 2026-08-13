/**
 * Shared number formatting for the feasibility UI.
 * Adds thousands separators and rounds to at most `maxDecimals` places.
 * Returns an em dash for null/undefined/NaN so the UI never prints "NaN".
 */
export function formatNumber(
  value: number | undefined | null,
  maxDecimals = 2
): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  if (!Number.isFinite(value)) return "∞";
  if (Number.isInteger(value)) return value.toLocaleString("en-US");
  const rounded = parseFloat(value.toFixed(maxDecimals));
  return rounded.toLocaleString("en-US", { maximumFractionDigits: maxDecimals });
}
