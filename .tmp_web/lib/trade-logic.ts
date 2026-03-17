
export interface TradeAsset {
    id: string;
    name: string;
    type: "player" | "draft_pick"; // Required for API compatibility
    team: string; // Current team
    position: string;
    cap_hit_millions: number;
    isRestructured?: boolean; // CFO Feature
    restructure_savings?: number; // Calculated savings
    dead_cap_millions: number; // If traded, this stays with original team (unless post-june 1)
    risk_score: number; // 0-1
    surplus_value: number; // Value provided - Cost
}

export interface TradeImpact {
    team: string;
    initial_cap_space: number; // Mocked for now
    cap_cleared: number; // Salary shed
    dead_money_acceleration: number; // Dead money taken on
    net_cap_change: number; // cleared - dead
    assets_acquired: TradeAsset[];
    assets_lost: TradeAsset[];
}

export interface VegasImpact {
    delta_wins: number;
    new_win_total: number;
    vegas_variance: number;
    ceiling: number;
    floor: number;
    super_bowl_odds_delta: string;
}

export interface SimulationResult {
    success: boolean;
    grade: 'A+' | 'A' | 'A-' | 'B+' | 'B' | 'B-' | 'C+' | 'C' | 'C-' | 'D' | 'F';
    summary: string;
    impacts: Record<string, TradeImpact>; // teamId -> Impact
    score: number; // 0-100
    vegas_impact?: Record<string, VegasImpact>;
}

/**
 * Calculates the financial impact of a trade for a specific team.
 * @param team The team identifier (e.g., 'KC')
 * @param assetsIn Assets arriving to this team
 * @param assetsOut Assets leaving this team
 * @param isPostJune1 If true, spread dead money over 2 years (simplified for now)
 */
export function calculateTradeImpact(
    team: string,
    assetsIn: TradeAsset[],
    assetsOut: TradeAsset[],
    isPostJune1: boolean = false
): TradeImpact {

    // 1. Calculate Salary Shed (Cap Cleared)
    // When a player leaves, you save their Salary (Cap Hit - Dead Cap component usually, but simplified here as Cap Hit for now)
    // NOTE: In reality, Cap Hit = Salary + Bonus Proration. 
    // If traded, Team saves Salary. Team eats Remaining Bonus Proration (Dead Cap).
    // We will assume `cap_hit_millions` is the total saveable amount for simplicity in this version, 
    // and `dead_cap_millions` is the penalty.

    const cap_cleared = assetsOut.reduce((sum, a) => sum + (a.cap_hit_millions || 0), 0);

    // 2. Calculate Dead Money Acceleration
    // The dead money stays with the trading team.
    let dead_money_acceleration = assetsOut.reduce((sum, a) => sum + (a.dead_cap_millions || 0), 0);

    // Post-June 1 logic: In reality, this splits the dead cap. 
    // For this simulation, we'll say it reduces current year hit by 50%.
    if (isPostJune1) {
        dead_money_acceleration = dead_money_acceleration * 0.5;
    }

    // 3. Calculate Acquired Salary
    // When acquiring a player, you generally take on their Base Salary. 
    // We'll assume the `cap_hit_millions` travels with them for simplicity, unless we had a specific "Salary" field.
    // Let's assume the acquiring team takes 80% of the Cap Hit (Base Salary) and 0% of the Dead Cap (Bonus).
    let acquired_salary = assetsIn.reduce((sum, a) => {
        let hit = a.cap_hit_millions * 0.8;

        // CFO Feature: Restructure Logic
        if (a.isRestructured) {
            // Simplified: Convert to min salary ($1M) + prorate rest over 5 years
            // New Hit = $1M + ((Original * 0.8) - $1M) / 5
            const base = hit;
            if (base > 1.2) { // Only worth it if salary > min
                const converted = base - 1.0;
                const proration = converted / 5;
                hit = 1.0 + proration;
            }
        }
        return sum + hit;
    }, 0);

    // Net Change = (Cap Cleared) - (Dead Money Taken) - (New Salaries)
    // Positive means MORE cap space. Negative means LESS.
    const net_cap_change = cap_cleared - dead_money_acceleration - acquired_salary;

    return {
        team,
        initial_cap_space: 0, // TODO: Fetch real cap space
        cap_cleared,
        dead_money_acceleration,
        net_cap_change,
        assets_acquired: assetsIn,
        assets_lost: assetsOut
    };
}


