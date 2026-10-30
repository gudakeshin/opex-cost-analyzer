import '@testing-library/jest-dom';

// Recharts uses ResizeObserver which is not available in jsdom
class ResizeObserverPolyfill {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserverPolyfill as unknown as typeof ResizeObserver;

// Node >= 25 ships an experimental `localStorage` global that is undefined unless started with
// --localstorage-file, and it shadows jsdom's. Provide a plain in-memory Storage when that happens.
function ensureStorage(name: 'localStorage' | 'sessionStorage') {
  const current = (globalThis as Record<string, unknown>)[name] as Storage | undefined;
  if (current && typeof current.clear === 'function') return;
  const data = new Map<string, string>();
  const storage: Storage = {
    get length() {
      return data.size;
    },
    clear: () => data.clear(),
    getItem: (key) => (data.has(key) ? (data.get(key) as string) : null),
    key: (index) => Array.from(data.keys())[index] ?? null,
    removeItem: (key) => void data.delete(key),
    setItem: (key, value) => void data.set(key, String(value)),
  };
  Object.defineProperty(globalThis, name, { value: storage, configurable: true });
  if (typeof window !== 'undefined') {
    Object.defineProperty(window, name, { value: storage, configurable: true });
  }
}
ensureStorage('localStorage');
ensureStorage('sessionStorage');
