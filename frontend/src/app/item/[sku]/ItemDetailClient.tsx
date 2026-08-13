"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, AlertTriangle, RefreshCw } from "lucide-react";
import ItemDetails from "@/app/components/ItemDetails/ItemDetails";
import { fetchWithAuth } from "@/app/services/auth";
import Loading from "@/app/item/[sku]/loading";

interface ItemData {
  sku: string;
  name: string;
  id?: string;
  description?: string;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL;

/**
 * Client component - fetches item, inventory, and production data with auth
 */
export default function ItemDetailClient({
  sku,
  desiredQuantity,
}: {
  sku: string;
  desiredQuantity: number;
}) {
  const router = useRouter();
  const [item, setItem] = useState<ItemData | null>(null);
  const [inventory, setInventory] = useState(null);
  const [production, setProduction] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryable, setRetryable] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const handleBack = () => {
    if (typeof window !== "undefined" && window.history.length > 1) {
      router.back();
    } else {
      router.push("/");
    }
  };

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    // Safety net: NetSuite can be slow under rate limiting; don't spin forever.
    const timeoutId = setTimeout(() => controller.abort(), 40000);

    const fetchData = async () => {
      setLoading(true);
      setError(null);
      setRetryable(false);

      try {
        const encodedSku = encodeURIComponent(sku);
        const opts = { signal: controller.signal };
        const [itemRes, inventoryRes, productionRes] = await Promise.all([
          fetchWithAuth(`${API_BASE_URL}/items/sku/${encodedSku}`, opts),
          fetchWithAuth(`${API_BASE_URL}/inventory/${encodedSku}`, opts),
          fetchWithAuth(`${API_BASE_URL}/production/feasibility/${encodedSku}?desired_quantity=${desiredQuantity}`, opts),
        ]);

        if (cancelled) return;

        if (!itemRes.ok) {
          setError(itemRes.status === 404 ? `No item found for SKU: ${sku}` : "Failed to load item data");
          setRetryable(itemRes.status !== 404);
          return;
        }

        const [itemData, inventoryData, productionData] = await Promise.all([
          itemRes.json(),
          inventoryRes.ok ? inventoryRes.json() : null,
          productionRes.ok ? productionRes.json() : null,
        ]);

        if (cancelled) return;
        setItem(itemData);
        setInventory(inventoryData);
        setProduction(productionData);
      } catch (err) {
        if (cancelled) return;
        const timedOut = err instanceof DOMException && err.name === "AbortError";
        console.error("Error fetching item data:", err);
        setError(
          timedOut
            ? "This is taking longer than expected — NetSuite may be busy. Please try again."
            : "Failed to load item data"
        );
        setRetryable(true);
      } finally {
        clearTimeout(timeoutId);
        if (!cancelled) setLoading(false);
      }
    };

    fetchData();

    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
      controller.abort();
    };
  }, [sku, desiredQuantity, reloadKey]);

  if (loading) {
    return (
      <div className="min-h-[calc(100vh-5rem)] bg-gradient-to-b from-blue-50 to-white px-4 pt-8">
        <div className="max-w-4xl mx-auto">
          <button
            type="button"
            onClick={handleBack}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg px-3 py-1.5 mb-4 shadow-sm hover:bg-gray-50 hover:border-gray-300 hover:text-gray-900 transition"
          >
            <ArrowLeft className="w-4 h-4" /> Back
          </button>
          <Loading />
        </div>
      </div>
    );
  }

  if (error || !item) {
    return (
      <div className="min-h-[calc(100vh-5rem)] bg-gradient-to-b from-blue-50 to-white px-4 pt-8">
        <div className="max-w-4xl mx-auto">
          <button
            type="button"
            onClick={handleBack}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg px-3 py-1.5 mb-4 shadow-sm hover:bg-gray-50 hover:border-gray-300 hover:text-gray-900 transition"
          >
            <ArrowLeft className="w-4 h-4" /> Back
          </button>
          <div className="bg-white rounded-xl shadow border border-gray-200 p-8 text-center">
            <div className="w-14 h-14 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <AlertTriangle className="w-7 h-7 text-red-600" />
            </div>
            <h1 className="text-xl font-bold text-gray-900 mb-2">
              {retryable ? "Couldn’t load this item" : "Item Not Found"}
            </h1>
            <p className="text-gray-500 text-sm mb-4">{error || `No item found for SKU: ${sku}`}</p>
            {retryable && (
              <button
                type="button"
                onClick={() => setReloadKey((k) => k + 1)}
                className="inline-flex items-center gap-1.5 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition"
              >
                <RefreshCw className="w-4 h-4" /> Try again
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-[calc(100vh-5rem)] bg-gradient-to-b from-blue-50 to-white px-4 pt-8 pb-8">
      <div className="max-w-4xl mx-auto">
        <button
          type="button"
          onClick={handleBack}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg px-3 py-1.5 mb-4 shadow-sm hover:bg-gray-50 hover:border-gray-300 hover:text-gray-900 transition"
        >
          <ArrowLeft className="w-4 h-4" /> Back
        </button>
        <ItemDetails
          sku={item.sku || sku}
          name={item.description || item.name}
          inventoryData={inventory}
          productionData={production}
          desiredQuantity={desiredQuantity}
        />
      </div>
    </div>
  );
}