export function generateTradeGrade(impactA: TradeImpact, impactB: TradeImpact): SimulationResult {
    const totalNetChange = impactA.net_cap_change + impactB.net_cap_change;
    const totalAssetsMoved = impactA.assets_acquired.length + impactB.assets_acquired.length;

    // Heuristic Score (0-100)
    // 1. Transaction Volume (Did stuff happen?)
    let score = 70; // Start at C-

    // 2. Cap Efficiency Bonus
    if (impactA.net_cap_change > 0) score += 5;
    if (impactB.net_cap_change > 0) score += 5;

    // 3. "Fleecing" Detection (Did one team get way more value?)
    // Using Surplus Value if available
    const surplusA = impactA.assets_acquired.reduce((sum, a) => sum + (a.surplus_value || 0), 0);
    const surplusB = impactB.assets_acquired.reduce((sum, a) => sum + (a.surplus_value || 0), 0);

    score += (surplusA + surplusB);

    // Clamp Score
    score = Math.min(99, Math.max(40, score));

    // Determine Grade
    let grade: SimulationResult['grade'] = 'C';
    if (score >= 97) grade = 'A+';
    else if (score >= 93) grade = 'A';
    else if (score >= 90) grade = 'A-';
    else if (score >= 87) grade = 'B+';
    else if (score >= 83) grade = 'B';
    else if (score >= 80) grade = 'B-';
    else if (score >= 77) grade = 'C+';
    else if (score >= 70) grade = 'C';
    else if (score >= 60) grade = 'D';
    else grade = 'F';

    // Generate Narrative
    const winner = surplusA > surplusB ? impactA.team : impactB.team;
    const narrative = `The ${impactA.team} clear ${Math.round(impactA.net_cap_change)}M in space. The ${impactB.team} acquire talent with a net impact of ${Math.round(impactB.net_cap_change)}M. ${winner} wins the value exchange.`;

    return {
        success: true,
        grade,
        summary: narrative,
        impacts: {
            [impactA.team]: impactA,
            [impactB.team]: impactB
        },
        score
    };
}

export function generateCounterOffer(
    losingImpact: TradeImpact,
    winningTeamAssets: TradeAsset[]
): TradeAsset | null {
    // 1. Calculate the Gap
    // How much value is the losing team missing?
    // We compare the surplus value they ARE getting vs what they GAVE up.
    // Actually, we should compare the Net Value of the trade for both sides.
    // If Team A Net = -50 and Team B Net = +50, Team A needs ~50 value.

    const lostValue = losingImpact.assets_lost.reduce((sum, a) => sum + (a.surplus_value || 0), 0);
    const gainedValue = losingImpact.assets_acquired.reduce((sum, a) => sum + (a.surplus_value || 0), 0);

    const deficit = lostValue - gainedValue;

    // If deficit is small, no counter needed (or they are winning)
    if (deficit < 5) return null; // Tolerance

    console.log(`[CounterOffer] ${losingImpact.team} is creating a deficit of ${deficit}. Searching for asset...`);

    // 2. Find an asset from the winner that matches this deficit
    // We want an asset where asset.surplus_value is close to deficit.
    // Let's filter for assets that are tradeable (e.g. not huge dead cap hits? ignored for now)

    // Sort assets by value proximity
    const candidates = winningTeamAssets.filter(a => a.surplus_value > 0).sort((a, b) => {
        const diffA = Math.abs(a.surplus_value - deficit);
        const diffB = Math.abs(b.surplus_value - deficit);
        return diffA - diffB;
    });

    if (candidates.length > 0) {
        // Return the best match
        return candidates[0];
    }

    return null;
}
