"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Plus, X, GripVertical, Info } from "lucide-react";
import type { AppRouterInstance } from "next/dist/shared/lib/app-router-context.shared-runtime";
import SkuAutocomplete from "./SkuAutocomplete";

export interface SkuRow {
  sku: string;
  qty: string;
}

export const MAX_ROWS = 50;

export const buildItemsParam = (rows: SkuRow[]): string =>
  rows
    .filter((r) => r.sku.trim().length > 0)
    .map((r) => {
      const sku = r.sku.trim().toUpperCase();
      const qty = parseInt(r.qty, 10);
      const safeQty = Number.isFinite(qty) && qty > 0 ? qty : 1;
      return `${encodeURIComponent(sku)}:${safeQty}`;
    })
    .join(",");

export const validRowsOf = (rows: SkuRow[]): SkuRow[] =>
  rows.filter((r) => r.sku.trim().length > 0);

export const canAnalyzeRows = (rows: SkuRow[]): boolean => {
  const valid = validRowsOf(rows);
  if (valid.length === 0) return false;
  return valid.every((r) => {
    const q = parseInt(r.qty, 10);
    return Number.isFinite(q) && q > 0;
  });
};

export const analyzeRows = (rows: SkuRow[], router: AppRouterInstance): void => {
  if (!canAnalyzeRows(rows)) return;
  const valid = validRowsOf(rows);
  if (valid.length === 1) {
    const only = valid[0];
    const qty = parseInt(only.qty, 10) || 1;
    router.push(
      `/item/${encodeURIComponent(only.sku.trim().toUpperCase())}?quantity=${qty}`
    );
    return;
  }
  const itemsParam = buildItemsParam(rows);
  router.push(`/multi-analyze?items=${itemsParam}`);
};

interface MultiSkuPanelProps {
  rows: SkuRow[];
  setRows: React.Dispatch<React.SetStateAction<SkuRow[]>>;
  onClose: () => void;
  variant?: "card" | "compact";
  startIndex?: number;
  hideHeader?: boolean;
  hideAnalyze?: boolean;
  hideClose?: boolean;
}

