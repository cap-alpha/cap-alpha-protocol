
import { getRosterData } from './app/actions';

async function verify() {
    try {
        console.log("Fetching Roster Data...");
        const data = await getRosterData();
        console.log(`Fetched ${data.length} players.`);

        const sample = data.find(p => p.player_name === "A.J. Brown");
        if (sample) {
            console.log(`\nVerifying A.J. Brown:`);
            console.log(`- Team: ${sample.team}`);
            console.log(`- History Entries: ${sample.history?.length}`);
            if (sample.history && sample.history.length > 0) {
                console.log(`- First History Entry:`, sample.history[0]);
                console.log("✅ History Hydration Successful!");
            } else {
                console.error("❌ History is missing or empty!");
            }
        } else {
            console.error("❌ Could not find A.J. Brown in roster.");
        }
    } catch (e) {
        console.error("Verification Failed:", e);
    }
}

verify();
