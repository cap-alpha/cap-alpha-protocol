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
                // Micro-typography — consolidates the arbitrary text-[9px]/[10px]/[11px]
                // values found in dense data tables (design audit §2.5, issue #1070
                // Phase 5). 12px call sites map to the existing `text-xs` (0.75rem).
                // No explicit lineHeight set (unlike the other scale entries above) —
                // the arbitrary text-[Npx] values being replaced only ever set
                // font-size and relied on inherited line-height; matching that keeps
                // this a font-size-only change with zero line-height shift.
                'micro': '0.6875rem',
                'micro-sm': '0.625rem',
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
                //
                // Wrapped in hsl(var(...) / <alpha-value>) — same convention as the
                // shadcn tokens above — NOT bare var(...). The underlying custom
                // properties are stored as HSL channel triples in globals.css
                // specifically so this works: bare `var(--x)` colors compile plain
                // utilities (`bg-navy`) fine but silently emit ZERO CSS for any
                // opacity-modifier variant (`bg-navy/10`), verified against
                // tailwindcss@3.4.19 (this repo's pinned version). Fixed here
                // 2026-07-20 after adversarial review caught the bug across 38+
                // downstream call sites in #1114/#1117.
                ink: 'hsl(var(--ink) / <alpha-value>)',
                'ink-2': 'hsl(var(--ink-2) / <alpha-value>)',
                'ink-3': 'hsl(var(--ink-3) / <alpha-value>)',
                'accent-editorial': 'hsl(var(--accent-editorial) / <alpha-value>)',
                'accent-editorial-light': 'hsl(var(--accent-editorial-light) / <alpha-value>)',
                correct: 'hsl(var(--correct) / <alpha-value>)',
                incorrect: 'hsl(var(--incorrect) / <alpha-value>)',
                pending: 'hsl(var(--pending) / <alpha-value>)',
                // Legacy V1 Data Editorial aliases — see globals.css comment. Do
                // not add new consumers; removal tracked under #1070.
                navy: 'hsl(var(--navy) / <alpha-value>)',
                'navy-light': 'hsl(var(--navy-light) / <alpha-value>)',
                gold: 'hsl(var(--gold) / <alpha-value>)',
                'gold-light': 'hsl(var(--gold-light) / <alpha-value>)',
                'editorial-bg': 'hsl(var(--bg) / <alpha-value>)',
                'editorial-card': 'hsl(var(--bg-card) / <alpha-value>)',
                'editorial-border': 'hsl(var(--border-editorial) / <alpha-value>)',
                pos: 'hsl(var(--pos) / <alpha-value>)',
                neg: 'hsl(var(--neg) / <alpha-value>)',
                warn: 'hsl(var(--warn) / <alpha-value>)',
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
