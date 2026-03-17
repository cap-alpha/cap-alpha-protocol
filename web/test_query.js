const { Database } = require('duckdb-async');
const dotenv = require('dotenv');
const path = require('path');

dotenv.config({ path: path.join(process.cwd(), '.env.local') });

async function checkPlayer() {
    try {
        const db = await Database.create(`md:nfl_dead_money?motherduck_token=${process.env.MOTHERDUCK_TOKEN}`);
        const result = await db.all("SELECT player_name, player_id, team_abbr FROM prediction_results LIMIT 5");
        console.log(JSON.stringify(result, null, 2));
    } catch (e) {
        console.error("FAILED:", e);
    }
}
checkPlayer();
