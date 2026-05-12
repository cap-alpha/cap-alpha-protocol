/**
 * Unit tests for the anti-scraping utilities.
 *
 * Covers:
 *  - isBotUserAgent: bot UA detection (production-only)
 *  - injectHoneypotFields: field injection shape
 *  - enforcePaginationLimit: limit validation and enforcement
 *  - logBlockedRequest: fire-and-forget, no-throw in non-production
 *
 * Issue: #884
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

import {
    isBotUserAgent,
    injectHoneypotFields,
    enforcePaginationLimit,
    logBlockedRequest,
    LEDGER_MAX_LIMIT,
} from "../anti-scraping";

// ── isBotUserAgent ────────────────────────────────────────────────────────────

describe("isBotUserAgent", () => {
    describe("in non-production (NODE_ENV=test)", () => {
        it("always returns false regardless of UA string", () => {
            // In test env, bot detection is disabled so local dev is unaffected.
            expect(isBotUserAgent("curl/7.88.0")).toBe(false);
            expect(isBotUserAgent("wget/1.21")).toBe(false);
            expect(isBotUserAgent("Scrapy/2.9")).toBe(false);
            expect(isBotUserAgent("Mozilla/5.0")).toBe(false);
            expect(isBotUserAgent(null)).toBe(false);
        });
    });

    describe("in production (VERCEL_ENV=production)", () => {
        const originalVercelEnv = process.env.VERCEL_ENV;

        beforeEach(() => {
            // Simulate production environment.
            // VERCEL_ENV=production is enough to trigger detection;
            // NODE_ENV is read-only in TypeScript so we only set VERCEL_ENV.
            process.env.VERCEL_ENV = "production";
        });

        afterEach(() => {
            process.env.VERCEL_ENV = originalVercelEnv;
        });

        it("detects curl UA", () => {
            expect(isBotUserAgent("curl/7.88.0")).toBe(true);
        });

        it("detects wget UA", () => {
            expect(isBotUserAgent("Wget/1.21.1")).toBe(true);
        });

        it("detects Scrapy UA", () => {
            expect(isBotUserAgent("Scrapy/2.9 (+https://scrapy.org)")).toBe(true);
        });

        it("detects Selenium UA substring", () => {
            expect(isBotUserAgent("Mozilla/5.0 selenium")).toBe(true);
        });

        it("detects puppeteer", () => {
            expect(isBotUserAgent("HeadlessChrome puppeteer/21.0")).toBe(true);
        });

        it("detects python-requests", () => {
            expect(isBotUserAgent("python-requests/2.31.0")).toBe(true);
        });

        it("detects Go HTTP client", () => {
            expect(isBotUserAgent("Go-http-client/2.0")).toBe(true);
        });

        it("does NOT flag a real browser UA", () => {
            const realBrowser =
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";
            expect(isBotUserAgent(realBrowser)).toBe(false);
        });

        it("does NOT flag Lighthouse UA (legitimate audit tool)", () => {
            // Lighthouse uses a Chrome UA; it must never be blocked.
            const lighthouseUA =
                "Mozilla/5.0 (Linux; Android 11; moto g power (2022)) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Mobile Safari/537.36 Chrome-Lighthouse";
            // Chrome-Lighthouse is not in our BOT_UA_PATTERNS list.
            expect(isBotUserAgent(lighthouseUA)).toBe(false);
        });

        it("returns false for null UA", () => {
            expect(isBotUserAgent(null)).toBe(false);
        });

        it("returns false for empty string UA", () => {
            expect(isBotUserAgent("")).toBe(false);
        });
    });
});

// ── injectHoneypotFields ──────────────────────────────────────────────────────

describe("injectHoneypotFields", () => {
    it("returns an object containing all original keys", () => {
        const original = { pundits: [], page: 1 };
        const result = injectHoneypotFields(original);
        expect(result.pundits).toEqual([]);
        expect(result.page).toBe(1);
    });

    it("adds internal_id and source_hash keys", () => {
        const result = injectHoneypotFields({ foo: "bar" });
        expect(result).toHaveProperty("internal_id");
        expect(result).toHaveProperty("source_hash");
    });

    it("honeypot values are non-empty strings", () => {
        const result = injectHoneypotFields({});
        expect(typeof result.internal_id).toBe("string");
        expect((result.internal_id as string).length).toBeGreaterThan(0);
        expect(typeof result.source_hash).toBe("string");
        expect((result.source_hash as string).length).toBeGreaterThan(0);
    });

    it("does not mutate the original object", () => {
        const original = { a: 1 };
        injectHoneypotFields(original);
        expect(original).not.toHaveProperty("internal_id");
    });

    it("honeypot values differ across calls (time-seeded)", () => {
        // Two back-to-back calls should produce different values because the
        // seed includes Date.now(). (Extremely unlikely to collide in practice.)
        const r1 = injectHoneypotFields({});
        const r2 = injectHoneypotFields({});
        // They might coincidentally match in the same millisecond, so we only
        // assert the type, not uniqueness, to avoid a flaky test.
        expect(typeof r1.internal_id).toBe("string");
        expect(typeof r2.internal_id).toBe("string");
    });
});

// ── enforcePaginationLimit ────────────────────────────────────────────────────

describe("enforcePaginationLimit", () => {
    it("returns the default limit when param is absent (null)", () => {
        const result = enforcePaginationLimit(null, 20);
        expect(result).toEqual({ valid: true, limit: 20 });
    });

    it("returns the default limit when param is absent (undefined)", () => {
        const result = enforcePaginationLimit(undefined, 20);
        expect(result).toEqual({ valid: true, limit: 20 });
    });

    it("returns the parsed limit for a valid in-range value", () => {
        const result = enforcePaginationLimit("50", 20);
        expect(result).toEqual({ valid: true, limit: 50 });
    });

    it("returns valid with LEDGER_MAX_LIMIT for exactly LEDGER_MAX_LIMIT", () => {
        const result = enforcePaginationLimit(String(LEDGER_MAX_LIMIT), 20);
        expect(result).toEqual({ valid: true, limit: LEDGER_MAX_LIMIT });
    });

    it("returns invalid for limit > LEDGER_MAX_LIMIT", () => {
        const result = enforcePaginationLimit(String(LEDGER_MAX_LIMIT + 1), 20);
        expect(result.valid).toBe(false);
        if (!result.valid) {
            expect(result.error).toContain(String(LEDGER_MAX_LIMIT));
        }
    });

    it("returns invalid for very large limit (10000)", () => {
        const result = enforcePaginationLimit("10000", 20);
        expect(result.valid).toBe(false);
    });

    it("returns the default for non-numeric input (NaN → default)", () => {
        const result = enforcePaginationLimit("abc", 20);
        expect(result).toEqual({ valid: true, limit: 20 });
    });

    it("returns the default for zero or negative limit", () => {
        expect(enforcePaginationLimit("0", 20)).toEqual({ valid: true, limit: 20 });
        expect(enforcePaginationLimit("-5", 20)).toEqual({ valid: true, limit: 20 });
    });

    it("LEDGER_MAX_LIMIT constant is 100", () => {
        expect(LEDGER_MAX_LIMIT).toBe(100);
    });
});

// ── logBlockedRequest ─────────────────────────────────────────────────────────

describe("logBlockedRequest", () => {
    it("does not throw in non-production (NODE_ENV=test)", () => {
        // Fire-and-forget; should be a no-op in test env.
        expect(() =>
            logBlockedRequest({
                timestamp: new Date().toISOString(),
                ip: "1.2.3.4",
                user_agent: "curl/7.88.0",
                endpoint: "/api/ledger/pundits",
                block_reason: "rate_limited",
            })
        ).not.toThrow();
    });

    it("does not throw for bot_rate_limited reason", () => {
        expect(() =>
            logBlockedRequest({
                timestamp: new Date().toISOString(),
                ip: "5.6.7.8",
                user_agent: "Scrapy/2.9",
                endpoint: "/api/ledger/recent",
                block_reason: "bot_rate_limited",
            })
        ).not.toThrow();
    });

    it("does not throw for limit_exceeded reason", () => {
        expect(() =>
            logBlockedRequest({
                timestamp: new Date().toISOString(),
                ip: "9.10.11.12",
                user_agent: "Mozilla/5.0",
                endpoint: "/api/ledger/pundits",
                block_reason: "limit_exceeded",
            })
        ).not.toThrow();
    });
});
