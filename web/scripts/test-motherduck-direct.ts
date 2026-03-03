import { config } from 'dotenv';
config({ path: '.env.local' });
import { getMotherDuckDb } from '../lib/motherduck';

async function run() {
    try {
        console.log("Connecting to MotherDuck...");
        const db = await getMotherDuckDb();
        console.log("Connected.");

        console.log("Executing Query...");
        const res = await db.all(`SELECT player_name, team, cap_hit_millions FROM fact_player_efficiency LIMIT 5`);
        console.log("Results:");
        console.log(res);

        process.exit(0);
    } catch (e) {
        console.error("Test Failed:", e);
        process.exit(1);
    }
}
run();
