import { db } from './db';
import { waitlist } from './db/schema';

async function verifyWaitlist() {
    console.log("🔍 Querying Vercel Postgres Waitlist Table...");
    const leads = await db.select().from(waitlist);

    if (leads.length === 0) {
        console.log("📭 The waitlist is currently empty.");
    } else {
        console.log(`✅ Found ${leads.length} active leads:`);
        console.log(JSON.stringify(leads, null, 2));
    }
    process.exit(0);
}

verifyWaitlist();
