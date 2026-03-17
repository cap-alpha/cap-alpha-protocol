import { TradeAsset, VegasImpact } from "./trade-logic";

export type { TradeAsset, VegasImpact };

export interface TradeProposal {
    team_a: string;
    team_b: string;
    team_a_assets: TradeAsset[];
    team_b_assets: TradeAsset[];
    config?: Record<string, any>;
}

export interface TradeAnalysis {
    financial_impact: string;
    roster_impact: string;
}

export interface TradeResult {
    grade: string;
    reason: string;
    status: "accepted" | "rejected" | "review";
    analysis?: TradeAnalysis;
    vegas_impact?: Record<string, VegasImpact>;
}

const API_BASE = '/api/python';

export const ApiClient = {
    /**
     * Sends a trade proposal to the Adversarial Engine for evaluation.
     */
    evaluateTrade: async (proposal: TradeProposal): Promise<TradeResult> => {
        try {
            const response = await fetch(`${API_BASE}/trade/evaluate`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(proposal),
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`API Error ${response.status}: ${errorText}`);
            }

            return await response.json();
        } catch (error) {
            console.error("Adversarial Engine Error:", error);
            // Fallback for dev/offline mode
            return {
                grade: "N/A",
                reason: "Adversarial Engine unreachable. (Is Python server running?)",
                status: "review"
            };
        }
    },

    getCounterOffer: async (proposal: TradeProposal): Promise<TradeAsset | null> => {
        try {
            const response = await fetch(`${API_BASE}/trade/counter`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(proposal),
            });
            if (!response.ok) return null;
            return await response.json();
        } catch (e) {
            console.error("Counter Offer Error:", e);
            return null;
        }
    },

    getVegasImpact: async (proposal: TradeProposal): Promise<Record<string, VegasImpact> | null> => {
        try {
            const response = await fetch(`${API_BASE}/analyze/vegas`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(proposal),
            });
            if (!response.ok) return null;
            return await response.json();
        } catch (e) {
            console.error("Vegas Analysis Error:", e);
            return null;
        }
    }
};
