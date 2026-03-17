import path from 'path';

// Prevent this module from being bundled for the client
if (typeof window !== 'undefined') {
    throw new Error('This module can only be used on the server.');
}

let dbInstance: any = null;

export const getDb = async () => {
    if (!dbInstance) {
        const duckdb = require('duckdb');

        // Use MotherDuck in production if token is provided
        const useMotherDuck = process.env.MOTHERDUCK_TOKEN;
        const dbPath = useMotherDuck
            ? 'md:nfl_dead_money'
            : path.resolve(process.cwd(), '../data/duckdb/nfl_production.db');

        console.log(`[DB] Attempting to open DuckDB (${useMotherDuck ? 'MotherDuck' : 'Local'}) at: ${dbPath}`);

        return new Promise((resolve, reject) => {
            const db = new duckdb.Database(dbPath, (err: any) => {
                if (err) {
                    console.error(`[DB] Initialization Error: ${err.message}`);
                    reject(err);
                } else {
                    console.log(`[DB] Connection Established Successfully.`);
                    dbInstance = db;
                    resolve(dbInstance);
                }
            });
        });
    }
    return dbInstance;
};

export const query = async (sql: string, params: any[] = []): Promise<any[]> => {
    try {
        const db = await getDb();
        return new Promise((resolve, reject) => {
            db.all(sql, ...params, (err: any, res: any) => {
                if (err) {
                    console.error(`[DB] Query Error: ${err.message}`);
                    reject(err);
                } else {
                    resolve(res);
                }
            });
        });
    } catch (err) {
        console.error(`[DB] Query Execution Failed:`, err);
        return [];
    }
};
