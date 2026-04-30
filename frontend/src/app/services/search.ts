import { fetchWithAuth, API_BASE_URL } from './auth';

export interface ItemSuggestion {
  id: string;
  sku: string;
  name: string | null;
}

/**
 * Validates if an exact SKU exists by fetching item details
 */
export async function validateSku(sku: string): Promise<boolean> {
  if (!sku) return false;
  try {
    const res = await fetchWithAuth(
      `${API_BASE_URL}/items/sku/${encodeURIComponent(sku)}`,
      { cache: "no-store" }
    );
    return res.ok;
  } catch (error) {
    console.error("Failed to validate SKU:", error);
    return false;
  }
}

/**
 * Typeahead suggestions from the local items DB.
 * Returns up to `limit` matches by SKU or name (case-insensitive).
 */
export async function fetchItemSuggestions(
  query: string,
  limit: number = 10,
  offset: number = 0
): Promise<ItemSuggestion[]> {
  const trimmed = (query || "").trim();
  if (trimmed.length < 1) return [];
  try {
    const res = await fetchWithAuth(
      `${API_BASE_URL}/items/search?q=${encodeURIComponent(trimmed)}&limit=${limit}&offset=${offset}`,
      { cache: "no-store" }
    );
    if (!res.ok) return [];
    return (await res.json()) as ItemSuggestion[];
  } catch (error) {
    console.error("Failed to fetch item suggestions:", error);
    return [];
  }
}
