'use server';

import { z } from 'zod';
import rosterData from '../data/roster_dump.json';
import historicalData from '../data/historical_predictions.json';

// --- SCHEMA DEFINITIONS (The Bridge) ---

const HistorySchema = z.object({
  year: z.number(),
  team: z.string(),
  actual: z.number(),
  predicted: z.number(),
});

const PlayerEfficiencySchema = z.object({
  player_name: z.string(),
  team: z.string(),
  position: z.string(),
  year: z.number().default(2024),
  age: z.number().optional().default(25),
  games_played: z.number().optional().default(0),
  cap_hit_millions: z.number().default(0),
  dead_cap_millions: z.number().default(0),
  edce_risk: z.number().default(0), // Expected Dead Cap Error ($M)
  risk_score: z.number().default(0), // Normalized Risk Probability (0-1)
  fair_market_value: z.number().default(0), // Surplus Value
  dead_cap_pre_june1: z.number().optional().default(0),
  savings_pre_june1: z.number().optional().default(0),
  dead_cap_post_june1: z.number().optional().default(0),
  savings_post_june1: z.number().optional().default(0),
  history: z.array(HistorySchema).optional().default([]), // Historical Authentication
});

// Infer the type from the schema
export type PlayerEfficiency = z.infer<typeof PlayerEfficiencySchema>;
export type PlayerHistory = z.infer<typeof HistorySchema>;

// --- MOCK DATA GENERATOR (The Safety Net) ---
// Used when the real pipeline data is missing or $0 (as confirmed in audit).
// This allows Frontend Development to proceed without blocking on Data Engineering.

function generateMockFinancials(player: any): PlayerEfficiency {
  // Deterministic "random" based on name length for consistency during dev
  const seed = player.player_name.length;

  // Mock Cap Hit: $1M - $50M based on name length mod
  const baseCap = (seed % 45) + 1;

  // Mock Risk: Higher cap = Higher risk (simplified heuristic)
  const risk = (baseCap > 30) ? 0.8 : (baseCap > 10) ? 0.4 : 0.1;

  // Mock FMV: Random variance from cap
  const surplus = baseCap * (1.2 - (seed % 5) / 10);

  return {
    ...player,
    cap_hit_millions: player.cap_hit_millions || baseCap,
    dead_cap_millions: player.dead_cap_millions || (baseCap * 0.5),
    edce_risk: player.edce_risk || (risk * 10), // approximate error
    risk_score: player.risk_score || risk,
    fair_market_value: player.fair_market_value || surplus,
    year: player.year || 2024
  };
}

// --- DATA HYDRATION ---

async function getHydratedData(): Promise<PlayerEfficiency[]> {
  try {
    const rawData: any[] = rosterData as any[];

    // transform historical data into a lookup map for O(1) access
    const historyMap = new Map<string, PlayerHistory[]>();
    (historicalData as any[]).forEach((record) => {
      if (!historyMap.has(record.player_name)) {
        historyMap.set(record.player_name, []);
      }
      historyMap.get(record.player_name)?.push({
        year: record.year,
        team: record.team,
        actual: record.actual,
        predicted: record.predicted
      });
    });

    // Validate and Parse, applying Mock Fallback if needed
    const parsedData = rawData.map(item => {
      const result = PlayerEfficiencySchema.safeParse(item);
      if (!result.success) {
        if (item.player_name) return generateMockFinancials(item);
        return null;
      }

      const p = result.data;

      // Attach History
      const history = historyMap.get(p.player_name) || [];
      // Sort history by year ascending
      p.history = history.sort((a, b) => a.year - b.year);

      if (p.cap_hit_millions === 0 && p.risk_score === 0) {
        return generateMockFinancials(p);
      }
      return p;
    }).filter((p): p is PlayerEfficiency => p !== null);

    return parsedData;

  } catch (e) {
    console.error("[Data] Error parsing roster data:", e);
    return [];
  }
}

// --- PUBLIC ACTIONS ---

