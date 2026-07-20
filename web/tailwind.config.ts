import type { Config } from "tailwindcss"

const config = {
    darkMode: ["class"],
    content: [
        './pages/**/*.{ts,tsx}',
        './components/**/*.{ts,tsx}',
        './app/**/*.{ts,tsx}',
        './src/**/*.{ts,tsx}',
    ],
    prefix: "",
    theme: {
        container: {
            center: true,
            padding: "2rem",
            screens: {
                "2xl": "1400px",
            },
        },
        extend: {
            fontFamily: {
                // V1 Data Editorial fonts (via CSS variables from next/font/google)
                display: ['var(--font-display)', 'Playfair Display', 'Georgia', 'serif'],
                body: ['var(--font-body)', 'Source Sans 3', 'system-ui', 'sans-serif'],
                mono: ['var(--font-mono)', 'JetBrains Mono', 'Fira Code', 'monospace'],
                // Legacy aliases — kept for backward compatibility
                serif: ['var(--font-display)', 'Playfair Display', 'Georgia', 'serif'],
                sans: ['var(--font-body)', 'Source Sans 3', 'system-ui', 'sans-serif'],
            },
            fontSize: {
                'display-xl': ['3.75rem', { lineHeight: '1.05', letterSpacing: '-0.02em', fontWeight: '900' }],
                'display-lg': ['3rem', { lineHeight: '1.08', letterSpacing: '-0.02em', fontWeight: '800' }],
                'display-md': ['2.25rem', { lineHeight: '1.1', letterSpacing: '-0.015em', fontWeight: '700' }],
                'heading-xl': ['1.875rem', { lineHeight: '1.2', letterSpacing: '-0.01em', fontWeight: '700' }],
                'heading-lg': ['1.5rem', { lineHeight: '1.25', letterSpacing: '-0.01em', fontWeight: '600' }],
                'heading-md': ['1.25rem', { lineHeight: '1.3', fontWeight: '600' }],
                'body-lg': ['1.125rem', { lineHeight: '1.6' }],
                'body-md': ['1rem', { lineHeight: '1.6' }],
                'body-sm': ['0.875rem', { lineHeight: '1.5' }],
                'label': ['0.75rem', { lineHeight: '1.4', letterSpacing: '0.06em', fontWeight: '500' }],
                'mono-lg': ['1rem', { lineHeight: '1.5' }],
                'mono-sm': ['0.875rem', { lineHeight: '1.5' }],
            },
            colors: {
                border: "hsl(var(--border))",
                input: "hsl(var(--input))",
                ring: "hsl(var(--ring))",
                background: "hsl(var(--background))",
                foreground: "hsl(var(--foreground))",
                primary: {
                    DEFAULT: "hsl(var(--primary))",
                    foreground: "hsl(var(--primary-foreground))",
                },
                secondary: {
                    DEFAULT: "hsl(var(--secondary))",
                    foreground: "hsl(var(--secondary-foreground))",
                },
                destructive: {
                    DEFAULT: "hsl(var(--destructive))",
                    foreground: "hsl(var(--destructive-foreground))",
                },
                muted: {
                    DEFAULT: "hsl(var(--muted))",
                    foreground: "hsl(var(--muted-foreground))",
                },
                accent: {
                    DEFAULT: "hsl(var(--accent))",
                    foreground: "hsl(var(--accent-foreground))",
                },
                popover: {
                    DEFAULT: "hsl(var(--popover))",
                    foreground: "hsl(var(--popover-foreground))",
                },
                card: {
                    DEFAULT: "hsl(var(--card))",
                    foreground: "hsl(var(--card-foreground))",
                },
                // L3 — Depth system (dark; backs the site-wide body default)
                canvas: 'hsl(var(--color-canvas))',
                surface: 'hsl(var(--color-surface))',
                elevated: 'hsl(var(--color-elevated))',
                // Editorial palette — canonical tokens (docs/design/2026-06-design-brief.md)
                ink: 'var(--ink)',
                'ink-2': 'var(--ink-2)',
                'ink-3': 'var(--ink-3)',
                'accent-editorial': 'var(--accent-editorial)',
                'accent-editorial-light': 'var(--accent-editorial-light)',
                correct: 'var(--correct)',
                incorrect: 'var(--incorrect)',
                pending: 'var(--pending)',
                // Legacy V1 Data Editorial aliases — see globals.css comment. Do
                // not add new consumers; removal tracked under #1070.
                navy: 'var(--navy)',
                'navy-light': 'var(--navy-light)',
                gold: 'var(--gold)',
                'gold-light': 'var(--gold-light)',
                'editorial-bg': 'var(--bg)',
                'editorial-card': 'var(--bg-card)',
                'editorial-border': 'var(--border-editorial)',
                pos: 'var(--pos)',
                neg: 'var(--neg)',
                warn: 'var(--warn)',
            },
            borderRadius: {
                lg: "var(--radius)",
                md: "calc(var(--radius) - 2px)",
                sm: "calc(var(--radius) - 4px)",
            },
            // boxShadow.glow-* removed — zero consumers found (2026-07-20 audit),
            // and glow effects are explicitly against the editorial direction
            // (docs/design/2026-06-design-brief.md: "no glow, no glassmorphism").
            keyframes: {
                "accordion-down": {
                    from: { height: "0" },
                    to: { height: "var(--radix-accordion-content-height)" },
                },
                "accordion-up": {
                    from: { height: "var(--radix-accordion-content-height)" },
                    to: { height: "0" },
                },
            },
            animation: {
                "accordion-down": "accordion-down 0.2s ease-out",
                "accordion-up": "accordion-up 0.2s ease-out",
            },
        },
    },
    plugins: [require("tailwindcss-animate")],
} satisfies Config

export default config
