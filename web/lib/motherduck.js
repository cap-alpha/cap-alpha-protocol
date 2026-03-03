"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getMotherDuckDb = getMotherDuckDb;
const duckdb_async_1 = require("duckdb-async");
// Global binding for connection pooling in Next.js Serverless environments
let cachedDb = null;
async function getMotherDuckDb() {
    if (cachedDb)
        return cachedDb;
    const token = process.env.MOTHERDUCK_TOKEN;
    if (!token) {
        throw new Error("MOTHERDUCK_TOKEN is missing. Cannot connect to cloud database.");
    }
    // Connect to the synchronized cloud database
    cachedDb = await duckdb_async_1.Database.create(`md:nfl_dead_money?motherduck_token=${token}`);
    return cachedDb;
}
