/**
 * Design token verification tests (L1/L2/L3)
 *
 * Verifies that:
 * - CSS variables exist in globals.css (L2 semantic colors + L3 depth tokens)
 * - Tailwind config contains all new color, shadow, and fontSize keys
 * - Font variables are exposed correctly via CSS variables in layout.tsx
 * - Homepage h1 uses the new typography tokens
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { resolve } from "path";

const ROOT = resolve(__dirname, "..");

function readFile(rel: string): string {
    return readFileSync(resolve(ROOT, rel), "utf-8");
}

// ---------------------------------------------------------------------------
// CSS variable presence in globals.css
// ---------------------------------------------------------------------------

// Updated 2026-07-20 (#1071, #1113): the L2 "semantic outcome colors" block
// this originally asserted (--color-correct(-bg)/--color-incorrect(-bg)/
// --color-pending(-bg)/--color-info(-bg)/--color-brand) was removed —
// zero consumers anywhere in app/components, and it duplicated the
// editorial --pos/--neg/--warn tokens that were already doing the same
// job under a different name. Asserting the canonical editorial token set
// that replaced it instead. See globals.css and docs/design/2026-06-design-brief.md.
describe("globals.css — editorial palette tokens (canonical, #1071)", () => {
    const css = readFile("app/globals.css");

    const editorialVars = [
        "--canvas",
        "--surface",
        "--ink",
        "--ink-2",
        "--ink-3",
        "--border-editorial",
        "--accent-editorial",
        "--correct",
        "--incorrect",
        "--pending",
    ];

    for (const v of editorialVars) {
        it(`declares ${v}`, () => {
            expect(css).toContain(v);
        });
    }
});

describe("globals.css — L3 depth tokens", () => {
    const css = readFile("app/globals.css");

    const l3Vars = [
        "--color-canvas",
        "--color-surface",
        "--color-elevated",
    ];

    for (const v of l3Vars) {
        it(`declares ${v}`, () => {
            expect(css).toContain(v);
        });
    }

    // boxShadow.glow-* (and the --shadow-glow-* vars this file used to
    // assert) were removed in #1071 — zero consumers, and glow effects are
    // explicitly against the editorial direction ("no glow, no
    // glassmorphism", docs/design/2026-06-design-brief.md).
    it("does not declare removed glow shadow tokens", () => {
        expect(css).not.toContain("--shadow-glow-brand");
        expect(css).not.toContain("--shadow-glow-correct");
        expect(css).not.toContain("--shadow-glow-incorrect");
    });

    it("body uses bg-canvas instead of bg-background or bg-black", () => {
        expect(css).toContain("bg-canvas");
    });
});

// ---------------------------------------------------------------------------
// Tailwind config — L1 typography scale (text-based checks)
// ---------------------------------------------------------------------------

describe("tailwind.config — L1 fontSize scale", () => {
    const cfg = readFile("tailwind.config.ts");

    const expectedKeys = [
        "display-xl",
        "display-lg",
        "display-md",
        "heading-xl",
        "heading-lg",
        "heading-md",
        "body-lg",
        "body-md",
        "body-sm",
        "label",
        "mono-lg",
        "mono-sm",
    ];

    for (const key of expectedKeys) {
        it(`has fontSize entry '${key}'`, () => {
            expect(cfg).toContain(`'${key}'`);
        });
    }
});

describe("tailwind.config — L1 fontFamily", () => {
    const cfg = readFile("tailwind.config.ts");

    it("fontFamily has Instrument Serif", () => {
        expect(cfg).toContain("Instrument Serif");
    });

    it("fontFamily has Inter", () => {
        expect(cfg).toContain("Inter");
    });

    it("fontFamily has JetBrains Mono", () => {
        expect(cfg).toContain("JetBrains Mono");
    });

    it("fontFamily has serif, sans, mono keys", () => {
        expect(cfg).toContain("serif:");
        expect(cfg).toContain("sans:");
        expect(cfg).toContain("mono:");
    });
});

// ---------------------------------------------------------------------------
// Tailwind config — L2 semantic colors (text-based checks)
// ---------------------------------------------------------------------------

// Updated 2026-07-20 (#1071, #1113): color.correct/incorrect/pending now
// reference the canonical --correct/--incorrect/--pending tokens directly
// (no "-bg" variants, no "info" concept — those were dead L2 tokens with
// zero consumers, removed alongside the CSS vars). Also asserts the
// hsl(var(...) / <alpha-value>) wrapping specifically, since a bare
// var(--x) reference compiles but silently drops every Tailwind opacity
// modifier (e.g. `ring-correct/30`) — a real bug caught by adversarial
// review after #1113 originally shipped without it.
describe("tailwind.config — editorial semantic colors (canonical, #1071)", () => {
    const cfg = readFile("tailwind.config.ts");

    it("has color.correct", () => { expect(cfg).toContain("correct:"); });
    it("has color.incorrect", () => { expect(cfg).toContain("incorrect:"); });
    it("has color.pending", () => { expect(cfg).toContain("pending:"); });
    it("references --correct CSS variable", () => { expect(cfg).toContain("var(--correct)"); });
    it("references --incorrect CSS variable", () => { expect(cfg).toContain("var(--incorrect)"); });
    it("references --pending CSS variable", () => { expect(cfg).toContain("var(--pending)"); });

    const alphaValueColors = [
        "ink", "ink-2", "ink-3", "accent-editorial", "correct", "incorrect",
        "pending", "navy", "gold", "editorial-bg", "editorial-card", "editorial-border",
    ];
    for (const key of alphaValueColors) {
        it(`color.${key} supports opacity modifiers (hsl(...) / <alpha-value> wrapping)`, () => {
            const re = new RegExp(`'?${key}'?:\\s*'hsl\\(var\\([^)]+\\)\\s*/\\s*<alpha-value>\\)'`);
            expect(cfg).toMatch(re);
        });
    }
});

