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

describe("globals.css — L2 semantic color tokens", () => {
    const css = readFile("app/globals.css");

    const l2Vars = [
        "--color-correct",
        "--color-correct-bg",
        "--color-incorrect",
        "--color-incorrect-bg",
        "--color-pending",
        "--color-pending-bg",
        "--color-info",
        "--color-info-bg",
        "--color-brand",
    ];

    for (const v of l2Vars) {
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
        "--shadow-glow-brand",
        "--shadow-glow-correct",
        "--shadow-glow-incorrect",
    ];

    for (const v of l3Vars) {
        it(`declares ${v}`, () => {
            expect(css).toContain(v);
        });
    }

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

describe("tailwind.config — L2 semantic colors", () => {
    const cfg = readFile("tailwind.config.ts");

    // Hyphenated keys are quoted; bare keys are not
    it("has color.correct", () => { expect(cfg).toContain("correct:"); });
    it("has color.correct-bg", () => { expect(cfg).toContain("'correct-bg'"); });
    it("has color.incorrect", () => { expect(cfg).toContain("incorrect:"); });
    it("has color.incorrect-bg", () => { expect(cfg).toContain("'incorrect-bg'"); });
    it("has color.pending", () => { expect(cfg).toContain("pending:"); });
    it("has color.pending-bg", () => { expect(cfg).toContain("'pending-bg'"); });
    it("has color.info", () => { expect(cfg).toContain("info:"); });
    it("has color.info-bg", () => { expect(cfg).toContain("'info-bg'"); });
    it("references --color-correct CSS variable", () => { expect(cfg).toContain("--color-correct"); });
    it("references --color-incorrect CSS variable", () => { expect(cfg).toContain("--color-incorrect"); });
    it("references --color-pending CSS variable", () => { expect(cfg).toContain("--color-pending"); });
    it("references --color-info CSS variable", () => { expect(cfg).toContain("--color-info"); });
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

describe("tailwind.config — L3 box shadows", () => {
    const cfg = readFile("tailwind.config.ts");

    it("has shadow glow-brand", () => { expect(cfg).toContain("'glow-brand'"); });
    it("has shadow glow-correct", () => { expect(cfg).toContain("'glow-correct'"); });
    it("has shadow glow-incorrect", () => { expect(cfg).toContain("'glow-incorrect'"); });
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
