/**
 * Regression tests for cache-key normalisation in web/app/actions.ts.
 *
 * Two bugs were fixed (no tests shipped with the fixes):
 *   - playerName variations (different case, extra spaces) produced different
 *     BQ query cache keys, causing duplicate queries.
 *   - position case variations ("QB" vs "qb") caused the same issue for
 *     getPositionalComps.
 *
 * These tests pin the normalised behaviour so a raw ${playerName} or
 * ${position} interpolation regression will immediately fail.
 *
 * Closes #733.
 */

import { describe, it, expect } from 'vitest';
import { buildPlayerCacheKey, buildPositionCacheKey } from '../lib/cache-keys';

// ---------------------------------------------------------------------------
// buildPlayerCacheKey
// ---------------------------------------------------------------------------

describe('buildPlayerCacheKey — normalisation', () => {
  it('canonicalises mixed case to lowercase', () => {
    expect(buildPlayerCacheKey('Patrick Mahomes')).toBe('patrick mahomes');
  });

  it('trims leading and trailing whitespace', () => {
    expect(buildPlayerCacheKey('  Patrick Mahomes  ')).toBe('patrick mahomes');
  });

  it('"Patrick Mahomes" equals "  patrick mahomes  "', () => {
    expect(buildPlayerCacheKey('Patrick Mahomes')).toBe(
      buildPlayerCacheKey('  patrick mahomes  ')
    );
  });

  it('trims + lowercases together', () => {
    expect(buildPlayerCacheKey('  PATRICK MAHOMES  ')).toBe('patrick mahomes');
  });

  it('returns empty string for blank input', () => {
    expect(buildPlayerCacheKey('')).toBe('');
    expect(buildPlayerCacheKey('   ')).toBe('');
  });

  it('preserves internal spaces', () => {
    const key = buildPlayerCacheKey('Travis Kelce');
    expect(key).toBe('travis kelce');
  });
});

// ---------------------------------------------------------------------------
// buildPositionCacheKey
// ---------------------------------------------------------------------------

describe('buildPositionCacheKey — normalisation', () => {
  it('"QB" and "qb" produce the same key', () => {
    expect(buildPositionCacheKey('QB')).toBe(buildPositionCacheKey('qb'));
  });

  it('lowercases the position string', () => {
    expect(buildPositionCacheKey('QB')).toBe('qb');
  });

  it('trims whitespace', () => {
    expect(buildPositionCacheKey('  QB  ')).toBe('qb');
  });

  it('handles mixed case positions', () => {
    expect(buildPositionCacheKey('Rb')).toBe('rb');
    expect(buildPositionCacheKey('WR')).toBe('wr');
  });
});

// ---------------------------------------------------------------------------
// Regression guard — raw interpolation must NOT appear in cache wrappers
//
// This test reads the source file and verifies that none of the five
// unstable_cache wrappers use a bare `${playerName}` or `${position}`
// template literal in their cache-key array.  If someone reverts to raw
// interpolation the test fails immediately.
// ---------------------------------------------------------------------------

describe('actions.ts source — no raw interpolation in cache keys', () => {
  const fs = require('fs');
  const path = require('path');
  const src: string = fs.readFileSync(
    path.resolve(__dirname, '../app/actions.ts'),
    'utf-8'
  );

  // Extract the unstable_cache key array lines (second argument to unstable_cache)
  // They look like:  [`some-key-${expr}`],
  const cacheKeyLines = src
    .split('\n')
    .filter((line: string) => line.includes('unstable_cache') || line.match(/^\s+\[`[^`]+`\]/));

  it('player-timeline cache key uses buildPlayerCacheKey', () => {
    expect(src).toContain('player-timeline-v6-${buildPlayerCacheKey(playerName)}');
    expect(src).not.toContain('player-timeline-v6-${playerName}');
  });

  it('intelligence-feed cache key uses buildPlayerCacheKey', () => {
    expect(src).toContain('intelligence-feed-v5-${buildPlayerCacheKey(playerName)}');
    expect(src).not.toContain('intelligence-feed-v5-${playerName}');
  });

  it('player-audit-ledger cache key uses buildPlayerCacheKey', () => {
    expect(src).toContain('player-audit-ledger-v1-${buildPlayerCacheKey(playerName)}');
    expect(src).not.toContain('player-audit-ledger-v1-${playerName}');
  });

  it('player-fmv-history cache key uses buildPlayerCacheKey', () => {
    expect(src).toContain('player-fmv-history-v1-${buildPlayerCacheKey(playerName)}');
    expect(src).not.toContain('player-fmv-history-v1-${playerName}');
  });

  it('positional-comps cache key uses buildPositionCacheKey', () => {
    expect(src).toContain('positional-comps-v1-${buildPositionCacheKey(position)}');
    expect(src).not.toContain('positional-comps-v1-${position}');
  });
});
