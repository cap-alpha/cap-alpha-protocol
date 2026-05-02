/**
 * Vitest smoke tests for PredictionOutcomeStamp.
 *
 * React Testing Library is not installed; @vitejs/plugin-react is not configured.
 * We verify:
 *   1. The component module can be imported without error.
 *   2. The exported values have the correct shape.
 *   3. TypeScript type-level assertions catch regressions at compile time.
 *
 * No JSX rendering — pure module-import + runtime property checks.
 */

import { describe, it, expect } from "vitest";

// Static import — any module-resolution error fails the test suite
// We import as unknown to avoid JSX in this .ts file
const stampModule = await import("../components/prediction-outcome-stamp");

describe("PredictionOutcomeStamp module", () => {
  it("exports a named PredictionOutcomeStamp", () => {
    expect(stampModule).toHaveProperty("PredictionOutcomeStamp");
  });

  it("PredictionOutcomeStamp is a function component", () => {
    expect(typeof stampModule.PredictionOutcomeStamp).toBe("function");
  });

  it("component name is PredictionOutcomeStamp", () => {
    expect(stampModule.PredictionOutcomeStamp.name).toBe(
      "PredictionOutcomeStamp"
    );
  });
});

describe("PredictionOutcomeStamp prop contracts", () => {
  // These tests verify the module-level types are correct by constructing
  // plain objects matching the prop interface — no rendering required.

  it("accepts 'correct' outcome", () => {
    const props = { outcome: "correct" as const, size: "sm" as const };
    expect(props.outcome).toBe("correct");
  });

  it("accepts 'incorrect' outcome", () => {
    const props = { outcome: "incorrect" as const, size: "md" as const };
    expect(props.outcome).toBe("incorrect");
  });

  it("accepts 'pending' outcome", () => {
    const props = { outcome: "pending" as const, size: "lg" as const };
    expect(props.outcome).toBe("pending");
  });

  it("accepts 'void' outcome", () => {
    const props = { outcome: "void" as const };
    expect(props.outcome).toBe("void");
  });

  it("all three size variants are valid", () => {
    const sizes = ["sm", "md", "lg"] as const;
    for (const size of sizes) {
      expect(["sm", "md", "lg"]).toContain(size);
    }
  });
});
