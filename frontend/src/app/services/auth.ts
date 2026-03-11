const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api/v1';

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface User {
  id: number;
  username: string;
  email: string;
  full_name: string;
  disabled: boolean;
  role: string;
}

/**
 * Helper function to make authenticated API calls
 */
export async function fetchWithAuth(url: string, options: RequestInit = {}) {
    // Get token from localStorage
    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
  
    // Add Authorization header if token exists
    const headers: Record<string, string> = {  // Changed from HeadersInit
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string>),
    };
  
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
  
    const response = await fetch(url, {
      ...options,
      headers,
    });
  
    // If unauthorized, clear token and redirect to login
    if (response.status === 401 || response.status === 403) {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('auth_token');
        window.location.href = '/login';
      }
      throw new Error('Unauthorized');
    }
  
    return response;
  }

export class AuthService {
  private static TOKEN_KEY = 'auth_token';

  /**
   * Login with email and password
   */
  static async login(email: string, password: string): Promise<LoginResponse> {
    const formData = new URLSearchParams();
    formData.append('username', email);
    formData.append('password', password);

    const response = await fetch(`${API_BASE_URL}/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: formData.toString(),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Login failed' }));
      throw new Error(error.detail || 'Invalid email or password');
    }

    const data: LoginResponse = await response.json();
    
    // Store token in localStorage
    this.setToken(data.access_token);
    
    return data;
  }

  /**
   * Get current user info
   */
  static async getCurrentUser(): Promise<User> {
    const token = this.getToken();
    
    if (!token) {
      throw new Error('No token found');
    }

    const response = await fetch(`${API_BASE_URL}/auth/me`, {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      this.logout(); // Token invalid, clear it
      throw new Error('Authentication failed');
    }

    return response.json();
  }

  /**
   * Logout - clear token
   */
  static logout(): void {
    if (typeof window !== 'undefined') {
      localStorage.removeItem(this.TOKEN_KEY);
    }
  }

  /**
   * Get stored token
   */
  static getToken(): string | null {
    if (typeof window !== 'undefined') {
      return localStorage.getItem(this.TOKEN_KEY);
    }
    return null;
  }

  /**
   * Store token
   */
  static setToken(token: string): void {
    if (typeof window !== 'undefined') {
      localStorage.setItem(this.TOKEN_KEY, token);
    }
  }

  /**
   * Check if user is authenticated
   */
  static isAuthenticated(): boolean {
    return !!this.getToken();
  }
}

export { API_BASE_URL };