// ---------------------------------------------------------------------------
// Tailwind config — L3 depth colors + shadows
// ---------------------------------------------------------------------------

describe("tailwind.config — L3 depth colors", () => {
    const cfg = readFile("tailwind.config.ts");

    it("has color.canvas", () => { expect(cfg).toContain("canvas:"); });
    it("has color.surface", () => { expect(cfg).toContain("surface:"); });
    it("has color.elevated", () => { expect(cfg).toContain("elevated:"); });
});

// boxShadow.glow-* removed in #1071 — zero consumers, and glow effects are
// explicitly against the editorial direction. Asserting absence instead of
// deleting this describe block outright, so a future re-add doesn't slip
// back in silently.
describe("tailwind.config — L3 box shadows (removed, #1071)", () => {
    const cfg = readFile("tailwind.config.ts");

    it("does not have shadow glow-brand/glow-correct/glow-incorrect", () => {
        expect(cfg).not.toContain("'glow-brand'");
        expect(cfg).not.toContain("'glow-correct'");
        expect(cfg).not.toContain("'glow-incorrect'");
    });
});

// ---------------------------------------------------------------------------
// Font variable exposure in layout.tsx
// ---------------------------------------------------------------------------

describe("layout.tsx — font CSS variables", () => {
    const layout = readFile("app/layout.tsx");

    it("exposes --font-sans via Inter variable", () => {
        expect(layout).toContain("--font-sans");
    });

    it("exposes --font-serif via Instrument_Serif variable", () => {
        expect(layout).toContain("--font-serif");
    });

    it("exposes --font-mono via JetBrains_Mono variable", () => {
        expect(layout).toContain("--font-mono");
    });

    it("imports Instrument_Serif from next/font/google", () => {
        expect(layout).toContain("Instrument_Serif");
    });

    it("imports JetBrains_Mono from next/font/google", () => {
        expect(layout).toContain("JetBrains_Mono");
    });
});

// ---------------------------------------------------------------------------
// Homepage h1 uses serif + display-xl
// ---------------------------------------------------------------------------

describe("page.tsx — homepage h1 typography", () => {
    const page = readFile("app/page.tsx");

    it("h1 uses font-serif", () => {
        expect(page).toMatch(/h1[^>]*font-serif/);
    });

    it("h1 uses text-display-xl", () => {
        expect(page).toMatch(/h1[^>]*text-display-xl/);
    });
});
