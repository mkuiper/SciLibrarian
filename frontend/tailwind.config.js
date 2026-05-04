/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        slate: {
          850: '#1a2236',
          950: '#0d1424',
        },
        alexandria: {
          50:  '#f0f4ff',
          100: '#dce7ff',
          200: '#bcd0ff',
          300: '#8aadff',
          400: '#547eff',
          500: '#2d55f5',
          600: '#1a38eb',
          700: '#1629d4',
          800: '#1825ac',
          900: '#192487',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        serif: ['Georgia', 'Cambria', 'serif'],
      },
    },
  },
  plugins: [],
}
