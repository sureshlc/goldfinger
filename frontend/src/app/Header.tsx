"use client";

import React, { useState, useEffect, Suspense, useRef } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ChevronDown, User, Settings, LogOut, Search, X } from "lucide-react";
import SearchInput from "./components/SearchInput";
import { fetchItemSuggestions } from "./services/search";
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

  const showSearch = pathname?.startsWith("/item/");
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

  // Close dropdown on click outside
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

  return (
    <header className="bg-white/95 backdrop-blur-sm border-b border-gray-200 shadow-sm sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo/Brand */}
          <Link
            href="/"
            className="flex items-center space-x-3 text-gray-900 hover:text-blue-600 transition group flex-shrink-0"
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

          {/* Search Section - Only on item pages */}
          {showSearch && (
            <div className="flex items-center gap-2 flex-1 mx-2 sm:mx-4 justify-center max-w-3xl">
              {/* Search Input - grows to fill, min-width on mobile */}
              <div className="flex items-center gap-2 bg-gray-50 rounded-lg border border-gray-200 px-3 py-1.5 flex-1 min-w-0 focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-100 transition">
                <Search className="w-4 h-4 text-gray-400 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <SearchInput
                    fetchSuggestions={fetchItemSuggestions}
                    onSelect={handleSelect}
                    placeholder="Search SKU..."
                    minQueryLength={2}
                    query={query}
                    setQuery={setQuery}
                  />
                </div>
              </div>

              {/* Quantity */}
              <div className="flex items-center gap-1.5 bg-gray-50 rounded-lg border border-gray-200 px-2.5 py-1.5 flex-shrink-0">
                <label className="text-xs font-medium text-gray-500 whitespace-nowrap hidden sm:block">Qty</label>
                <input
                  type="number"
                  min="1"
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                  onKeyPress={handleQuantityKeyPress}
                  disabled={isAnalyzing}
                  className="w-14 sm:w-16 bg-transparent border-none text-sm font-medium focus:outline-none disabled:text-gray-400"
                />
                {quantity !== "1" && (
                  <button
                    onClick={handleResetQuantity}
                    disabled={isAnalyzing}
                    className="text-gray-400 hover:text-gray-600 transition disabled:opacity-50"
                    title="Reset to 1"
                    type="button"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>

              <AnalyzeButton
                query={query}
                onAnalyze={handleAnalyze}
                isAnalyzing={isAnalyzing}
              />
            </div>
          )}

          {/* Home page - show search when main search scrolls away */}
          {!showSearch && showHomeSearch && (
            <div className="flex items-center gap-2 flex-1 justify-center max-w-lg mx-4">
              <div className="flex items-center gap-2 bg-gray-50 rounded-lg border border-gray-200 px-3 py-1.5 flex-1 focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-100 transition">
                <Search className="w-4 h-4 text-gray-400 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <SearchInput
                    fetchSuggestions={fetchItemSuggestions}
                    onSelect={handleHomeSelect}
                    placeholder="Search by SKU..."
                    minQueryLength={2}
                    query={query}
                    setQuery={setQuery}
                  />
                </div>
              </div>
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
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-16">
          <Link href="/" className="flex items-center space-x-3 text-gray-900">
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
