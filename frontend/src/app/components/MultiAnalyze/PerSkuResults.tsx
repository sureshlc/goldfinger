"use client";

import React, { useState } from "react";
import Link from "next/link";
import { ChevronDown, ChevronRight, CheckCircle2, AlertTriangle, XCircle, ArrowRight } from "lucide-react";
import { formatNumber as formatNum } from "@/app/lib/format";

interface SubComponentDetail {
  item_id?: string;
  item_sku?: string;
  item_name?: string;
  available_quantity?: number;
  qty_per_unit?: number;
  unit?: string;
}

interface ShortageEntry {
  item_sku?: string;
  item_name?: string;
  shortage_quantity?: number;
  required_quantity?: number;
  available_quantity?: number;
  unit?: string;
  reason?: string;
  sub_component_details?: SubComponentDetail[];
}

interface BatchItemResult {
  item_sku: string;
  item_name: string;
  desired_quantity: number;
  can_produce: boolean;
  max_quantity_producible: number;
  limiting_component: string | null;
  shortages: ShortageEntry[];
  status: "fully_producible" | "partially_producible" | "blocked";
}

const isUselessName = (name?: string, sku?: string): boolean => {
  if (!name) return true;
  const trimmed = name.trim();
  if (!trimmed) return true;
  if (sku && trimmed.toUpperCase() === sku.trim().toUpperCase()) return true;
  // Hide pure-numeric or very short codes (likely a NetSuite internal id, not a real name)
  if (/^\d+$/.test(trimmed)) return true;
  return false;
};

const StatusBadge: React.FC<{ status: BatchItemResult["status"] }> = ({ status }) => {
  if (status === "fully_producible") {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-semibold text-green-700 bg-green-50 border border-green-200 rounded-full px-2.5 py-0.5">
        <CheckCircle2 className="w-3.5 h-3.5" /> Fully producible
      </span>
    );
  }
  if (status === "partially_producible") {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-semibold text-amber-700 bg-amber-50 border border-amber-200 rounded-full px-2.5 py-0.5">
        <AlertTriangle className="w-3.5 h-3.5" /> Partial
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs font-semibold text-red-700 bg-red-50 border border-red-200 rounded-full px-2.5 py-0.5">
      <XCircle className="w-3.5 h-3.5" /> Blocked
    </span>
  );
};

