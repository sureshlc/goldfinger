"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { AuthService, User } from "../services/auth";

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  isLoading: true,
  logout: () => {},
});

// Define public routes outside component since it's a constant
const PUBLIC_ROUTES = ["/login"];

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    const checkAuth = async () => {
      // If on login page, don't check auth
      if (PUBLIC_ROUTES.includes(pathname)) {
        setIsLoading(false);
        return;
      }

      try {
        // Check if user has a token
        if (!AuthService.isAuthenticated()) {
          router.push("/login");
          setIsLoading(false);
          return;
        }

        // Verify token is valid and get user info
        const currentUser = await AuthService.getCurrentUser();
        setUser(currentUser);
        setIsLoading(false);
      } catch (_error) {
        // Token invalid or expired, redirect to login
        AuthService.logout();
        router.push("/login");
        setIsLoading(false);
      }
    };

    checkAuth();
  }, [pathname, router]);

  const logout = () => {
    AuthService.logout();
    setUser(null);
    router.push("/login");
  };

  // Show loading state while checking authentication
  if (isLoading && !PUBLIC_ROUTES.includes(pathname)) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <svg className="animate-spin h-8 w-8 mx-auto text-blue-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <p className="mt-2 text-gray-600">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={{ user, isLoading, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}