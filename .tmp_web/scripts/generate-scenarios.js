const fs = require('fs');
const path = require('path');

// Paths
const ROSTER_PATH = path.join(__dirname, '../data/roster_dump.json');
const OUTPUT_PATH = path.join(__dirname, '../data/trade_scenarios.json');

// Constants
const CAP_SPACE_ESTIMATES = {
    // Mocking cap space based on typical 2026 projections slightly modified for 'needs'
    // Sellers (Low Cap / Rebuild)
    'NO': -60, 'CLE': -40, 'MIA': -20, 'SF': -10, 'DEN': 5, 'LV': 10, 'NYG': 15, 'CAR': 20, 'TEN': 30, 'TB': -15, 'SEA': -5,
    // Buyers (High Cap / Contenders)
    'WAS': 80, 'NE': 70, 'ARI': 60, 'DET': 45, 'HOU': 40, 'KC': 5, 'BUF': 2, 'PHI': 10, 'GB': 15, 'BAL': 5, 'CIN': 35, 'PIT': 25, 'CHI': 50, 'LAC': 45, 'IND': 40, 'MIN': 30, 'ATL': 15, 'DAL': -10, 'LAR': 10, 'JAX': 25, 'NYJ': 15
};

// Load Data
const roster = JSON.parse(fs.readFileSync(ROSTER_PATH, 'utf8'));

// Helper: Get Team Cap Space (Mock)
const getCapSpace = (team) => CAP_SPACE_ESTIMATES[team] || 20;

// Logic: Identify Trade Candidates
// Criteria: High Cap Hit (>15M), On a Team with < 10M Cap Space (Sellers)
const tradeBlock = roster.filter(p => {
    const space = getCapSpace(p.team);
    return space < 10 && p.cap_hit_millions > 15;
});

// Logic: Identify Buyers
const buyers = Object.entries(CAP_SPACE_ESTIMATES)
    .filter(([team, space]) => space > 30)
    .map(([team]) => team);

console.log(`Found ${tradeBlock.length} potential trade assets.`);
console.log(`Found ${buyers.length} potential buyers.`);

const scenarios = [];

// Generate Scenarios
tradeBlock.forEach(player => {
    // Find a buyer
    // Simple heuristic: Buyer needs this position? (Skip complex need logic, just random fit for now)
    // We'll pick a random buyer for valid candidates

    // Filter out same team
    const validBuyers = buyers.filter(b => b !== player.team);

    // Create 1-2 scenarios per asset
    for (let i = 0; i < Math.min(2, validBuyers.length); i++) {
        const buyer = validBuyers[Math.floor(Math.random() * validBuyers.length)];

        // Calculate Basic Utility
        // Buyer Utility: Surplus Value (capped)
        const buyerUtil = Math.min(10, Math.max(1, (player.surplus_value || 0) / 5));

        // Seller Utility: Cap Relief
        const sellerUtil = Math.min(10, player.cap_hit_millions / 4);

        const score = buyerUtil + sellerUtil;

        if (score > 5) { // Only good trades
            scenarios.push({
                buyer,
                seller: player.team,
                player: player.player_name,
                cap: player.cap_hit_millions,
                cost: "2026 Draft Capital", // Placeholder
                buyer_gain: Number(buyerUtil.toFixed(1)),
                seller_gain: Number(sellerUtil.toFixed(1)),
                score: Number(score.toFixed(1)),
                rationale: `**${buyer} (Needs ${player.position})**: Acquires star talent. **${player.team} (Clearing Space)**: Sheds $${player.cap_hit_millions.toFixed(1)}M.`
            });
        }
    }
});

// Sort by Score
scenarios.sort((a, b) => b.score - a.score);

// Deduplicate
const uniqueScenarios = [];
const seen = new Set();
for (const s of scenarios) {
    const key = `${s.player}-${s.buyer}`;
    if (!seen.has(key)) {
        seen.add(key);
        uniqueScenarios.push(s);
    }
}

// Slice Top 50
const topScenarios = uniqueScenarios.slice(0, 50);

// Write
fs.writeFileSync(OUTPUT_PATH, JSON.stringify(topScenarios, null, 2));
console.log(`Successfully generated ${topScenarios.length} scenarios to ${OUTPUT_PATH}`);
