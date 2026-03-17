
import { calculateTradeImpact, TradeAsset } from "../lib/trade-logic";
import { generateCapHistory } from "../lib/utils";

console.log("=== RUNNING TRADE LOGIC TESTS ===");

// Mocks
const playerA: TradeAsset = {
    id: "p1", name: "Player A", type: "player", team: "KC", position: "QB",
    cap_hit_millions: 10, dead_cap_millions: 5, risk_score: 0.2, surplus_value: 20
};

const playerB: TradeAsset = {
    id: "p2", name: "Player B", type: "player", team: "BUF", position: "WR",
    cap_hit_millions: 15, dead_cap_millions: 2, risk_score: 0.8, surplus_value: 15
};

// TEST 1: Simple Trade Impact for Team A (Receiving B, Sending A)
console.log("\n[TEST 1] Team A acquires Player B, sends Player A");
const impactA = calculateTradeImpact("KC", [playerB], [playerA]);

// Expected:
// Cap Cleared = 10 (Player A Salary)
// Dead Money = 5 (Player A Bonus)
// Acquired Salary = 15 * 0.8 = 12 (standard acquisition assumption)
// Net Change = 10 - 5 - 12 = -7
const expectedNet = 10 - 5 - (15 * 0.8);

if (Math.abs(impactA.net_cap_change - expectedNet) < 0.1) {
    console.log(`✅ PASS: Net Change is ${impactA.net_cap_change} (Expected ${expectedNet})`);
} else {
    console.error(`❌ FAIL: Net Change is ${impactA.net_cap_change} (Expected ${expectedNet})`);
}

// TEST 2: Restructure Logic (CFO Feature)
console.log("\n[TEST 2] Team A acquires Restructured Player B");
const restructuredB = { ...playerB, isRestructured: true };
const impactRestructured = calculateTradeImpact("KC", [restructuredB], [playerA]);

// Expected:
// Acquired Hit Original = 12
// Restructured Hit calculation:
// Base = 12
// Excess = 12 - 1.0 = 11.0
// Prorated Excess = 11.0 / 5 = 2.2
// New Hit = 1.0 + 2.2 = 3.2
const expectedHit = 1.0 + ((15 * 0.8) - 1.0) / 5;
const expectedNetRestructure = 10 - 5 - expectedHit;

if (Math.abs(impactRestructured.net_cap_change - expectedNetRestructure) < 0.1) {
    console.log(`✅ PASS: Restructured Net Change is ${impactRestructured.net_cap_change.toFixed(2)} (Expected ${expectedNetRestructure.toFixed(2)})`);
    console.log(`   Savings vs Standard: ${(impactRestructured.net_cap_change - impactA.net_cap_change).toFixed(2)}M`);
} else {
    console.error(`❌ FAIL: Restructured Net Change is ${impactRestructured.net_cap_change} (Expected ${expectedNetRestructure})`);
}

// TEST 3: Cap History Generation
console.log("\n[TEST 3] Cap History Generation");
const history = generateCapHistory(10, 0.8); // High Risk
if (history.length === 4 && history[3] > history[1]) {
    console.log(`✅ PASS: History Generated: ${history.map(n => n.toFixed(1)).join(", ")}`);
} else {
    console.error(`❌ FAIL: History Generated: ${history.map(n => n.toFixed(1)).join(", ")}`);
}

console.log("\n=== TESTS COMPLETE ===");
