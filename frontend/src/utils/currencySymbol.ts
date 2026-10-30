const SYMBOLS: Record<string, string> = {
  INR: '₹',
  USD: '$',
  EUR: '€',
  GBP: '£',
  JPY: '¥',
  SGD: 'S$',
  AUD: 'A$',
  AED: 'AED ',
  CHF: 'CHF ',
};

/** Display symbol for an ISO currency code; unknown codes show the code itself (never assume dollars). */
export function currencySymbol(currency?: string | null): string {
  const code = (currency || 'INR').toUpperCase();
  return SYMBOLS[code] ?? `${code} `;
}
