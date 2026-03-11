"use client";

import React, { useCallback, useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Search, CheckCircle2, BarChart3, AlertTriangle, ArrowRight, Clock } from "lucide-react";
import SearchInput from "./components/SearchInput";
import { fetchItemSuggestions } from "./services/search";
import { fetchWithAuth, API_BASE_URL } from "./services/auth";

interface TopItem {
  item_sku: string;
  item_name: string | null;
  request_count: number;
  last_requested: string | null;
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "";
  const now = new Date();
  const then = new Date(dateStr);
  const diffMs = now.getTime() - then.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

export default function Home() {
  const router = useRouter();

  const [query, setQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [topItems, setTopItems] = useState<TopItem[]>([]);
  const [topItemsLoading, setTopItemsLoading] = useState(true);
  const [quantities, setQuantities] = useState<Record<string, string>>({});
  const searchCardRef = useRef<HTMLDivElement>(null);
  const memoizedFetchSuggestions = useCallback(fetchItemSuggestions, []);

  // Track when search card scrolls behind the sticky header
  useEffect(() => {
    const el = searchCardRef.current;
    if (!el) return;

    const checkVisibility = () => {
      const rect = el.getBoundingClientRect();
      const isVisible = rect.bottom > 80;
      window.dispatchEvent(
        new CustomEvent("homeSearchVisibility", {
          detail: { visible: isVisible },
        })
      );
    };

    window.addEventListener("scroll", checkVisibility, { passive: true });
    checkVisibility();

    return () => {
      window.removeEventListener("scroll", checkVisibility);
      window.dispatchEvent(
        new CustomEvent("homeSearchVisibility", { detail: { visible: true } })
      );
    };
  }, []);

  useEffect(() => {
    const fetchTopItems = async () => {
      try {
        const res = await fetchWithAuth(`${API_BASE_URL}/analytics/top-items?limit=5`);
        if (res.ok) {
          const data = await res.json();
          setTopItems(data);
        }
      } catch {
        /* ignore */
      } finally {
        setTopItemsLoading(false);
      }
    };
    fetchTopItems();
  }, []);

  const handleSelect = (itemSku: string) => {
    if (itemSku) {
      setIsSearching(true);
      router.push(`/item/${itemSku}`);
      setQuery("");
    }
  };

  const handleSearch = () => {
    if (query.trim()) {
      setIsSearching(true);
      router.push(`/item/${query.trim().toUpperCase()}`);
      setQuery("");
    }
  };

  const handleAnalyzeItem = (sku: string) => {
    const qty = parseInt(quantities[sku] || "1") || 1;
    router.push(`/item/${sku}?quantity=${qty}`);
  };

  return (
    <div className="min-h-[calc(100vh-5rem)] bg-gradient-to-b from-blue-50 to-white px-4 pt-8 pb-12">
      <div className="max-w-4xl mx-auto">
        {/* Hero Section */}
        <div className="text-center mb-10">
          <h1 className="text-4xl md:text-5xl font-bold text-gray-900 mb-3">
            Agent Goldfinger
          </h1>
          <div className="w-20 h-1 bg-yellow-500 mx-auto mb-5 rounded-full"></div>
          <p className="text-lg md:text-xl text-gray-600 mb-1">
            Production Intelligence Assistant
          </p>
          <p className="text-sm text-gray-400">
            Analyze production feasibility and identify component shortages instantly
          </p>
        </div>

        {/* Search Card */}
        <div ref={searchCardRef} className="bg-white p-6 md:p-8 rounded-2xl shadow-lg border border-gray-200 max-w-2xl mx-auto mb-10">
          <div className="flex items-center gap-2 justify-center mb-4">
            <Search className="w-5 h-5 text-blue-600" />
            <h2 className="text-base md:text-lg font-semibold text-gray-900">
              Search for an Item
            </h2>
          </div>
          <div className="flex flex-col sm:flex-row gap-2">
            <div className="flex items-center gap-2 flex-1 border border-gray-300 rounded-lg px-3 py-1.5 focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-100 transition bg-white">
              <Search className="w-4 h-4 text-gray-400 flex-shrink-0" />
              <SearchInput
                fetchSuggestions={memoizedFetchSuggestions}
                onSelect={handleSelect}
                query={query}
                setQuery={setQuery}
              />
            </div>
            <button
              onClick={handleSearch}
              disabled={!query.trim() || isSearching}
              className={`px-6 py-2.5 font-semibold rounded-lg transition flex items-center justify-center gap-2 ${
                query.trim() && !isSearching
                  ? "bg-blue-600 text-white hover:bg-blue-700 shadow-md"
                  : "bg-gray-200 text-gray-400 cursor-not-allowed"
              }`}
            >
              {isSearching ? (
                <>
                  <svg className="animate-spin h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Searching...
                </>
              ) : (
                "Search"
              )}
            </button>
          </div>
          <p className="text-xs text-gray-400 mt-3 text-center">
            Enter item name or SKU to check production status
          </p>
        </div>

        {/* Feature Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-10">
          <div className="bg-white p-5 rounded-xl shadow-sm border border-gray-100 flex items-start gap-3 hover:shadow-md transition">
            <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center flex-shrink-0">
              <CheckCircle2 className="w-5 h-5 text-green-600" />
            </div>
            <div>
              <p className="text-sm font-semibold text-gray-800 mb-0.5">Can Produce?</p>
              <p className="text-xs text-gray-500">Check feasibility instantly</p>
            </div>
          </div>
          <div className="bg-white p-5 rounded-xl shadow-sm border border-gray-100 flex items-start gap-3 hover:shadow-md transition">
            <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center flex-shrink-0">
              <BarChart3 className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <p className="text-sm font-semibold text-gray-800 mb-0.5">Max Quantity</p>
              <p className="text-xs text-gray-500">See production capacity</p>
            </div>
          </div>
          <div className="bg-white p-5 rounded-xl shadow-sm border border-gray-100 flex items-start gap-3 hover:shadow-md transition">
            <div className="w-10 h-10 rounded-lg bg-red-100 flex items-center justify-center flex-shrink-0">
              <AlertTriangle className="w-5 h-5 text-red-600" />
            </div>
            <div>
              <p className="text-sm font-semibold text-gray-800 mb-0.5">Shortages</p>
              <p className="text-xs text-gray-500">Identify missing components</p>
            </div>
          </div>
        </div>

        {/* Frequently Analyzed Items */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-900">Frequently Analyzed Items</h3>
            {topItems.length > 0 && (
              <span className="text-xs text-gray-400">Top {topItems.length} by request count</span>
            )}
          </div>
          <div className="bg-white rounded-xl shadow border border-gray-200 overflow-hidden">
            {topItemsLoading ? (
              <div className="p-6 space-y-4">
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="animate-pulse flex items-center gap-4">
                    <div className="h-4 bg-gray-200 rounded w-24"></div>
                    <div className="h-4 bg-gray-200 rounded w-40"></div>
                    <div className="flex-1"></div>
                    <div className="h-8 bg-gray-200 rounded w-16"></div>
                    <div className="h-8 bg-gray-200 rounded w-20"></div>
                  </div>
                ))}
              </div>
            ) : topItems.length === 0 ? (
              <div className="p-10 text-center">
                <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-3">
                  <BarChart3 className="w-6 h-6 text-gray-400" />
                </div>
                <p className="text-gray-500 text-sm mb-1">No data yet</p>
                <p className="text-gray-400 text-xs">Start analyzing items to see your most requested ones here.</p>
              </div>
            ) : (
              <>
                {/* Desktop table */}
                <div className="hidden sm:block">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 border-b border-gray-100">
                      <tr>
                        <th className="px-5 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">SKU</th>
                        <th className="px-5 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Description</th>
                        <th className="px-5 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Requests</th>
                        <th className="px-5 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Last</th>
                        <th className="px-5 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Qty</th>
                        <th className="px-5 py-3"></th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                      {topItems.map((item) => (
                        <tr key={item.item_sku} className="hover:bg-blue-50/50 transition group">
                          <td className="px-5 py-3.5">
                            <span className="font-semibold text-gray-900">{item.item_sku}</span>
                          </td>
                          <td className="px-5 py-3.5 text-gray-500 text-xs max-w-[200px] truncate">
                            {item.item_name || "-"}
                          </td>
                          <td className="px-5 py-3.5">
                            <span className="bg-blue-100 text-blue-700 px-2.5 py-0.5 rounded-full text-xs font-semibold">
                              {item.request_count}
                            </span>
                          </td>
                          <td className="px-5 py-3.5">
                            {item.last_requested && (
                              <span className="flex items-center gap-1 text-xs text-gray-400">
                                <Clock className="w-3 h-3" />
                                {timeAgo(item.last_requested)}
                              </span>
                            )}
                          </td>
                          <td className="px-5 py-3.5">
                            <input
                              type="number"
                              min="1"
                              value={quantities[item.item_sku] || "1"}
                              onChange={(e) =>
                                setQuantities((prev) => ({ ...prev, [item.item_sku]: e.target.value }))
                              }
                              className="w-16 border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                            />
                          </td>
                          <td className="px-5 py-3.5 text-right">
                            <button
                              onClick={() => handleAnalyzeItem(item.item_sku)}
                              className="inline-flex items-center gap-1 bg-blue-600 text-white px-3.5 py-1.5 rounded-lg text-sm font-medium hover:bg-blue-700 transition shadow-sm"
                              type="button"
                            >
                              Analyze
                              <ArrowRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Mobile cards */}
                <div className="sm:hidden divide-y divide-gray-100">
                  {topItems.map((item) => (
                    <div key={item.item_sku} className="p-4">
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-semibold text-gray-900">{item.item_sku}</span>
                        <span className="bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full text-xs font-semibold">
                          {item.request_count} requests
                        </span>
                      </div>
                      {item.item_name && (
                        <p className="text-xs text-gray-500 mb-3 truncate">{item.item_name}</p>
                      )}
                      <div className="flex items-center gap-2">
                        <input
                          type="number"
                          min="1"
                          value={quantities[item.item_sku] || "1"}
                          onChange={(e) =>
                            setQuantities((prev) => ({ ...prev, [item.item_sku]: e.target.value }))
                          }
                          className="w-16 border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                        <button
                          onClick={() => handleAnalyzeItem(item.item_sku)}
                          className="flex-1 bg-blue-600 text-white px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-blue-700 transition"
                          type="button"
                        >
                          Analyze
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
