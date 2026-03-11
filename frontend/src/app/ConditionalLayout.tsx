"use client";

import React from "react";
import { usePathname } from "next/navigation";
import Header from "./Header";

export default function ConditionalLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  // Routes where header and footer should not be shown
  const authRoutes = ["/login"];
  const isAuthRoute = authRoutes.includes(pathname);

  // If it's an auth route (login), show only children without header/footer
  if (isAuthRoute) {
    return <>{children}</>;
  }

  // For all other routes, show header, content, and footer
  return (
    <div className="min-h-screen flex flex-col">
      <Header />
      <main className="flex-grow">
        {children}
      </main>
      <footer className="bg-white border-t-2 border-blue-200 py-6">
        <div className="max-w-7xl mx-auto px-4 text-center text-sm text-gray-500">
          &copy; {new Date().getFullYear()} Agent Goldfinger. All rights reserved.
        </div>
      </footer>
    </div>
  );
}
