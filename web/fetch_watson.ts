import { BigQuery } from '@google-cloud/bigquery';
import * as dotenv from 'dotenv';
dotenv.config({ path: '.env.local' });

const bigquery = new BigQuery({
  projectId: process.env.GCP_PROJECT_ID,
  credentials: {
    client_email: process.env.GCP_CLIENT_EMAIL,
    private_key: process.env.GCP_PRIVATE_KEY?.replace(/\\n/g, '\n'),
  }
});

async function run() {
  const query = `SELECT * FROM \`my-project-1525668581184.nfl_dead_money.fact_player_efficiency\` WHERE player_name = 'Deshaun Watson' ORDER BY year DESC LIMIT 1`;
  const [rows] = await bigquery.query({ query });
  console.log(JSON.stringify(rows[0], null, 2));
}

run();
