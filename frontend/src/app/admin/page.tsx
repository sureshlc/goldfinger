"use client";

import React, { useState, useEffect, useCallback, useRef, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Eye, EyeOff, Upload, Download, X, Check, X as XIcon } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { fetchWithAuth, API_BASE_URL } from "../services/auth";

function usePasswordStrength(password: string) {
  return useMemo(() => {
    if (!password) return { rules: [], allPassed: true };
    const rules = [
      { label: "At least 8 characters", passed: password.length >= 8 },
      { label: "One uppercase letter", passed: /[A-Z]/.test(password) },
      { label: "One digit", passed: /\d/.test(password) },
      { label: "One special character", passed: /[^A-Za-z0-9]/.test(password) },
    ];
    return { rules, allPassed: rules.every((r) => r.passed) };
  }, [password]);
}

type Tab = "audit-logs" | "items" | "users";

interface AuditLog {
  timestamp: string;
  user_id: number;
  username: string | null;
  action: string;
  details: string | null;
}

interface AdminItem {
  id: number;
  sku: string;
  name: string | null;
}

interface AdminUser {
  id: number;
  email: string;
  username: string;
  role: string;
  disabled: boolean;
  created_at: string | null;
  last_login: string | null;
}

export default function AdminPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<Tab>("audit-logs");

  useEffect(() => {
    if (user && user.role !== "admin") {
      router.push("/");
    }
  }, [user, router]);

  if (!user || user.role !== "admin") {
    return (
      <div className="min-h-[calc(100vh-5rem)] flex flex-col items-center justify-center gap-4">
        <p className="text-gray-500">Access denied. Admin only.</p>
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-700 transition"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Home
        </Link>
      </div>
    );
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: "audit-logs", label: "Audit Logs" },
    { key: "items", label: "Manage Items" },
    { key: "users", label: "Manage Users" },
  ];

  return (
    <div className="min-h-[calc(100vh-5rem)] bg-gradient-to-b from-blue-50 to-white px-4 pt-8">
      <div className="max-w-6xl mx-auto">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-700 mb-4 transition"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Home
        </Link>
        <h1 className="text-2xl font-bold text-gray-900 mb-6">Admin Settings</h1>

        {/* Tab bar */}
        <div className="flex border-b border-gray-200 mb-6">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition ${
                activeTab === tab.key
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
              }`}
              type="button"
            >
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === "audit-logs" && <AuditLogsTab />}
        {activeTab === "items" && <ItemsTab />}
        {activeTab === "users" && <UsersTab />}
      </div>
    </div>
  );
}

// ============================================================================
// AUDIT LOGS TAB
// ============================================================================
function AuditLogsTab() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const perPage = 25;

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchWithAuth(
        `${API_BASE_URL}/admin/audit-logs?page=${page}&per_page=${perPage}`
      );
      const data = await res.json();
      setLogs(data.logs || []);
      setTotal(data.total || 0);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  const totalPages = Math.ceil(total / perPage);

  const actionLabels: Record<string, { label: string; color: string }> = {
    login: { label: "Login", color: "bg-blue-100 text-blue-700" },
    logout: { label: "Logout", color: "bg-gray-100 text-gray-700" },
    password_changed: { label: "Password Changed", color: "bg-yellow-100 text-yellow-700" },
    admin_password_reset: { label: "Password Reset", color: "bg-orange-100 text-orange-700" },
    profile_updated: { label: "Profile Updated", color: "bg-blue-100 text-blue-700" },
    user_created: { label: "User Created", color: "bg-green-100 text-green-700" },
    user_updated: { label: "User Updated", color: "bg-blue-100 text-blue-700" },
    user_deleted: { label: "User Deleted", color: "bg-red-100 text-red-700" },
    item_created: { label: "Item Created", color: "bg-green-100 text-green-700" },
    item_updated: { label: "Item Updated", color: "bg-blue-100 text-blue-700" },
    item_deleted: { label: "Item Deleted", color: "bg-red-100 text-red-700" },
    items_imported: { label: "Bulk Import", color: "bg-purple-100 text-purple-700" },
    production_check: { label: "Production Check", color: "bg-indigo-100 text-indigo-700" },
  };

  return (
    <div className="bg-white rounded-xl shadow border border-gray-200 overflow-hidden">
      {loading ? (
        <div className="p-8 text-center text-gray-500">Loading...</div>
      ) : logs.length === 0 ? (
        <div className="p-8 text-center text-gray-500">No logs yet</div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-100">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Timestamp</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">User</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Action</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {logs.map((log, i) => {
                  const info = actionLabels[log.action] || { label: log.action, color: "bg-gray-100 text-gray-700" };
                  return (
                    <tr key={i} className="hover:bg-blue-50/50 transition">
                      <td className="px-4 py-2.5 text-gray-600 text-xs whitespace-nowrap">
                        {log.timestamp ? new Date(log.timestamp).toLocaleString() : "-"}
                      </td>
                      <td className="px-4 py-2.5 text-gray-900 font-medium text-xs whitespace-nowrap">
                        {log.username || (log.user_id ? `User #${log.user_id}` : "-")}
                      </td>
                      <td className="px-4 py-2.5">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${info.color}`}>
                          {info.label}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-gray-700 text-xs">{log.details || "-"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100 bg-gray-50">
            <span className="text-sm text-gray-500">
              Page {page} of {totalPages} ({total} total)
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="px-3 py-1 text-sm border border-gray-200 rounded-lg hover:bg-gray-100 disabled:opacity-50 transition"
                type="button"
              >
                Prev
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="px-3 py-1 text-sm border border-gray-200 rounded-lg hover:bg-gray-100 disabled:opacity-50 transition"
                type="button"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ============================================================================
// ITEMS TAB
// ============================================================================
interface ImportError {
  row: number;
  data: { id?: string; sku?: string; name?: string };
  error: string;
}

interface ImportResult {
  success_count: number;
  total: number;
  errors: ImportError[];
}

function ItemsTab() {
  const [items, setItems] = useState<AdminItem[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editItem, setEditItem] = useState<AdminItem | null>(null);
  const [formId, setFormId] = useState("");
  const [formSku, setFormSku] = useState("");
  const [formName, setFormName] = useState("");
  const [showImport, setShowImport] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const perPage = 20;

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
      if (search) params.set("search", search);
      const res = await fetchWithAuth(`${API_BASE_URL}/admin/items?${params}`);
      const data = await res.json();
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [page, search]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (editItem) {
        await fetchWithAuth(`${API_BASE_URL}/admin/items/${editItem.id}`, {
          method: "PUT",
          body: JSON.stringify({ sku: formSku, name: formName }),
        });
      } else {
        await fetchWithAuth(`${API_BASE_URL}/admin/items`, {
          method: "POST",
          body: JSON.stringify({ id: parseInt(formId), sku: formSku, name: formName }),
        });
      }
      setShowForm(false);
      setEditItem(null);
      setFormId("");
      setFormSku("");
      setFormName("");
      fetchItems();
    } catch {
      /* ignore */
    }
  };

  const handleEdit = (item: AdminItem) => {
    setEditItem(item);
    setFormId(String(item.id));
    setFormSku(item.sku);
    setFormName(item.name || "");
    setShowForm(true);
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this item?")) return;
    try {
      await fetchWithAuth(`${API_BASE_URL}/admin/items/${id}`, { method: "DELETE" });
      fetchItems();
    } catch {
      /* ignore */
    }
  };

  const downloadTemplate = () => {
    const csv = "id,sku,name\n1001,ITEM-001,Example Item Name\n";
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "items_import_template.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleFileImport = async (file: File) => {
    setImporting(true);
    setImportResult(null);

    try {
      const text = await file.text();
      const lines = text.split(/\r?\n/).filter((l) => l.trim());
      if (lines.length < 2) {
        setImportResult({ success_count: 0, total: 0, errors: [{ row: 0, data: {}, error: "File is empty or has no data rows" }] });
        setImporting(false);
        return;
      }

      // Parse header to find column indices
      const header = lines[0].split(",").map((h) => h.trim().toLowerCase());
      const idIdx = header.indexOf("id");
      const skuIdx = header.indexOf("sku");
      const nameIdx = header.indexOf("name");

      if (idIdx === -1 || skuIdx === -1) {
        setImportResult({ success_count: 0, total: 0, errors: [{ row: 0, data: {}, error: "CSV must have 'id' and 'sku' columns in the header" }] });
        setImporting(false);
        return;
      }

      const dataRows = lines.slice(1);
      const validItems: { id: number; sku: string; name: string | null }[] = [];
      const errors: ImportError[] = [];

      dataRows.forEach((line, idx) => {
        const cols = line.split(",").map((c) => c.trim());
        const rowNum = idx + 2; // 1-indexed + header
        const rawId = cols[idIdx] || "";
        const rawSku = cols[skuIdx] || "";
        const rawName = nameIdx !== -1 ? cols[nameIdx] || "" : "";

        const parsedId = parseInt(rawId);
        if (!rawId || isNaN(parsedId)) {
          errors.push({ row: rowNum, data: { id: rawId, sku: rawSku, name: rawName }, error: "Invalid or missing ID (must be a number)" });
          return;
        }
        if (!rawSku) {
          errors.push({ row: rowNum, data: { id: rawId, sku: rawSku, name: rawName }, error: "SKU is required" });
          return;
        }
        validItems.push({ id: parsedId, sku: rawSku, name: rawName || null });
      });

      // Send valid items to backend
      let successCount = 0;
      if (validItems.length > 0) {
        try {
          const res = await fetchWithAuth(`${API_BASE_URL}/admin/items/bulk-import`, {
            method: "POST",
            body: JSON.stringify({ items: validItems }),
          });
          if (res.ok) {
            const data = await res.json();
            successCount = data.success_count || validItems.length;
            if (data.errors) {
              for (const err of data.errors) {
                errors.push(err);
              }
            }
          } else {
            const errData = await res.json().catch(() => ({ detail: "Import failed" }));
            // All valid items failed on server side
            for (const item of validItems) {
              errors.push({ row: 0, data: { id: String(item.id), sku: item.sku, name: item.name || "" }, error: errData.detail || "Server error" });
            }
          }
        } catch {
          for (const item of validItems) {
            errors.push({ row: 0, data: { id: String(item.id), sku: item.sku, name: item.name || "" }, error: "Network error" });
          }
        }
      }

      setImportResult({ success_count: successCount, total: dataRows.length, errors });
      if (successCount > 0) fetchItems();
    } catch {
      setImportResult({ success_count: 0, total: 0, errors: [{ row: 0, data: {}, error: "Failed to read file" }] });
    } finally {
      setImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const totalPages = Math.ceil(total / perPage);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <input
          type="text"
          placeholder="Search items..."
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm w-64 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <div className="flex gap-2">
          <button
            onClick={() => { setShowImport(true); setImportResult(null); }}
            className="inline-flex items-center gap-1.5 bg-gray-100 text-gray-700 px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-200 border border-gray-300"
            type="button"
          >
            <Upload className="w-4 h-4" />
            Bulk Import
          </button>
          <button
            onClick={() => {
              setShowForm(true);
              setEditItem(null);
              setFormId("");
              setFormSku("");
              setFormName("");
            }}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700"
            type="button"
          >
            Add Item
          </button>
        </div>
      </div>

      {/* Bulk Import Panel */}
      {showImport && (
        <div className="bg-white p-5 rounded-lg shadow border mb-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-800">Bulk Import Items</h3>
            <button type="button" onClick={() => { setShowImport(false); setImportResult(null); }} className="text-gray-400 hover:text-gray-600">
              <X className="w-4 h-4" />
            </button>
          </div>
          <p className="text-xs text-gray-500 mb-3">
            Upload a CSV file with <strong>id</strong>, <strong>sku</strong>, and <strong>name</strong> columns. Download the template below to get started.
          </p>
          <div className="flex items-center gap-3 mb-4">
            <button
              type="button"
              onClick={downloadTemplate}
              className="inline-flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-700 font-medium"
            >
              <Download className="w-4 h-4" />
              Download Template
            </button>
          </div>
          <div className="flex items-center gap-3">
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFileImport(file);
              }}
              className="text-sm text-gray-600 file:mr-3 file:py-1.5 file:px-4 file:rounded-lg file:border file:border-gray-300 file:text-sm file:font-medium file:bg-gray-50 file:text-gray-700 hover:file:bg-gray-100"
            />
            {importing && <span className="text-sm text-gray-500">Importing...</span>}
          </div>

          {/* Import Results */}
          {importResult && (
            <div className="mt-4">
              <div className={`p-3 rounded-lg text-sm font-medium ${
                importResult.errors.length === 0
                  ? "bg-green-50 text-green-800 border border-green-200"
                  : importResult.success_count > 0
                  ? "bg-yellow-50 text-yellow-800 border border-yellow-200"
                  : "bg-red-50 text-red-800 border border-red-200"
              }`}>
                {importResult.success_count} of {importResult.total} rows imported successfully.
                {importResult.errors.length > 0 && ` ${importResult.errors.length} row(s) had errors.`}
              </div>

              {importResult.errors.length > 0 && (
                <div className="mt-3 max-h-60 overflow-y-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-red-50 border-b border-red-100 sticky top-0">
                      <tr>
                        <th className="px-3 py-2 text-left font-semibold text-red-700">Row</th>
                        <th className="px-3 py-2 text-left font-semibold text-red-700">ID</th>
                        <th className="px-3 py-2 text-left font-semibold text-red-700">SKU</th>
                        <th className="px-3 py-2 text-left font-semibold text-red-700">Name</th>
                        <th className="px-3 py-2 text-left font-semibold text-red-700">Error</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-red-50">
                      {importResult.errors.map((err, i) => (
                        <tr key={i} className="bg-white">
                          <td className="px-3 py-1.5 text-gray-600">{err.row || "-"}</td>
                          <td className="px-3 py-1.5 text-gray-700">{err.data?.id || "-"}</td>
                          <td className="px-3 py-1.5 text-gray-700">{err.data?.sku || "-"}</td>
                          <td className="px-3 py-1.5 text-gray-700">{err.data?.name || "-"}</td>
                          <td className="px-3 py-1.5 text-red-700 font-medium">{err.error}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {showForm && (
        <form onSubmit={handleSubmit} className="bg-white p-4 rounded-lg shadow border mb-4 flex gap-3 items-end">
          {!editItem && (
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">ID</label>
              <input
                type="number"
                value={formId}
                onChange={(e) => setFormId(e.target.value)}
                required
                className="border rounded px-2 py-1.5 text-sm w-24"
              />
            </div>
          )}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">SKU</label>
            <input
              type="text"
              value={formSku}
              onChange={(e) => setFormSku(e.target.value)}
              required
              className="border rounded px-2 py-1.5 text-sm w-32"
            />
          </div>
          <div className="flex-1">
            <label className="block text-xs font-medium text-gray-600 mb-1">Name</label>
            <input
              type="text"
              value={formName}
              onChange={(e) => setFormName(e.target.value)}
              className="border rounded px-2 py-1.5 text-sm w-full"
            />
          </div>
          <button type="submit" className="bg-blue-600 text-white px-4 py-1.5 rounded text-sm font-medium hover:bg-blue-700">
            {editItem ? "Update" : "Create"}
          </button>
          <button
            type="button"
            onClick={() => {
              setShowForm(false);
              setEditItem(null);
            }}
            className="text-gray-500 px-3 py-1.5 rounded text-sm hover:bg-gray-100"
          >
            Cancel
          </button>
        </form>
      )}

      <div className="bg-white rounded-xl shadow border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-500">Loading...</div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-100">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">ID</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">SKU</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Name</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {items.map((item) => (
                    <tr key={item.id} className="hover:bg-blue-50/50 transition">
                      <td className="px-4 py-2.5 text-gray-600">{item.id}</td>
                      <td className="px-4 py-2.5 text-gray-900 font-semibold">{item.sku}</td>
                      <td className="px-4 py-2.5 text-gray-700">{item.name || "-"}</td>
                      <td className="px-4 py-2.5 text-right">
                        <button onClick={() => handleEdit(item)} className="text-blue-600 hover:text-blue-700 text-sm font-medium mr-3" type="button">
                          Edit
                        </button>
                        <button onClick={() => handleDelete(item.id)} className="text-red-600 hover:text-red-700 text-sm font-medium" type="button">
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100 bg-gray-50">
              <span className="text-sm text-gray-500">
                Page {page} of {totalPages} ({total} total)
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="px-3 py-1 text-sm border border-gray-200 rounded-lg hover:bg-gray-100 disabled:opacity-50 transition"
                  type="button"
                >
                  Prev
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="px-3 py-1 text-sm border border-gray-200 rounded-lg hover:bg-gray-100 disabled:opacity-50 transition"
                  type="button"
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// USERS TAB
// ============================================================================
function UsersTab() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editUser, setEditUser] = useState<AdminUser | null>(null);
  const [formEmail, setFormEmail] = useState("");
  const [formUsername, setFormUsername] = useState("");
  const [formPassword, setFormPassword] = useState("");
  const [formRole, setFormRole] = useState("user");
  const [formError, setFormError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const pwStrength = usePasswordStrength(formPassword);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchWithAuth(`${API_BASE_URL}/admin/users`);
      const data = await res.json();
      setUsers(data);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    try {
      let res;
      if (editUser) {
        const body: Record<string, unknown> = { username: formUsername, role: formRole };
        if (formPassword) body.password = formPassword;
        res = await fetchWithAuth(`${API_BASE_URL}/admin/users/${editUser.id}`, {
          method: "PUT",
          body: JSON.stringify(body),
        });
      } else {
        res = await fetchWithAuth(`${API_BASE_URL}/admin/users`, {
          method: "POST",
          body: JSON.stringify({
            email: formEmail,
            username: formUsername,
            password: formPassword,
            role: formRole,
          }),
        });
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Operation failed" }));
        setFormError(err.detail || "Operation failed");
        return;
      }
      setShowForm(false);
      setEditUser(null);
      resetForm();
      fetchUsers();
    } catch {
      setFormError("Network error. Please try again.");
    }
  };

  const resetForm = () => {
    setFormEmail("");
    setFormUsername("");
    setFormPassword("");
    setFormRole("user");
    setFormError(null);
    setShowPassword(false);
  };

  const handleEdit = (u: AdminUser) => {
    setEditUser(u);
    setFormEmail(u.email);
    setFormUsername(u.username);
    setFormPassword("");
    setFormRole(u.role);
    setFormError(null);
    setShowPassword(false);
    setShowForm(true);
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this user?")) return;
    try {
      const res = await fetchWithAuth(`${API_BASE_URL}/admin/users/${id}`, { method: "DELETE" });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Delete failed" }));
        alert(err.detail || "Delete failed");
        return;
      }
      fetchUsers();
    } catch {
      /* ignore */
    }
  };

  const handleToggleDisabled = async (u: AdminUser) => {
    try {
      await fetchWithAuth(`${API_BASE_URL}/admin/users/${u.id}`, {
        method: "PUT",
        body: JSON.stringify({ disabled: !u.disabled }),
      });
      fetchUsers();
    } catch {
      /* ignore */
    }
  };

  return (
    <div>
      <div className="flex justify-end mb-4">
        <button
          onClick={() => {
            setShowForm(true);
            setEditUser(null);
            resetForm();
          }}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700"
          type="button"
        >
          Add User
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className="bg-white p-4 rounded-lg shadow border mb-4 grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Email</label>
            <input
              type="email"
              value={formEmail}
              onChange={(e) => setFormEmail(e.target.value)}
              required
              disabled={!!editUser}
              className="border rounded px-2 py-1.5 text-sm w-full disabled:bg-gray-50"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Username</label>
            <input
              type="text"
              value={formUsername}
              onChange={(e) => setFormUsername(e.target.value)}
              required
              className="border rounded px-2 py-1.5 text-sm w-full"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Password {editUser && "(leave blank to keep)"}
            </label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                value={formPassword}
                onChange={(e) => setFormPassword(e.target.value)}
                required={!editUser}
                className={`border rounded px-2 py-1.5 pr-8 text-sm w-full ${
                  formPassword && !pwStrength.allPassed ? "border-red-300" : ""
                }`}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                tabIndex={-1}
              >
                {showPassword ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
              </button>
            </div>
            {formPassword && (
              <ul className="mt-1 space-y-0.5">
                {pwStrength.rules.map((rule) => (
                  <li key={rule.label} className={`flex items-center gap-1 text-xs ${rule.passed ? "text-green-600" : "text-red-500"}`}>
                    {rule.passed ? <Check className="w-3 h-3" /> : <XIcon className="w-3 h-3" />}
                    {rule.label}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Role</label>
            <select
              value={formRole}
              onChange={(e) => setFormRole(e.target.value)}
              className="border rounded px-2 py-1.5 text-sm w-full"
            >
              <option value="user">User</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          {formError && (
            <div className="col-span-2 p-2.5 rounded-lg text-sm bg-red-50 text-red-800 border border-red-200">
              {formError}
            </div>
          )}
          <div className="col-span-2 flex gap-2">
            <button type="submit" className="bg-blue-600 text-white px-4 py-1.5 rounded text-sm font-medium hover:bg-blue-700">
              {editUser ? "Update" : "Create"}
            </button>
            <button
              type="button"
              onClick={() => {
                setShowForm(false);
                setEditUser(null);
              }}
              className="text-gray-500 px-3 py-1.5 rounded text-sm hover:bg-gray-100"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      <div className="bg-white rounded-xl shadow border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-500">Loading...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-100">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">ID</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Name</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Email</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Role</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {users.map((u) => (
                  <tr key={u.id} className="hover:bg-blue-50/50 transition">
                    <td className="px-4 py-2.5 text-gray-600">{u.id}</td>
                    <td className="px-4 py-2.5 text-gray-900 font-medium">{u.username}</td>
                    <td className="px-4 py-2.5 text-gray-700">{u.email}</td>
                    <td className="px-4 py-2.5">
                      <span
                        className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                          u.role === "admin" ? "bg-purple-100 text-purple-700" : "bg-gray-100 text-gray-700"
                        }`}
                      >
                        {u.role}
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      <button
                        onClick={() => handleToggleDisabled(u)}
                        className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                          u.disabled ? "bg-red-100 text-red-700" : "bg-green-100 text-green-700"
                        }`}
                        type="button"
                      >
                        {u.disabled ? "Disabled" : "Active"}
                      </button>
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <button onClick={() => handleEdit(u)} className="text-blue-600 hover:text-blue-700 text-sm font-medium mr-3" type="button">
                        Edit
                      </button>
                      <button onClick={() => handleDelete(u.id)} className="text-red-600 hover:text-red-700 text-sm font-medium" type="button">
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
