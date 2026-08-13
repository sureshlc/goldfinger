"use client";

import React, { useState, useEffect, Suspense, useRef } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ChevronDown, User, Settings, LogOut, Search, X, Plus, Layers } from "lucide-react";
import SkuAutocomplete from "./components/SkuAutocomplete";
import MultiSkuPanel, { SkuRow, validRowsOf } from "./components/MultiSkuPanel";
import { useAuth } from "./contexts/AuthContext";

function HeaderContent() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, logout } = useAuth();

  const [query, setQuery] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const previousQuantity = useRef("1");
  const previousPathname = useRef("");

  const [homeSearchVisible, setHomeSearchVisible] = useState(true);
  const [multiMode, setMultiMode] = useState(false);
  const [multiOpen, setMultiOpen] = useState(false);
  const [multiRows, setMultiRows] = useState<SkuRow[]>([
    { sku: "", qty: "1" },
    { sku: "", qty: "1" },
  ]);
  const lastSeededItemsRef = useRef<string>("");
  const multiContainerRef = useRef<HTMLDivElement>(null);

  const isMultiAnalyzePage = pathname?.startsWith("/multi-analyze") ?? false;

  const enterMultiMode = () => {
    setMultiRows((prev) => {
      const seeded = [...prev];
      const seededSku = query.trim().toUpperCase();
      if (seededSku && !seeded[0].sku) {
        seeded[0] = { sku: seededSku, qty: quantity || "1" };
      }
      return seeded;
    });
    setMultiMode(true);
    setMultiOpen(true);
  };

  // Closing only collapses the dropdown; keeps multi-mode if we're already on the results page.
  const closeMultiPanel = () => setMultiOpen(false);

  // Clear the batch and leave multi-mode so the user can start fresh — but stay on the page.
  const exitMultiMode = () => {
    setMultiOpen(false);
    setMultiMode(false);
    setMultiRows([
      { sku: "", qty: "1" },
      { sku: "", qty: "1" },
    ]);
    setQuery("");
    setQuantity("1");
    // Keep ref equal to the current URL items so auto-seed doesn't re-enter multi-mode.
    lastSeededItemsRef.current = searchParams.get("items") || "";
  };

  // Auto-seed multi-mode from URL when landing on /multi-analyze. Panel stays collapsed by default.
  useEffect(() => {
    if (!isMultiAnalyzePage) {
      // Leaving the results page: drop multi-mode unless user is actively editing in dropdown.
      if (multiMode && !multiOpen) {
        setMultiMode(false);
        lastSeededItemsRef.current = "";
      }
      return;
    }
    const itemsParam = searchParams.get("items") || "";
    if (itemsParam === lastSeededItemsRef.current) return;
    lastSeededItemsRef.current = itemsParam;
    const parsed = itemsParam
      .split(",")
      .map((p) => p.trim())
      .filter(Boolean)
      .map((p) => {
        const [skuRaw, qtyRaw] = p.split(":");
        return {
          sku: decodeURIComponent(skuRaw || "").toUpperCase(),
          qty: (qtyRaw || "1").trim(),
        };
      })
      .filter((r) => r.sku.length > 0);
    if (parsed.length === 0) return;
    setMultiRows(parsed.length === 1 ? [...parsed, { sku: "", qty: "1" }] : parsed);
    setMultiMode(true);
    // Do NOT auto-open the panel — show the compact summary bar instead.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isMultiAnalyzePage, searchParams]);

  // Click outside the multi-panel area closes the dropdown (but keeps multi-mode).
  useEffect(() => {
    if (!multiOpen) return;
    const handler = (event: MouseEvent) => {
      if (
        multiContainerRef.current &&
        !multiContainerRef.current.contains(event.target as Node)
      ) {
        setMultiOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [multiOpen]);

  const showSearch = pathname?.startsWith("/item/") || isMultiAnalyzePage;
  const isHomePage = pathname === "/";
  const showHomeSearch = isHomePage && !homeSearchVisible;

  // Listen for home page search card visibility
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      setHomeSearchVisible(detail.visible);
    };
    window.addEventListener("homeSearchVisibility", handler);
    return () => window.removeEventListener("homeSearchVisibility", handler);
  }, []);

  // Reset when navigating away from home
  useEffect(() => {
    if (!isHomePage) {
      setHomeSearchVisible(true);
    }
  }, [isHomePage]);

  // Close user dropdown on click outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    if (showSearch) {
      const currentQuantity = searchParams.get("quantity") || "1";

      if (currentQuantity !== previousQuantity.current || pathname !== previousPathname.current) {
        setQuantity(currentQuantity);
        setIsAnalyzing(false);
        previousQuantity.current = currentQuantity;
        previousPathname.current = pathname || "";
      }
    }
  }, [searchParams, showSearch, pathname]);

  const handleSelect = (sku: string) => {
    const qty = parseInt(quantity) || 1;
    setIsAnalyzing(true);
    const params = new URLSearchParams(searchParams.toString());
    params.set("quantity", qty.toString());
    router.push(`/item/${sku.toUpperCase()}?${params.toString()}`);
    setQuery("");
  };

  const handleAnalyze = () => {
    const sku = query.trim();
    const qty = parseInt(quantity) || 1;
    const params = new URLSearchParams(searchParams.toString());
    const currentQuantity = searchParams.get("quantity") || "1";

    if (sku) {
      setIsAnalyzing(true);
      params.set("quantity", qty.toString());
      router.push(`/item/${sku.toUpperCase()}?${params.toString()}`);
      setQuery("");
    } else if (pathname?.startsWith("/item/")) {
      if (qty.toString() !== currentQuantity) {
        setIsAnalyzing(true);
        params.set("quantity", qty.toString());
        const currentSku = pathname.split("/item/")[1]?.split("?")[0];
        if (currentSku) {
          router.push(`/item/${currentSku}?${params.toString()}`);
        }
      }
    }
  };

  const handleResetQuantity = () => {
    setQuantity("1");
  };

  const handleQuantityKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleAnalyze();
    }
  };

  const handleHomeSelect = (sku: string) => {
    if (sku) {
      router.push(`/item/${sku.toUpperCase()}`);
      setQuery("");
    }
  };

  const handleHomeSearch = () => {
    const sku = query.trim();
    if (sku) {
      router.push(`/item/${sku.toUpperCase()}`);
      setQuery("");
    }
  };

  const handleLogout = () => {
    setDropdownOpen(false);
    logout();
  };

  interface AnalyzeButtonProps {
    query: string;
    onAnalyze: () => void;
    isAnalyzing: boolean;
  }

  function AnalyzeButton({ query, onAnalyze, isAnalyzing }: AnalyzeButtonProps) {
    const currentQuantity = searchParams.get("quantity") || "1";
    const quantityChanged = quantity !== currentQuantity;
    const isEnabled = query.trim() || (pathname?.startsWith("/item/") && quantityChanged);

    return (
      <button
        onClick={onAnalyze}
        disabled={!isEnabled || isAnalyzing}
        className={`px-4 py-2 font-semibold rounded-lg transition flex items-center gap-2 ${
          isEnabled && !isAnalyzing
            ? 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm'
            : 'bg-gray-200 text-gray-400 cursor-not-allowed'
        }`}
        type="button"
        aria-label="Analyze"
      >
        {isAnalyzing ? (
          <>
            <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            Analyzing...
          </>
        ) : (
          'Analyze'
        )}
      </button>
    );
  }

  // Compact bar shown when in multi-mode but the panel is collapsed.
  function MultiCompactBar({ wide }: { wide: boolean }) {
    const valid = validRowsOf(multiRows);
    const count = valid.length;
    const summary = (() => {
      if (count === 0) return "Add SKUs to your batch";
      if (count === 1) return valid[0].sku;
      if (count === 2) return `${valid[0].sku} · ${valid[1].sku}`;
      return `${valid[0].sku} · +${count - 2} · ${valid[count - 1].sku}`;
    })();
    return (
      <button
        type="button"
        onClick={() => setMultiOpen((v) => !v)}
        className={`flex items-center gap-2 bg-gray-50 rounded-lg border border-gray-200 px-3 py-1.5 ${
          wide ? "flex-1 min-w-0" : "flex-1 min-w-0"
        } hover:border-blue-300 hover:bg-blue-50/40 transition text-left`}
        aria-label={multiOpen ? "Collapse multi-SKU batch editor" : "Expand multi-SKU batch editor"}
        aria-expanded={multiOpen}
      >
        <Layers className="w-4 h-4 text-blue-500 flex-shrink-0" />
        <span className="text-sm font-medium text-gray-900 flex-shrink-0">
          {count} {count === 1 ? "SKU" : "SKUs"}
        </span>
        <span className="text-sm text-gray-500 truncate">{summary}</span>
        <ChevronDown
          className={`w-4 h-4 text-gray-400 flex-shrink-0 ml-auto transition-transform ${
            multiOpen ? "rotate-180" : ""
          }`}
        />
      </button>
    );
  }

  return (
    <header className="bg-white/95 backdrop-blur-sm border-b border-gray-200 shadow-sm sticky top-0 z-50">
      <div className="w-full px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo/Brand */}
          <Link
            href="/"
            className="flex items-center space-x-3 text-blue-600 hover:text-blue-700 transition group flex-shrink-0"
          >
            <Image
              src="/Eagle-Logo.png"
              alt="Company Logo"
              width={100}
              height={44}
              className="drop-shadow-sm"
            />
            <div className="hidden sm:block">
              <span className="text-xl font-bold tracking-tight">Agent Goldfinger</span>
            </div>
          </Link>

          {/* Search Section - Only on item / multi-analyze pages */}
          {showSearch && (
            <div
              ref={multiMode ? multiContainerRef : undefined}
              className="flex items-center gap-2 flex-1 mx-2 sm:mx-4 justify-center max-w-3xl relative"
            >
              {!multiMode && (
                <>
                  <div className="relative flex items-center gap-2 bg-gray-50 rounded-lg border border-gray-200 px-3 py-1.5 flex-1 min-w-0 focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-100 transition">
                    <Search className="w-4 h-4 text-gray-400 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <SkuAutocomplete
                        value={query}
                        onChange={setQuery}
                        onSelect={handleSelect}
                        onSubmit={handleAnalyze}
                        placeholder="Search SKU..."
                      />
                    </div>
                  </div>

                  <input
                    type="number"
                    min="1"
                    value={quantity}
                    onChange={(e) => setQuantity(e.target.value)}
                    onKeyPress={handleQuantityKeyPress}
                    disabled={isAnalyzing}
                    placeholder="Qty"
                    className="w-16 bg-gray-50 border border-gray-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-400 disabled:text-gray-400 flex-shrink-0"
                  />

                  <button
                    type="button"
                    onClick={enterMultiMode}
                    disabled={!query.trim()}
                    title={query.trim() ? "Add multiple SKUs" : "Enter a SKU first to start a batch"}
                    aria-label="Add multiple SKUs"
                    className="flex-shrink-0 inline-flex items-center justify-center w-9 h-9 rounded-lg bg-gray-50 border border-gray-200 text-gray-500 hover:text-blue-600 hover:border-blue-200 transition disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:text-gray-500 disabled:hover:border-gray-200"
                  >
                    <Plus className="w-4 h-4" />
                  </button>
                  <AnalyzeButton
                    query={query}
                    onAnalyze={handleAnalyze}
                    isAnalyzing={isAnalyzing}
                  />
                </>
              )}

              {multiMode && (
                <>
                  <MultiCompactBar wide />
                  <button
                    type="button"
                    onClick={exitMultiMode}
                    title={isMultiAnalyzePage ? "Close batch editor" : "Exit multi-SKU mode"}
                    aria-label={isMultiAnalyzePage ? "Close batch editor" : "Exit multi-SKU mode"}
                    className="flex-shrink-0 inline-flex items-center justify-center w-9 h-9 rounded-lg bg-gray-50 border border-gray-200 text-gray-500 hover:text-red-600 hover:border-red-200 transition"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </>
              )}

              {multiMode && multiOpen && (
                <div className="absolute top-full left-0 right-0 mt-2 z-50">
                  <MultiSkuPanel
                    rows={multiRows}
                    setRows={setMultiRows}
                    onClose={closeMultiPanel}
                    variant="card"
                    hideClose
                  />
                </div>
              )}
            </div>
          )}

          {/* Home page - show search when main search scrolls away */}
          {!showSearch && showHomeSearch && (
            <div
              ref={multiMode ? multiContainerRef : undefined}
              className="flex items-center gap-2 mx-4 relative"
            >
              {!multiMode && (
                <>
                  <div className="relative flex items-center gap-2 bg-gray-50 rounded-lg border border-gray-200 px-3 py-1.5 flex-1 min-w-0 focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-100 transition">
                    <Search className="w-4 h-4 text-gray-400 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <SkuAutocomplete
                        value={query}
                        onChange={setQuery}
                        onSelect={handleHomeSelect}
                        onSubmit={handleHomeSearch}
                        placeholder="Search by SKU..."
                      />
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={enterMultiMode}
                    disabled={!query.trim()}
                    title={query.trim() ? "Add multiple SKUs" : "Enter a SKU first to start a batch"}
                    aria-label="Add multiple SKUs"
                    className="flex-shrink-0 inline-flex items-center justify-center w-9 h-9 rounded-lg bg-gray-50 border border-gray-200 text-gray-500 hover:text-blue-600 hover:border-blue-200 transition disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:text-gray-500 disabled:hover:border-gray-200"
                  >
                    <Plus className="w-4 h-4" />
                  </button>
                  <button
                    onClick={handleHomeSearch}
                    disabled={!query.trim()}
                    className={`px-4 py-2 font-semibold rounded-lg transition text-sm ${
                      query.trim()
                        ? "bg-blue-600 text-white hover:bg-blue-700 shadow-sm"
                        : "bg-gray-200 text-gray-400 cursor-not-allowed"
                    }`}
                    type="button"
                  >
                    Search
                  </button>
                </>
              )}

              {multiMode && (
                <>
                  <MultiCompactBar wide />
                  <button
                    type="button"
                    onClick={exitMultiMode}
                    title="Exit multi-SKU mode"
                    aria-label="Exit multi-SKU mode"
                    className="flex-shrink-0 inline-flex items-center justify-center w-9 h-9 rounded-lg bg-gray-50 border border-gray-200 text-gray-500 hover:text-red-600 hover:border-red-200 transition"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </>
              )}

              {multiMode && multiOpen && (
                <div className="absolute top-full left-0 right-0 mt-2 z-50">
                  <MultiSkuPanel
                    rows={multiRows}
                    setRows={setMultiRows}
                    onClose={closeMultiPanel}
                    variant="card"
                    hideClose
                  />
                </div>
              )}
            </div>
          )}

          {/* Spacer when no search visible */}
          {!showSearch && !showHomeSearch && (
            <div className="flex-1" />
          )}

          {/* User Dropdown */}
          {user && (
            <div className="relative ml-3 flex-shrink-0" ref={dropdownRef}>
              <button
                onClick={() => setDropdownOpen(!dropdownOpen)}
                className="flex items-center gap-2 px-2.5 py-1.5 text-gray-700 hover:text-blue-600 hover:bg-gray-50 rounded-lg transition"
                type="button"
              >
                <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-blue-600 rounded-full flex items-center justify-center shadow-sm">
                  <span className="text-white text-xs font-bold">
                    {(user.username || user.email || "U").charAt(0).toUpperCase()}
                  </span>
                </div>
                <span className="text-sm font-medium hidden sm:block max-w-[100px] truncate">
                  {user.username || user.email}
                </span>
                <ChevronDown className={`w-3.5 h-3.5 text-gray-400 transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
              </button>

              {dropdownOpen && (
                <div className="absolute right-0 mt-2 w-56 bg-white rounded-xl shadow-lg border border-gray-200 py-1 z-50">
                  <div className="px-4 py-3 border-b border-gray-100">
                    <p className="text-sm font-semibold text-gray-900">{user.username}</p>
                    <p className="text-xs text-gray-500">{user.email}</p>
                  </div>

                  <div className="py-1">
                    <Link
                      href="/profile"
                      onClick={() => setDropdownOpen(false)}
                      className="flex items-center gap-2.5 px-4 py-2 text-sm text-gray-700 hover:bg-blue-50 hover:text-blue-600 transition"
                    >
                      <User className="w-4 h-4" />
                      <span>Profile Settings</span>
                    </Link>

                    {user.role === "admin" && (
                      <Link
                        href="/admin"
                        onClick={() => setDropdownOpen(false)}
                        className="flex items-center gap-2.5 px-4 py-2 text-sm text-gray-700 hover:bg-blue-50 hover:text-blue-600 transition"
                      >
                        <Settings className="w-4 h-4" />
                        <span>Admin Settings</span>
                      </Link>
                    )}
                  </div>

                  <div className="border-t border-gray-100 py-1">
                    <button
                      onClick={handleLogout}
                      className="flex items-center gap-2.5 w-full px-4 py-2 text-sm text-red-600 hover:bg-red-50 transition"
                      type="button"
                    >
                      <LogOut className="w-4 h-4" />
                      <span>Logout</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

export default function Header() {
  return (
    <Suspense fallback={
      <header className="bg-white/95 backdrop-blur-sm border-b border-gray-200 shadow-sm sticky top-0 z-50">
        <div className="w-full px-4 sm:px-6 lg:px-8 flex items-center justify-between h-16">
          <Link href="/" className="flex items-center space-x-3 text-blue-600 hover:text-blue-700 transition">
            <Image
              src="/Eagle-Logo.png"
              alt="Company Logo"
              width={100}
              height={44}
              className="drop-shadow-sm"
            />
            <span className="text-xl font-bold hidden sm:block">Agent Goldfinger</span>
          </Link>
        </div>
      </header>
    }>
      <HeaderContent />
    </Suspense>
  );
}
