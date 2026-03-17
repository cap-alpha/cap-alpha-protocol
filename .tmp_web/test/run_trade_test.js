
// --- INLINE LOGIC FOR VERIFICATION (Copy of trade-logic.ts converted to JS) ---

function calculateTradeImpact(team, assetsIn, assetsOut, isPostJune1 = false) {
    const cap_cleared = assetsOut.reduce((sum, a) => sum + (a.cap_hit_millions || 0), 0);

    let dead_money_acceleration = assetsOut.reduce((sum, a) => sum + (a.dead_cap_millions || 0), 0);
    if (isPostJune1) {
        dead_money_acceleration = dead_money_acceleration * 0.5;
    }

    const acquired_salary = assetsIn.reduce((sum, a) => sum + (a.cap_hit_millions * 0.8), 0);
    const net_cap_change = cap_cleared - dead_money_acceleration - acquired_salary;

    return {
        team,
        initial_cap_space: 0,
        cap_cleared,
        dead_money_acceleration,
        net_cap_change,
        assets_acquired: assetsIn,
        assets_lost: assetsOut
    };
}

function generateTradeGrade(impactA, impactB) {
    const totalNetChange = impactA.net_cap_change + impactB.net_cap_change;

    let score = 70; // Start at C-
    if (impactA.net_cap_change > 0) score += 5;
    if (impactB.net_cap_change > 0) score += 5;

    const surplusA = impactA.assets_acquired.reduce((sum, a) => sum + (a.surplus_value || 0), 0);
    const surplusB = impactB.assets_acquired.reduce((sum, a) => sum + (a.surplus_value || 0), 0);

    score += (surplusA + surplusB);
    score = Math.min(99, Math.max(40, score));

    return { success: true, score };
}

// --- TEST RUNNER ---

function expect(actual, expected, message) {
    if (actual !== expected) {
        console.error(`❌ FAIL: ${message}`);
        console.error(`   Expected: ${expected}`);
        console.error(`   Actual:   ${actual}`);
        process.exit(1);
    } else {
        console.log(`✅ PASS: ${message}`);
    }
}

function runTests() {
    console.log("Running Trade Logic Verification (Inline)...");

    const mockPlayer = {
        id: 'p1', name: 'Test Player', team: 'KC', position: 'QB',
        cap_hit_millions: 20, dead_cap_millions: 10, risk_score: 0.5, surplus_value: 5
    };

    // Test 1: Basic Trade
    const impact1 = calculateTradeImpact('KC', [], [mockPlayer], false);
    expect(impact1.cap_cleared, 20, "KC clears 20M salary");
    expect(impact1.dead_money_acceleration, 10, "KC takes 10M dead money");
    expect(impact1.net_cap_change, 10, "KC net gain is 10M");

    // Test 2: Post-June 1
    const impact2 = calculateTradeImpact('KC', [], [mockPlayer], true);
    expect(impact2.dead_money_acceleration, 5, "Post-June 1 dead money is 5M");
    expect(impact2.net_cap_change, 15, "Post-June 1 net gain is 15M");

    // Test 3: Acquiring
    const impact3 = calculateTradeImpact('MIN', [mockPlayer], [], false);
    expect(impact3.net_cap_change, -16, "MIN takes -16M hit (80% of 20M)");

    console.log("All tests passed!");
}

runTests();