const MultiSkuPanel: React.FC<MultiSkuPanelProps> = ({
  rows,
  setRows,
  onClose,
  variant = "card",
  startIndex = 0,
  hideHeader = false,
  hideAnalyze = false,
  hideClose = false,
}) => {
  const router = useRouter();
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [overIndex, setOverIndex] = useState<number | null>(null);

  const updateRow = (index: number, patch: Partial<SkuRow>) => {
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  };

  const lastRowEmpty = rows.length > 0 && rows[rows.length - 1].sku.trim().length === 0;
  const canAddRow = rows.length < MAX_ROWS && !lastRowEmpty;

  const addRow = () => {
    if (!canAddRow) return;
    setRows((prev) => [...prev, { sku: "", qty: "1" }]);
  };

  const removeRow = (index: number) => {
    setRows((prev) => (prev.length <= 1 ? prev : prev.filter((_, i) => i !== index)));
  };

  // Clear all resets the rows and drops back to single-SKU search (it replaces the old close X).
  const clearAll = () => {
    setRows([{ sku: "", qty: "1" }]);
    onClose();
  };

  const reorderRow = (from: number, to: number) => {
    if (from === to) return;
    setRows((prev) => {
      if (from < 0 || from >= prev.length || to < 0 || to >= prev.length) return prev;
      const next = [...prev];
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved);
      return next;
    });
  };

  const validRows = validRowsOf(rows);
  const canAnalyze = canAnalyzeRows(rows);

  const skuCounts: Record<string, number> = {};
  validRows.forEach((r) => {
    const key = r.sku.trim().toUpperCase();
    skuCounts[key] = (skuCounts[key] || 0) + 1;
  });
  const hasDuplicates = Object.values(skuCounts).some((n) => n > 1);

  const handleAnalyze = () => {
    if (!canAnalyze) return;
    const cleaned = rows.filter((r) => r.sku.trim().length > 0);
    if (cleaned.length === 0) return;
    if (cleaned.length !== rows.length) {
      setRows(cleaned);
    }
    analyzeRows(cleaned, router);
    onClose();
  };

  const wrapperClass =
    variant === "card"
      ? "bg-white border border-gray-200 rounded-2xl shadow-lg p-5 md:p-6 w-full"
      : "bg-white border border-gray-200 rounded-xl shadow-lg p-4 w-full";

  const visibleRows = rows
    .map((row, index) => ({ row, index }))
    .filter(({ index }) => index >= startIndex);

  const hasNoVisibleRows = visibleRows.length === 0;

  return (
    <div className={wrapperClass}>
      {!hideHeader && (
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-900">Multi-SKU analysis</h3>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={clearAll}
              className="inline-flex items-center text-xs font-medium text-gray-700 bg-white border border-gray-200 rounded-md px-2.5 py-1 hover:bg-gray-50 hover:border-gray-300 transition"
            >
              Clear all
            </button>
            {!hideClose && (
              <button
                type="button"
                onClick={onClose}
                className="text-gray-400 hover:text-gray-600 transition p-1"
                aria-label="Close multi-SKU mode"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      )}

      <div className="bg-blue-50 border border-blue-100 rounded-md px-3 py-2 mb-3 flex items-start gap-2 text-xs text-blue-800">
        <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
        <span>
          <strong>Order matters:</strong> earlier SKUs claim shared inventory first. Drag the
          handle on the left of any row to reorder.
        </span>
      </div>

      {hasNoVisibleRows ? (
        <p className="text-xs text-gray-500">Click &ldquo;Add another&rdquo; to add SKUs to your batch.</p>
      ) : (
        <div className="space-y-2">
          {visibleRows.map(({ row, index }) => {
            const isDragging = dragIndex === index;
            const isOver = overIndex === index && dragIndex !== null && dragIndex !== index;
            return (
              <div
                key={index}
                onDragOver={(e) => {
                  if (dragIndex === null) return;
                  e.preventDefault();
                  e.dataTransfer.dropEffect = "move";
                  if (overIndex !== index) setOverIndex(index);
                }}
                onDragLeave={() => {
                  if (overIndex === index) setOverIndex(null);
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  if (dragIndex !== null && dragIndex !== index) {
                    reorderRow(dragIndex, index);
                  }
                  setDragIndex(null);
                  setOverIndex(null);
                }}
                className={`flex items-center gap-2 rounded-lg transition ${
                  isDragging ? "opacity-50" : ""
                } ${isOver ? "ring-2 ring-blue-300 bg-blue-50/40" : ""}`}
              >
                <button
                  type="button"
                  draggable
                  onDragStart={(e) => {
                    setDragIndex(index);
                    e.dataTransfer.effectAllowed = "move";
                    // Some browsers need data set to start drag
                    e.dataTransfer.setData("text/plain", String(index));
                  }}
                  onDragEnd={() => {
                    setDragIndex(null);
                    setOverIndex(null);
                  }}
                  className="text-gray-400 hover:text-blue-600 cursor-grab active:cursor-grabbing flex-shrink-0 p-1"
                  aria-label={`Drag to reorder row ${index + 1}`}
                  title="Drag to reorder"
                >
                  <GripVertical className="w-4 h-4" />
                </button>
                <div className="relative flex-1 min-w-0">
                  <SkuAutocomplete
                    value={row.sku}
                    onChange={(next) => updateRow(index, { sku: next })}
                    onSelect={(sku) => updateRow(index, { sku })}
                    onSubmit={handleAnalyze}
                    placeholder={`SKU ${index + 1}`}
                    className="w-full border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-400 uppercase placeholder:normal-case placeholder:text-gray-400"
                  />
                </div>
                <input
                  type="number"
                  min="1"
                  value={row.qty}
                  onChange={(e) => updateRow(index, { qty: e.target.value })}
                  className="w-16 border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-400 flex-shrink-0"
                  aria-label={`Quantity for row ${index + 1}`}
                />
                <button
                  type="button"
                  onClick={() => removeRow(index)}
                  disabled={rows.length <= 1}
                  className="text-gray-400 hover:text-red-500 disabled:opacity-30 disabled:hover:text-gray-400 transition p-1 flex-shrink-0"
                  aria-label={`Remove row ${index + 1}`}
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            );
          })}
        </div>
      )}

      {hasDuplicates && (
        <p className="text-xs text-amber-600 mt-2">
          Duplicate SKUs detected. The shared ledger will deduct in input order; consider consolidating.
        </p>
      )}
      {rows.length >= MAX_ROWS && (
        <p className="text-xs text-gray-500 mt-2">Maximum of {MAX_ROWS} SKUs reached.</p>
      )}

      <div className="flex items-center justify-between mt-4 gap-2">
        <button
          type="button"
          onClick={addRow}
          disabled={!canAddRow}
          title={
            rows.length >= MAX_ROWS
              ? `Maximum of ${MAX_ROWS} SKUs reached`
              : lastRowEmpty
                ? "Fill the current row before adding another"
                : "Add another SKU"
          }
          className="inline-flex items-center gap-1.5 text-sm font-medium text-blue-600 hover:text-blue-700 disabled:text-gray-400 disabled:cursor-not-allowed transition"
        >
          <Plus className="w-4 h-4" /> Add another
        </button>
        {!hideAnalyze && (
          <button
            type="button"
            onClick={handleAnalyze}
            disabled={!canAnalyze}
            className={`px-5 py-2 font-semibold rounded-lg transition text-sm ${
              canAnalyze
                ? "bg-blue-600 text-white hover:bg-blue-700 shadow-sm"
                : "bg-gray-200 text-gray-400 cursor-not-allowed"
            }`}
          >
            {validRows.length >= 2 ? "Analyze All" : "Analyze"}
          </button>
        )}
      </div>
    </div>
  );
};

export default MultiSkuPanel;
