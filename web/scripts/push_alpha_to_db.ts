import { config } from 'dotenv';
config({ path: '.env.local' });
import { db } from '../db';
import { proofOfAlpha, proofOfAlphaTweets } from '../db/schema';
import fs from 'fs';
import path from 'path';

// Define the shape of our Python output payload
interface AlphaPayload {
    id: number;
    date: string;
    player_name: string;
    team: string;
    contract_size: string;
    prediction: string;
    outcome: string;
    outcome_date: string;
    media_sentiment: string;
    cap_alpha_insight: string;
    roi: string;
    trend: string;
    image_url: string;
    tweets: Array<{
        text: string;
        author: string;
        url: string;
        source: string;
        likes: string;
        reposts: string;
    }>;
}

async function main() {
    console.log('🔄 Starting Proof of Alpha DB Hydration...');

    try {
        const payloadPath = path.join(__dirname, 'alpha_payload.json');
        if (!fs.existsSync(payloadPath)) {
            console.error(`❌ alpha_payload.json not found at ${payloadPath}`);
            process.exit(1);
        }

        const payloadRaw = fs.readFileSync(payloadPath, 'utf8');
        const records: AlphaPayload[] = JSON.parse(payloadRaw);

        console.log(`📡 Found ${records.length} records to process. (Appending for Time-Travel Metrics)`);

        for (const record of records) {
            console.log(`[${record.player_name}] Upserting metadata to proofOfAlpha table...`);

            // Upsert the core record - using player_name + date as composite key conceptually, 
            // but relying on Drizzle insert/conflict if we had unique constraints.
            // For now, we'll clear the table and insert fresh to avoid ID conflicts 
            // during local testing, or just insert if this was a true append-only log.

            // Because we are just migrating the static list to DB for now, we'll insert directly.
            const [insertedAlpha] = await db.insert(proofOfAlpha).values({
                date: record.date,
                playerName: record.player_name,
                team: record.team,
                contractSize: record.contract_size,
                prediction: record.prediction,
                mediaSentiment: record.media_sentiment,
                capAlphaInsight: record.cap_alpha_insight,
                outcome: record.outcome,
                outcomeDate: record.outcome_date,
                roi: record.roi,
                trend: record.trend,
                imageUrl: record.image_url,
            }).returning({ id: proofOfAlpha.id });

            console.log(`   -> Core record created [ID: ${insertedAlpha.id}]`);

            // Insert associated tweets
            if (record.tweets && record.tweets.length > 0) {
                console.log(`   -> Found ${record.tweets.length} associated tweets. Inserting...`);

                for (const tweet of record.tweets) {
                    await db.insert(proofOfAlphaTweets).values({
                        proofOfAlphaId: insertedAlpha.id,
                        text: tweet.text,
                        author: tweet.author,
                        url: tweet.url,
                        source: tweet.source,
                        likes: tweet.likes,
                        reposts: tweet.reposts,
                    });
                }
            }
        }

        console.log('\n✅ Successfully hydrated Vercel Postgres with Proof of Alpha data.');
        process.exit(0);

    } catch (error) {
        console.error('❌ Failed to hydrate database:', error);
        process.exit(1);
    }
}

main();
