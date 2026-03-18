
import { neon } from '@neondatabase/serverless';
import { drizzle } from 'drizzle-orm/neon-http';
import * as schema from './schema';

// Provide a fallback dummy URL during Vercel static build generation to prevent neon() from crashing
const connectionString = process.env.POSTGRES_URL || "postgres://dummy:dummy@dummy.com/dummy";
const sql = neon(connectionString);
export const db = drizzle(sql, { schema });
