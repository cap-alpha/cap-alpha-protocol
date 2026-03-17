"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const dotenv_1 = require("dotenv");
(0, dotenv_1.config)({ path: '.env.local' });
const motherduck_1 = require("../lib/motherduck");
async function run() {
    try {
        console.log("Connecting to MotherDuck...");
        const db = await (0, motherduck_1.getMotherDuckDb)();
        console.log("Connected.");
        console.log("Executing Query...");
        const res = await db.all(`SELECT player_name, team, cap_hit_millions FROM fact_player_efficiency LIMIT 5`);
        console.log("Results:");
        console.log(res);
        process.exit(0);
    }
    catch (e) {
        console.error("Test Failed:", e);
        process.exit(1);
    }
}
run();
