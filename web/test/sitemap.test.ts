/**
 * Unit tests for web/app/sitemap.ts
 *
 * Strategy: the sitemap module exports a default async function that calls
 * the FastAPI backend. Rather than spinning up a server, we test the
 * guaranteed-static parts — the static routes array — by reading the module
 * source.
 *
 * The `/sitemap.xml` HTTP response is covered by the Playwright E2E suite
 * (tests/e2e/sitemap.spec.ts), which runs against a real deployment.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { resolve } from "path";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const SITEMAP_SRC = readFileSync(
    resolve(__dirname, "../app/sitemap.ts"),
    "utf-8"
);

// ---------------------------------------------------------------------------
// Static routes — contract tests against the source
// ---------------------------------------------------------------------------

describe("sitemap static routes", () => {
    const requiredRoutes = [
        '`${BASE_URL}/`',
        '`${BASE_URL}/ledger`',
        '`${BASE_URL}/methodology`',
        '`${BASE_URL}/pricing`',
        '`${BASE_URL}/docs`',
        '`${BASE_URL}/quality`',
        '`${BASE_URL}/legal/terms`',
        '`${BASE_URL}/legal/privacy`',
        '`${BASE_URL}/legal/disclosure`',
        '`${BASE_URL}/legal/responsible-gambling`',
        '`${BASE_URL}/legal/corrections`',
        '`${BASE_URL}/legal/acceptable-use`',
    ];

    for (const route of requiredRoutes) {
        it(`includes ${route}`, () => {
            expect(SITEMAP_SRC).toContain(route);
        });
    }

    it("sets revalidate to 86400 (daily)", () => {
        expect(SITEMAP_SRC).toContain("revalidate = 86400");
    });
});

// ---------------------------------------------------------------------------
// Auth header — ensure x-api-key is wired up for the pundits fetch
// ---------------------------------------------------------------------------

describe("sitemap API auth", () => {
    it('passes x-api-key header from CAP_ALPHA_INTERNAL_API_KEY env var', () => {
        expect(SITEMAP_SRC).toContain("CAP_ALPHA_INTERNAL_API_KEY");
        expect(SITEMAP_SRC).toContain('"x-api-key"');
    });
});
