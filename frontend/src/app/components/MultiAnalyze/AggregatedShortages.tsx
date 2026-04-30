"use client";

import React from "react";

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
  sub_component_details?: SubComponentDetail[];
}

interface BatchItemResult {
  item_sku: string;
  item_name: string;
  desired_quantity: number;
  shortages: ShortageEntry[];
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

interface AffectedRow {
  sku: string;
  required: number;
  shortage: number;
}

interface AggregatedRow {
  component_sku: string;
  component_name: string;
  unit: string;
  total_demanded: number;
  total_available: number;
  total_shortage: number;
  affected: AffectedRow[];
}

const formatNum = (value: number): string => {
  if (!Number.isFinite(value)) return "—";
  if (Number.isInteger(value)) return value.toString();
  return parseFloat(value.toFixed(2)).toString();
};

const isUselessName = (name?: string, sku?: string): boolean => {
  if (!name) return true;
  const trimmed = name.trim();
  if (!trimmed) return true;
  if (sku && trimmed.toUpperCase() === sku.trim().toUpperCase()) return true;
  if (/^\d+$/.test(trimmed)) return true;
  return false;
};

const aggregate = (
  results: BatchItemResult[],
  contentions: MaterialContention[]
): AggregatedRow[] => {
  const byComponent: Record<string, AggregatedRow> = {};

  const addToComponent = (
    keyRaw: string,
    sku: string,
    name: string,
    unit: string,
    required: number,
    available: number,
    shortage: number,
    parentSku: string
  ) => {
    const key = keyRaw.trim();
    if (!key) return;
    if (!byComponent[key]) {
      byComponent[key] = {
        component_sku: sku || key,
        component_name: name || sku || key,
        unit,
        total_demanded: 0,
        total_available: available,
        total_shortage: 0,
        affected: [],
      };
    }
    const row = byComponent[key];
    if (!row.unit && unit) row.unit = unit;
    row.total_demanded += required;
    row.total_shortage += shortage;
    // Track the lowest available we've observed (snapshot from the ledger)
    row.total_available = Math.min(row.total_available, available);
    const existing = row.affected.find((a) => a.sku === parentSku);
    if (existing) {
      existing.required += required;
      existing.shortage += shortage;
    } else {
      row.affected.push({ sku: parentSku, required, shortage });
    }
  };

  // Seed from per-SKU shortages (covers deep BOM shortages)
  for (const result of results) {
    for (const s of result.shortages) {
      const subDetails = s.sub_component_details || [];
      // If this shortage is a sub-assembly (formula) with raw-material breakdown,
      // expand into its raw materials instead of showing the formula itself.
      if (subDetails.length > 0) {
        const parentRequired = s.required_quantity ?? 0;
        for (const sub of subDetails) {
          const qtyPerUnit = sub.qty_per_unit ?? 0;
          const subRequired = qtyPerUnit * parentRequired;
          const subAvailable = sub.available_quantity ?? 0;
          const subShortage = Math.max(0, subRequired - subAvailable);
          if (subShortage <= 0 && subRequired <= 0) continue;
          addToComponent(
            sub.item_sku || sub.item_id || sub.item_name || "",
            sub.item_sku || sub.item_id || "",
            sub.item_name || sub.item_sku || "",
            sub.unit || "",
            subRequired,
            subAvailable,
            subShortage,
            result.item_sku
          );
        }
      } else {
        const key = (s.item_sku || s.item_name || "").trim();
        if (!key) continue;
        addToComponent(
          key,
          s.item_sku || key,
          s.item_name || key,
          s.unit || "",
          s.required_quantity ?? 0,
          s.available_quantity ?? 0,
          s.shortage_quantity ?? 0,
          result.item_sku
        );
      }
    }
  }

  // Overlay backend-reported contentions (more authoritative for direct-component shortages)
  for (const c of contentions) {
    const key = c.component_sku;
    if (!byComponent[key]) {
      byComponent[key] = {
        component_sku: c.component_sku,
        component_name: c.component_name,
        unit: c.unit || "",
        total_demanded: c.total_demanded,
        total_available: c.total_available,
        total_shortage: c.shortage,
        affected: c.demanded_by.map((d) => ({
          sku: d.sku,
          required: d.quantity_needed,
          shortage: 0,
        })),
      };
    } else {
      const row = byComponent[key];
      if (!row.unit && c.unit) row.unit = c.unit;
      row.total_demanded = Math.max(row.total_demanded, c.total_demanded);
      row.total_available = Math.max(row.total_available, c.total_available);
      row.total_shortage = Math.max(row.total_shortage, c.shortage);
      // Merge affected SKUs from contention if missing
      for (const d of c.demanded_by) {
        if (!row.affected.some((a) => a.sku === d.sku)) {
          row.affected.push({ sku: d.sku, required: d.quantity_needed, shortage: 0 });
        }
      }
    }
  }

  return Object.values(byComponent)
    .filter((row) => row.total_shortage > 0)
    .sort((a, b) => b.total_shortage - a.total_shortage);
};

const AggregatedShortages: React.FC<{
  results: BatchItemResult[];
  contentions: MaterialContention[];
}> = ({ results, contentions }) => {
  const rows = aggregate(results, contentions);

  if (rows.length === 0) {
    return (
      <div className="bg-white rounded-xl shadow border border-gray-200 p-5 mb-6">
        <h3 className="text-base font-semibold text-gray-900 mb-1">
          Material Shortages
        </h3>
        <p className="text-sm text-gray-500">
          No raw-material shortages across the requested SKUs.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl shadow border border-gray-200 overflow-hidden mb-6">
      <div className="px-5 py-4 border-b border-gray-100">
        <h3 className="text-base font-semibold text-gray-900">
          Material Shortages
        </h3>
        <p className="text-xs text-gray-500 mt-0.5">
          Raw materials short across all requested SKUs, with the SKUs affected by each shortfall.
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs text-gray-500 uppercase tracking-wide">
            <tr>
              <th className="text-left font-medium px-5 py-2.5">Component</th>
              <th className="text-right font-medium px-3 py-2.5">Demanded</th>
              <th className="text-right font-medium px-3 py-2.5">Available</th>
              <th className="text-right font-medium px-3 py-2.5">Short</th>
              <th className="text-left font-medium px-5 py-2.5">Affected SKUs</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.map((r) => (
              <tr key={r.component_sku} className="hover:bg-amber-50/40 transition">
                <td className="px-5 py-3 align-top">
                  <div className="font-medium text-gray-900">{r.component_sku}</div>
                  {!isUselessName(r.component_name, r.component_sku) && (
                    <div className="text-xs text-gray-500">{r.component_name}</div>
                  )}
                </td>
                <td className="px-3 py-3 text-right text-gray-900 align-top">
                  {formatNum(r.total_demanded)} {r.unit}
                </td>
                <td className="px-3 py-3 text-right text-gray-900 align-top">
                  {formatNum(r.total_available)} {r.unit}
                </td>
                <td className="px-3 py-3 text-right text-red-600 font-semibold align-top">
                  {formatNum(r.total_shortage)} {r.unit}
                </td>
                <td className="px-5 py-3 align-top">
                  <div className="flex flex-wrap gap-1.5">
                    {r.affected.map((a) => (
                      <span
                        key={a.sku}
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs border ${
                          a.shortage > 0
                            ? "bg-red-50 border-red-200 text-red-700"
                            : "bg-gray-50 border-gray-200 text-gray-700"
                        }`}
                        title={
                          a.shortage > 0
                            ? `needs ${formatNum(a.required)}, short ${formatNum(a.shortage)}`
                            : `needs ${formatNum(a.required)}`
                        }
                      >
                        <span className="font-medium">{a.sku}</span>
                      </span>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default AggregatedShortages;
