"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, AlertTriangle } from "lucide-react";
import { fetchWithAuth, API_BASE_URL } from "@/app/services/auth";
import SummaryBanner from "@/app/components/MultiAnalyze/SummaryBanner";
import MaterialSummary from "@/app/components/MultiAnalyze/MaterialSummary";
import PerSkuResults from "@/app/components/MultiAnalyze/PerSkuResults";

interface BatchItemResult {
  item_sku: string;
  item_name: string;
  desired_quantity: number;
  can_produce: boolean;
  max_quantity_producible: number;
  limiting_component: string | null;
  shortages: Array<{
    item_sku?: string;
    item_name?: string;
    shortage_quantity?: number;
    required_quantity?: number;
    available_quantity?: number;
    unit?: string;
    reason?: string;
  }>;
  status: "fully_producible" | "partially_producible" | "blocked";
}

interface MaterialContention {
  component_sku: string;
  component_name: string;
  total_available: number;
  total_demanded: number;
  shortage: number;
  demanded_by: Array<{ sku: string; quantity_needed: number }>;
  unit?: string;
}

interface MaterialSummaryRow {
  component_sku: string;
  component_name: string;
  unit: string;
  total_demanded: number;
  total_available: number;
  shortage: number;
  demanded_by: Array<{ sku: string; quantity_needed: number }>;
}

interface BatchSummary {
  total_skus: number;
  fully_producible: number;
  partially_producible: number;
  blocked: number;
  contention_count: number;
}

interface BatchFeasibilityResponse {
  results: BatchItemResult[];
  material_contentions: MaterialContention[];
  material_summary?: MaterialSummaryRow[];
  summary: BatchSummary;
}

interface ParsedItem {
  sku: string;
  desired_quantity: number;
}

function parseItemsParam(raw: string): ParsedItem[] {
  if (!raw) return [];
  return raw
    .split(",")
    .map((pair) => pair.trim())
    .filter(Boolean)
    .map((pair) => {
      const [skuRaw, qtyRaw] = pair.split(":");
      const sku = (skuRaw || "").trim().toUpperCase();
      const qty = parseInt((qtyRaw || "1").trim(), 10);
      return { sku, desired_quantity: Number.isFinite(qty) && qty > 0 ? qty : 1 };
    })
    .filter((item) => item.sku.length > 0);
}

export default function MultiAnalyzeClient({ itemsParam }: { itemsParam: string }) {
  const items = parseItemsParam(itemsParam);
  const router = useRouter();
  const resultsRef = useRef<HTMLDivElement>(null);

  const [data, setData] = useState<BatchFeasibilityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const handleBack = () => {
    if (typeof window !== "undefined" && window.history.length > 1) {
      router.back();
    } else {
      router.push("/");
    }
  };

  useEffect(() => {
    if (items.length === 0) {
      setLoading(false);
      setError("No SKUs provided. Use the search to add at least two SKUs.");
      return;
    }

    const fetchBatch = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetchWithAuth(
          `${API_BASE_URL}/production/batch-feasibility`,
          {
            method: "POST",
            body: JSON.stringify({ items }),
          }
        );
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          setError(body.detail || `Request failed (${res.status})`);
          return;
        }
        const json: BatchFeasibilityResponse = await res.json();
        setData(json);
        setTimeout(() => {
          resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 0);
      } catch {
        setError("Failed to load batch feasibility");
      } finally {
        setLoading(false);
      }
    };

    fetchBatch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [itemsParam]);

  return (
    <div className="min-h-[calc(100vh-5rem)] bg-gradient-to-b from-blue-50 to-white px-4 pt-8 pb-12">
      <div className="max-w-4xl mx-auto">
        <button
          type="button"
          onClick={handleBack}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg px-3 py-1.5 mb-4 shadow-sm hover:bg-gray-50 hover:border-gray-300 hover:text-gray-900 transition"
        >
          <ArrowLeft className="w-4 h-4" /> Back
        </button>

        <h1 className="text-2xl md:text-3xl font-bold text-gray-900 mb-2">
          Multi-SKU Production Feasibility
        </h1>
        <p className="text-sm text-gray-500 mb-6">
          Plan a batch — see if the warehouse can produce all desired SKUs from the current shared inventory.
        </p>

        {loading && (
          <div className="bg-white rounded-xl shadow border border-gray-200 p-8 text-center">
            <svg
              className="animate-spin h-6 w-6 mx-auto text-blue-600 mb-3"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
            <p className="text-sm text-gray-500">Analyzing {items.length} SKUs…</p>
          </div>
        )}

        {!loading && error && (
          <div className="bg-white rounded-xl shadow border border-gray-200 p-8 text-center">
            <div className="w-14 h-14 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <AlertTriangle className="w-7 h-7 text-red-600" />
            </div>
            <h2 className="text-xl font-bold text-gray-900 mb-2">Could not analyze batch</h2>
            <p className="text-sm text-gray-500 mb-4">{error}</p>
            <Link href="/" className="text-sm text-blue-600 hover:text-blue-700 font-medium">
              Back to search
            </Link>
          </div>
        )}

        {!loading && !error && data && (
          <div ref={resultsRef} className="scroll-mt-20">
            <SummaryBanner summary={data.summary} />
            <MaterialSummary
              results={data.results}
              contentions={data.material_contentions}
              materialSummary={data.material_summary}
              batchItems={items}
            />
            <PerSkuResults results={data.results} />
          </div>
        )}
      </div>
    </div>
  );
}
