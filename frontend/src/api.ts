import { API_BASE_URL } from './config';

/**
 * API Client wrapper that ensures all requests use the correct base URL
 */
export const apiClient = {
  async fetch(endpoint: string, options?: RequestInit) {
    const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`;
    return fetch(url, options);
  },

  async get(endpoint: string, options?: RequestInit) {
    return this.fetch(endpoint, { ...options, method: 'GET' });
  },

  async post(endpoint: string, body?: any, options?: RequestInit) {
    return this.fetch(endpoint, {
      ...options,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  },

  async put(endpoint: string, body?: any, options?: RequestInit) {
    return this.fetch(endpoint, {
      ...options,
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  },

  async delete(endpoint: string, options?: RequestInit) {
    return this.fetch(endpoint, { ...options, method: 'DELETE' });
  },
};
