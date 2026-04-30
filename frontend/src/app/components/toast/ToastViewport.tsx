"use client";

import React from "react";
import { CheckCircle2, AlertTriangle, Info, X } from "lucide-react";
import { useToast } from "./ToastContext";

const STYLES: Record<string, { bg: string; border: string; iconColor: string; Icon: React.ComponentType<{ className?: string }> }> = {
  success: {
    bg: "bg-green-50",
    border: "border-green-200",
    iconColor: "text-green-600",
    Icon: CheckCircle2,
  },
  error: {
    bg: "bg-red-50",
    border: "border-red-200",
    iconColor: "text-red-600",
    Icon: AlertTriangle,
  },
  info: {
    bg: "bg-blue-50",
    border: "border-blue-200",
    iconColor: "text-blue-600",
    Icon: Info,
  },
};

const ToastViewport: React.FC = () => {
  const { toasts, dismiss } = useToast();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[60] flex flex-col gap-2 w-[min(360px,calc(100vw-2rem))]" aria-live="polite">
      {toasts.map((t) => {
        const style = STYLES[t.kind];
        const Icon = style.Icon;
        return (
          <div
            key={t.id}
            role="status"
            className={`${style.bg} ${style.border} border rounded-lg shadow-md px-3 py-2.5 flex items-start gap-2 animate-fade-in`}
          >
            <Icon className={`w-4 h-4 ${style.iconColor} flex-shrink-0 mt-0.5`} />
            <p className="flex-1 text-sm text-gray-900 leading-snug">{t.message}</p>
            <button
              type="button"
              onClick={() => dismiss(t.id)}
              className="text-gray-400 hover:text-gray-600 transition flex-shrink-0"
              aria-label="Dismiss"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
};

export default ToastViewport;
