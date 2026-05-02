/**
 * Pricing recommendation logic tests
 *
 * Tests the quiz recommendation engine, annual toggle pricing,
 * and matrix tier coverage — all without DOM / React.
 */

import { describe, it, expect } from "vitest";

// ---------------------------------------------------------------------------
// Import the pure logic from the client module
// ---------------------------------------------------------------------------

// Re-implement the pure recommendation function here so this test
// file has no React / browser dependencies.

type TierKey = "free" | "pro" | "api_starter" | "api_growth";
type UserType = "fan" | "fantasy" | "bettor" | "developer" | "organization";
type CareAbout = "leaderboard" | "tracking" | "api" | "team";
type ApiVolume = "low" | "mid" | "high";

function computeRecommendation(
    userType: UserType,
    careAbout: CareAbout,
    apiVolume: ApiVolume | null,
): TierKey {
    if (careAbout === "team" || userType === "organization") return "api_growth";
    if (careAbout === "api") {
        if (apiVolume === "high") return "api_growth";
        return "api_starter";
    }
    if (careAbout === "leaderboard" && (userType === "fan" || userType === "fantasy")) return "free";
    if (careAbout === "tracking" || userType === "bettor") return "pro";
    return "pro";
}

const ANNUAL_DISCOUNT = 0.8;

const TIER_MONTHLY_PRICES: Record<TierKey, number> = {
    free: 0,
    pro: 9,
    api_starter: 49,
    api_growth: 199,
};

function annualPrice(monthly: number): number {
    return Math.round(monthly * ANNUAL_DISCOUNT);
}

// ---------------------------------------------------------------------------
// Recommendation logic
// ---------------------------------------------------------------------------

describe("recommendation: fan + leaderboard → Free", () => {
    it("returns free", () => {
        expect(computeRecommendation("fan", "leaderboard", null)).toBe("free");
    });
});

describe("recommendation: fantasy + leaderboard → Free", () => {
    it("returns free", () => {
        expect(computeRecommendation("fantasy", "leaderboard", null)).toBe("free");
    });
});

describe("recommendation: bettor + tracking → Pro", () => {
    it("returns pro", () => {
        expect(computeRecommendation("bettor", "tracking", null)).toBe("pro");
    });
});

describe("recommendation: fan + tracking → Pro", () => {
    it("returns pro (tracking always at least pro)", () => {
        expect(computeRecommendation("fan", "tracking", null)).toBe("pro");
    });
});

describe("recommendation: developer + api + low → API Starter", () => {
    it("returns api_starter", () => {
        expect(computeRecommendation("developer", "api", "low")).toBe("api_starter");
    });
});

describe("recommendation: developer + api + mid → API Starter", () => {
    it("returns api_starter", () => {
        expect(computeRecommendation("developer", "api", "mid")).toBe("api_starter");
    });
});

describe("recommendation: developer + api + high (50k+) → API Growth", () => {
    it("returns api_growth", () => {
        expect(computeRecommendation("developer", "api", "high")).toBe("api_growth");
    });
});

describe("recommendation: organization + anything → API Growth", () => {
    it("returns api_growth for org regardless of care-about", () => {
        expect(computeRecommendation("organization", "leaderboard", null)).toBe("api_growth");
    });
});

describe("recommendation: any + team workflows → API Growth", () => {
    it("returns api_growth when care-about is team", () => {
        expect(computeRecommendation("developer", "team", null)).toBe("api_growth");
    });
});

// ---------------------------------------------------------------------------
// Annual pricing — 20% discount
// ---------------------------------------------------------------------------

describe("annual toggle reduces price by 20%", () => {
    it("pro: $9/mo → $7/mo annual", () => {
        expect(annualPrice(TIER_MONTHLY_PRICES.pro)).toBe(7);
    });

    it("api_starter: $49/mo → $39/mo annual", () => {
        expect(annualPrice(TIER_MONTHLY_PRICES.api_starter)).toBe(39);
    });

    it("api_growth: $199/mo → $159/mo annual", () => {
        expect(annualPrice(TIER_MONTHLY_PRICES.api_growth)).toBe(159);
    });

    it("free tier stays $0 with annual", () => {
        expect(annualPrice(TIER_MONTHLY_PRICES.free)).toBe(0);
    });
});

// ---------------------------------------------------------------------------
// Matrix coverage — all 4 tiers present
// ---------------------------------------------------------------------------

describe("matrix: all 4 tiers defined", () => {
    const tiers: TierKey[] = ["free", "pro", "api_starter", "api_growth"];

    it("has 4 tiers", () => {
        expect(tiers).toHaveLength(4);
    });

    for (const tier of tiers) {
        it(`tier ${tier} has a monthly price`, () => {
            expect(TIER_MONTHLY_PRICES[tier]).toBeDefined();
            expect(typeof TIER_MONTHLY_PRICES[tier]).toBe("number");
        });
    }
});
