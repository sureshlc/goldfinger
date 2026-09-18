"use client";

import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";

interface PaginationProps {
  page: number;
  totalPages: number;
  total?: number;
  onChange: (page: number) => void;
  /** Max page-number buttons shown at once (sliding window). */
  windowSize?: number;
}

/**
 * Pagination bar: First / Prev / [sliding window of page numbers] / Next / Last.
 *
 * The page numbers are a window of up to `windowSize` (default 7) centered on the current page and
 * clamped to the ends — so as you move, newer/older page numbers slide into view. First/Last jump
 * to the ends; ellipses hint when there are pages beyond the visible window.
 */
export default function Pagination({ page, totalPages, total, onChange, windowSize = 7 }: PaginationProps) {
  if (totalPages < 1) return null;

  // Sliding window: keep it full-width near the ends (e.g. window stays 7 even at page 1 / last).
  const w = Math.min(windowSize, totalPages);
  const end = Math.min(totalPages, Math.max(page + Math.floor((w - 1) / 2), w));
  const start = Math.max(1, end - w + 1);
  const pages: number[] = [];
  for (let p = start; p <= end; p++) pages.push(p);

  const go = (p: number) => {
    const clamped = Math.min(totalPages, Math.max(1, p));
    if (clamped !== page) onChange(clamped);
  };

  const atFirst = page <= 1;
  const atLast = page >= totalPages;
  const nav =
    "inline-flex items-center gap-1 px-2.5 py-1 text-sm border border-gray-200 rounded-lg hover:bg-gray-100 " +
    "disabled:opacity-40 disabled:hover:bg-transparent disabled:cursor-not-allowed transition";

  return (
    <div className="relative flex flex-wrap items-center justify-center gap-x-3 gap-y-2 px-4 py-3 border-t border-gray-100 bg-gray-50">
      {/* Count pinned left on wider screens; stacks above the centered controls on mobile. */}
      <span className="text-sm text-gray-500 sm:absolute sm:left-4">
        Page {page} of {totalPages}
        {typeof total === "number" ? ` (${total} total)` : ""}
      </span>

      <div className="flex items-center gap-1">
        <button type="button" onClick={() => go(1)} disabled={atFirst} className={nav} aria-label="First page">
          <ChevronsLeft className="w-4 h-4" />
          <span className="hidden sm:inline">First</span>
        </button>
        <button type="button" onClick={() => go(page - 1)} disabled={atFirst} className={nav} aria-label="Previous page">
          <ChevronLeft className="w-4 h-4" />
          <span className="hidden sm:inline">Prev</span>
        </button>

        {start > 1 && <span className="px-1 text-gray-400 select-none">…</span>}

        {pages.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => go(p)}
            aria-current={p === page ? "page" : undefined}
            className={
              p === page
                ? "min-w-[2rem] px-3 py-1 text-sm rounded-lg border border-blue-600 bg-blue-600 text-white font-semibold transition"
                : "min-w-[2rem] px-3 py-1 text-sm rounded-lg border border-gray-200 hover:bg-gray-100 transition"
            }
          >
            {p}
          </button>
        ))}

        {end < totalPages && <span className="px-1 text-gray-400 select-none">…</span>}

        <button type="button" onClick={() => go(page + 1)} disabled={atLast} className={nav} aria-label="Next page">
          <span className="hidden sm:inline">Next</span>
          <ChevronRight className="w-4 h-4" />
        </button>
        <button type="button" onClick={() => go(totalPages)} disabled={atLast} className={nav} aria-label="Last page">
          <span className="hidden sm:inline">Last</span>
          <ChevronsRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
