
import { calculateTradeImpact, generateTradeGrade, TradeAsset } from '../lib/trade-logic';

describe('Trade Logic', () => {
    const mockPlayer: TradeAsset = {
        id: 'p1',
        name: 'Test Player',
        team: 'KC',
        position: 'QB',
        cap_hit_millions: 20,
        dead_cap_millions: 10,
        risk_score: 0.5,
        surplus_value: 5,
        type: 'player'
    };

    test('calculateTradeImpact: Basic Trade (Pre-June 1)', () => {
        // Scenario: KC trades player.
        // KC Clears: 20M (Salary)
        // KC Takes: 10M (Dead Money)
        // Net: +10M
        const impact = calculateTradeImpact('KC', [], [mockPlayer], false);

        expect(impact.cap_cleared).toBe(20);
        expect(impact.dead_money_acceleration).toBe(10);
        expect(impact.net_cap_change).toBe(10);
    });

    test('calculateTradeImpact: Post-June 1 Designation', () => {
        // Scenario: KC trades player post-June 1.
        // KC Clears: 20M
        // KC Takes: 5M (50% of 10M)
        // Net: +15M
        const impact = calculateTradeImpact('KC', [], [mockPlayer], true);

        expect(impact.dead_money_acceleration).toBe(5);
        expect(impact.net_cap_change).toBe(15);
    });

    test('calculateTradeImpact: Acquiring Player', () => {
        // Scenario: MIN acquires player.
        // MIN Clears: 0
        // MIN Takes: 16M (80% of 20M cap hit as salary)
        // Net: -16M
        const impact = calculateTradeImpact('MIN', [mockPlayer], [], false);

        expect(impact.net_cap_change).toBe(-16);
    });

    test('generateTradeGrade: Balanced Trade', () => {
        // KC saves 10M, MIN takes 10M hit but gets 5M surplus value
        const impactA = calculateTradeImpact('KC', [], [mockPlayer], false); // +10M
        const impactB = calculateTradeImpact('MIN', [mockPlayer], [], false); // -16M (-6 net total)

        // Total Net Change: -6
        // Surplus: +5

        const result = generateTradeGrade(impactA, impactB);
        expect(result.success).toBe(true);
        // Score logic: 70 + 5 (A positive) + 5 (Surplus) = 80
        // Actually Logic: 
        // Start 70
        // A.net > 0 (+5) -> 75
        // B.net < 0 (+0) -> 75
        // Surplus A (0) + Surplus B (5) -> 80
        // Grade should be B- or better

        expect(result.score).toBeGreaterThanOrEqual(80);
    });
});
