import { Database } from 'duckdb-async';

// Global binding for connection pooling in Next.js Serverless environments
let cachedDb: Database | null = null;

export async function getMotherDuckDb() {
    if (cachedDb) return cachedDb;

    const token = process.env.MOTHERDUCK_TOKEN;
    if (!token) {
        throw new Error("MOTHERDUCK_TOKEN is missing. Cannot connect to cloud database.");
    }

    // Connect to the synchronized cloud database
    cachedDb = await Database.create(`md:nfl_dead_money?motherduck_token=${token}`);
    return cachedDb;
}
