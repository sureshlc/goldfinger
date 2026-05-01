"use client";

import React, { useMemo, useRef, useState } from "react";
import { CheckCircle2, AlertTriangle, Download, Mail, X } from "lucide-react";
import { fetchWithAuth, API_BASE_URL } from "@/app/services/auth";
import { emitToast } from "@/app/components/toast/ToastContext";

interface SubComponentDetail {
  item_id?: string;
  item_sku?: string;
  item_name?: string;
  available_quantity?: number;
  initial_quantity?: number;
  qty_per_unit?: number;
  unit?: string;
}

interface ShortageEntry {
  item_sku?: string;
  item_name?: string;
  shortage_quantity?: number;
  required_quantity?: number;
  available_quantity?: number;
  initial_quantity?: number;
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

interface MaterialSummaryRow {
  component_sku: string;
  component_name: string;
  unit: string;
  total_demanded: number;
  total_available: number;
  shortage: number;
  demanded_by: Array<{ sku: string; quantity_needed: number }>;
}

interface BatchInputItem {
  sku: string;
  desired_quantity: number;
}

const formatNum = (value: number): string => {
  if (!Number.isFinite(value)) return "—";
  if (Number.isInteger(value)) return value.toString();
  return parseFloat(value.toFixed(2)).toString();
};

const csvEscape = (cell: string): string => {
  if (cell == null) return "";
  if (/[",\n]/.test(cell)) return `"${cell.replace(/"/g, '""')}"`;
  return cell;
};

const isUselessName = (name?: string, sku?: string): boolean => {
  if (!name) return true;
  const trimmed = name.trim();
  if (!trimmed) return true;
  if (sku && trimmed.toUpperCase() === sku.trim().toUpperCase()) return true;
  if (/^\d+$/.test(trimmed)) return true;
  return false;
};

// Fallback aggregator (used when backend doesn't provide material_summary).
const aggregateFromPerSkuShortages = (
  results: BatchItemResult[],
  contentions: MaterialContention[]
): MaterialSummaryRow[] => {
  const byComponent: Record<string, MaterialSummaryRow> = {};

  const add = (
    keyRaw: string,
    sku: string,
    name: string,
    unit: string,
    required: number,
    initial: number,
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
        total_available: initial,
        shortage: 0,
        demanded_by: [],
      };
    }
    const row = byComponent[key];
    if (!row.unit && unit) row.unit = unit;
    if (initial > row.total_available) row.total_available = initial;
    row.total_demanded += required;
    row.shortage = Math.max(0, row.total_demanded - row.total_available);
    const existing = row.demanded_by.find((d) => d.sku === parentSku);
    if (existing) existing.quantity_needed += required;
    else row.demanded_by.push({ sku: parentSku, quantity_needed: required });
  };

  for (const result of results) {
    for (const s of result.shortages) {
      const subs = s.sub_component_details || [];
      if (subs.length > 0) {
        const parentReq = s.required_quantity ?? 0;
        for (const sub of subs) {
          const subReq = (sub.qty_per_unit ?? 0) * parentReq;
          if (subReq <= 0) continue;
          add(
            sub.item_sku || sub.item_id || "",
            sub.item_sku || sub.item_id || "",
            sub.item_name || "",
            sub.unit || "",
            subReq,
            sub.initial_quantity ?? sub.available_quantity ?? 0,
            result.item_sku
          );
        }
      } else {
        add(
          (s.item_sku || s.item_name || "").trim(),
          s.item_sku || "",
          s.item_name || "",
          s.unit || "",
          s.required_quantity ?? 0,
          s.initial_quantity ?? s.available_quantity ?? 0,
          result.item_sku
        );
      }
    }
  }

  for (const c of contentions) {
    const key = c.component_sku;
    if (!byComponent[key]) {
      byComponent[key] = {
        component_sku: c.component_sku,
        component_name: c.component_name,
        unit: c.unit || "",
        total_demanded: c.total_demanded,
        total_available: c.total_available,
        shortage: c.shortage,
        demanded_by: c.demanded_by.map((d) => ({ ...d })),
      };
    } else {
      const row = byComponent[key];
      if (!row.unit && c.unit) row.unit = c.unit;
      if (c.total_available > row.total_available) row.total_available = c.total_available;
      row.shortage = Math.max(0, row.total_demanded - row.total_available);
      for (const d of c.demanded_by) {
        if (!row.demanded_by.some((x) => x.sku === d.sku)) {
          row.demanded_by.push({ sku: d.sku, quantity_needed: d.quantity_needed });
        }
      }
    }
  }

  return Object.values(byComponent).sort((a, b) => b.shortage - a.shortage);
};

const buildCsv = (rows: MaterialSummaryRow[]): string => {
  const header = [
    "Component SKU",
    "Component Name",
    "Unit",
    "Total Demanded",
    "Total Available",
    "Shortage",
    "Affected SKUs",
  ].join(",");
  const lines = rows.map((r) =>
    [
      csvEscape(r.component_sku),
      csvEscape(r.component_name),
      csvEscape(r.unit || ""),
      csvEscape(formatNum(r.total_demanded)),
      csvEscape(formatNum(r.total_available)),
      csvEscape(formatNum(r.shortage)),
      csvEscape(r.demanded_by.map((d) => d.sku).join("; ")),
    ].join(",")
  );
  return [header, ...lines].join("\n");
};

const downloadCsv = (rows: MaterialSummaryRow[]) => {
  const csv = buildCsv(rows);
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const date = new Date().toISOString().slice(0, 10);
  a.href = url;
  a.download = `materials-${date}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};

interface Props {
  results: BatchItemResult[];
  contentions: MaterialContention[];
  materialSummary?: MaterialSummaryRow[];
  batchItems: BatchInputItem[];
}

const MaterialSummary: React.FC<Props> = ({
  results,
  contentions,
  materialSummary,
  batchItems,
}) => {
  const [showOnlyShortages, setShowOnlyShortages] = useState(false);
  const [emailOpen, setEmailOpen] = useState(false);
  const [recipients, setRecipients] = useState("");
  const [note, setNote] = useState("");
  const [sending, setSending] = useState(false);
  const recipientsRef = useRef<HTMLInputElement>(null);

  const rowsAll = useMemo<MaterialSummaryRow[]>(() => {
    if (materialSummary && materialSummary.length > 0) {
      // Backend already sorts shortages first; trust it.
      return materialSummary;
    }
    return aggregateFromPerSkuShortages(results, contentions);
  }, [materialSummary, results, contentions]);

  const rows = showOnlyShortages ? rowsAll.filter((r) => r.shortage > 0) : rowsAll;
  const shortageCount = rowsAll.filter((r) => r.shortage > 0).length;

  const handleEmailSend = async () => {
    const recipientList = recipients
      .split(/[,\s;]+/)
      .map((r) => r.trim())
      .filter(Boolean);
    if (recipientList.length === 0) {
      emitToast("error", "Please enter at least one recipient.");
      return;
    }
    setSending(true);
    try {
      const res = await fetchWithAuth(
        `${API_BASE_URL}/production/batch-feasibility/email`,
        {
          method: "POST",
          body: JSON.stringify({
            items: batchItems,
            recipients: recipientList,
            note: note.trim() || null,
          }),
        }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        emitToast("error", body.detail || `Failed to send (${res.status})`);
        return;
      }
      const data = await res.json();
      emitToast(
        "success",
        `Report sent to ${data.recipients_count} recipient${data.recipients_count === 1 ? "" : "s"}.`
      );
      setEmailOpen(false);
      setRecipients("");
      setNote("");
    } catch {
      emitToast("error", "Failed to send report email.");
    } finally {
      setSending(false);
    }
  };

  if (rowsAll.length === 0) {
    return (
      <div className="bg-white rounded-xl shadow border border-gray-200 p-5 mb-6">
        <h3 className="text-base font-semibold text-gray-900 mb-1">Materials Summary</h3>
        <p className="text-sm text-gray-500">No materials demanded by this batch.</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl shadow border border-gray-200 overflow-hidden mb-6">
      <div className="px-5 py-4 border-b border-gray-100 flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="text-base font-semibold text-gray-900">Materials Summary</h3>
          <p className="text-xs text-gray-500 mt-0.5">
            Every raw material the batch consumes — Demanded vs Available against the shared inventory pool.
            {shortageCount > 0 && (
              <>
                {" "}
                <span className="text-red-600 font-medium">
                  {shortageCount} short
                </span>
                .
              </>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0 ml-auto">
          <label className="inline-flex items-center gap-1.5 text-xs text-gray-600 cursor-pointer">
            <input
              type="checkbox"
              checked={showOnlyShortages}
              onChange={(e) => setShowOnlyShortages(e.target.checked)}
              className="rounded border-gray-300"
            />
            Only shortages
          </label>
          <button
            type="button"
            onClick={() => downloadCsv(rowsAll)}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-gray-700 bg-gray-50 border border-gray-200 hover:border-gray-300 hover:bg-gray-100 rounded-md px-2.5 py-1.5 transition"
          >
            <Download className="w-3.5 h-3.5" /> Export CSV
          </button>
          <button
            type="button"
            onClick={() => setEmailOpen((v) => !v)}
            className={`inline-flex items-center gap-1.5 text-xs font-medium rounded-md px-2.5 py-1.5 transition border ${
              emailOpen
                ? "bg-blue-50 border-blue-200 text-blue-700"
                : "bg-gray-50 border-gray-200 text-gray-700 hover:border-gray-300 hover:bg-gray-100"
            }`}
          >
            <Mail className="w-3.5 h-3.5" /> {emailOpen ? "Cancel" : "Email"}
          </button>
        </div>
      </div>

      {emailOpen && (
        <div className="bg-blue-50/40 border-b border-blue-100 px-5 py-3 flex flex-col gap-2">
          <div className="flex items-start gap-2">
            <div className="flex-1">
              <label className="text-xs font-medium text-gray-700 block mb-1">Recipients</label>
              <div className="relative">
                <input
                  ref={recipientsRef}
                  type="text"
                  value={recipients}
                  onChange={(e) => setRecipients(e.target.value)}
                  placeholder="email1@example.com, email2@example.com"
                  className="w-full border border-gray-300 rounded-md px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-400 pr-8"
                />
                {recipients && (
                  <button
                    type="button"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => {
                      setRecipients("");
                      recipientsRef.current?.focus();
                    }}
                    className="absolute right-1.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition p-0.5"
                    aria-label="Clear recipients"
                    title="Clear recipients"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>
          </div>
          <div>
            <label className="text-xs font-medium text-gray-700 block mb-1">
              Optional note
            </label>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              placeholder="Anything the production team should know about this batch?"
              className="w-full border border-gray-300 rounded-md px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-400 resize-y"
            />
          </div>
          <div className="flex justify-end">
            <button
              type="button"
              onClick={handleEmailSend}
              disabled={sending || !recipients.trim()}
              className={`px-4 py-1.5 rounded-md text-sm font-semibold transition ${
                sending || !recipients.trim()
                  ? "bg-gray-200 text-gray-400 cursor-not-allowed"
                  : "bg-blue-600 text-white hover:bg-blue-700 shadow-sm"
              }`}
            >
              {sending ? "Sending…" : "Send report"}
            </button>
          </div>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs text-gray-500 uppercase tracking-wide">
            <tr>
              <th className="text-left font-medium px-5 py-2.5">Component</th>
              <th className="text-right font-medium px-3 py-2.5">Demanded</th>
              <th className="text-right font-medium px-3 py-2.5">Available</th>
              <th className="text-right font-medium px-3 py-2.5">Short</th>
              <th className="text-center font-medium px-3 py-2.5">Status</th>
              <th className="text-left font-medium px-5 py-2.5">Affected SKUs</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.map((r) => {
              const isShort = r.shortage > 0;
              return (
                <tr
                  key={r.component_sku}
                  className={`${isShort ? "hover:bg-amber-50/40" : "hover:bg-gray-50"} transition`}
                >
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
                  <td
                    className={`px-3 py-3 text-right align-top ${
                      isShort ? "text-red-600 font-semibold" : "text-gray-400"
                    }`}
                  >
                    {isShort ? `${formatNum(r.shortage)} ${r.unit}` : "—"}
                  </td>
                  <td className="px-3 py-3 text-center align-top">
                    {isShort ? (
                      <span className="inline-flex items-center gap-1 text-xs font-semibold text-red-700 bg-red-50 border border-red-200 rounded-full px-2 py-0.5">
                        <AlertTriangle className="w-3 h-3" /> Short
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs font-semibold text-green-700 bg-green-50 border border-green-200 rounded-full px-2 py-0.5">
                        <CheckCircle2 className="w-3 h-3" /> OK
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-3 align-top">
                    <div className="flex flex-wrap gap-1.5">
                      {r.demanded_by.map((d) => (
                        <span
                          key={d.sku}
                          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs border ${
                            isShort
                              ? "bg-red-50 border-red-200 text-red-700"
                              : "bg-gray-50 border-gray-200 text-gray-700"
                          }`}
                          title={`needs ${formatNum(d.quantity_needed)}`}
                        >
                          <span className="font-medium">{d.sku}</span>
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default MaterialSummary;
