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
        // ── Category-level thresholds (enforced) ──────────────────────────────
        'categories:performance': ['warn', {minScore: 0.9}],
        'categories:accessibility': ['error', {minScore: 0.9}],
        'categories:best-practices': ['error', {minScore: 0.9}],
        'categories:seo': ['warn', {minScore: 0.9}],
        // ── Core Web Vitals ───────────────────────────────────────────────────
        'first-contentful-paint': ['warn', {maxNumericValue: 3000}],
        'largest-contentful-paint': ['warn', {maxNumericValue: 4000}],
        'cumulative-layout-shift': ['warn', {maxNumericValue: 0.1}],
        // ── Audits that produce no numeric score — minScore is invalid ────────
        'lcp-lazy-loaded': 'off',
        'non-composited-animations': 'off',
        'prioritize-lcp-image': 'off',
        // ── Third-party auth (Clerk) — third-party cookies are unavoidable ───
        'third-party-cookies': ['warn', {minScore: 0}],
        // ── Best-practices individual audits (Clerk-driven) ───────────────────
        'errors-in-console': ['warn', {minScore: 0}],
        'inspector-issues': ['warn', {minScore: 0}],
        // ── Accessibility — design-system improvements tracked separately ─────
        'color-contrast': ['warn', {minScore: 0}],
        'link-in-text-block': ['warn', {minScore: 0}],
        // ── SEO ───────────────────────────────────────────────────────────────
        'link-text': ['warn', {minScore: 0}],
        'is-crawlable': ['warn', {minScore: 0}],  // /status intentionally noindex
        // ── Performance / bundle size ─────────────────────────────────────────
        'unused-css-rules': ['warn', {maxLength: 5}],
        'unused-javascript': ['warn', {maxLength: 10}],
        'uses-rel-preconnect': ['warn', {maxLength: 3}],
        // ── bfcache — complex server-header fix, tracked separately ──────────
        'bf-cache': ['warn', {minScore: 0}],
      },
    },
    upload: {
      target: 'temporary-public-storage',
    },
  },
};
