'use server';

import { z } from 'zod';
import { getMotherDuckDb } from '@/lib/motherduck';
import { slugify } from '@/lib/utils';
import historicalData from '../data/historical_predictions.json';
import { unstable_cache } from 'next/cache';

// --- SCHEMA DEFINITIONS (The Bridge) ---

const HistorySchema = z.object({
  year: z.coerce.number(),
  team: z.string(),
  actual: z.coerce.number(),
  predicted: z.coerce.number(),
});

const PlayerEfficiencySchema = z.object({
  player_name: z.string(),
  team: z.string(),
  position: z.string(),
  year: z.coerce.number().default(new Date().getFullYear()),
  age: z.coerce.number().optional().default(25),
  games_played: z.coerce.number().optional().default(0),
  cap_hit_millions: z.coerce.number().default(0),
  dead_cap_millions: z.coerce.number().default(0),
  edce_risk: z.coerce.number().default(0), // Expected Dead Cap Error ($M)
  risk_score: z.coerce.number().default(0), // Normalized Risk Probability (0-1)
  fair_market_value: z.coerce.number().default(0), // Surplus Value
  dead_cap_pre_june1: z.coerce.number().optional().default(0),
  savings_pre_june1: z.coerce.number().optional().default(0),
  dead_cap_post_june1: z.coerce.number().optional().default(0),
  savings_post_june1: z.coerce.number().optional().default(0),
  base_salary_millions: z.coerce.number().optional().default(0),
  prorated_bonus_millions: z.coerce.number().optional().default(0),
  roster_bonus_millions: z.coerce.number().optional().default(0),
  guaranteed_salary_millions: z.coerce.number().optional().default(0),
  total_pass_yds: z.coerce.number().optional().default(0),
  total_rush_yds: z.coerce.number().optional().default(0),
  total_rec_yds: z.coerce.number().optional().default(0),
  total_tds: z.coerce.number().optional().default(0),
  total_sacks: z.coerce.number().optional().default(0),
  total_int: z.coerce.number().optional().default(0),
  report_status: z.string().optional(),
  report_primary_injury: z.string().optional(),
  history: z.array(HistorySchema).optional().default([]), // Historical Authentication
});

// Infer the type from the schema
export type PlayerEfficiency = z.infer<typeof PlayerEfficiencySchema>;
export type PlayerHistory = z.infer<typeof HistorySchema>;

// --- MOCK DATA GENERATOR REMOVED ---
// We no longer provide fallback mock data during production or staging.


// --- DATA HYDRATION ---

