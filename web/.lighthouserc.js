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
      },
    },
    upload: {
      target: 'temporary-public-storage',
    },
  },
};
