import { Client } from 'pg';
import dotenv from 'dotenv';
dotenv.config({ path: '.env.local' });

const client = new Client({
  connectionString: process.env.POSTGRES_URL || process.env.MOTHERDUCK_TOKEN,
  ssl: { rejectUnauthorized: false }
});

async function main() {
  if (process.env.MOTHERDUCK_TOKEN) {
     const duckdb = await import('duckdb-async');
     const db = await duckdb.Database.create(`md:nfl?motherduck_token=${process.env.MOTHERDUCK_TOKEN}`);
     const rows = await db.all("SELECT MAX(year) as max_year, COUNT(*) as cnt FROM fact_player_efficiency");
     console.log("MotherDuck Data:", rows);
     const names = await db.all("SELECT player_name, MAX(year) as max_year FROM fact_player_efficiency WHERE year >= 2024 GROUP BY player_name ORDER BY max_year DESC LIMIT 5");
     console.log("Recent players:", names);
  }
}
main().catch(console.error);
