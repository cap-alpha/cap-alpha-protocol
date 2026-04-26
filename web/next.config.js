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
        return [
            {
                source: '/(.*)',
                headers: [
                    {
                        key: 'Content-Security-Policy',
                        value: "worker-src 'self' blob:;",
                    },
                    {
                        key: 'Strict-Transport-Security',
                        value: 'max-age=63072000; includeSubDomains; preload',
                    },
                    {
                        key: 'X-Content-Type-Options',
                        value: 'nosniff',
                    },
                    {
                        key: 'X-Frame-Options',
                        value: 'DENY',
                    },
                    {
                        key: 'Referrer-Policy',
                        value: 'strict-origin-when-cross-origin',
                    },
                ],
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
