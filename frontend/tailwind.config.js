/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          green: '#86BC25',
          navy: '#000000',
          'navy-light': '#53565A',
          ink: '#000000',
          surface: '#FFFFFF',
          'surface-muted': '#F7F7F5',
          muted: '#53565A',
          border: '#E0E0E0',
        },
        deloitte: {
          green: '#86BC25',
          black: '#000000',
          gray: '#53565A',
          'gray-light': '#BBBCBC',
          navy: '#000000',
          'accent-navy': '#0F172A',
          'dark-slate': '#1e293b',
        },
        success: '#22C55E',
        warning: '#F59E0B',
        error: '#EF4444',
        info: '#0563C1',
      },
      fontFamily: {
        sans: ['Open Sans', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      width: {
        'sidebar-expanded': '240px',
        'sidebar-collapsed': '60px',
      },
      spacing: {
        'sidebar-expanded': '240px',
        'sidebar-collapsed': '60px',
      },
    },
  },
  plugins: [],
}
