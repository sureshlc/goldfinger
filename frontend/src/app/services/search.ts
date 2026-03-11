import { fetchWithAuth, API_BASE_URL } from './auth';

/**
 * Validates if an exact SKU exists by fetching item details
 * Returns true if item exists, false otherwise
 */
export async function validateSku(sku: string): Promise<boolean> {
  console.log("[validateSku] called with:", sku);
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

// Keep this for backward compatibility with existing code
export async function fetchItemSuggestions(): Promise<unknown[]> {
  // Return empty array since we don't have autocomplete
  return [];
}