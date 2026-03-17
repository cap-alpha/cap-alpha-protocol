"use server";

import { db } from "@/db";
import { proofOfAlpha, proofOfAlphaTweets } from "@/db/schema";
import { eq, desc } from "drizzle-orm";

export type Tweet = {
    text: string;
    author: string;
    url: string;
    source: string;
    likes: string;
    reposts: string;
};

export type Receipt = {
    id: number;
    date: string;
    player_name: string;
    team: string;
    contract_size: string;
    prediction: string;
    media_sentiment: string;
    cap_alpha_insight: string;
    outcome: string;
    outcome_date?: string;
    roi: string;
    trend: string;
    image_url?: string;
    image_position?: string;
    tweets: Tweet[];
};

export async function getProofOfAlpha(): Promise<Receipt[]> {
    const records = await db.select().from(proofOfAlpha).orderBy(desc(proofOfAlpha.id)).limit(5);

    // Fetch all tweets to join in memory (efficient for small datasets)
    const tweets = await db.select().from(proofOfAlphaTweets);

    return records.map(record => ({
        id: record.id,
        date: record.date,
        player_name: record.playerName,
        team: record.team,
        contract_size: record.contractSize,
        prediction: record.prediction,
        media_sentiment: record.mediaSentiment,
        cap_alpha_insight: record.capAlphaInsight,
        outcome: record.outcome,
        outcome_date: record.outcomeDate || undefined,
        roi: record.roi,
        trend: record.trend,
        image_url: record.imageUrl || undefined,
        image_position: record.imagePosition || undefined,
        tweets: tweets
            .filter(t => t.proofOfAlphaId === record.id)
            .map(t => ({
                text: t.text,
                author: t.author,
                url: t.url,
                source: t.source,
                likes: t.likes || "0",
                reposts: t.reposts || "0"
            }))
    }));
}
