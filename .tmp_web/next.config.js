/** @type {import('next').NextConfig} */
const nextConfig = {
    experimental: {
        serverComponentsExternalPackages: ['duckdb', '@mapbox/node-pre-gyp', 'node-gyp'],
    },
    webpack: (config, { isServer }) => {
        if (isServer) {
            config.externals.push('duckdb');
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

module.exports = nextConfig;
