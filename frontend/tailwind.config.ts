import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Bricolage Grotesque"', 'sans-serif'],
        body: ['"Schibsted Grotesk"', 'sans-serif'],
        mono: ['"Azeret Mono"', 'monospace'],
      },
      colors: {
        bg: 'oklch(97% 0.006 120)',
        fg: 'oklch(18% 0.010 240)',
        accent: 'oklch(45% 0.130 150)',
        'accent-muted': 'oklch(90% 0.040 150)',
        border: 'oklch(87% 0.010 120)',
        muted: 'oklch(60% 0.008 240)',
      },
    },
  },
  plugins: [],
} satisfies Config
