"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, AlertTriangle } from "lucide-react";
import ItemDetails from "@/app/components/ItemDetails/ItemDetails";
import { fetchWithAuth } from "@/app/services/auth";
import Loading from "@/app/item/[sku]/loading";

type Props = {
  params: Promise<{
    sku: string;
  }>;
  searchParams: Promise<{
    quantity?: string;
  }>;
};

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
export default function ItemDetailPage({ params, searchParams }: Props) {
  const { sku } = use(params);
  const { quantity } = use(searchParams);
  const desiredQuantity = parseInt(quantity || "1");

  const [item, setItem] = useState<ItemData | null>(null);
  const [inventory, setInventory] = useState(null);
  const [production, setProduction] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);


  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      setError(null);

      try {
        // Fetch all data with authentication
        const [itemRes, inventoryRes, productionRes] = await Promise.all([
          fetchWithAuth(`${API_BASE_URL}/items/sku/${sku}`),
          fetchWithAuth(`${API_BASE_URL}/inventory/${sku}`),
          fetchWithAuth(`${API_BASE_URL}/production/feasibility/${sku}?desired_quantity=${desiredQuantity}`),
        ]);

        const [itemData, inventoryData, productionData] = await Promise.all([
          itemRes.json(),
          inventoryRes.ok ? inventoryRes.json() : null,
          productionRes.ok ? productionRes.json() : null,
        ]);

        setItem(itemData);
        setInventory(inventoryData);
        setProduction(productionData);
      } catch (err) {
        console.error("Error fetching item data:", err);
        setError("Failed to load item data");
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [sku, desiredQuantity]);

  if (loading) {
    return (
      <div className="min-h-[calc(100vh-5rem)] bg-gradient-to-b from-blue-50 to-white px-4 pt-8">
        <div className="max-w-4xl mx-auto">
          <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-700 mb-4 transition">
            <ArrowLeft className="w-4 h-4" /> Back to Home
          </Link>
          <Loading />
        </div>
      </div>
    );
  }

  if (error || !item) {
    return (
      <div className="min-h-[calc(100vh-5rem)] bg-gradient-to-b from-blue-50 to-white px-4 pt-8">
        <div className="max-w-4xl mx-auto">
          <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-700 mb-4 transition">
            <ArrowLeft className="w-4 h-4" /> Back to Home
          </Link>
          <div className="bg-white rounded-xl shadow border border-gray-200 p-8 text-center">
            <div className="w-14 h-14 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <AlertTriangle className="w-7 h-7 text-red-600" />
            </div>
            <h1 className="text-xl font-bold text-gray-900 mb-2">Item Not Found</h1>
            <p className="text-gray-500 text-sm">{error || `No item found for SKU: ${sku}`}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-[calc(100vh-5rem)] bg-gradient-to-b from-blue-50 to-white px-4 pt-8 pb-8">
      <div className="max-w-4xl mx-auto">
        <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-700 mb-4 transition">
          <ArrowLeft className="w-4 h-4" /> Back to Home
        </Link>
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
