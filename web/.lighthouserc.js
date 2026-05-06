module.exports = {
  ci: {
    collect: {
      url: ['http://localhost:3000/', 'http://localhost:3000/ledger', 'http://localhost:3000/status'],
      startServerCommand: 'npm run start',
      numberOfRuns: 1,
    },
    assert: {
      preset: 'lighthouse:no-pwa',
      assertions: {
        'categories:performance': ['warn', {minScore: 0.9}],
        'categories:accessibility': ['error', {minScore: 0.9}],
        'categories:best-practices': ['error', {minScore: 0.9}],
        'categories:seo': ['warn', {minScore: 0.9}],
        'first-contentful-paint': ['warn', {maxNumericValue: 3000}],
        'largest-contentful-paint': ['warn', {maxNumericValue: 4000}],
        'cumulative-layout-shift': ['warn', {maxNumericValue: 0.1}],

        // Informational audits — minScore is not valid; preset wrongly asserts them
        'lcp-lazy-loaded': 'off',
        'non-composited-animations': 'off',
        'prioritize-lcp-image': 'off',

        // Next.js always ships some unused CSS/JS chunks; maxLength:0 is unreachable
        'unused-css-rules': ['warn', {maxLength: 5}],
        'unused-javascript': ['warn', {maxLength: 10}],

        // Third-party cookies: Clerk sets auth cookies; downgrade to warn
        'third-party-cookies': ['warn', {minScore: 0}],
      },
    },
    upload: {
      target: 'temporary-public-storage',
    },
  },
};
