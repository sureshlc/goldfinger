"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { fetchWithAuth, API_BASE_URL } from "../services/auth";

type Tab = "audit-logs" | "items" | "users";

interface AuditLog {
  id: number;
  timestamp: string;
  user_id: number;
  username: string | null;
  item_sku: string;
  desired_quantity: string;
  can_produce: string | null;
  status_code: number;
  response_time_ms: number;
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
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Item SKU</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Qty</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Producible</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Time (ms)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {logs.map((log) => {
                  const isProducible = log.can_produce === "True" || log.can_produce === "true";
                  const hasProduceData = log.can_produce != null && log.can_produce !== "";
                  return (
                    <tr key={log.id} className="hover:bg-blue-50/50 transition">
                      <td className="px-4 py-2.5 text-gray-600 text-xs">
                        {log.timestamp ? new Date(log.timestamp).toLocaleString() : "-"}
                      </td>
                      <td className="px-4 py-2.5 text-gray-900 font-medium text-xs">
                        {log.username || `User #${log.user_id}` || "-"}
                      </td>
                      <td className="px-4 py-2.5 text-gray-900 font-semibold">{log.item_sku || "-"}</td>
                      <td className="px-4 py-2.5 text-gray-700">{log.desired_quantity || "-"}</td>
                      <td className="px-4 py-2.5">
                        {hasProduceData ? (
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${
                              isProducible
                                ? "bg-green-100 text-green-700"
                                : "bg-red-100 text-red-700"
                            }`}
                          >
                            {isProducible ? "Yes" : "No"}
                          </span>
                        ) : (
                          <span className="text-gray-400 text-xs">-</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-gray-600">
                        {log.response_time_ms != null ? log.response_time_ms.toFixed(0) : "-"}
                      </td>
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
    try {
      if (editUser) {
        const body: Record<string, unknown> = { username: formUsername, role: formRole };
        if (formPassword) body.password = formPassword;
        await fetchWithAuth(`${API_BASE_URL}/admin/users/${editUser.id}`, {
          method: "PUT",
          body: JSON.stringify(body),
        });
      } else {
        await fetchWithAuth(`${API_BASE_URL}/admin/users`, {
          method: "POST",
          body: JSON.stringify({
            email: formEmail,
            username: formUsername,
            password: formPassword,
            role: formRole,
          }),
        });
      }
      setShowForm(false);
      setEditUser(null);
      resetForm();
      fetchUsers();
    } catch {
      /* ignore */
    }
  };

  const resetForm = () => {
    setFormEmail("");
    setFormUsername("");
    setFormPassword("");
    setFormRole("user");
  };

  const handleEdit = (u: AdminUser) => {
    setEditUser(u);
    setFormEmail(u.email);
    setFormUsername(u.username);
    setFormPassword("");
    setFormRole(u.role);
    setShowForm(true);
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this user?")) return;
    try {
      await fetchWithAuth(`${API_BASE_URL}/admin/users/${id}`, { method: "DELETE" });
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
            <input
              type="password"
              value={formPassword}
              onChange={(e) => setFormPassword(e.target.value)}
              required={!editUser}
              className="border rounded px-2 py-1.5 text-sm w-full"
            />
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