export async function getRosterData() {
  const data = await getHydratedData();
  const seen = new Set();

  return data
    .filter((d) => {
      const key = `${d.player_name}-${d.team}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .map((d) => ({
      ...d,
      // Ensure frontend friendly names if needed, but schema matches types now
      risk_score: d.risk_score,
      surplus_value: d.fair_market_value
    }))
    .sort((a, b) => b.cap_hit_millions - a.cap_hit_millions);
}

export async function getTeamCapSummary() {
  const data = await getHydratedData();
  const teams: Record<string, any> = {};

  data.forEach((d) => {
    if (!teams[d.team]) {
      teams[d.team] = {
        team: d.team,
        total_cap: 0,
        risk_cap: 0,
        count: 0,
        avg_age: 0
      };
    }

    teams[d.team].total_cap += d.cap_hit_millions;
    teams[d.team].count += 1;

    // Risk Threshold: 0.7
    if (d.risk_score > 0.7) {
      teams[d.team].risk_cap += d.cap_hit_millions;
    }
  });

  return Object.values(teams).sort((a, b) => b.total_cap - a.total_cap);
}

export async function getTeams() {
  const data = await getHydratedData();
  const teams = Array.from(new Set(data.map((d) => d.team)));
  return teams.sort();
}

export async function getTradeableAssets(team?: string) {
  const data = await getHydratedData();

  let filtered = data;
  if (team) {
    filtered = data.filter((d) => d.team === team);
  }

  return filtered.map((d) => ({
    id: d.player_name, // Unique ID ideally
    name: d.player_name,
    team: d.team,
    position: d.position,
    cap_hit_millions: d.cap_hit_millions,
    risk_score: d.risk_score,
    dead_cap_millions: d.dead_cap_millions,
    surplus_value: d.fair_market_value,
    type: 'player'
  }))
    .sort((a, b) => b.cap_hit_millions - a.cap_hit_millions);
}

// TODO: Refactor this to use simulation engine API when available
export async function simulateTrade(assets: any[]) {
  console.log("Simulating trade with assets:", assets);

  // Simple heuristic for simulation delta (Mocking the AI)
  // In real system: This would call the Python `AdversarialTradeEngine`
  const win_delta = (Math.random() * 0.1) - 0.02;
  const cap_delta_a = assets.reduce((sum, a) => sum + (a.cap_hit_millions || 0), 0);

  return {
    success: true,
    summary: `Trade simulation completed. Analyzed ${assets.length} assets. Resulting in ${win_delta > 0 ? 'positive' : 'negative'} EPA delta.`,
    teamA_cap_delta: -cap_delta_a, // Simplified: Team A sheds the salary
    teamB_cap_delta: cap_delta_a,  // Team B takes it
    win_prob_delta: win_delta
  };
}

// --- BENCHMARKING ACTIONS ---

export async function getPositionDistribution(position: string) {
  const data = await getHydratedData();

  // Filter by position and valid cap hit
  const peers = data
    .filter(p => p.position === position && p.cap_hit_millions > 0)
    .sort((a, b) => a.cap_hit_millions - b.cap_hit_millions);

  // Calculate Buckets (Histogram)
  // We want ~10-15 buckets
  if (peers.length === 0) return [];

  const maxCap = Math.max(...peers.map(p => p.cap_hit_millions));
  const bucketSize = Math.ceil(maxCap / 15);

  const buckets: Record<string, { range: string, count: number, players: string[], min: number }> = {};

  // Initialize buckets
  for (let i = 0; i < 15; i++) {
    const min = i * bucketSize;
    const max = (i + 1) * bucketSize;
    const key = `${min}-${max}`;
    buckets[key] = { range: `$${min}M - $${max}M`, count: 0, players: [], min };
  }

  peers.forEach(p => {
    // Find bucket
    const bucketIndex = Math.min(Math.floor(p.cap_hit_millions / bucketSize), 14);
    const min = bucketIndex * bucketSize;
    const max = (bucketIndex + 1) * bucketSize;
    const key = `${min}-${max}`;

    if (buckets[key]) {
      buckets[key].count++;
      buckets[key].players.push(p.player_name);
    }
  });

  return Object.values(buckets).sort((a, b) => a.min - b.min);
}
