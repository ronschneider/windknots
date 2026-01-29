/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./themes/windknots/layouts/**/*.html",
    "./content/**/*.md",
  ],
  theme: {
    extend: {
      colors: {
        'copper': {
          50:  '#fdf8f1',
          100: '#f9edda',
          200: '#f2d7b0',
          300: '#e9bb7d',
          400: '#df9a48',
          500: '#d6802a',
          600: '#c46a20',
          700: '#a3521d',
          800: '#84421f',
          900: '#6c371c',
        },
        'river': {
          50:  '#f0f7fb',
          100: '#dcedf5',
          200: '#bddcea',
          300: '#8ec5da',
          400: '#58a6c4',
          500: '#3d8bab',
          600: '#347191',
          700: '#2e5c76',
          800: '#2b4d63',
          900: '#284154',
        },
      },
      fontFamily: {
        display: ['"Playfair Display"', 'Georgia', 'serif'],
        sans: ['"Source Sans 3"', 'system-ui', 'sans-serif'],
      },
      typography: (theme) => ({
        DEFAULT: {
          css: {
            '--tw-prose-body': theme('colors.slate.700'),
            '--tw-prose-headings': theme('colors.slate.900'),
            '--tw-prose-links': theme('colors.river.700'),
            '--tw-prose-bold': theme('colors.slate.900'),
            '--tw-prose-quotes': theme('colors.slate.600'),
            '--tw-prose-quote-borders': theme('colors.copper.300'),
            h1: { fontFamily: theme('fontFamily.display').join(', ') },
            h2: { fontFamily: theme('fontFamily.display').join(', ') },
            h3: { fontFamily: theme('fontFamily.display').join(', ') },
            h4: { fontFamily: theme('fontFamily.display').join(', ') },
            a: {
              color: theme('colors.river.700'),
              '&:hover': { color: theme('colors.river.900') },
            },
            blockquote: {
              borderLeftColor: theme('colors.copper.300'),
            },
          },
        },
      }),
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}
