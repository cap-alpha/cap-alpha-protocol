const duckdb = require('duckdb');
require('dotenv').config({ path: '.env.local' });

const db = new duckdb.Database(`md:nfl_dead_money?motherduck_token=${process.env.MOTHERDUCK_TOKEN}`, (err) => {
    if (err) {
        console.error("Connection Error:", err);
        process.exit(1);
    }
});

const players = ['Damar Hamlin', 'Zach Wilson', 'Taron Johnson'];
console.log("Starting UAT queries against MotherDuck...");

players.forEach(player => {
    db.all(`SELECT player_name, year, team, age, base_salary, sign_bonus, cap_hit, details FROM fact_player_efficiency WHERE player_name = '${player}' ORDER BY year DESC LIMIT 1`, (err, res) => {
        if (err) {
            // fallback if columns don't match exactly
            db.all(`SELECT * FROM fact_player_efficiency WHERE player_name = '${player}' ORDER BY year DESC LIMIT 1`, (e, r) => {
                if (e) console.error(`Error querying ${player}:`, e);
                else {
                    console.log(`\n--- ${player} ---`);
                    console.log(r);
                }
            });
        }
        else {
            console.log(`\n--- ${player} ---`);
            console.log(res);
        }
    });
});