async function getHydratedData(): Promise<PlayerEfficiency[]> {
  try {
    // 1. Attempt Cloud Sync (MotherDuck)
    let rawData: any[] = [];
    try {
      const db = await getMotherDuckDb();
      const res = await db.all(`SELECT * FROM fact_player_efficiency WHERE year = (SELECT MAX(year) FROM fact_player_efficiency)`);
      rawData = res as any[];
      console.log(`[MotherDuck] Successfully fetched ${rawData.length} records from cloud.`);
    } catch (dbError) {
      console.warn("[MotherDuck] Database connection failed. Returning empty state.", dbError);
      return [];
    }

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
        return null;
      }

      const p = result.data;

      // Attach History
      const history = historyMap.get(p.player_name) || [];
      // Sort history by year ascending
      p.history = history.sort((a, b) => a.year - b.year);

      if (p.cap_hit_millions === 0 && p.risk_score === 0) {
        return null; // Return nothing instead of mocking
      }
      return p;
    }).filter((p): p is PlayerEfficiency => p !== null);

    return parsedData;

  } catch (e) {
    console.error("[Data] Error loading roster data:", e);
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

export type SearchIndexItem = {
    type: 'player' | 'team';
    label: string;
    sub: string;
    url: string;
};

async function fetchSearchIndex(): Promise<SearchIndexItem[]> {
    const data = await getHydratedData();
    const seen = new Set<string>();
    const index: SearchIndexItem[] = [];

    data.forEach(d => {
        // Player Index
        if (!seen.has(`player_${d.player_name}`)) {
            seen.add(`player_${d.player_name}`);
            index.push({
                type: 'player',
                label: d.player_name,
                sub: `${d.position} • ${d.team}`,
                url: `/player/${encodeURIComponent(slugify(d.player_name))}`
            });
        }
        
        // Team Index
        if (!seen.has(`team_${d.team}`)) {
            seen.add(`team_${d.team}`);
            index.push({
                type: 'team',
                label: d.team,
                sub: 'Franchise Hub',
                url: `/team/${encodeURIComponent(d.team)}`
            });
        }
    });

    return index.sort((a, b) => a.label.localeCompare(b.label));
}

// Wrap the actual fetch in unstable_cache for sub-second latency
export const getSearchIndex = unstable_cache(
    async () => fetchSearchIndex(),
    ['global-search-index'],
    { revalidate: 3600 } // Cache for 1 hour
);

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

// --- PLAYER TIMELINE ACTIONS ---

export type TimelineEvent = {
  year: number;
  week: number;
  date_of_event: string | null;
  event_type: 'CONTRACT' | 'ML_ALERT' | 'MEDIA_CONSENSUS' | 'PERFORMANCE_DROP';
  description: string;
};

export async function getPlayerTimeline(playerName: string): Promise<TimelineEvent[]> {
  try {
    const db = await getMotherDuckDb();
    
    // Construct the Unified Timeline CTE
    const query = `
      -- 1. Contract / Financial Base
      SELECT 
          year, 
          0 as week, 
          year || '-03-15' as date_of_event, 
          'CONTRACT' as event_type, 
          'Cap Hit: $' || ROUND(cap_hit_millions, 1) || 'M (Total: $' || ROUND(total_contract_value_millions, 1) || 'M)' as description 
      FROM silver_spotrac_contracts 
      WHERE player_name = ?
      
      UNION ALL
      
      -- 2. ML Prediction Triggers
      SELECT 
          year, 
          week, 
          NULL as date_of_event, 
          'ML_ALERT' as event_type, 
          '🚨 Alpha Protocol Alert: High Bust Probability Detected.' as description 
      FROM prediction_results 
      WHERE player_name = ? AND predicted_risk_score = 1
      
      UNION ALL
      
      -- 3. Media Consensus
      SELECT 
          year, 
          media_consensus_week as week, 
          media_date_approx as date_of_event, 
          'MEDIA_CONSENSUS' as event_type, 
          '🗞️ Media Consensus Shift: ' || rationale as description 
      FROM media_lag_metrics 
      WHERE player_name = ?
      
      ORDER BY year ASC, week ASC;
    `;
    
    const results = await db.all(query, playerName, playerName, playerName);
    return results as unknown as TimelineEvent[];
    
  } catch (error) {
    console.error(`[Data] Error loading timeline for ${playerName}:`, error);
    return []; // ZERO MOCKS. Return true empty state on error.
  }
}

// --- INTELLIGENCE FEED ACTIONS ---

export type IntelligenceEvent = {
  type: string;
  text: string;
  icon: 'TrendingDown' | 'TrendingUp' | 'AlertCircle' | 'FileText';
  color: string;
  url?: string; // Optional URL field for source citation
  provenanceHash?: string;
  timestamp?: string;
};

export async function getIntelligenceFeed(playerName: string): Promise<IntelligenceEvent[]> {
  try {
    const db = await getMotherDuckDb();
    const feed: IntelligenceEvent[] = [];

    // 1. Predictions
    const preds = await db.all(`
      SELECT year, week, predicted_risk_score, high_uncertainty_flag 
      FROM prediction_results 
      WHERE player_name = ? 
      ORDER BY year DESC, week DESC LIMIT 5
    `, playerName);
    
    if (preds && preds.length > 0) {
      const latest = preds[0] as any;
      if (latest.predicted_risk_score == 1) {
          feed.push({ type: "Warning", text: "Alpha Protocol model alerts high bust probability for current production trends.", icon: 'TrendingDown', color: 'text-rose-400' });
      } else {
          feed.push({ type: "Stable", text: "Alpha Protocol modeling shows stable production aligning with contract expectations.", icon: 'TrendingUp', color: 'text-emerald-400' });
      }
    }

    // 2. Media Consensus
    const media = await db.all(`
      SELECT media_date_approx as date_of_event, rationale
      FROM media_lag_metrics
      WHERE player_name = ?
      ORDER BY year DESC, media_consensus_week DESC LIMIT 3
    `, playerName);
    
    if (media && media.length > 0) {
      for (const m of media) {
        feed.push({
          type: "Media",
          text: `Consensus shift: ${(m as any).rationale}`,
          icon: 'AlertCircle',
          color: 'text-amber-400',
          url: (m as any).source_url || undefined,
        });
      }
    }

    // 3. Raw News / Tweets (Guarantees every player has a feed)
    try {
      const rawNews = await db.all(`
        SELECT headline as rationale, published_at as date_of_event, url as source_url, source_type, provenance_hash
        FROM raw_media_mentions
        WHERE player_name = ?
        ORDER BY published_at DESC LIMIT 5
      `, playerName);
      
      if (rawNews && rawNews.length > 0) {
        for (const n of rawNews) {
          const isTwitter = (n as any).source_type === 'twitter';
          feed.push({
            type: isTwitter ? "X_POST" : "WEB_ARCHIVE",
            text: (n as any).rationale,
            icon: 'FileText',
            color: 'text-zinc-300',
            url: (n as any).source_url || undefined,
            provenanceHash: (n as any).provenance_hash || undefined,
            timestamp: (n as any).date_of_event || new Date().toISOString(),
          });
        }
      }
    } catch(e) { /* Might not exist yet */ }

    // No, we let the UI handle empty state. No filler.
    return feed;
  } catch (error) {
    console.error("[Data] Error loading intelligence feed:", error);
    return []; // ZERO MOCKS.
  }
}

// --- WAR ROOM ACTIONS ---

export type WarRoomData = {
  redAlerts: {
    player_name: string;
    team: string;
    year: number;
    week: number;
    uncertainty_score: number;
  }[];
  roiMetrics: {
    averageLeadTime: number;
    totalValidations: number;
    topPerformers: {
      player_name: string;
      year: number;
      lead_time: number;
      rationale: string;
    }[];
  };
};

export async function getWarRoomData(): Promise<WarRoomData> {
  try {
    const db = await getMotherDuckDb();

    // 1. Red Alerts (Isolation Forest Anomalies)
    const redAlertsQuery = `
      SELECT DISTINCT
          player_name, 
          team,
          year,
          week,
          uncertainty_score
      FROM prediction_results 
      WHERE high_uncertainty_flag = 1
      ORDER BY uncertainty_score DESC, year DESC, week DESC
      LIMIT 10;
    `;
    const redAlertsRes = await db.all(redAlertsQuery);

    // 2. ROI Metrics (Media Lag)
    const roiQuery = `
      SELECT 
          AVG(alpha_lead_time_weeks) as avg_lead,
          COUNT(*) as total_validations
      FROM media_lag_metrics
      WHERE alpha_lead_time_weeks > 0;
    `;
    const roiRes = await db.all(roiQuery);
    
    let avgLead = 0;
    let totalValidations = 0;
    if (roiRes.length > 0) {
      // DuckDB might return BigInts or Decimals, convert safely
      avgLead = Number(roiRes[0].avg_lead || 0);
      totalValidations = Number(roiRes[0].total_validations || 0);
    }

    const topRoiQuery = `
      SELECT 
          player_name,
          year,
          alpha_lead_time_weeks as lead_time,
          rationale
      FROM media_lag_metrics
      WHERE alpha_lead_time_weeks > 0
      ORDER BY alpha_lead_time_weeks DESC
      LIMIT 5;
    `;
    const topRoiRes = await db.all(topRoiQuery);

    return {
      redAlerts: redAlertsRes as any[],
      roiMetrics: {
        averageLeadTime: avgLead,
        totalValidations: totalValidations,
        topPerformers: topRoiRes as any[]
      }
    };
  } catch (error) {
    console.error(`[Data] Error loading War Room Data:`, error);
    // Return empty state rather than mock data
    return {
      redAlerts: [],
      roiMetrics: {
        averageLeadTime: 0,
        totalValidations: 0,
        topPerformers: []
      }
    };
  }
}

// --- CRYPTOGRAPHIC LEDGER ACTIONS ---

export type AuditEntry = {
    entry_id: string;
    year: number;
    week: number;
    payload: string;
    payload_type: string;
    signature_hash: string;
    created_at: string;
    merkle_root: string;
};

export async function getPlayerAuditLedger(playerName: string): Promise<AuditEntry[]> {
    try {
        const db = await getMotherDuckDb();
        const query = `
            SELECT 
                e.entry_id, 
                e.year, 
                e.week, 
                e.payload, 
                e.payload_type,
                e.signature_hash, 
                CAST(e.created_at AS VARCHAR) as created_at,
                b.merkle_root
            FROM gold_layer.audit_ledger_entries e
            LEFT JOIN gold_layer.audit_ledger_blocks b 
                ON e.year = b.year AND e.week = b.week
            WHERE e.player_name = ?
            ORDER BY e.year DESC, e.week DESC;
        `;
        const res = await db.all(query, playerName);
        return res as unknown as AuditEntry[];
    } catch (error) {
        // Table might not exist yet
        console.error(`[Data] Error loading audit ledger for ${playerName}:`, error);
        return [];
    }
}
