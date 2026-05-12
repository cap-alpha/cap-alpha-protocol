// @ts-check
const { withSentryConfig } = require("@sentry/nextjs");

/** @type {import('next').NextConfig} */
const nextConfig = {
    images: {
        remotePatterns: [
            {
                protocol: "https",
                hostname: "a.espncdn.com",
                pathname: "/i/teamlogos/**",
            },
        ],
    },
    experimental: {
        serverComponentsExternalPackages: ['duckdb', 'duckdb-async', '@mapbox/node-pre-gyp', 'node-gyp'],
    },
    webpack: (config, { isServer }) => {
        if (isServer) {
            config.externals.push('duckdb', 'duckdb-async');
        }
        return config;
    },
    typescript: {
        ignoreBuildErrors: true,
    },
    eslint: {
        ignoreDuringBuilds: true,
    },
    async headers() {
        // Content-Security-Policy:
        //   - default-src 'self'                      block unlisted origins by default
        //   - script-src: Clerk (auth UI), Stripe (checkout), Sentry replay SDK
        //   - style-src: 'unsafe-inline' required by Clerk/Tailwind CSS-in-JS
        //   - font-src: Google Fonts static assets
        //   - connect-src: API backend, Clerk API, Sentry ingest, Stripe API
        //   - img-src: ESPN logos (remotePatterns), Clerk avatar CDN, data URIs
        //   - frame-src: Stripe 3DS/checkout iframes
        //   - worker-src: blob: for Sentry replay worker
        const csp = [
            "default-src 'self'",
            // Scripts — Clerk injects its own <script> tags; Stripe needs js.stripe.com
            "script-src 'self' 'unsafe-inline' https://clerk.cap-alpha.co https://*.clerk.accounts.dev https://js.stripe.com https://browser.sentry-cdn.com https://js.sentry-cdn.com https://*.sentry.io",
            // Styles — Tailwind + Clerk require inline styles at runtime
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            // Fonts — Google Fonts static files
            "font-src 'self' https://fonts.gstatic.com",
            // Connections — API backend, Clerk, Sentry ingest, Stripe
            "connect-src 'self' https://clerk.cap-alpha.co https://*.clerk.accounts.dev https://api.clerk.dev https://*.ingest.sentry.io https://*.ingest.us.sentry.io https://api.stripe.com https://generativelanguage.googleapis.com https://pundit-ledger-api-wvhvx2muna-uc.a.run.app",
            // Images — ESPN team logos, Clerk user avatars, data URIs for OG images
            "img-src 'self' data: blob: https://a.espncdn.com https://img.clerk.com https://*.clerk.com",
            // Frames — Stripe 3DS and checkout iframes
            "frame-src 'self' https://js.stripe.com https://hooks.stripe.com",
            // Workers — Sentry replay uses a blob: worker
            "worker-src 'self' blob:",
            // Media — no external audio/video sources needed
            "media-src 'none'",
            // Object — no Flash/plugin embeds
            "object-src 'none'",
            // Base — prevent base-tag hijacking
            "base-uri 'self'",
            // Form submissions — only to self
            "form-action 'self'",
            // Frame ancestors — replaces X-Frame-Options for CSP-aware browsers
            "frame-ancestors 'self'",
        ].join('; ');

        return [
            {
                source: '/(.*)',
                headers: [
                    {
                        key: 'Content-Security-Policy',
                        value: csp,
                    },
                    // HSTS: 2-year max-age, include all subdomains, eligible for preload list
                    {
                        key: 'Strict-Transport-Security',
                        value: 'max-age=63072000; includeSubDomains; preload',
                    },
                    // Prevent MIME-type sniffing attacks
                    {
                        key: 'X-Content-Type-Options',
                        value: 'nosniff',
                    },
                    // Keep X-Frame-Options for older browsers (CSP frame-ancestors covers modern ones)
                    {
                        key: 'X-Frame-Options',
                        value: 'SAMEORIGIN',
                    },
                    // Limit referrer info to origin only on cross-origin requests
                    {
                        key: 'Referrer-Policy',
                        value: 'strict-origin-when-cross-origin',
                    },
                    // Disable browser features not used by this app
                    {
                        key: 'Permissions-Policy',
                        value: 'camera=(), microphone=(), geolocation=(), payment=(self "https://js.stripe.com"), usb=(), bluetooth=()',
                    },
                    // Enable DNS prefetching for performance (safe, no privacy leak from self-hosted app)
                    {
                        key: 'X-DNS-Prefetch-Control',
                        value: 'on',
                    },
                ],
            },
        ];
    },
    async redirects() {
        return [
            // Vestigial NFL dead-money era dashboard pages → redirect to bettor-first destinations
            // 301 permanent — these pages have no external link equity and are being retired (#774)
            {
                source: '/dashboard/gm',
                destination: '/ledger',
                permanent: true,
            },
            {
                source: '/dashboard/agent',
                destination: '/ledger',
                permanent: true,
            },
            {
                source: '/dashboard/fan',
                destination: '/ledger',
                permanent: true,
            },
            {
                source: '/dashboard/team-select',
                destination: '/',
                permanent: true,
            },
        ];
    },
    async rewrites() {
        return [
            {
                source: '/api/python/:path*',
                destination: 'http://127.0.0.1:8000/api/:path*', // Proxy to FastAPI
            },
        ]
    },
    env: {
        NEXT_PUBLIC_COMMIT_SHA: process.env.VERCEL_GIT_COMMIT_SHA || 'local-dev',
    },
};

module.exports = withSentryConfig(nextConfig, {
    // Suppress Sentry CLI output during builds
    silent: !process.env.CI,
    // Don't upload source maps unless SENTRY_AUTH_TOKEN is set
    authToken: process.env.SENTRY_AUTH_TOKEN,
    org: process.env.SENTRY_ORG,
    project: process.env.SENTRY_PROJECT || "cap-alpha-protocol",
    // Route browser error reports through Next.js to avoid ad-blockers
    tunnelRoute: "/monitoring-tunnel",
    // Tree-shake Sentry logger in production
    disableLogger: true,
    // Hide source maps from client bundles
    hideSourceMaps: true,
});
