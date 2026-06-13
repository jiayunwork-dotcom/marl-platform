/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        grid: {
          empty: '#f0f0f0',
          obstacle: '#374151',
          resource: '#10b981',
          spawn: '#3b82f6',
          target: '#f59e0b',
        },
      },
    },
  },
  plugins: [],
}
