import "./globals.css";
import React from "react";
import { AuthProvider } from "./contexts/AuthContext";
import ConditionalLayout from "./ConditionalLayout";

export const metadata = {
  title: "Agent Goldfinger - Production Intelligence",
  description: "Analyze production feasibility and identify component shortages instantly",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="flex flex-col min-h-full">
        <AuthProvider>
          <ConditionalLayout>
            {children}
          </ConditionalLayout>
        </AuthProvider>
      </body>
    </html>
  );
}