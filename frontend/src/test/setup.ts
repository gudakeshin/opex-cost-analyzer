import '@testing-library/jest-dom';

// Recharts uses ResizeObserver which is not available in jsdom
class ResizeObserverPolyfill {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserverPolyfill as unknown as typeof ResizeObserver;
