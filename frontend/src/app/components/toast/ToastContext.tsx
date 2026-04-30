"use client";

import React, { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

export type ToastKind = "success" | "error" | "info";

export interface ToastEntry {
  id: number;
  kind: ToastKind;
  message: string;
}

interface ToastApi {
  toasts: ToastEntry[];
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
  dismiss: (id: number) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

const DEFAULT_TIMEOUT_MS = 4000;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastEntry[]>([]);
  const idRef = useRef(0);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (kind: ToastKind, message: string) => {
      const id = ++idRef.current;
      setToasts((prev) => [...prev, { id, kind, message }]);
      window.setTimeout(() => dismiss(id), DEFAULT_TIMEOUT_MS);
    },
    [dismiss]
  );

  const api = useMemo<ToastApi>(
    () => ({
      toasts,
      success: (msg) => push("success", msg),
      error: (msg) => push("error", msg),
      info: (msg) => push("info", msg),
      dismiss,
    }),
    [toasts, push, dismiss]
  );

  // Bridge: expose a global emit function so non-component code (services/auth.ts) can fire toasts.
  if (typeof window !== "undefined") {
    (window as unknown as { __emitToast?: (kind: ToastKind, message: string) => void }).__emitToast =
      (kind, message) => push(kind, message);
  }

  return <ToastContext.Provider value={api}>{children}</ToastContext.Provider>;
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within <ToastProvider>");
  }
  return ctx;
}

export function emitToast(kind: ToastKind, message: string) {
  if (typeof window === "undefined") return;
  const fn = (window as unknown as { __emitToast?: (k: ToastKind, m: string) => void }).__emitToast;
  fn?.(kind, message);
}
