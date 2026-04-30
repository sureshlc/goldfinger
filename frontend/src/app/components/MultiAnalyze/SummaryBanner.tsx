"use client";

import React from "react";
import { CheckCircle2, AlertTriangle, XCircle, Layers } from "lucide-react";

interface BatchSummary {
  total_skus: number;
  fully_producible: number;
  partially_producible: number;
  blocked: number;
  contention_count: number;
}

const SummaryBanner: React.FC<{ summary: BatchSummary }> = ({ summary }) => {
  const allGreen = summary.blocked === 0 && summary.partially_producible === 0;
  return (
    <div
      className={`rounded-xl border p-4 mb-6 ${
        allGreen ? "border-green-200 bg-green-50" : "border-amber-200 bg-amber-50"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-gray-900">
            {allGreen ? "All SKUs are producible" : "Mixed feasibility across the batch"}
          </h2>
          <p className="text-xs text-gray-600 mt-0.5">
            Analyzed {summary.total_skus} SKU{summary.total_skus === 1 ? "" : "s"} against shared inventory
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="inline-flex items-center gap-1.5 bg-white border border-green-200 text-green-700 rounded-full px-3 py-1">
            <CheckCircle2 className="w-3.5 h-3.5" />
            {summary.fully_producible} full
          </span>
          <span className="inline-flex items-center gap-1.5 bg-white border border-amber-200 text-amber-700 rounded-full px-3 py-1">
            <AlertTriangle className="w-3.5 h-3.5" />
            {summary.partially_producible} partial
          </span>
          <span className="inline-flex items-center gap-1.5 bg-white border border-red-200 text-red-700 rounded-full px-3 py-1">
            <XCircle className="w-3.5 h-3.5" />
            {summary.blocked} blocked
          </span>
          <span className="inline-flex items-center gap-1.5 bg-white border border-gray-200 text-gray-700 rounded-full px-3 py-1">
            <Layers className="w-3.5 h-3.5" />
            {summary.contention_count} contention{summary.contention_count === 1 ? "" : "s"}
          </span>
        </div>
      </div>
    </div>
  );
};

export default SummaryBanner;
