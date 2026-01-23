/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        parchment: {
          50: '#fefdfb',
          100: '#fdf9f3',
          200: '#f9f0e3',
          300: '#f3e4cd',
          400: '#e8d2a8',
          500: '#d9bc7f',
          600: '#c9a45c',
          700: '#b08a3e',
          800: '#8a6c30',
          900: '#6a5226',
        },
        dungeon: {
          50: '#f5f5f5',
          100: '#e8e8e8',
          200: '#d1d1d1',
          300: '#a3a3a3',
          400: '#737373',
          500: '#525252',
          600: '#3d3d3d',
          700: '#2e2e2e',
          800: '#1f1f1f',
          900: '#141414',
        },
      },
      fontFamily: {
        serif: ['Crimson Text', 'Georgia', 'serif'],
        display: ['IM Fell English', 'Georgia', 'serif'],
      },
    },
  },
  plugins: [],
}
