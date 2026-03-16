import { Database } from 'duckdb-async';
import * as dotenv from 'dotenv';
import path from 'path';

dotenv.config({ path: path.join(process.cwd(), '.env.local') });

async function verifyDb() {
    try {
        console.log("Connecting to md:nfl_dead_money...");
        const db = await Database.create(`md:nfl_dead_money?motherduck_token=${process.env.MOTHERDUCK_TOKEN}`);
        
        console.log("Checking prediction_results...");
        const preds = await db.all("SELECT COUNT(*) as count FROM prediction_results");
        console.log("Prediction Results Count:", preds[0].count);

        console.log("Checking media_lag_metrics...");
        const media = await db.all("SELECT COUNT(*) as count FROM media_lag_metrics");
        console.log("Media Lag Metrics Count:", media[0].count);

        console.log("Checking history/efficiency data...");
        const eff = await db.all("SELECT COUNT(*) as count FROM fact_player_efficiency");
        console.log("Fact Player Efficiency Count:", eff[0].count);

    } catch (e) {
        console.error("CONNECTION OR QUERY FAILED:", e);
        process.exit(1);
    }
}

verifyDb();