const ResultRow: React.FC<{ result: BatchItemResult }> = ({ result }) => {
  const isFully = result.status === "fully_producible";
  const hasShortages = result.shortages.length > 0;
  const [open, setOpen] = useState(false);

  return (
    <div className="border-b border-gray-100 last:border-b-0 px-5 py-3">
      {/* Card face — key facts always visible, no click needed */}
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-gray-900">{result.item_sku}</span>
            <span className="text-xs text-gray-500">× {formatNum(result.desired_quantity)}</span>
            <StatusBadge status={result.status} />
          </div>
          {!isUselessName(result.item_name, result.item_sku) && (
            <div className="text-xs text-gray-500 mt-0.5 truncate">{result.item_name}</div>
          )}
          {!isFully && (
            <div className="flex items-center gap-x-3 gap-y-1 flex-wrap mt-1.5 text-xs">
              {result.limiting_component && (
                <span className="text-gray-600">
                  Limiting:{" "}
                  <span className="font-medium text-gray-900">{result.limiting_component}</span>
                </span>
              )}
              {hasShortages && (
                <button
                  type="button"
                  onClick={() => setOpen((v) => !v)}
                  className="inline-flex items-center gap-1 font-medium text-gray-500 hover:text-gray-800 transition"
                  aria-expanded={open}
                >
                  {result.shortages.length} shortage{result.shortages.length > 1 ? "s" : ""}
                  {open ? (
                    <ChevronDown className="w-3.5 h-3.5" />
                  ) : (
                    <ChevronRight className="w-3.5 h-3.5" />
                  )}
                </button>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center gap-3 flex-shrink-0">
          <div className="text-center">
            <div className="text-base font-bold text-blue-700">
              {formatNum(result.max_quantity_producible)}
            </div>
            <div className="text-xs text-gray-500">Max producible</div>
          </div>
          <Link
            href={`/item/${encodeURIComponent(result.item_sku)}?quantity=${result.desired_quantity}`}
            className="inline-flex items-center gap-1 whitespace-nowrap bg-blue-600 text-white px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-blue-700 shadow-sm transition"
          >
            View details
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>

      {/* Optional expand — full shortage breakdown only */}
      {open && hasShortages && (
        <div className="mt-3 bg-gray-50/50 rounded-md p-2.5">
          <div className="space-y-2">
              {result.shortages.map((s, idx) => {
                const subs = (s.sub_component_details || [])
                  .map((sub) => {
                    const qtyPerUnit = sub.qty_per_unit ?? 0;
                    const subRequired = qtyPerUnit * (s.required_quantity ?? 0);
                    const subAvailable = sub.available_quantity ?? 0;
                    const subShortage = Math.max(0, subRequired - subAvailable);
                    return {
                      ...sub,
                      subRequired,
                      subAvailable,
                      subShortage,
                    };
                  })
                  .filter((sub) => sub.subShortage > 0);

                return (
                  <React.Fragment key={`${s.item_sku || idx}`}>
                    <div className="border-l-4 border-red-400 bg-white rounded-r-md p-2.5 border border-gray-100">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-gray-900">
                          {s.item_sku || "—"}
                        </p>
                        {!isUselessName(s.item_name, s.item_sku) && (
                          <p className="text-[11px] text-gray-500">{s.item_name}</p>
                        )}
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-[11px] mt-1.5">
                        <div>
                          <p className="text-gray-500">Required</p>
                          <p className="font-medium text-gray-900">
                            {formatNum(s.required_quantity)} {s.unit || ""}
                          </p>
                        </div>
                        <div>
                          <p className="text-gray-500">Available</p>
                          <p className="font-medium text-gray-900">
                            {formatNum(s.available_quantity)} {s.unit || ""}
                          </p>
                        </div>
                        <div>
                          <p className="text-gray-500">Short</p>
                          <p className="font-semibold text-red-600">
                            {formatNum(s.shortage_quantity)} {s.unit || ""}
                          </p>
                        </div>
                      </div>
                    </div>

                    {subs.map((sub, subIdx) => (
                      <div
                        key={`${s.item_sku || idx}-sub-${subIdx}`}
                        style={{ marginLeft: 24 }}
                        className="border-l-4 border-red-200 bg-white rounded-r-md p-2.5 border border-gray-100"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5">
                            <span className="text-[10px] bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">
                              raw
                            </span>
                            <p className="text-xs font-medium text-gray-900">
                              {sub.item_sku || "—"}
                            </p>
                          </div>
                          {!isUselessName(sub.item_name, sub.item_sku) && (
                            <p className="text-[11px] text-gray-500 mt-0.5">{sub.item_name}</p>
                          )}
                        </div>
                        <div className="grid grid-cols-3 gap-2 text-[11px] mt-1.5">
                          <div>
                            <p className="text-gray-500">Required</p>
                            <p className="font-medium text-gray-900">
                              {formatNum(sub.subRequired)} {sub.unit || s.unit || ""}
                            </p>
                          </div>
                          <div>
                            <p className="text-gray-500">Available</p>
                            <p className="font-medium text-gray-900">
                              {formatNum(sub.subAvailable)} {sub.unit || s.unit || ""}
                            </p>
                          </div>
                          <div>
                            <p className="text-gray-500">Short</p>
                            <p className="font-semibold text-red-600">
                              {formatNum(sub.subShortage)} {sub.unit || s.unit || ""}
                            </p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </React.Fragment>
                );
              })}
          </div>
        </div>
      )}
    </div>
  );
};

const PerSkuResults: React.FC<{ results: BatchItemResult[] }> = ({ results }) => {
  return (
    <div className="bg-white rounded-xl shadow border border-gray-200 overflow-hidden mb-6">
      <div className="px-5 py-4 border-b border-gray-100">
        <h3 className="text-base font-semibold text-gray-900">Per-SKU Results</h3>
        <p className="text-xs text-gray-500 mt-0.5">
          Each SKU is checked against the inventory remaining after earlier SKUs in the list have consumed their share.
        </p>
      </div>
      <div>
        {results.map((r) => (
          <ResultRow key={r.item_sku} result={r} />
        ))}
      </div>
    </div>
  );
};

export default PerSkuResults;
