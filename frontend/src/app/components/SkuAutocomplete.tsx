"use client";

import React, { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { fetchItemSuggestions, type ItemSuggestion } from "@/app/services/search";

interface SkuAutocompleteProps {
  value: string;
  onChange: (next: string) => void;
  onSelect?: (sku: string) => void;
  onSubmit?: () => void;
  placeholder?: string;
  className?: string;
  ariaLabel?: string;
  autoFocus?: boolean;
}

const DEBOUNCE_MS = 180;
const PAGE_SIZE = 10;

const SkuAutocomplete: React.FC<SkuAutocompleteProps> = ({
  value,
  onChange,
  onSelect,
  onSubmit,
  placeholder = "Enter SKU",
  className = "",
  ariaLabel,
  autoFocus,
}) => {
  const [suggestions, setSuggestions] = useState<ItemSuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(-1);
  const [loading, setLoading] = useState(false);
  const [reachedEnd, setReachedEnd] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<number | null>(null);
  const requestSeqRef = useRef(0);

  // Debounced fetch on value change
  useEffect(() => {
    const trimmed = value.trim();
    if (debounceRef.current !== null) {
      window.clearTimeout(debounceRef.current);
    }
    if (trimmed.length < 1) {
      setSuggestions([]);
      setReachedEnd(false);
      setLoading(false);
      return;
    }
    setLoading(true);
    setReachedEnd(false);
    debounceRef.current = window.setTimeout(async () => {
      const seq = ++requestSeqRef.current;
      const res = await fetchItemSuggestions(trimmed, PAGE_SIZE, 0);
      if (seq === requestSeqRef.current) {
        setSuggestions(res);
        setReachedEnd(res.length < PAGE_SIZE);
        setLoading(false);
      }
    }, DEBOUNCE_MS);
    return () => {
      if (debounceRef.current !== null) window.clearTimeout(debounceRef.current);
    };
  }, [value]);

  // Click outside closes the dropdown
  useEffect(() => {
    if (!open) return;
    const handler = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const choose = (s: ItemSuggestion) => {
    const sku = s.sku.toUpperCase();
    onChange(sku);
    setOpen(false);
    setHighlight(-1);
    // Click only fills; user submits via Enter or the Analyze button.
  };

  const loadMore = async () => {
    if (loadingMore || reachedEnd) return;
    setLoadingMore(true);
    const next = await fetchItemSuggestions(value.trim(), PAGE_SIZE, suggestions.length);
    setSuggestions((prev) => [...prev, ...next]);
    setReachedEnd(next.length < PAGE_SIZE);
    setLoadingMore(false);
  };

  const handleClear = () => {
    onChange("");
    setSuggestions([]);
    setOpen(false);
    setHighlight(-1);
    setReachedEnd(false);
    inputRef.current?.focus();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (suggestions.length === 0) return;
      setOpen(true);
      setHighlight((h) => (h + 1) % suggestions.length);
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (suggestions.length === 0) return;
      setOpen(true);
      setHighlight((h) => (h <= 0 ? suggestions.length - 1 : h - 1));
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      if (open && highlight >= 0 && suggestions[highlight]) {
        choose(suggestions[highlight]);
        return;
      }
      onSubmit?.();
      return;
    }
    if (e.key === "Escape") {
      setOpen(false);
      setHighlight(-1);
    }
  };

  const trimmed = value.trim();
  const showDropdown = open && trimmed.length > 0;
  const showEmptyState = !loading && trimmed.length > 0 && suggestions.length === 0;

  const inputClassName =
    className ||
    "w-full bg-transparent border-none outline-none text-sm text-gray-900 placeholder-gray-400 py-1 uppercase placeholder:normal-case";

  return (
    <div ref={containerRef} className="w-full">
      <div className="relative w-full">
        <input
          ref={inputRef}
          type="text"
          value={value}
          autoFocus={autoFocus}
          onFocus={() => {
            if (trimmed.length > 0) setOpen(true);
          }}
          onChange={(e) => {
            onChange(e.target.value);
            setOpen(true);
            setHighlight(-1);
          }}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          aria-label={ariaLabel || placeholder}
          className={inputClassName + (value.length > 0 ? " pr-7" : "")}
        />
        {value.length > 0 && (
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={handleClear}
            aria-label="Clear search"
            title="Clear"
            className="absolute right-1 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition p-0.5"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {showDropdown && (
        <ul
          role="listbox"
          className="absolute left-0 right-0 top-full mt-1 z-50 bg-white border border-gray-200 rounded-lg shadow-lg max-h-80 overflow-auto py-1"
        >
          {loading && suggestions.length === 0 && (
            <li className="px-3 py-2 text-xs text-gray-500 italic">Searching…</li>
          )}

          {suggestions.map((s, idx) => {
            const isHighlighted = idx === highlight;
            return (
              <li
                role="option"
                aria-selected={isHighlighted}
                key={s.id}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => choose(s)}
                onMouseEnter={() => setHighlight(idx)}
                className={`px-3 py-2 cursor-pointer text-sm ${
                  isHighlighted ? "bg-blue-50" : "hover:bg-gray-50"
                }`}
              >
                <div className="font-medium text-gray-900">{s.sku}</div>
                {s.name && <div className="text-xs text-gray-500 truncate">{s.name}</div>}
              </li>
            );
          })}

          {showEmptyState && (
            <li className="px-3 py-2 text-xs text-gray-600 leading-snug">
              No matches in local catalog —{" "}
              <span className="text-blue-600 font-medium">press Enter</span> to search NetSuite for &ldquo;{trimmed}&rdquo;.
            </li>
          )}

          {!loading && suggestions.length > 0 && !reachedEnd && (
            <li
              className="px-3 py-2 text-xs text-blue-600 hover:bg-blue-50 text-center cursor-pointer border-t border-gray-100"
              onMouseDown={(e) => e.preventDefault()}
              onClick={loadMore}
            >
              {loadingMore ? "Loading…" : `Load ${PAGE_SIZE} more`}
            </li>
          )}
        </ul>
      )}
    </div>
  );
};

export default SkuAutocomplete;
