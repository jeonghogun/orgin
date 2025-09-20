import axios from 'axios';

const trimTrailingSlash = (value) => value?.replace(/\/+$/, '') ?? '';
const ensureLeadingSlash = (value) => (value.startsWith('/') ? value : `/${value}`);

const rawApiBase = (import.meta.env.VITE_API_BASE_URL ?? '').trim();
const API_BASE_URL = trimTrailingSlash(rawApiBase);

const apiClient = axios.create({
  baseURL: API_BASE_URL || undefined,
});

export const getApiBaseUrl = () => API_BASE_URL;

export const resolveApiUrl = (path = '') => {
  if (!path) {
    return API_BASE_URL || '';
  }

  if (/^https?:\/\//i.test(path)) {
    return path;
  }

  if (!API_BASE_URL) {
    return path;
  }

  return `${API_BASE_URL}${ensureLeadingSlash(path)}`;
};

const rawWsBase = (import.meta.env.VITE_WS_BASE_URL ?? '').trim();
const WS_BASE_URL = trimTrailingSlash(rawWsBase);

const inferWsBase = () => {
  if (WS_BASE_URL) {
    return WS_BASE_URL;
  }

  if (API_BASE_URL) {
    return API_BASE_URL.replace(/^http/i, (match) =>
      match.toLowerCase() === 'https' ? 'wss' : 'ws'
    );
  }

  if (typeof window !== 'undefined' && window.location?.origin) {
    return window.location.origin.replace(/^http/i, (match) =>
      match.toLowerCase() === 'https' ? 'wss' : 'ws'
    );
  }

  return '';
};

export const getWsBaseUrl = () => inferWsBase();

export const resolveWsUrl = (path = '') => {
  if (!path) {
    return inferWsBase();
  }

  if (/^wss?:\/\//i.test(path)) {
    return path;
  }

  const base = inferWsBase();
  if (!base) {
    return path;
  }

  return `${base}${ensureLeadingSlash(path)}`;
};

export default apiClient;
